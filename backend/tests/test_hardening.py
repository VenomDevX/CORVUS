"""Regression tests for the agent-safety fixes. Nothing here launches a real
process: every case is rejected before Windows is asked to open anything."""

import pytest

from corvus.actions import win
from corvus.actions.registry import ActionResult, ActionSpec, Registry, Risk, build_default_registry
from corvus.workflows.engine import WorkflowEngine, WorkflowError


@pytest.mark.parametrize("name", [
    "x&calc", "a|b", r"C:\Users\Public\evil.exe", r"\\server\share\x.exe",
    "ms-msdt:/id", "search-ms:query=x", r"..\..\x", "%ComSpec%", "*", "a?", "",
])
def test_free_form_app_names_rejected(name):
    with pytest.raises(ValueError):
        win.launch_app(name)


def test_close_app_wildcard_rejected():
    with pytest.raises(ValueError):
        win.close_app("*")


async def test_open_folder_refuses_files(tmp_path):
    exe = tmp_path / "evil.exe"
    exe.write_text("x")
    result = await build_default_registry().execute("open_folder", {"folder": str(exe)})
    assert not result.ok and "isn't a folder" in result.message


async def test_search_files_stays_in_root():
    result = await build_default_registry().execute(
        "search_files", {"query": "*/../../../../Windows/win.ini"})
    assert not result.ok


def _registry():
    reg = Registry()
    reg.register(ActionSpec("open_app", "o", {"type": "object", "properties": {}}, Risk.LOW,
                            lambda **_: ActionResult(True, "ok")))
    reg.register(ActionSpec("copy_item", "c", {"type": "object", "properties": {}}, Risk.MEDIUM,
                            lambda **_: ActionResult(True, "copied"), confirm_prompt=lambda a: "copy?"))
    reg.register(ActionSpec("run_workflow", "r", {"type": "object", "properties": {}}, Risk.LOW,
                            lambda **_: ActionResult(True, "ran")))
    return reg


def test_workflows_reject_medium_and_recursion(repo):
    engine = WorkflowEngine(repo, _registry())
    with pytest.raises(WorkflowError):
        engine.create("persist", [{"action": "copy_item", "arguments": {}}])
    with pytest.raises(WorkflowError):
        engine.create("loop", [{"action": "run_workflow", "arguments": {"name": "loop"}}])


async def test_workflow_rechecks_risk_at_run_time(repo):
    # A row saved before the rules tightened (or whose action got riskier) won't run.
    repo.create_workflow("old", [{"action": "copy_item", "arguments": {}}], "manual", None)
    with pytest.raises(WorkflowError):
        await WorkflowEngine(repo, _registry()).run("old")


def test_voice_match_needs_whole_phrase(repo):
    engine = WorkflowEngine(repo, _registry())
    engine.create("morning", [{"action": "open_app", "arguments": {}}], "voice",
                  {"phrase": "start your day"})
    assert engine.match_voice("Okay, start your day!") == "morning"
    for heard in ("you", ".", "", "start", "start your daydream"):
        assert engine.match_voice(heard) is None, heard


def test_plugin_actions_floor_at_medium():
    from corvus.plugins.sdk import PluginContext

    reg = Registry()
    ctx = PluginContext.__new__(PluginContext)
    ctx._manifest = type("M", (), {"id": "demo"})()
    ctx._registry, ctx.registered_actions = reg, []
    ctx.action("wipe", "d", {"type": "object", "properties": {}}, lambda: None, risk=Risk.SAFE)
    spec = reg.get("demo.wipe")
    assert spec.risk == Risk.MEDIUM and spec.requires_confirmation
    assert "demo" in spec.confirm_prompt({})


def test_bare_json_tool_call_is_recovered():
    # Formerly the root-level scratch scripts test.py / test_extract.py.
    from corvus.llm.ollama import _extract_text_tool_calls, _is_any_tool_call

    content = '{"name": "system_status", "arguments": {}}'
    calls = _extract_text_tool_calls(content, {"system_status"})
    assert [c.name for c in calls] == ["system_status"]
    assert _is_any_tool_call(content)
