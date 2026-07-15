import pytest

from corvus.actions.registry import ActionResult, ActionSpec, Registry, Risk
from corvus.workflows.engine import WorkflowEngine, WorkflowError


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
