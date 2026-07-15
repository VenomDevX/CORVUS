"""Google Gemini provider via the generateContent API.

Gemini uses `contents` with role "user"/"model", a separate systemInstruction,
and functionCall/functionResponse parts for tools. Streaming uses the
streamGenerateContent endpoint (SSE with alt=sse).
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import Delta, Message, ToolCall


def _to_contents(messages: list[Message]) -> tuple[dict | None, list[dict]]:
    system = None
    contents: list[dict] = []
    for m in messages:
        if m.role == "system":
            system = {"parts": [{"text": m.content}]}
        elif m.role == "tool":
            contents.append({"role": "user", "parts": [
                {"functionResponse": {"name": m.tool_name or "",
                                      "response": {"result": m.content}}}
            ]})
        elif m.tool_calls:
            parts: list[dict] = []
            if m.content:
                parts.append({"text": m.content})
            for c in m.tool_calls:
                parts.append({"functionCall": {"name": c.name, "args": c.arguments}})
            contents.append({"role": "model", "parts": parts})
        else:
            role = "model" if m.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.content}]})
    return system, contents


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str,
                 base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 transport: httpx.AsyncBaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, transport=self._transport,
            headers={"x-goog-api-key": self._api_key},
        )

    async def _stream(self, model: str, payload: dict) -> AsyncIterator[Delta]:
        calls: list[ToolCall] = []
        async with self._client(300.0) as client:
            async with client.stream(
                "POST", f"/models/{model}:streamGenerateContent?alt=sse", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = json.loads(line[5:].strip())
                    for cand in chunk.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            if "text" in part and part["text"]:
                                yield Delta(content=part["text"])
                            if "functionCall" in part:
                                fc = part["functionCall"]
                                calls.append(ToolCall(name=fc.get("name", ""),
                                                      arguments=fc.get("args", {}) or {}))
        yield Delta(content="", done=True, tool_calls=calls)

    def _payload(self, messages, tools=None) -> dict:
        system, contents = _to_contents(messages)
        payload: dict = {"contents": contents}
        if system:
            payload["systemInstruction"] = system
        if tools:
            payload["tools"] = [{"functionDeclarations": [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "parameters": t["function"].get("parameters", {"type": "object", "properties": {}})}
                for t in tools]}]
        return payload

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        async for d in self._stream(model, self._payload(messages)):
            yield d

    async def stream_chat_with_tools(
        self, messages: list[Message], model: str, tools: list[dict[str, Any]]
    ) -> AsyncIterator[Delta]:
        async for d in self._stream(model, self._payload(messages, tools)):
            yield d

    async def complete(self, messages: list[Message], model: str) -> str:
        return "".join([d.content async for d in self.stream_chat(messages, model)])

    async def list_models(self) -> list[str]:
        try:
            async with self._client(15.0) as client:
                resp = await client.get("/models")
                resp.raise_for_status()
                names = [m["name"].split("/")[-1] for m in resp.json().get("models", [])]
                return [n for n in names if "gemini" in n]
        except Exception:
            return ["gemini-2.5-flash", "gemini-2.5-pro"]
