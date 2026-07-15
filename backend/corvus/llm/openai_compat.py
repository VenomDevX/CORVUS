"""OpenAI-compatible chat providers (OpenAI and DeepSeek share this wire format).

Streaming SSE over httpx, matching the internal LLMProvider protocol. Tool
calls arrive fragmented across chunks (arguments stream in pieces, keyed by
index); they're reassembled and emitted once complete.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import Delta, Message, ToolCall


def _to_wire(messages: list[Message]) -> list[dict]:
    wire: list[dict] = []
    for m in messages:
        entry: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            entry["tool_calls"] = [
                {"id": c.id or c.name, "type": "function",
                 "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in m.tool_calls
            ]
        if m.role == "tool":
            entry["role"] = "tool"
            entry["tool_call_id"] = m.tool_name or ""
            entry["name"] = m.tool_name or ""
        wire.append(entry)
    return wire


class OpenAICompatProvider:
    def __init__(self, name: str, base_url: str, api_key: str,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    async def _stream(self, payload: dict) -> AsyncIterator[Delta]:
        tool_frags: dict[int, dict] = {}
        async with self._client(300.0) as client:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content") or ""
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        frag = tool_frags.setdefault(idx, {"name": "", "args": ""})
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            frag["name"] = fn["name"]
                        if fn.get("arguments"):
                            frag["args"] += fn["arguments"]
                    if content:
                        yield Delta(content=content)
        calls = []
        for frag in tool_frags.values():
            if not frag["name"]:
                continue
            try:
                args = json.loads(frag["args"]) if frag["args"] else {}
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(name=frag["name"], arguments=args if isinstance(args, dict) else {}))
        yield Delta(content="", done=True, tool_calls=calls)

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        async for d in self._stream({
            "model": model, "messages": _to_wire(messages), "stream": True,
        }):
            yield d

    async def stream_chat_with_tools(
        self, messages: list[Message], model: str, tools: list[dict[str, Any]]
    ) -> AsyncIterator[Delta]:
        payload = {"model": model, "messages": _to_wire(messages), "stream": True}
        if tools:
            payload["tools"] = tools
        async for d in self._stream(payload):
            yield d

    async def complete(self, messages: list[Message], model: str) -> str:
        parts = [d.content async for d in self.stream_chat(messages, model)]
        return "".join(parts)

    async def list_models(self) -> list[str]:
        async with self._client(15.0) as client:
            resp = await client.get("/models")
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]
