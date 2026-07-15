"""WebSocket chat: one socket per assistant turn, now agent-capable.

Protocol (JSON frames):
  client -> {"type": "start", "conversation_id": int|null, "content": str}
  client -> {"type": "confirm", "approved": bool}   answer to an action prompt
  client -> {"type": "cancel"}                       stop generation
  server -> {"type": "start", "conversation_id", "user_message_id"}
  server -> {"type": "delta", "content"}             streamed assistant text
  server -> {"type": "action_proposed", "name", "arguments", "risk", "category"}
  server -> {"type": "action_confirming", "name", "prompt", "risk"}  awaits confirm
  server -> {"type": "action_result", "name", "ok", "message", ...}
  server -> {"type": "done", "message_id", "conversation_id"}
  server -> {"type": "error", "message"}

Text streams token-by-token as the model produces it, including the preamble
before a tool call. Cancel keeps and persists the partial output, matching the
stop-generation button semantics in the UI; a cancel while an action awaits
confirmation also declines that action.
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
    # Remember where we are, so a crash mid-task restores this conversation.
    ws.app.state.session.set_active_conversation(conversation_id)
    await ws.send_json(
        {"type": "start", "conversation_id": conversation_id, "user_message_id": user_message["id"]}
    )

    history = repo.list_messages(conversation_id)[-MAX_HISTORY_MESSAGES:]
    system = SYSTEM_PROMPT + "\n\n" + agent_system_prompt(registry)
    messages = [Message("system", system)] + [Message(m["role"], m["content"]) for m in history]
    model = ws.app.state.active_model()

    # Pending-confirmation plumbing: the agent loop calls confirm(), which
    # sends an action_confirming frame and waits for the client's reply.
    pending: dict[str, asyncio.Future] = {}
    cancelled = asyncio.Event()

    async def emit(event: dict) -> None:
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await ws.send_json(event)

    async def confirm(name: str, prompt: str, args: dict) -> bool:
        if cancelled.is_set():
            return False
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        pending["current"] = future
        # action_confirming was already emitted by the agent loop.
        try:
            return await asyncio.wait_for(future, timeout=120)
        except asyncio.TimeoutError:
            return False
        finally:
            pending.pop("current", None)

    def resolve_pending(approved: bool) -> None:
        fut = pending.get("current")
        if fut is not None and not fut.done():
            fut.set_result(approved)

    async def read_client() -> None:
        """Feed confirm/cancel frames to the agent loop."""
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            while True:
                frame = await ws.receive_json()
                if frame.get("type") == "confirm":
                    resolve_pending(bool(frame.get("approved")))
                elif frame.get("type") == "cancel":
                    # Stop generating, and decline whatever is awaiting an answer.
                    cancelled.set()
                    resolve_pending(False)
                    return

    reader = asyncio.create_task(read_client())

    def log_action(action, arguments, result, outcome):
        repo.log_action(conversation_id, action, arguments, outcome, result.message)

    assistant_text = ""
    error: str | None = None
    log.info("chat_turn_start", conversation_id=conversation_id, model=model)
    try:
        outcome = await run_agent_turn(
            provider, model, messages, registry, confirm, emit=emit, log_action=log_action,
            should_stop=cancelled.is_set,
        )
        assistant_text = outcome.text
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

    log.info(
        "chat_turn_done",
        conversation_id=conversation_id,
        chars=len(assistant_text),
        cancelled=cancelled.is_set(),
    )

    if assistant_text and not cancelled.is_set():
        # Background, bounded second pass; failures only log.
        await extract_memory(provider, model, repo, content, assistant_text, conversation_id)
