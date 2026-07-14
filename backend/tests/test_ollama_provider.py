import json

import httpx
import pytest

from corvus.llm.base import Message
from corvus.llm.ollama import OllamaProvider


def ndjson_response(chunks: list[dict]) -> httpx.Response:
    body = "\n".join(json.dumps(c) for c in chunks)
    return httpx.Response(200, content=body.encode(), headers={"content-type": "application/x-ndjson"})


def make_provider(handler) -> OllamaProvider:
    return OllamaProvider(base_url="http://ollama.test", transport=httpx.MockTransport(handler))


async def test_stream_chat_yields_deltas_until_done():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["messages"][0]["role"] == "system"
        return ndjson_response(
            [
                {"message": {"content": "Hel"}, "done": False},
                {"message": {"content": "lo"}, "done": False},
                {"message": {"content": ""}, "done": True},
            ]
        )

    provider = make_provider(handler)
    deltas = [
        d
        async for d in provider.stream_chat(
            [Message("system", "s"), Message("user", "hi")], "test-model"
        )
    ]
    assert "".join(d.content for d in deltas) == "Hello"
    assert deltas[-1].done is True


async def test_stream_chat_raises_on_ollama_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response([{"error": "model not found"}])

    provider = make_provider(handler)
    with pytest.raises(RuntimeError, match="model not found"):
        async for _ in provider.stream_chat([Message("user", "hi")], "missing"):
            pass


async def test_complete_concatenates():
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response(
            [{"message": {"content": "a"}, "done": False}, {"message": {"content": "b"}, "done": True}]
        )

    provider = make_provider(handler)
    assert await provider.complete([Message("user", "x")], "m") == "ab"


async def test_list_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:latest"}]})

    provider = make_provider(handler)
    assert await provider.list_models() == ["qwen2.5-coder:latest"]
