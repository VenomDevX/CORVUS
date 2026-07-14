"""WebSocket chat: one socket per assistant turn.

Protocol (JSON frames):
  client -> {"type": "start", "conversation_id": int|null, "content": str}
  client -> {"type": "cancel"}                    (mid-generation stop)
  server -> {"type": "start", "conversation_id", "user_message_id"}
  server -> {"type": "delta", "content"}
  server -> {"type": "done", "message_id", "conversation_id"}
  server -> {"type": "error", "message"}

Cancel keeps and persists the partial output, matching the stop-generation
button semantics in the UI.
"""

import asyncio
import contextlib

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import SYSTEM_PROMPT
from ..llm.base import Message
from ..memory.extractor import extract_memory

ws_router = APIRouter()
log = structlog.get_logger("corvus")

MAX_HISTORY_MESSAGES = 40


async def _watch_for_cancel(ws: WebSocket, cancelled: asyncio.Event) -> None:
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            frame = await ws.receive_json()
            if frame.get("type") == "cancel":
                cancelled.set()
                return


@ws_router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    repo = ws.app.state.repo
    provider = ws.app.state.provider

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
    messages = [Message("system", SYSTEM_PROMPT)] + [
        Message(m["role"], m["content"]) for m in history
    ]
    model = repo.get_setting("model")

    cancelled = asyncio.Event()
    watcher = asyncio.create_task(_watch_for_cancel(ws, cancelled))
    parts: list[str] = []
    error: str | None = None

    log.info("chat_turn_start", conversation_id=conversation_id, model=model)
    try:
        async for delta in provider.stream_chat(messages, model):
            if cancelled.is_set():
                log.info("chat_turn_cancelled", conversation_id=conversation_id)
                break
            if delta.content:
                parts.append(delta.content)
                await ws.send_json({"type": "delta", "content": delta.content})
    except Exception as exc:
        error = str(exc)
        log.error("chat_turn_error", conversation_id=conversation_id, error=error)
    finally:
        watcher.cancel()

    assistant_text = "".join(parts)
    message_id = None
    if assistant_text:
        message_id = repo.add_message(conversation_id, "assistant", assistant_text)["id"]

    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        if error and not assistant_text:
            await ws.send_json({"type": "error", "message": f"Corvus couldn't reach the model: {error}"})
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
