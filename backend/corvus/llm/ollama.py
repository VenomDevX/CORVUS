"""Ollama provider: streams /api/chat NDJSON over httpx."""

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from ..config import DEFAULT_NUM_CTX, OLLAMA_URL
from .base import Delta, Message, ToolCall

log = structlog.get_logger("corvus")

# Models Ollama rejected with "does not support tools" (400): remembered for
# the process lifetime so later turns skip the doomed with-tools attempt.
_no_tools_models: set[str] = set()


def _parse_tool_calls(message: dict) -> list[ToolCall]:
    """Read Ollama's tool_calls off one chat chunk. Arguments arrive as an
    object, but some models emit a JSON string - accept both."""
    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        fn = raw.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        calls.append(ToolCall(name=fn.get("name", ""), arguments=args or {}))
    return calls


# Start of a JSON tool-call region: `{"`, `{}`, `[{`, `["`, or a ```json fence.
# Also matches prefixes at the end of the buffer (`{\s*$`, `\[\s*$`, ```[json]*$) 
# to hold incomplete chunks until they resolve.
# Deliberately does NOT match prose braces ("{x}") or ```python code fences, so
# ordinary answers and code blocks keep streaming untouched.
_JSON_START = re.compile(r'\{\s*["}]|\[\s*[\[{"]|```json|```(?:j(?:s(?:o(?:n)?)?)?)?$|\{\s*$|\[\s*$', re.IGNORECASE)


def _json_start(text: str) -> int:
    match = _JSON_START.search(text)
    return match.start() if match else -1


