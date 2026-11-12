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
        self._undelivered: dict[int, dict] = {}

    # -- pub/sub --------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        # Hand over reminders that fired while no window was listening.
        for reminder_id, event in list(self._undelivered.items()):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)
                self.repo.mark_reminder_fired(reminder_id)
                del self._undelivered[reminder_id]
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
            try:
                self._schedule(reminder)
            except Exception as exc:  # one bad row must never block startup
                log.error("reminder_unschedulable", reminder_id=reminder.get("id"), error=str(exc))
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

    @staticmethod
    def _local_naive(fire_at: datetime) -> datetime:
        """Times are stored and compared as naive local time; convert "…Z"/offsets."""
        return fire_at.astimezone().replace(tzinfo=None) if fire_at.tzinfo else fire_at

    def schedule(self, text: str, kind: str, fire_at: datetime) -> dict:
        fire_at = self._local_naive(fire_at)
        reminder = self.repo.add_reminder(text, kind, fire_at.isoformat(timespec="seconds"))
        self._schedule(reminder)
        return reminder

    def schedule_in(self, text: str, kind: str, minutes: float) -> dict:
        return self.schedule(text, kind, datetime.now() + timedelta(minutes=minutes))

    def _schedule(self, reminder: dict) -> None:
        if self._loop is None:
            return
        fire_at = self._local_naive(datetime.fromisoformat(reminder["fire_at"]))
        delay = max(0.0, (fire_at - datetime.now()).total_seconds())
        self._tasks[reminder["id"]] = self._loop.create_task(self._fire_after(reminder, delay))

    async def _fire_after(self, reminder: dict, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        titles = {"timer": "Timer", "alarm": "Alarm", "reminder": "Reminder"}
        event = {
            "type": "reminder",
            "id": reminder["id"],
            "kind": reminder["kind"],
            "title": f"Corvus {titles.get(reminder['kind'], 'Reminder')}",
            "message": reminder["text"],
        }
        self._tasks.pop(reminder["id"], None)
        if not self._subscribers:
            # No window connected (e.g. overdue at startup): keep it pending
            # and deliver on the next subscribe instead of silently dropping it.
            self._undelivered[reminder["id"]] = event
            return
        self._emit(event)
        self.repo.mark_reminder_fired(reminder["id"])
        log.info("reminder_fired", reminder_id=reminder["id"], kind=reminder["kind"])

    def cancel(self, reminder_id: int) -> bool:
        task = self._tasks.pop(reminder_id, None)
        if task:
            task.cancel()
        self._undelivered.pop(reminder_id, None)
        return self.repo.delete_reminder(reminder_id)

    def list_pending(self) -> list[dict]:
        return self.repo.pending_reminders()
