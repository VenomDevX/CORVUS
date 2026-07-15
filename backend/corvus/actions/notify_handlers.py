"""Notification, timer, and reminder actions (Milestone 8).

Registered only when a notification hub is available. Setting a reminder/timer
is low-risk (easily cancelled and clearly surfaced), so these don't gate on
confirmation.
"""

from datetime import datetime

from .registry import ActionResult, ActionSpec, Registry, Risk


def register_notification_actions(reg: Registry, hub) -> None:
    def notify(title: str, message: str) -> ActionResult:
        hub.notify(title, message)
        return ActionResult(True, f"Sent a notification: {title}.")

    reg.register(ActionSpec(
        "notify", "Show a desktop notification immediately.",
        {"type": "object", "properties": {
            "title": {"type": "string"}, "message": {"type": "string"},
        }, "required": ["title", "message"]},
        Risk.SAFE, notify, category="notifications",
    ))

    def set_timer(minutes: float, label: str = "Time's up!") -> ActionResult:
        r = hub.schedule_in(label, "timer", float(minutes))
        return ActionResult(True, f"Timer set for {minutes:g} minute(s).", {"id": r["id"]})

    reg.register(ActionSpec(
        "set_timer", "Start a countdown timer that notifies when it elapses.",
        {"type": "object", "properties": {
            "minutes": {"type": "number", "description": "Minutes from now"},
            "label": {"type": "string", "description": "What the timer is for"},
        }, "required": ["minutes"]},
        Risk.LOW, set_timer, category="notifications",
    ))

    def set_reminder(text: str, in_minutes: float | None = None, at: str | None = None) -> ActionResult:
        if at:
            try:
                fire = datetime.fromisoformat(at)
            except ValueError:
                return ActionResult(False, f"Couldn't understand the time '{at}'. Use ISO 8601.")
            r = hub.schedule(text, "reminder", fire)
            return ActionResult(True, f"Reminder set for {fire:%Y-%m-%d %H:%M}.", {"id": r["id"]})
        if in_minutes is not None:
            r = hub.schedule_in(text, "reminder", float(in_minutes))
            return ActionResult(True, f"Reminder set for {in_minutes:g} minute(s) from now.", {"id": r["id"]})
        return ActionResult(False, "Provide either in_minutes or an ISO time (at).")

    reg.register(ActionSpec(
        "set_reminder", "Set a reminder that notifies you later. Give either in_minutes or an ISO "
        "datetime in 'at'.",
        {"type": "object", "properties": {
            "text": {"type": "string", "description": "What to be reminded about"},
            "in_minutes": {"type": "number", "description": "Minutes from now"},
            "at": {"type": "string", "description": "Absolute time, ISO 8601"},
        }, "required": ["text"]},
        Risk.LOW, set_reminder, category="notifications",
    ))

    def list_reminders() -> ActionResult:
        pending = hub.list_pending()
        return ActionResult(True, f"{len(pending)} pending reminder(s).", {"reminders": pending})

    reg.register(ActionSpec(
        "list_reminders", "List pending timers and reminders.",
        {"type": "object", "properties": {}}, Risk.SAFE, list_reminders, category="notifications",
    ))

    def cancel_reminder(reminder_id: int) -> ActionResult:
        ok = hub.cancel(int(reminder_id))
        return ActionResult(ok, "Cancelled the reminder." if ok else "No such reminder.")

    reg.register(ActionSpec(
        "cancel_reminder", "Cancel a pending timer or reminder by its id.",
        {"type": "object", "properties": {"reminder_id": {"type": "integer"}},
         "required": ["reminder_id"]},
        Risk.LOW, cancel_reminder, category="notifications",
    ))
