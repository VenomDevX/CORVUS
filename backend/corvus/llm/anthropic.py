"""Anthropic (Claude) provider via the Messages API.

Anthropic separates the system prompt from the message list and uses
content-block streaming (SSE). Tool calls arrive as tool_use blocks whose JSON
input streams as partial_json deltas.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import Delta, Message, ToolCall

API_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 2048


def _split_system(messages: list[Message]) -> tuple[str, list[dict]]:
    system_parts = [m.content for m in messages if m.role == "system"]
    wire: list[dict] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            wire.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m.tool_name or "", "content": m.content}
            ]})
        elif m.tool_calls:
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for c in m.tool_calls:
                blocks.append({"type": "tool_use", "id": c.id or c.name,
                               "name": c.name, "input": c.arguments})
            wire.append({"role": "assistant", "content": blocks})
        else:
            wire.append({"role": m.role, "content": m.content})
    return "\n\n".join(system_parts), wire


def _tools_to_anthropic(tools: list[dict]) -> list[dict]:
    out = []
    for t in tools:
        fn = t.get("function", {})
        out.append({"name": fn.get("name"), "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}})})
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1",
                 transport: httpx.AsyncBaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, transport=self._transport,
            headers={"x-api-key": self._api_key, "anthropic-version": API_VERSION},
        )

    async def _stream(self, payload: dict) -> AsyncIterator[Delta]:
        blocks: dict[int, dict] = {}
        async with self._client(300.0) as client:
            async with client.stream("POST", "/messages", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].strip())
                    etype = event.get("type")
                    if etype == "content_block_start":
                        blocks[event["index"]] = {"block": event["content_block"], "json": ""}
                    elif etype == "content_block_delta":
                        d = event["delta"]
                        if d.get("type") == "text_delta" and d.get("text"):
                            yield Delta(content=d["text"])
                        elif d.get("type") == "input_json_delta":
                            blocks.setdefault(event["index"], {"block": {}, "json": ""})
                            blocks[event["index"]]["json"] += d.get("partial_json", "")
        calls = []
        for b in blocks.values():
            block = b["block"]
            if block.get("type") == "tool_use":
                try:
                    args = json.loads(b["json"]) if b["json"] else block.get("input", {})
                except json.JSONDecodeError:
                    args = {}
                calls.append(ToolCall(name=block.get("name", ""), id=block.get("id", ""),
                                      arguments=args if isinstance(args, dict) else {}))
        yield Delta(content="", done=True, tool_calls=calls)

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        system, wire = _split_system(messages)
        payload = {"model": model, "system": system, "messages": wire,
                   "max_tokens": DEFAULT_MAX_TOKENS, "stream": True}
        async for d in self._stream(payload):
            yield d

    async def stream_chat_with_tools(
        self, messages: list[Message], model: str, tools: list[dict[str, Any]]
    ) -> AsyncIterator[Delta]:
        system, wire = _split_system(messages)
        payload = {"model": model, "system": system, "messages": wire,
                   "max_tokens": DEFAULT_MAX_TOKENS, "stream": True}
        if tools:
            payload["tools"] = _tools_to_anthropic(tools)
        async for d in self._stream(payload):
            yield d

    async def complete(self, messages: list[Message], model: str) -> str:
        return "".join([d.content async for d in self.stream_chat(messages, model)])

    async def list_models(self) -> list[str]:
        # Anthropic's public model ids (the /models endpoint requires the same key).
        try:
            async with self._client(15.0) as client:
                resp = await client.get("/models")
                resp.raise_for_status()
                return [m["id"] for m in resp.json().get("data", [])]
        except Exception:
            return ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"]
