import json

from fastapi.testclient import TestClient

from corvus.api.app import create_app
from corvus.memory.repository import Repository
from tests.conftest import FakeProvider


def make_client(tmp_path, provider: FakeProvider) -> TestClient:
    repo = Repository(tmp_path / "api.db")
    app = create_app(repo=repo, provider=provider, voice=False)
    return TestClient(app)


def test_health(tmp_path, fake_provider):
    client = make_client(tmp_path, fake_provider)
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["app"] == "Corvus"


def test_ws_chat_full_turn_persists(tmp_path, fake_provider):
    client = make_client(tmp_path, fake_provider)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "start", "conversation_id": None, "content": "Hi Corvus"})
        first = ws.receive_json()
        assert first["type"] == "start"
        conversation_id = first["conversation_id"]

        text, done = "", None
        while True:
            frame = ws.receive_json()
            if frame["type"] == "delta":
                text += frame["content"]
            else:
                done = frame
                break
        assert done["type"] == "done"
        assert text == "Hello from Corvus"

    messages = client.get(f"/conversations/{conversation_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Hello from Corvus"

    conversations = client.get("/conversations").json()
    assert conversations[0]["title"].startswith("Hi Corvus")


def test_ws_chat_bad_start_frame(tmp_path, fake_provider):
    client = make_client(tmp_path, fake_provider)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "start", "content": "   "})
        assert ws.receive_json()["type"] == "error"


def test_memory_extraction_stores_and_lists(tmp_path):
    provider = FakeProvider(
        extraction=json.dumps(
            {"store": True, "category": "preference", "content": "Prefers dark mode"}
        )
    )
    client = make_client(tmp_path, provider)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "start", "conversation_id": None, "content": "I always use dark mode"})
        while ws.receive_json()["type"] not in ("done", "error"):
            pass

    memories = client.get("/memories").json()
    assert len(memories) == 1
    assert memories[0]["category"] == "preference"

    # delete + export
    assert client.delete(f"/memories/{memories[0]['id']}").json() == {"ok": True}
    exported = client.get("/memories/export")
    assert exported.headers["content-disposition"].endswith('"corvus-memories.json"')
    assert json.loads(exported.text)["memories"] == []


def test_settings_and_models(tmp_path, fake_provider):
    client = make_client(tmp_path, fake_provider)
    settings = client.get("/settings").json()
    assert settings["provider"] == "ollama"

    updated = client.patch("/settings", json={"model": "fake-model:latest"}).json()
    assert updated["model"] == "fake-model:latest"

    assert client.patch("/settings", json={"provider": "openai"}).status_code == 400
    assert client.get("/models").json() == {"models": ["fake-model:latest"]}


def test_logs_endpoint_returns_structured_entries(tmp_path, fake_provider):
    client = make_client(tmp_path, fake_provider)
    entries = client.get("/logs?limit=50").json()
    assert isinstance(entries, list)
    assert any(e.get("event") == "corvus_start" for e in entries)
