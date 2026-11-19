"""Notification, timer, and reminder actions (Milestone 8).

Registered only when a notification hub is available. Setting a reminder/timer
is low-risk (easily cancelled and clearly surfaced), so these don't gate on
confirmation.
"""

import re
from datetime import datetime, timedelta

from .registry import ActionResult, ActionSpec, Registry, Risk


def register_notification_actions(reg: Registry, hub) -> None:
    def notify(title: str, message: str) -> ActionResult:
        hub.notify(title, message)
        return ActionResult(True, f"Sent a notification: {title}.")

    reg.register(ActionSpec(
        "notify", "Show a desktop notification immediately, when the user asks for one. "
        "Never use it to report errors or results; say those in your reply.",
        {"type": "object", "properties": {
            "title": {"type": "string"}, "message": {"type": "string"},
        }, "required": ["title", "message"]},
        Risk.SAFE, notify, category="notifications", once_per_turn=True,
    ))

    def set_timer(minutes: float, label: str = "Time's up!") -> ActionResult:
        # No id in the result: handed one, the model re-called set_* with
        # "reminder_id" and, on the error, made a duplicate. list_reminders has ids.
        hub.schedule_in(label, "timer", float(minutes))
        return ActionResult(True, f"Timer set for {minutes:g} minute(s).")

    reg.register(ActionSpec(
        "set_timer", "Start a countdown timer that notifies when it elapses.",
        {"type": "object", "properties": {
            "minutes": {"type": "number", "description": "Minutes from now"},
            "label": {"type": "string", "description": "What the timer is for"},
        }, "required": ["minutes"]},
        Risk.LOW, set_timer, category="notifications",
    ))

    def set_reminder(text: str, in_minutes: float | None = None, at: str | None = None,
                     day: str | None = None, time: str | None = None) -> ActionResult:
        if at and not time and _CLOCK.match(at):
            # {"day": "tomorrow", "at": "09:00"}: the model's usual near miss.
            time, at = at, None
        if time:
            try:
                fire = _resolve_day_time(day, time, datetime.now())
            except ValueError as exc:
                return ActionResult(False, str(exc))
            hub.schedule(text, "reminder", fire)
            return ActionResult(True, f"Reminder set for {fire:%A %Y-%m-%d %H:%M}.")
        if at:
            try:
                fire = datetime.fromisoformat(at)
            except ValueError:
                return ActionResult(False, f"Couldn't understand the time '{at}'. Use ISO 8601.")
            now = datetime.now(fire.tzinfo)
            if fire <= now:
                # A model without the date writes last year's; refuse rather
                # than fire at once, and say what "now" is so it can retry.
                return ActionResult(False, f"{fire:%Y-%m-%d %H:%M} is in the past; it is now "
                                           f"{now:%A %Y-%m-%d %H:%M}. Give a future time.")
            hub.schedule(text, "reminder", fire)
            return ActionResult(True, f"Reminder set for {fire:%A %Y-%m-%d %H:%M}.")
        if in_minutes is not None:
            hub.schedule_in(text, "reminder", float(in_minutes))
            return ActionResult(True, f"Reminder set for {in_minutes:g} minute(s) from now.")
        return ActionResult(False, "Provide either in_minutes or an ISO time (at).")

    reg.register(ActionSpec(
        "set_reminder", "Set a reminder that notifies you later. For a clock time give time "
        "(and day, e.g. day='tomorrow', time='09:00'); for 'in 20 minutes' give in_minutes.",
        {"type": "object", "properties": {
            "text": {"type": "string", "description": "What to be reminded about"},
            "in_minutes": {"type": "number", "description": "Minutes from now"},
            "day": {"type": "string", "description": "today, tomorrow, or a weekday name (default: the next time that clock time comes round)"},
            "time": {"type": "string", "description": "Clock time, e.g. 09:00, 9am or 5:30pm"},
            "at": {"type": "string", "description": "Absolute local time, ISO 8601, e.g. 2026-11-20T09:00"},
        }, "required": ["text"]},
        Risk.LOW, set_reminder, category="notifications",
    ))

    def list_reminders() -> ActionResult:
        # Only what the user cares about: created_at is UTC and fire_at local,
        # and the model reported both as if they were the same clock.
        # "when" spelled out: given bare ISO times the model named the wrong weekday.
        pending = [{"id": r["id"], "kind": r["kind"], "text": r["text"],
                    "when": f"{datetime.fromisoformat(r['fire_at']):%A %d %B, %H:%M}"}
                   for r in hub.list_pending()]
        return ActionResult(True, f"{len(pending)} pending reminder(s).", {"reminders": pending})

    reg.register(ActionSpec(
        "list_reminders", "List pending timers and reminders.",
        {"type": "object", "properties": {}}, Risk.SAFE, list_reminders, category="notifications",
    ))

    def cancel_reminder(reminder_id: int | None = None) -> ActionResult:
        if reminder_id is None:
            # "Cancel that timer" means the one just set: the newest. (Refusing
            # made the model cancel every pending one by id instead. The agent
            # never re-runs an identical call, so this can't cascade.)
            pending = hub.list_pending()
            if not pending:
                return ActionResult(False, "No timers or reminders are pending.")
            newest = max(pending, key=lambda r: r["id"])
            ok = hub.cancel(int(newest["id"]))
            return ActionResult(ok, f"Cancelled the {newest['kind']} “{newest['text']}”. "
                                    "Nothing else needs cancelling.")
        ok = hub.cancel(int(reminder_id))
        return ActionResult(ok, "Cancelled the reminder." if ok else "No such reminder.")

    reg.register(ActionSpec(
        "cancel_reminder", "Cancel a pending timer or reminder by its id (ids come from "
        "list_reminders). Leave the id out to cancel the one set most recently.",
        {"type": "object", "properties": {"reminder_id": {"type": "integer"}}},
        Risk.LOW, cancel_reminder, category="notifications",
    ))


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_CLOCK = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)


def _resolve_day_time(day: str | None, time: str, now: datetime) -> datetime:
    """day='tomorrow', time='9am' -> a datetime. A 7B model told today's date
    in the prompt still wrote 2023 into ISO times; the user's own words it
    copies correctly, so the date arithmetic happens here."""
    m = _CLOCK.match(time)
    if not m:
        raise ValueError(f"Couldn't read the time '{time}'. Use e.g. 09:00 or 9am.")
    hour, minute, half = int(m[1]), int(m[2] or 0), (m[3] or "").lower()
    if half == "pm" and hour < 12:
        hour += 12
    elif half == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError(f"'{time}' isn't a valid time of day.")
    d = (day or "").strip().lower()
    base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if d == "tomorrow":
        return base + timedelta(days=1)
    if d in _WEEKDAYS:
        ahead = (_WEEKDAYS.index(d) - now.weekday()) % 7
        fire = base + timedelta(days=ahead)
        return fire if fire > now else fire + timedelta(days=7)
    if d not in ("", "today"):
        raise ValueError(f"Couldn't read the day '{day}'. Use today, tomorrow or a weekday name.")
    if d == "today" and base <= now:
        raise ValueError(f"{time} today has already passed; it is now {now:%H:%M}.")
    return base if base > now else base + timedelta(days=1)
