"""Device specs endpoint + model fit heuristic + onboarding flag."""

import pytest
from fastapi.testclient import TestClient

from corvus import system_info
from corvus.api.app import create_app
from corvus.memory.repository import Repository
from tests.conftest import FakeProvider


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    async def fake_ollama():
        return {"running": True, "models": [{"name": "llama3.2:3b", "size_gb": 2.0}]}

    monkeypatch.setattr(system_info, "_ram_gb", lambda: 16.0)
    monkeypatch.setattr(system_info, "_ollama", fake_ollama)
    repo = Repository(tmp_path / "system.db")
    app = create_app(repo=repo, provider=FakeProvider(), voice=False, browser=False)
    return TestClient(app, headers={"X-Corvus-Token": "test-token"})


def test_specs_with_gpu(client, monkeypatch):
    monkeypatch.setattr(system_info, "_gpu", lambda: {"name": "RTX 4050", "vram_gb": 6.0})
    body = client.get("/system/specs").json()
    assert body["ram_gb"] == 16.0
    assert body["gpu"]["vram_gb"] == 6.0
    assert body["ollama"]["running"] is True

    fits = {c["id"]: c["fit"] for c in body["catalog"]}
    # 6GB VRAM: 3B-class fits the GPU; 7B (4.7+1.5=6.2) does not, but 16GB RAM runs it on CPU.
    assert fits["llama3.2:3b"] == "recommended"
    assert fits["qwen2.5-coder:7b"] == "cpu_ok"
    assert fits["qwen2.5:14b"] == "too_big"
    # Largest GPU-fitting model wins the suggestion.
    assert body["suggested"] == "phi3.5"


def test_specs_without_gpu(client, monkeypatch):
    monkeypatch.setattr(system_info, "_gpu", lambda: None)
    body = client.get("/system/specs").json()
    assert body["gpu"] is None
    fits = {c["id"]: c["fit"] for c in body["catalog"]}
    assert fits["llama3.2:1b"] == "cpu_ok"
    assert fits["qwen2.5:14b"] == "too_big"
    # No GPU: largest CPU-capable model is suggested.
    assert body["suggested"] == "llama3.1:8b"


def test_onboarding_flag_roundtrip(client):
    assert client.get("/settings").json()["onboarding_complete"] is False
    client.patch("/settings", json={"onboarding_complete": True})
    assert client.get("/settings").json()["onboarding_complete"] is True
