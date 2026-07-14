"""Ollama provider: streams /api/chat NDJSON over httpx."""

import json
from collections.abc import AsyncIterator

import httpx

from ..config import OLLAMA_URL
from .base import Delta, Message


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = OLLAMA_URL, transport: httpx.AsyncBaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, transport=self._transport
        )

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        async with self._client(timeout=300.0) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise RuntimeError(f"Ollama error: {chunk['error']}")
                    content = chunk.get("message", {}).get("content", "")
                    done = bool(chunk.get("done", False))
                    if content or done:
                        yield Delta(content=content, done=done)
                    if done:
                        return

    async def complete(self, messages: list[Message], model: str) -> str:
        """Non-streaming convenience used by the memory extractor."""
        parts: list[str] = []
        async for delta in self.stream_chat(messages, model):
            parts.append(delta.content)
        return "".join(parts)

    async def list_models(self) -> list[str]:
        async with self._client(timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
