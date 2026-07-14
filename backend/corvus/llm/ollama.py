"""Ollama provider: streams /api/chat NDJSON over httpx."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..config import OLLAMA_URL
from .base import Delta, Message, ToolCall, TurnResult


def _to_wire(messages: list[Message]) -> list[dict]:
    """Serialize Corvus messages to Ollama's chat schema, including tools."""
    wire: list[dict] = []
    for m in messages:
        entry: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            entry["tool_calls"] = [
                {"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls
            ]
        if m.tool_name:
            entry["tool_name"] = m.tool_name
        wire.append(entry)
    return wire


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

    async def chat_with_tools(
        self, messages: list[Message], model: str, tools: list[dict[str, Any]]
    ) -> TurnResult:
        payload = {
            "model": model,
            "messages": _to_wire(messages),
            "tools": tools,
            "stream": False,
            # Bound the context so the KV cache fits modest GPUs; the tool
            # schemas + short history stay well under this.
            "options": {"num_ctx": 8192},
        }
        async with self._client(timeout=300.0) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
        message = body.get("message", {})
        calls = []
        for raw in message.get("tool_calls", []) or []:
            fn = raw.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            calls.append(ToolCall(name=fn.get("name", ""), arguments=args or {}))
        return TurnResult(content=message.get("content", "") or "", tool_calls=calls)

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
