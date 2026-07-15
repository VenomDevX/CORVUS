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
