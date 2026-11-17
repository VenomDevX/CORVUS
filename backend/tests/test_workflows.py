from datetime import datetime, timedelta

import pytest

import corvus.workflows.engine as wf_engine
from corvus.actions.registry import ActionResult, ActionSpec, Registry, Risk
from corvus.workflows.engine import WorkflowEngine, WorkflowError, validate_trigger


def build_registry(calls: list) -> Registry:
    reg = Registry()

    def opener(app):
        calls.append(app)
        return ActionResult(True, f"Opening {app}")

    reg.register(ActionSpec("open_app", "open", {"type": "object", "properties": {
        "app": {"type": "string"}}, "required": ["app"]}, Risk.LOW, opener, category="apps"))
    reg.register(ActionSpec("system_status", "status", {"type": "object", "properties": {}},
                            Risk.SAFE, lambda: ActionResult(True, "ok"), category="monitoring"))
    reg.register(ActionSpec("delete_item", "del", {"type": "object", "properties": {
        "path": {"type": "string"}}}, Risk.HIGH,
        lambda path: ActionResult(True, "deleted"),
        confirm_prompt=lambda a: "delete?", category="files"))
    return reg


@pytest.fixture
def engine(repo):
    return WorkflowEngine(repo, build_registry([]))


def test_create_and_list(repo):
    calls = []
    engine = WorkflowEngine(repo, build_registry(calls))
    wf = engine.create("morning", [
        {"action": "open_app", "arguments": {"app": "chrome"}},
        {"action": "open_app", "arguments": {"app": "spotify"}},
    ])
    assert wf["name"] == "morning"
    assert len(wf["steps"]) == 2
    assert [w["name"] for w in engine.list()] == ["morning"]


def test_high_risk_action_rejected_in_workflow(engine):
    with pytest.raises(WorkflowError, match="high-risk"):
        engine.create("danger", [{"action": "delete_item", "arguments": {"path": "x"}}])


def test_unknown_action_rejected(engine):
    with pytest.raises(WorkflowError, match="Unknown action"):
        engine.create("bad", [{"action": "ghost"}])


def test_empty_workflow_rejected(engine):
    with pytest.raises(WorkflowError, match="at least one step"):
        engine.create("empty", [])


async def test_run_executes_steps_in_order(repo):
    calls = []
    engine = WorkflowEngine(repo, build_registry(calls))
    engine.create("morning", [
        {"action": "open_app", "arguments": {"app": "chrome"}},
        {"action": "system_status", "arguments": {}},
        {"action": "open_app", "arguments": {"app": "spotify"}},
    ])
    results = await engine.run("morning")
    assert [r.action for r in results] == ["open_app", "system_status", "open_app"]
    assert all(r.ok for r in results)
    assert calls == ["chrome", "spotify"]  # opener ran in order


async def test_run_missing_workflow(engine):
    with pytest.raises(WorkflowError, match="No workflow"):
        await engine.run("nope")


def test_voice_trigger_matching(repo):
    engine = WorkflowEngine(repo, build_registry([]))
    engine.create("morning", [{"action": "system_status"}], trigger_type="voice",
                  trigger_config={"phrase": "start my day"})
    assert engine.match_voice("Corvus, start my day please") == "morning"
    assert engine.match_voice("what's the weather") is None


def test_update_existing_workflow(repo):
    engine = WorkflowEngine(repo, build_registry([]))
    engine.create("wf", [{"action": "system_status"}])
    engine.create("wf", [{"action": "open_app", "arguments": {"app": "chrome"}},
                         {"action": "system_status"}])
    workflows = engine.list()
    assert len(workflows) == 1
    assert len(workflows[0]["steps"]) == 2


# -- triggers -----------------------------------------------------------------

MONDAY_9 = datetime(2026, 11, 16, 9, 0)  # a Monday


def test_validate_trigger(tmp_path):
    assert validate_trigger("schedule", {"at": "8:05", "days": [4, 0, 0]}) == {"at": "08:05", "days": [0, 4]}
    assert validate_trigger("interval", {"every_minutes": 15}) == {"every_minutes": 15}
    assert validate_trigger("folder", {"path": str(tmp_path)}) == {"path": str(tmp_path.resolve())}
    assert validate_trigger("startup", {"junk": 1}) == {}
    for kind, config in [
        ("schedule", {"at": "25:00"}), ("schedule", {"at": "08:00", "days": [7]}),
        ("schedule", {"at": "08:00", "days": []}), ("interval", {"every_minutes": 0}),
        ("interval", {"every_minutes": True}), ("idle", {}), ("voice", {"phrase": "  "}),
        ("folder", {"path": str(tmp_path / "missing")}), ("folder", {"path": "relative/dir"}),
        ("hotkey", {}),
    ]:
        with pytest.raises(WorkflowError):
            validate_trigger(kind, config)


