from corvus.actions.registry import ActionResult, ActionSpec, Registry, Risk
from corvus.llm.agent import run_agent_turn
from corvus.llm.base import Message, ToolCall, TurnResult
from tests.conftest import FakeProvider


def build_registry(calls: list):
    reg = Registry()

    def safe_handler(**kw):
        calls.append(("safe", kw))
        return ActionResult(True, "did safe thing")

    def risky_handler(**kw):
        calls.append(("risky", kw))
        return ActionResult(True, "did risky thing")

    def medium_handler(**kw):
        calls.append(("medium", kw))
        return ActionResult(True, "did medium thing")

    reg.register(ActionSpec("safe_act", "a safe action", {"type": "object", "properties": {}},
                            Risk.SAFE, safe_handler, category="test"))
    reg.register(ActionSpec("risky_act", "a risky action", {"type": "object", "properties": {}},
                            Risk.HIGH, risky_handler,
                            confirm_prompt=lambda a: f"Do risky thing to {a.get('target')}?",
                            category="test"))
    reg.register(ActionSpec("medium_act", "a medium action", {"type": "object", "properties": {}},
                            Risk.MEDIUM, medium_handler,
                            confirm_prompt=lambda a: f"Do medium thing to {a.get('target')}?",
                            category="test"))
    return reg


async def always_yes(name, prompt, args):
    return True


async def always_no(name, prompt, args):
    return False


async def test_safe_action_runs_without_confirmation():
    calls = []
    reg = build_registry(calls)
    provider = FakeProvider(
        chunks=["Done."],
        tool_script=[
            TurnResult("", [ToolCall("safe_act", {"x": 1})]),
            TurnResult("All set.", []),
        ],
    )
    events = []
    outcome = await run_agent_turn(
        provider, "m", [Message("user", "do it")], reg, always_no, emit=events.append,
    )
    assert ("safe", {"x": 1}) in calls  # ran despite confirmer=always_no
    assert outcome.text == "All set."
    assert any(e["type"] == "action_result" and e["ok"] for e in events)


async def test_risky_action_requires_and_respects_approval():
    calls = []
    reg = build_registry(calls)
    provider = FakeProvider(tool_script=[
        TurnResult("", [ToolCall("risky_act", {"target": "disk"})]),
        TurnResult("Finished.", []),
    ])
    events = []
    outcome = await run_agent_turn(
        provider, "m", [Message("user", "wipe")], reg, always_yes, emit=events.append,
    )
    assert ("risky", {"target": "disk"}) in calls
    confirming = [e for e in events if e["type"] == "action_confirming"]
    assert confirming and "disk" in confirming[0]["prompt"]
    assert outcome.text == "Finished."


async def test_declined_risky_action_does_not_run():
    calls = []
    reg = build_registry(calls)
    provider = FakeProvider(tool_script=[
        TurnResult("", [ToolCall("risky_act", {"target": "disk"})]),
        TurnResult("Okay, cancelled.", []),
    ])
    events = []
    outcome = await run_agent_turn(
        provider, "m", [Message("user", "wipe")], reg, always_no, emit=events.append,
    )
    assert ("risky", {"target": "disk"}) not in calls
    assert any(e.get("declined") for e in events if e["type"] == "action_result")
    assert outcome.text == "Okay, cancelled."


async def test_plain_chat_no_tools():
    reg = build_registry([])
    provider = FakeProvider(chunks=["Just chatting."], tool_script=[TurnResult("Just chatting.", [])])
    outcome = await run_agent_turn(provider, "m", [Message("user", "hi")], reg, always_yes)
    assert outcome.text == "Just chatting."
    assert outcome.actions_run == []


async def test_confirmation_event_carries_the_actual_risk_tier():
    # A MEDIUM action must not be announced to the user as HIGH.
    reg = build_registry([])
    provider = FakeProvider(tool_script=[
        TurnResult("", [ToolCall("medium_act", {"target": "notes"})]),
        TurnResult("Done.", []),
    ])
    events = []
    await run_agent_turn(
        provider, "m", [Message("user", "go")], reg, always_yes, emit=events.append,
    )
    confirming = [e for e in events if e["type"] == "action_confirming"]
    assert confirming and confirming[0]["risk"] == "medium"


async def test_text_streams_as_deltas_including_tool_preamble():
    reg = build_registry([])
    provider = FakeProvider(tool_script=[
        TurnResult("Let me check.", [ToolCall("safe_act", {})]),
        TurnResult("All done.", []),
    ])
    events = []
    outcome = await run_agent_turn(
        provider, "m", [Message("user", "go")], reg, always_yes, emit=events.append,
    )
    deltas = "".join(e["content"] for e in events if e["type"] == "delta")
    assert deltas == "Let me check.\n\nAll done."
    # What streamed is exactly what gets persisted, so a reloaded conversation
    # looks like what was on screen.
    assert outcome.text == deltas


async def test_stopping_mid_stream_keeps_the_text_already_seen():
    reg = build_registry([])
    provider = FakeProvider(chunks=["Part one.", " Part two."])
    stopped = False
    events = []

    def emit(event):
        nonlocal stopped
        events.append(event)
        stopped = True  # user hits stop right after the first delta

    outcome = await run_agent_turn(
        provider, "m", [Message("user", "go")], reg, always_yes,
        emit=emit, should_stop=lambda: stopped,
    )
    assert outcome.text == "Part one."  # partial output survives, as in M4


async def test_stopping_prevents_tool_execution():
    calls = []
    reg = build_registry(calls)
    provider = FakeProvider(tool_script=[
        TurnResult("", [ToolCall("safe_act", {})]),
        TurnResult("Should never get here.", []),
    ])
    outcome = await run_agent_turn(
        provider, "m", [Message("user", "go")], reg, always_yes, should_stop=lambda: True,
    )
    assert calls == []
    assert outcome.text == ""


async def test_action_logging_callback():
    calls = []
    reg = build_registry(calls)
    logged = []
    provider = FakeProvider(tool_script=[
        TurnResult("", [ToolCall("safe_act", {})]),
        TurnResult("done", []),
    ])
    await run_agent_turn(
        provider, "m", [Message("user", "go")], reg, always_yes,
        log_action=lambda n, a, r, o: logged.append((n, o)),
    )
    assert ("safe_act", "executed") in logged
