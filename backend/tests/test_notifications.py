import asyncio
from datetime import datetime, timedelta

import pytest

from corvus.notifications.hub import NotificationHub


@pytest.fixture
async def hub(repo):
    h = NotificationHub(repo)
    await h.start()
    yield h
    await h.stop()


async def test_immediate_notify_reaches_subscriber(hub):
    q = hub.subscribe()
    hub.notify("Hello", "world")
    event = await asyncio.wait_for(q.get(), timeout=1)
    assert event == {"type": "notify", "title": "Hello", "message": "world", "level": "info"}


async def test_timer_fires_and_is_marked(hub, repo):
    q = hub.subscribe()
    r = hub.schedule_in("tea ready", "timer", minutes=0.001)  # ~60ms
    event = await asyncio.wait_for(q.get(), timeout=2)
    assert event["type"] == "reminder"
    assert event["kind"] == "timer"
    assert "tea ready" in event["message"]
    # Marked fired, so it won't refire on restart.
    assert repo.pending_reminders() == []
    assert r["id"] is not None


async def test_reminder_at_absolute_time(hub):
    q = hub.subscribe()
    when = datetime.now() + timedelta(seconds=0.06)
    hub.schedule("call mom", "reminder", when)
    event = await asyncio.wait_for(q.get(), timeout=2)
    assert event["message"] == "call mom"


async def test_cancel_prevents_fire(hub, repo):
    q = hub.subscribe()
    r = hub.schedule_in("nope", "reminder", minutes=0.05)
    assert hub.cancel(r["id"]) is True
    assert repo.pending_reminders() == []
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.3)


async def test_pending_reminders_reschedule_on_restart(repo):
    # Persist a future reminder without firing, then a fresh hub reschedules it.
    fire = (datetime.now() + timedelta(seconds=0.06)).isoformat(timespec="seconds")
    repo.add_reminder("survive restart", "reminder", fire)

    hub = NotificationHub(repo)
    q = hub.subscribe()
    await hub.start()
    assert len(hub.list_pending()) == 1
    event = await asyncio.wait_for(q.get(), timeout=2)
    assert event["message"] == "survive restart"
    await hub.stop()


async def test_overdue_reminder_fires_immediately(repo):
    past = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    repo.add_reminder("missed while off", "reminder", past)
    hub = NotificationHub(repo)
    q = hub.subscribe()
    await hub.start()
    event = await asyncio.wait_for(q.get(), timeout=1)
    assert event["message"] == "missed while off"
    await hub.stop()


async def test_timezone_aware_time_is_accepted(hub):
    import asyncio
    from datetime import datetime, timedelta, timezone

    q = hub.subscribe()
    hub.schedule("utc", "reminder", datetime.now(timezone.utc) + timedelta(milliseconds=50))
    event = await asyncio.wait_for(q.get(), 2)
    assert event["message"] == "utc"


async def test_reminder_waits_for_a_subscriber(repo):
    import asyncio

    repo.add_reminder("missed", "reminder", "2000-01-01T00:00:00")
    hub = NotificationHub(repo)
    await hub.start()
    await asyncio.sleep(0.05)
    assert len(repo.pending_reminders()) == 1  # not silently dropped
    q = hub.subscribe()
    assert (await asyncio.wait_for(q.get(), 1))["message"] == "missed"
    assert repo.pending_reminders() == []
    await hub.stop()


def test_cancel_without_id_cancels_only_the_newest():
    from corvus.actions.notify_handlers import register_notification_actions
    from corvus.actions.registry import Registry

    class Hub:
        pending = [{"id": 3, "kind": "reminder", "text": "a", "fire_at": "x"},
                   {"id": 5, "kind": "timer", "text": "b", "fire_at": "y"}]
        cancelled = []
        def list_pending(self): return self.pending
        def cancel(self, i): self.cancelled.append(i); return True

    reg, hub = Registry(), Hub()
    register_notification_actions(reg, hub)
    reg.get("cancel_reminder").handler()
    assert hub.cancelled == [5]


def test_day_and_time_resolve_without_the_model_doing_dates():
    from datetime import datetime

    from corvus.actions.notify_handlers import _resolve_day_time
    now = datetime(2026, 11, 19, 2, 53)  # a Thursday
    assert _resolve_day_time("tomorrow", "9am", now) == datetime(2026, 11, 20, 9, 0)
    assert _resolve_day_time(None, "09:00", now) == datetime(2026, 11, 19, 9, 0)
    assert _resolve_day_time(None, "1:30", now) == datetime(2026, 11, 20, 1, 30)
    assert _resolve_day_time("monday", "5:30pm", now) == datetime(2026, 11, 23, 17, 30)
    assert _resolve_day_time("Thursday", "1am", now) == datetime(2026, 11, 26, 1, 0)
    for day, t in (("today", "1am"), ("someday", "9am"), (None, "25:00"), (None, "soon")):
        try:
            _resolve_day_time(day, t, now)
        except ValueError:
            continue
        raise AssertionError((day, t))


def test_clock_time_in_at_is_read_as_time():
    # Live: the model sent {"day": "tomorrow", "at": "09:00"} twice.
    from corvus.actions.notify_handlers import register_notification_actions
    from corvus.actions.registry import Registry

    class Hub:
        scheduled = []
        def schedule(self, text, kind, fire): self.scheduled.append(fire); return {"id": 1}

    reg, hub = Registry(), Hub()
    register_notification_actions(reg, hub)
    res = reg.get("set_reminder").handler(text="Call mom", day="tomorrow", at="09:00")
    assert res.ok and hub.scheduled[0].hour == 9
