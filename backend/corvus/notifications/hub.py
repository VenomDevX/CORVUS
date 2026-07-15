"""Notification hub: immediate desktop notifications plus scheduled timers,
alarms, and reminders.

Reminders persist in SQLite so they survive a restart (crash recovery). The hub
schedules an asyncio task per pending reminder; when one fires it's pushed to
subscribers (the /ws/notifications socket), and the Electron renderer raises a
native Windows toast. Anything already overdue at startup fires immediately.
"""

import asyncio
import contextlib
from datetime import datetime, timedelta

import structlog

log = structlog.get_logger("corvus")


class NotificationHub:
    def __init__(self, repo):
        self.repo = repo
        self._subscribers: set[asyncio.Queue] = set()
        self._tasks: dict[int, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- pub/sub --------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _emit(self, event: dict) -> None:
        for q in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        for reminder in self.repo.pending_reminders():
            self._schedule(reminder)
        log.info("notification_hub_started", pending=len(self._tasks))

    async def stop(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    # -- immediate notifications ----------------------------------------------

    def notify(self, title: str, message: str, level: str = "info") -> None:
        self._emit({"type": "notify", "title": title, "message": message, "level": level})
        log.info("notification", title=title, level=level)

    # -- scheduling -----------------------------------------------------------

    def schedule(self, text: str, kind: str, fire_at: datetime) -> dict:
        reminder = self.repo.add_reminder(text, kind, fire_at.isoformat(timespec="seconds"))
        self._schedule(reminder)
        return reminder

    def schedule_in(self, text: str, kind: str, minutes: float) -> dict:
        return self.schedule(text, kind, datetime.now() + timedelta(minutes=minutes))

    def _schedule(self, reminder: dict) -> None:
        if self._loop is None:
            return
        fire_at = datetime.fromisoformat(reminder["fire_at"])
        delay = max(0.0, (fire_at - datetime.now()).total_seconds())
        self._tasks[reminder["id"]] = self._loop.create_task(self._fire_after(reminder, delay))

    async def _fire_after(self, reminder: dict, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        titles = {"timer": "Timer", "alarm": "Alarm", "reminder": "Reminder"}
        self._emit({
            "type": "reminder",
            "id": reminder["id"],
            "kind": reminder["kind"],
            "title": f"Corvus {titles.get(reminder['kind'], 'Reminder')}",
            "message": reminder["text"],
        })
        self.repo.mark_reminder_fired(reminder["id"])
        self._tasks.pop(reminder["id"], None)
        log.info("reminder_fired", reminder_id=reminder["id"], kind=reminder["kind"])

    def cancel(self, reminder_id: int) -> bool:
        task = self._tasks.pop(reminder_id, None)
        if task:
            task.cancel()
        return self.repo.delete_reminder(reminder_id)

    def list_pending(self) -> list[dict]:
        return self.repo.pending_reminders()