def test_schedule_respects_weekdays(engine):
    cfg = {"at": "09:00", "days": [1]}  # Tuesdays only
    assert not engine._due("wf", "schedule", cfg, MONDAY_9, False, set())
    assert engine._due("wf", "schedule", cfg, MONDAY_9 + timedelta(days=1), False, set())


def test_interval_starts_clock_then_fires(engine):
    cfg = {"every_minutes": 10}
    assert not engine._due("wf", "interval", cfg, MONDAY_9, True, set())
    assert not engine._due("wf", "interval", cfg, MONDAY_9 + timedelta(minutes=9), False, set())
    assert engine._due("wf", "interval", cfg, MONDAY_9 + timedelta(minutes=10), False, set())
    assert not engine._due("wf", "interval", cfg, MONDAY_9 + timedelta(minutes=11), False, set())


def test_idle_fires_once_per_idle_stretch(engine, monkeypatch):
    idle = iter([60, 301, 400, 5, 302])
    monkeypatch.setattr(wf_engine, "idle_seconds", lambda: next(idle))
    fired = [engine._due("wf", "idle", {"minutes": 5}, MONDAY_9, False, set()) for _ in range(5)]
    assert fired == [False, True, False, False, True]  # re-arms after input at 5s


def test_folder_fires_on_new_finished_file(engine, tmp_path):
    (tmp_path / "old.txt").write_text("x")
    cfg = {"path": str(tmp_path)}
    due = lambda: engine._due("wf", "folder", cfg, MONDAY_9, False, set())
    assert not due()  # baseline: existing files never fire
    (tmp_path / "movie.mp4.crdownload").write_text("x")
    assert not due()  # still downloading
    (tmp_path / "movie.mp4").write_text("x")
    assert due()
    assert not due()  # nothing new since


async def test_startup_trigger_skipped_after_crash(repo):
    import asyncio

    for run_startup, expected in [(True, ["chrome"]), (False, [])]:
        calls = []
        engine = WorkflowEngine(repo, build_registry(calls))
        engine.create("launch", [{"action": "open_app", "arguments": {"app": "chrome"}}], "startup")
        await engine.start(run_startup=run_startup)
        await asyncio.sleep(0.05)
        await engine.stop()
        assert calls == expected


async def test_same_workflow_never_overlaps(repo):
    import asyncio

    gate = asyncio.Event()
    calls = []
    reg = Registry()

    async def slow():
        calls.append(1)
        await gate.wait()
        return ActionResult(True, "ok")

    reg.register(ActionSpec("slow", "slow", {"type": "object", "properties": {}}, Risk.SAFE, slow,
                            category="monitoring"))
    engine = WorkflowEngine(repo, reg)
    engine.create("wf", [{"action": "slow"}], "interval", {"every_minutes": 1})
    engine._spawn("wf")
    await asyncio.sleep(0.01)
    engine._spawn("wf")  # still running: skipped
    gate.set()
    await asyncio.sleep(0.01)
    assert calls == [1]


def test_old_database_migrates_trigger_check(tmp_path):
    import sqlite3

    from corvus.memory.db import connect

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, steps TEXT NOT NULL,
            trigger_type TEXT NOT NULL DEFAULT 'manual'
                CHECK (trigger_type IN ('manual', 'schedule', 'voice')),
            trigger_config TEXT NOT NULL DEFAULT '{}', enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')));
        INSERT INTO workflows (name, steps, trigger_type) VALUES ('kept', '[]', 'voice');
    """)
    old.close()
    conn = connect(path)
    conn.execute("INSERT INTO workflows (name, steps, trigger_type) VALUES ('new', '[]', 'folder')")
    assert [r["name"] for r in conn.execute("SELECT name FROM workflows ORDER BY id")] == ["kept", "new"]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO workflows (name, steps, trigger_type) VALUES ('bad', '[]', 'hotkey')")
    conn.close()


async def test_create_workflow_action_maps_trigger_args(repo, tmp_path):
    from corvus.actions.workflow_handlers import (
        _describe_create,
        register_workflow_actions,
    )

    reg = build_registry([])
    engine = WorkflowEngine(repo, reg)
    register_workflow_actions(reg, engine)
    args = {"name": "tidy", "steps": [{"action": "system_status"}], "trigger": "folder",
            "folder": str(tmp_path)}
    assert "without asking" in _describe_create(args)
    assert (await reg.execute("create_workflow", args)).ok
    assert engine.list()[0]["trigger_config"] == {"path": str(tmp_path.resolve())}
    bad = await reg.execute("create_workflow", {**args, "name": "x", "trigger": "idle"})
    assert not bad.ok and "Idle minutes" in bad.message
    extra = await reg.execute("create_workflow", {**args, "name": "y", "surprise": 1})
    assert not extra.ok
