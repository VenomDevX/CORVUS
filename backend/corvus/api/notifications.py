"""Notifications WebSocket + REST.

The renderer holds one /ws/notifications socket open; the hub pushes immediate
notifications and reminder fires, which the Electron app raises as native
Windows toasts.
"""

import asyncio
import contextlib

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

notify_router = APIRouter()


@notify_router.get("/reminders")
def list_reminders(request: Request) -> list[dict]:
    hub = request.app.state.notifications
    return hub.list_pending() if hub is not None else []


@notify_router.delete("/reminders/{reminder_id}")
def cancel_reminder(request: Request, reminder_id: int) -> dict:
    hub = request.app.state.notifications
    if hub is None or not hub.cancel(reminder_id):
        raise HTTPException(404, "reminder not found")
    return {"ok": True}


@notify_router.websocket("/ws/notifications")
async def notifications_ws(ws: WebSocket) -> None:
    await ws.accept()
    hub = ws.app.state.notifications
    if hub is None:
        await ws.close()
        return
    queue = hub.subscribe()
    try:
        while True:
            event = await queue.get()
            await ws.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await ws.close()
