"""Ollama provider: streams /api/chat NDJSON over httpx."""

import asyncio
import json
import os
import re
import shutil
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from ..config import DEFAULT_NUM_CTX, OLLAMA_URL
from .base import Delta, Message, ToolCall

log = structlog.get_logger("corvus")

# Models Ollama rejected with "does not support tools" (400): remembered for
# the process lifetime so later turns skip the doomed with-tools attempt.
_no_tools_models: set[str] = set()

_start_lock = asyncio.Lock()


def _launch_ollama() -> bool:
    """Launch the installed Ollama tray app (which runs the server and outlives
    Corvus, like opening it by hand). Falls back to `ollama serve`."""
    install = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
    tray = install / "ollama app.exe"
    cli = install / "ollama.exe" if (install / "ollama.exe").exists() else shutil.which("ollama")
    if tray.exists():
        cmd = [str(tray)]
    elif cli:
        cmd = [str(cli), "serve"]
    else:
        return False
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) \
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(cmd, creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("ollama_autostart_failed", error=str(exc))
        return False
    log.info("ollama_autostart", cmd=cmd[0])
    return True


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


# Start of a JSON tool-call region: '{"', '{}', '[{', '["', or a 'json' block fence.
# Also matches prefixes at the end of the buffer ('{\s*$', '\[\s*$', '[json]*$') 
# to hold incomplete chunks until they resolve.
# Deliberately does NOT match prose braces ("{x}") or 'python' code fences, so
# ordinary answers and code blocks keep streaming untouched.
_JSON_START = re.compile(r'\{\s*["}]|\[\s*[\[{"]|`{3}json|`{3}(?:j(?:s(?:o(?:n)?)?)?)?$|\{\s*$|\[\s*$', re.IGNORECASE)


def _json_start(text: str) -> int:
    match = _JSON_START.search(text)
    return match.start() if match else -1


def _parse_tool_objects(text: str, valid_names: set[str] | None) -> list[ToolCall]:
    """Tool-call objects in `text`; valid_names=None accepts any name."""
    text = text.strip()
    if text.startswith("`" * 3):
        text = re.sub(r"^`{3}[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*`{3}$", "", text).strip()
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
        if isinstance(name, str) and name and (valid_names is None or name in valid_names) and isinstance(args, dict):
            calls.append(ToolCall(name=name, arguments=args))
    return calls


def _extract_text_tool_calls(content: str, valid_names: set[str]) -> list[ToolCall]:
    """Recover tool calls that a model wrote as JSON *content* instead of using
    Ollama's structured tool_calls field.

    Several capable local models (e.g. qwen2.5-coder) reliably emit a
    '{"name": ..., "arguments": {...}}' object (optionally fenced, optionally a
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
    if content.startswith("`" * 3):
        content = re.sub(r"^`{3}[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*`{3}$", "", content).strip()
    
    def check_parsed(parsed: Any) -> bool:
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict):
                if "name" in item and ("arguments" in item or "parameters" in item):
                    return True
                # Catch hallucinated JSON schemas (e.g. {"type": "object", "properties": ...})
                if "type" in item and "properties" in item:
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


def _is_broken_tool_call(content: str, valid_names: set[str]) -> bool:
    """Malformed JSON that is still plainly a call to one of this turn's tools,
    e.g. '{"name": "cancel_reminder", "arguments": {"reminder_id": <id>}}'.
    It can't run, and it must not reach the user as an answer."""
    match = re.search(r'"name"\s*:\s*"([^"]+)"', content)
    return bool(match and match.group(1) in valid_names
                and re.search(r'"(arguments|parameters)"\s*:', content))


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


async def _raise_for_error(response: httpx.Response) -> None:
    """5xx carries Ollama's real reason (e.g. cudaMalloc failed) in the body;
    surface it through _format_ollama_error instead of httpx's generic text.
    4xx stays an HTTPStatusError for describe_error (404 = model not pulled)."""
    if response.status_code >= 500:
        body = (await response.aread()).decode("utf-8", errors="replace")
        try:
            body = json.loads(body).get("error", body)
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(_format_ollama_error(str(body)))
    response.raise_for_status()


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = OLLAMA_URL, transport: httpx.AsyncBaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, transport=self._transport
        )

    async def _ensure_running(self) -> None:
        """Start a local Ollama that isn't running, so chat works without the
        user opening it first. A no-op when it's up, remote, or not installed
        (the request then fails with the usual "isn't running" advice)."""
        if self._transport is not None or urlparse(self._base_url).hostname not in ("127.0.0.1", "localhost"):
            return
        async with _start_lock:
            if await self._reachable():
                return
            if not _launch_ollama():
                return
            for _ in range(40):  # up to ~20s for the server to listen
                await asyncio.sleep(0.5)
                if await self._reachable():
                    log.info("ollama_autostarted")
                    return
            log.warning("ollama_autostart_timeout")

    async def _reachable(self) -> bool:
        try:
            async with self._client(timeout=2.0) as client:
                await client.get("/api/version")
            return True
        except httpx.HTTPError:
            return False

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        await self._ensure_running()
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"num_ctx": DEFAULT_NUM_CTX},
        }
        async with self._client(timeout=300.0) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                await _raise_for_error(response)
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
        await self._ensure_running()
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
                await _raise_for_error(response)
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
                        if not text_calls and not emitted_native_calls and held.strip():
                            # The whole reply is a call to a tool that doesn't exist
                            # ("calculate_speed", "adjust_volume"); live tests hit this on
                            # 1 in 3 math prompts. Pass it to the agent, which answers
                            # "Unknown action" so the model retries or replies in words,
                            # instead of showing the user raw JSON.
                            text_calls = _parse_tool_objects(held, None)
                        if text_calls:
                            if not emitted_native_calls:
                                yield Delta(content="", done=True, tool_calls=text_calls)
                            else:
                                yield Delta(content="", done=True)
                        elif held:
                            if (emitted_native_calls and _is_any_tool_call(held)) or _is_broken_tool_call(held, valid_names):
                                # A duplicate echo of native calls, or an unparseable call — drop it.
                                yield Delta(content="", done=True)
                            else:
                                # Held content is not a valid tool call — emit as normal prose.
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

        await self._ensure_running()
        data = base64.b64encode(Path(image_path).read_bytes()).decode()
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
        await self._ensure_running()
        async with self._client(timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
