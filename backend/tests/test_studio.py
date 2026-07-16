"""Voice Studio: generation endpoints, history, playback (synthesis faked)."""

import pytest
from fastapi.testclient import TestClient

from corvus.api.app import create_app
from corvus.memory.repository import Repository
from corvus.voice import studio
from tests.conftest import FakeProvider

FAKE_MP3 = b"ID3fake-mp3-bytes"


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    async def fake_synthesize(engine, text, voice, rate=0, pitch=0, volume=0):
        if engine == "piper" and voice == "not-installed":
            raise FileNotFoundError("Piper voice 'not-installed' is not installed")
        return FAKE_MP3, "mp3"

    async def fake_edge_voices():
        return [{"id": "en-US-AriaNeural", "name": "Aria", "locale": "en-US", "gender": "Female"}]

    monkeypatch.setattr("corvus.api.studio.studio.synthesize", fake_synthesize)
    monkeypatch.setattr("corvus.voice.studio.edge_voices", fake_edge_voices)
    repo = Repository(tmp_path / "studio.db")
    app = create_app(repo=repo, provider=FakeProvider(), voice=False, browser=False)
    return TestClient(app)


def _generate(client, **overrides) -> dict:
    body = {"text": "Hello world. This is a voiceover.", "engine": "edge",
            "voice": "en-US-AriaNeural", "rate": 10, "pitch": -5, "volume": 0}
    body.update(overrides)
    res = client.post("/studio/generate", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_generate_persists_row_and_file(client):
    row = _generate(client)
    assert row["engine"] == "edge"
    assert row["voice"] == "en-US-AriaNeural"
    assert row["rate"] == 10
    assert (studio.voiceovers_dir() / row["filename"]).read_bytes() == FAKE_MP3

    listed = client.get("/studio/generations").json()
    assert [v["id"] for v in listed] == [row["id"]]


def test_audio_roundtrip_and_delete(client):
    row = _generate(client)
    audio = client.get(f"/studio/generations/{row['id']}/audio")
    assert audio.status_code == 200
    assert audio.content == FAKE_MP3

    assert client.delete(f"/studio/generations/{row['id']}").json() == {"ok": True}
    assert not (studio.voiceovers_dir() / row["filename"]).exists()
    assert client.get(f"/studio/generations/{row['id']}/audio").status_code == 404
    assert client.delete(f"/studio/generations/{row['id']}").status_code == 404


def test_generate_validation(client):
    bad = {"text": "  ", "engine": "edge", "voice": "v"}
    assert client.post("/studio/generate", json=bad).status_code == 400

    too_long = {"text": "x" * (studio.MAX_TEXT_CHARS + 1), "engine": "edge", "voice": "v"}
    assert client.post("/studio/generate", json=too_long).status_code == 400

    wrong = {"text": "hi there friend", "engine": "premium", "voice": "v"}
    assert client.post("/studio/generate", json=wrong).status_code == 400


def test_piper_voice_not_installed_is_409(client):
    body = {"text": "hello there", "engine": "piper", "voice": "not-installed"}
    res = client.post("/studio/generate", json=body)
    assert res.status_code == 409
    assert "not installed" in res.json()["detail"]


def test_piper_catalog_lists_curated_voices(client):
    res = client.get("/studio/voices")
    assert res.status_code == 200
    piper = res.json()["piper"]
    ids = {v["id"] for v in piper}
    assert "en_US-amy-medium" in ids
    assert all(v["installed"] is False for v in piper)
    assert {"id", "name", "language", "gender", "size_mb", "installed"} <= set(piper[0])


def test_voiceover_repo_roundtrip(repo):
    row = repo.add_voiceover("hi", "piper", "en_US-amy-medium", 0, 0, 0, "a.wav")
    assert repo.get_voiceover(row["id"])["voice"] == "en_US-amy-medium"
    assert repo.list_voiceovers()[0]["id"] == row["id"]
    assert repo.delete_voiceover(row["id"]) is True
    assert repo.get_voiceover(row["id"]) is None
