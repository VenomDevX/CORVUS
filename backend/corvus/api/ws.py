"""WebSocket chat: one socket per assistant turn, now agent-capable.

Protocol (JSON frames):
  client -> {"type": "start", "conversation_id": int|null, "content": str}
  client -> {"type": "confirm", "approved": bool}   answer to an action prompt
  client -> {"type": "cancel"}                       stop generation
  server -> {"type": "start", "conversation_id", "user_message_id"}
  server -> {"type": "delta", "content"}             streamed final answer
  server -> {"type": "action_proposed", "name", "arguments", "risk", "category"}
  server -> {"type": "action_confirming", "name", "prompt"}   awaits a confirm frame
  server -> {"type": "action_result", "name", "ok", "message", ...}
  server -> {"type": "done", "message_id", "conversation_id"}
  server -> {"type": "error", "message"}

Text answers stream token-by-token when no tools are involved. When the model
requests actions, they run first (with confirmation for risky ones), then the
final answer streams.
"""

import asyncio
import contextlib

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import SYSTEM_PROMPT
from ..llm.agent import agent_system_prompt, run_agent_turn
from ..llm.base import Message
from ..memory.extractor import extract_memory

ws_router = APIRouter()
log = structlog.get_logger("corvus")

MAX_HISTORY_MESSAGES = 40


@ws_router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    repo = ws.app.state.repo
    provider = ws.app.state.provider
    registry = ws.app.state.registry

    try:
        start = await ws.receive_json()
    except WebSocketDisconnect:
        return
    if start.get("type") != "start" or not str(start.get("content", "")).strip():
        await ws.send_json({"type": "error", "message": "expected a start frame with content"})
        await ws.close()
        return

    content = str(start["content"]).strip()
    conversation_id = start.get("conversation_id")
    if conversation_id is None or repo.get_conversation(conversation_id) is None:
        title = content[:60] + ("…" if len(content) > 60 else "")
        conversation_id = repo.create_conversation(title)["id"]

    user_message = repo.add_message(conversation_id, "user", content)
    await ws.send_json(
        {"type": "start", "conversation_id": conversation_id, "user_message_id": user_message["id"]}
    )

    history = repo.list_messages(conversation_id)[-MAX_HISTORY_MESSAGES:]
    system = SYSTEM_PROMPT + "\n\n" + agent_system_prompt(registry)
    messages = [Message("system", system)] + [Message(m["role"], m["content"]) for m in history]
    model = repo.get_setting("model")

    # Pending-confirmation plumbing: the agent loop calls confirm(), which
    # sends an action_confirming frame and waits for the client's reply.
    pending: dict[str, asyncio.Future] = {}

    async def emit(event: dict) -> None:
        # The final text is streamed separately as deltas; skip the whole-text event.
        if event.get("type") == "text":
            return
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await ws.send_json(event)

    async def confirm(name: str, prompt: str, args: dict) -> bool:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        pending["current"] = future
        # action_confirming was already emitted by the agent loop.
        try:
            return await asyncio.wait_for(future, timeout=120)
        except asyncio.TimeoutError:
            return False
        finally:
            pending.pop("current", None)

    async def read_client() -> None:
        """Feed confirm/cancel frames to the agent loop."""
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            while True:
                frame = await ws.receive_json()
                if frame.get("type") == "confirm" and "current" in pending:
                    fut = pending["current"]
                    if not fut.done():
                        fut.set_result(bool(frame.get("approved")))
                elif frame.get("type") == "cancel" and "current" in pending:
                    fut = pending["current"]
                    if not fut.done():
                        fut.set_result(False)

    reader = asyncio.create_task(read_client())

    def log_action(action, arguments, result, outcome):
        repo.log_action(conversation_id, action, arguments, outcome, result.message)

    assistant_text = ""
    error: str | None = None
    log.info("chat_turn_start", conversation_id=conversation_id, model=model)
    try:
        outcome = await run_agent_turn(
            provider, model, messages, registry, confirm, emit=emit, log_action=log_action,
        )
        assistant_text = outcome.text
        # Stream the final answer for a typing feel (agent path returns it whole).
        if assistant_text:
            await _stream_text(ws, assistant_text)
    except Exception as exc:
        error = str(exc)
        log.error("chat_turn_error", conversation_id=conversation_id, error=error)
    finally:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader

    message_id = None
    if assistant_text:
        message_id = repo.add_message(conversation_id, "assistant", assistant_text)["id"]

    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        if error and not assistant_text:
            await ws.send_json({"type": "error", "message": f"Corvus hit a problem: {error}"})
        else:
            await ws.send_json(
                {"type": "done", "message_id": message_id, "conversation_id": conversation_id}
            )
        await ws.close()

    log.info("chat_turn_done", conversation_id=conversation_id, chars=len(assistant_text))

    if assistant_text:
        await extract_memory(provider, model, repo, content, assistant_text, conversation_id)


async def _stream_text(ws: WebSocket, text: str) -> None:
    """Send text as word-chunk deltas so the UI animates it."""
    words = text.split(" ")
    buffer = ""
    for i, word in enumerate(words):
        buffer += word + (" " if i < len(words) - 1 else "")
        if len(buffer) >= 12 or i == len(words) - 1:
            with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                await ws.send_json({"type": "delta", "content": buffer})
            buffer = ""
            await asyncio.sleep(0.01)
