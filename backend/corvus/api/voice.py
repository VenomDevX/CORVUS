"""Voice WebSocket: event fan-out + control commands.

Server -> client events (from the pipeline):
  {"type": "state", "state": "idle|listening|thinking|speaking", "conversation_id"}
  {"type": "level", "value": 0..1}         live input/output audio level
  {"type": "wake"}                          wake phrase detected
  {"type": "transcript", "text"}            what Corvus heard
  {"type": "assistant_delta", "text"}       streamed response text
  {"type": "assistant_done", "conversation_id"}
  {"type": "wake_enabled", "enabled"}
  {"type": "unavailable", "reason"}         no usable microphone
  {"type": "error", "message"}

Client -> server commands:
  {"type": "ptt"}                           push-to-talk: listen now
  {"type": "set_wake", "enabled": bool}     always-listening toggle
  {"type": "stop"}                          stop speaking / cancel the turn
"""

import asyncio
import contextlib

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

voice_router = APIRouter()


@voice_router.get("/voice/status")
def voice_status(request: Request) -> dict:
    pipeline = request.app.state.voice
    if pipeline is None:
        return {"available": False, "state": "off", "wake_enabled": False}
    return {
        "available": pipeline.available,
        "state": pipeline.state,
        "wake_enabled": pipeline.wake_enabled,
        "voice": pipeline.speaker.voice,
    }


@voice_router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket) -> None:
    await ws.accept()
    pipeline = ws.app.state.voice
    if pipeline is None or not pipeline.available:
        await ws.send_json({"type": "unavailable", "reason": "voice pipeline is not running"})
        await ws.close()
        return

    events = pipeline.subscribe()
    await ws.send_json(
        {"type": "state", "state": pipeline.state, "conversation_id": pipeline.conversation_id}
    )
    await ws.send_json({"type": "wake_enabled", "enabled": pipeline.wake_enabled})

    async def forward_events() -> None:
        while True:
            event = await events.get()
            await ws.send_json(event)

    forwarder = asyncio.create_task(forward_events())
    try:
        while True:
            command = await ws.receive_json()
            kind = command.get("type")
            if kind == "ptt":
                pipeline.push_to_talk()
            elif kind == "set_wake":
                pipeline.set_wake_enabled(bool(command.get("enabled")))
            elif kind == "stop":
                pipeline.stop_speaking()
    except WebSocketDisconnect:
        pass
    finally:
        forwarder.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await forwarder
        pipeline.unsubscribe(events)
