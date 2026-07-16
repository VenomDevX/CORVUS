"""Launch-token auth: enforced only when CORVUS_TOKEN is set (SECURITY.md item 1)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from corvus.api.app import create_app
from corvus.memory.repository import Repository
from tests.conftest import FakeProvider

TOKEN = "test-launch-token-0123456789abcdef"


def make_client(tmp_path, monkeypatch, token: str | None) -> TestClient:
    if token is None:
        monkeypatch.delenv("CORVUS_TOKEN", raising=False)
    else:
        monkeypatch.setenv("CORVUS_TOKEN", token)
    repo = Repository(tmp_path / "auth.db")
    app = create_app(repo=repo, provider=FakeProvider(), voice=False, browser=False)
    return TestClient(app)


def test_no_token_env_means_no_enforcement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, token=None)
    assert client.get("/health").status_code == 200
    assert client.get("/conversations").status_code == 200


def test_health_stays_open_without_token(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, token=TOKEN)
    assert client.get("/health").status_code == 200


def test_http_requires_token(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, token=TOKEN)
    assert client.get("/conversations").status_code == 401
    assert (
        client.get("/conversations", headers={"X-Corvus-Token": "wrong"}).status_code
        == 401
    )
    assert (
        client.get("/conversations", headers={"X-Corvus-Token": TOKEN}).status_code
        == 200
    )


def test_http_accepts_token_query_param(tmp_path, monkeypatch):
    # memories/export is used as a plain href, so the query form must work.
    client = make_client(tmp_path, monkeypatch, token=TOKEN)
    assert client.get(f"/memories/export?token={TOKEN}").status_code == 200


def test_websocket_rejected_without_token(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, token=TOKEN)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat"):
            pass


def test_websocket_accepts_token_query_param(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, token=TOKEN)
    with client.websocket_connect(f"/ws/chat?token={TOKEN}") as ws:
        ws.send_json({"type": "start", "conversation_id": None, "content": "Hi"})
        assert ws.receive_json()["type"] == "start"