def _parse_tool_objects(text: str, valid_names: set[str]) -> list[ToolCall]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = parsed if isinstance(parsed, list) else [parsed]
    calls: list[ToolCall] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        args = item.get("arguments", item.get("parameters", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name in valid_names and isinstance(args, dict):
            calls.append(ToolCall(name=name, arguments=args))
    return calls


def _extract_text_tool_calls(content: str, valid_names: set[str]) -> list[ToolCall]:
    """Recover tool calls that a model wrote as JSON *content* instead of using
    Ollama's structured tool_calls field.

    Several capable local models (e.g. qwen2.5-coder) reliably emit a
    `{"name": ..., "arguments": {...}}` object (optionally fenced, optionally a
    list, sometimes after a sentence of narration) rather than using the
    structured field. Only names present in the turn's tool set are accepted,
    so ordinary JSON the user asked for is never misread as an action.
    """
    calls = _parse_tool_objects(content, valid_names)
    if calls:
        return calls
    # Narration may precede the object ("Getting status…\n\n{...}"): try the
    # span from the first brace to the last matching close.
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        calls = _parse_tool_objects(content[start : end + 1], valid_names)
    return calls


def _is_any_tool_call(content: str) -> bool:
    """Check if the text represents *any* tool call JSON, even an invalid one."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content).strip()
    
    def check_parsed(parsed: Any) -> bool:
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict) and "name" in item:
                return True
        return False
        
    try:
        if check_parsed(json.loads(content)):
            return True
    except json.JSONDecodeError:
        pass
        
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        try:
            if check_parsed(json.loads(content[start : end + 1])):
                return True
        except json.JSONDecodeError:
            pass
            
    return False


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


def _format_ollama_error(msg: str) -> str:
    lower = msg.lower()
    if any(k in lower for k in ("cudamalloc", "unable to allocate", "cpu_repack", "out of memory", "commit limit")):
        return (
            "System ran out of memory (Windows commit limit). Try closing background apps or browser tabs, "
            f"or switch to a smaller model (e.g. llama3.2:1b or qwen2.5-coder:1.5b). Details: {msg}"
        )
    return f"Ollama error: {msg}"


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
            "options": {"num_ctx": DEFAULT_NUM_CTX},
        }
        async with self._client(timeout=300.0) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise RuntimeError(_format_ollama_error(str(chunk["error"])))
                    content = chunk.get("message", {}).get("content", "")
                    done = bool(chunk.get("done", False))
                    if content or done:
                        yield Delta(content=content, done=done)
                    if done:
                        return

    async def stream_chat_with_tools(
        self, messages: list[Message], model: str, tools: list[dict[str, Any]]
    ) -> AsyncIterator[Delta]:
        base_payload = {
            "model": model,
            "messages": _to_wire(messages),
            "stream": True,
            # Bound the context so the KV cache fits modest GPUs; the tool
            # schemas + short history stay well under this.
            "options": {"num_ctx": DEFAULT_NUM_CTX},
        }
        valid_names = {
            t["function"]["name"] for t in tools if isinstance(t.get("function"), dict)
        }
        # Ollama rejects the whole request with 400 when a model lacks tool
        # support (e.g. deepseek-coder). Fall back to a plain request - the
        # agent system prompt makes such models emit calls as JSON content,
        # which the held-buffer recovery below still picks up.
        attempts = ["plain"] if (model in _no_tools_models or not tools) else ["tools", "plain"]

        # Some models write a tool call as JSON content rather than using the
        # structured field, often after a sentence of narration. Stream prose
        # normally, but once a JSON-object region begins, hold from there to the
        # end of the turn and then decide: real tool call, or text to release.
        buffer = ""
        emitted = 0
        emitted_native_calls = False

        async with self._client(timeout=300.0) as client:
            response = None
            for attempt in attempts:
                payload = dict(base_payload)
                if attempt == "tools":
                    payload["tools"] = tools
                stream_ctx = client.stream("POST", "/api/chat", json=payload)
                response = await stream_ctx.__aenter__()
                if attempt == "tools" and response.status_code == 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    await stream_ctx.__aexit__(None, None, None)
                    if "tool" in body.lower():
                        _no_tools_models.add(model)
                        log.info("ollama_tools_unsupported", model=model)
                        continue
                    raise RuntimeError(_format_ollama_error(body))
                break

            try:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise RuntimeError(_format_ollama_error(str(chunk["error"])))
                    message = chunk.get("message", {})
                    content = message.get("content", "") or ""
                    calls = _parse_tool_calls(message)
                    done = bool(chunk.get("done", False))

                    if calls:
                        emitted_native_calls = True
                        yield Delta(content="", done=False, tool_calls=calls)

                    if content:
                        buffer += content
                        hold = _json_start(buffer)
                        # Emit prose up to the JSON region (or all of it if none).
                        limit = hold if hold != -1 else len(buffer)
                        if limit > emitted:
                            yield Delta(content=buffer[emitted:limit])
                            emitted = limit

                    if done:
                        held = buffer[emitted:]
                        text_calls = _extract_text_tool_calls(held, valid_names) if held.strip() else []
                        if text_calls:
                            if not emitted_native_calls:
                                yield Delta(content="", done=True, tool_calls=text_calls)
                            else:
                                yield Delta(content="", done=True)
                        elif held:
                            if emitted_native_calls and _is_any_tool_call(held):
                                yield Delta(content="", done=True)
                            else:
                                yield Delta(content=held, done=True)
                        else:
                            yield Delta(content="", done=True)
                        return
            finally:
                await stream_ctx.__aexit__(None, None, None)

    async def complete(self, messages: list[Message], model: str) -> str:
        """Non-streaming convenience used by the memory extractor."""
        parts: list[str] = []
        async for delta in self.stream_chat(messages, model):
            parts.append(delta.content)
        return "".join(parts)

    async def describe_image(self, image_path: str, model: str) -> str:
        """Describe an image with a vision-capable Ollama model (llava-class).

        Only called when such a model is installed; ordinary chat models don't
        accept the images field.
        """
        import base64

        data = base64.b64encode(open(image_path, "rb").read()).decode()
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "Describe this image, including any visible UI elements or text.",
                    "images": [data],
                }
            ],
            "stream": False,
        }
        async with self._client(timeout=120.0) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")

    async def list_models(self) -> list[str]:
        async with self._client(timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
