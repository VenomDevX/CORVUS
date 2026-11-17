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


# -- loop edge cases (testing plan item 3) ------------------------------------------

async def test_unknown_tool_call_reports_and_continues():
    provider = FakeProvider(tool_script=[
        TurnResult("Trying.", [ToolCall("no_such_action", {})]),
        TurnResult("Sorry, I can't do that.", []),
    ])
    events = []
    outcome = await run_agent_turn(provider, "m", [Message("user", "do it")],
                                   build_registry([]), always_yes, emit=events.append,
                                   include_tools=True)
    assert "can't do that" in outcome.text
    tool_msgs = [m for m in provider.calls[-1] if m.role == "tool"]
    assert "Unknown action" in tool_msgs[0].content


async def test_malformed_empty_turn_never_leaves_silence():
    from corvus.llm.agent import EMPTY_REPLY

    provider = FakeProvider(chunks=[], tool_script=[TurnResult("", [])])
    outcome = await run_agent_turn(provider, "m", [Message("user", "do it")],
                                   build_registry([]), always_yes, include_tools=True)
    assert outcome.text == EMPTY_REPLY


async def test_silent_tool_loop_is_broken():
    calls = []
    # Two silent tool rounds, then the forced summary turn streams `chunks`.
    provider = FakeProvider(chunks=["Here's a summary."], tool_script=[
        TurnResult("", [ToolCall("safe_act", {})]) for _ in range(2)
    ])
    outcome = await run_agent_turn(provider, "m", [Message("user", "check")],
                                   build_registry(calls), always_yes, include_tools=True)
    assert len(calls) == 1  # second silent round triggers the breaker
    assert outcome.text == "Here's a summary."


async def test_include_tools_false_sends_no_tool_schemas():
    seen = []

    class Spy(FakeProvider):
        async def stream_chat_with_tools(self, messages, model, tools):
            seen.append(tools)
            async for d in super().stream_chat_with_tools(messages, model, tools):
                yield d

    await run_agent_turn(Spy(), "m", [Message("user", "open chrome")], build_registry([]),
                         always_yes, include_tools=False)
    assert seen == [[]]


async def test_bad_arguments_fail_before_confirmation():
    reg = Registry()
    reg.register(ActionSpec("typed", "t", {"type": "object", "properties": {
        "n": {"type": "integer"}}, "required": ["n"]}, Risk.HIGH, lambda n: "ran",
        confirm_prompt=lambda a: "Run?"))
    provider = FakeProvider(tool_script=[TurnResult("Ok.", [ToolCall("typed", {"n": "x"})]),
                                         TurnResult("Fixed.", [])])
    events = []
    await run_agent_turn(provider, "m", [Message("user", "go")], reg, always_yes,
                         emit=events.append, include_tools=True)
    assert not any(e["type"] == "action_confirming" for e in events)
    assert any(e["type"] == "action_result" and not e["ok"] for e in events)


import pytest  # noqa: E402

from corvus.llm.agent import _is_conversational  # noqa: E402


@pytest.mark.parametrize("text,conversational", [
    ("hi", True),
    ("what is an array", True),
    ("write a python function to reverse a list", True),
    ("tell me a joke", True),
    ("write me an email and copy it to the clipboard", False),
    ("what is my battery level", False),
    ("how do I free up space in my downloads folder", False),
    ("open chrome", False),
    ("remind me in 10 minutes to stretch", False),
    ("explain what's on my screen", False),
])
async def test_conversational_classifier(text, conversational):
    assert await _is_conversational(text) is conversational
