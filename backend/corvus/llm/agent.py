"""The Corvus agent loop.

Given a conversation, the model may request actions from the registry. This
loop runs those actions - pausing for explicit user confirmation on anything
the action's risk tier requires - and feeds results back until the model
produces a final text answer. Text streams to the UI as it arrives, and the
loop emits structured events so the UI can render action chips, confirmation
cards, and results.

Confirmation is delegated to an injected async `confirm` callback: the WS
layer prompts the user and returns their decision. Providers that don't
support tool calls simply never yield tool_calls, so this degrades to plain
chat.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from ..actions.registry import ActionResult, Registry
from ..untrusted import UNTRUSTED_RULE
from .base import LLMProvider, Message, ToolCall, TurnResult

log = structlog.get_logger("corvus")

MAX_TOOL_ROUNDS = 6

# event: {"type": "delta"|"action_proposed"|"action_confirming"|"action_result", ...}
EventSink = Callable[[dict[str, Any]], Awaitable[None] | None]
# confirm(action_name, prompt, args) -> bool
Confirmer = Callable[[str, str, dict[str, Any]], Awaitable[bool]]
# should_stop() -> True once the user has asked to stop generating
StopCheck = Callable[[], bool]


@dataclass
class AgentOutcome:
    text: str
    actions_run: list[dict[str, Any]]


async def _emit(sink: EventSink | None, event: dict[str, Any]) -> None:
    if sink is None:
        return
    result = sink(event)
    if result is not None:
        await result


async def _stream_turn(
    provider: LLMProvider,
    model: str,
    convo: list[Message],
    tools: list[dict[str, Any]],
    emit: EventSink | None,
    should_stop: StopCheck | None,
) -> TurnResult:
    """Stream one model turn, emitting text deltas as they arrive."""
    parts: list[str] = []
    calls: list[ToolCall] = []
    async for delta in provider.stream_chat_with_tools(convo, model, tools):
        if should_stop and should_stop():
            break
        if delta.tool_calls:
            calls.extend(delta.tool_calls)
        if delta.content:
            parts.append(delta.content)
            await _emit(emit, {"type": "delta", "content": delta.content})
    return TurnResult(content="".join(parts), tool_calls=calls)


async def run_agent_turn(
    provider: LLMProvider,
    model: str,
    messages: list[Message],
    registry: Registry,
    confirm: Confirmer,
    emit: EventSink | None = None,
    log_action: Callable[[str, dict, ActionResult, str], None] | None = None,
    should_stop: StopCheck | None = None,
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> AgentOutcome:
    """Run one user turn to completion, executing any requested actions."""
    tools = registry.tool_schemas()
    convo = list(messages)
    actions_run: list[dict[str, Any]] = []
    # Exactly the text the user saw stream by, across every round: a tool
    # preamble ("Let me check…") plus the answer that follows read as one
    # message. Persisting this verbatim keeps a reloaded conversation
    # identical to what was on screen live.
    spoken: list[str] = []

    def outcome() -> AgentOutcome:
        return AgentOutcome(text="".join(spoken).strip(), actions_run=actions_run)

    for _round in range(max_rounds):
        turn = await _stream_turn(provider, model, convo, tools, emit, should_stop)
        if turn.content:
            spoken.append(turn.content)

        if not turn.tool_calls or (should_stop and should_stop()):
            return outcome()

        # More is coming after the actions run, so break the preamble off it.
        if turn.content.strip():
            await _emit(emit, {"type": "delta", "content": "\n\n"})
            spoken.append("\n\n")

        # Record the assistant's tool request in the running history.
        convo.append(Message("assistant", turn.content, tool_calls=turn.tool_calls))

        for call in turn.tool_calls:
            result = await _run_one(call, registry, confirm, emit, log_action)
            actions_run.append({"name": call.name, "arguments": call.arguments, "ok": result.ok, "message": result.message})
            convo.append(Message("tool", json.dumps({"ok": result.ok, "message": result.message, **result.data}), tool_name=call.name))

        if should_stop and should_stop():
            return outcome()

    # Safety valve: ask for a plain summary after too many rounds.
    convo.append(Message("system", "Stop calling tools now and give the user a short summary of what you did."))
    final = await _stream_turn(provider, model, convo, [], emit, should_stop)
    if final.content:
        spoken.append(final.content)
    return outcome()


async def _run_one(
    call: ToolCall,
    registry: Registry,
    confirm: Confirmer,
    emit: EventSink | None,
    log_action: Callable[[str, dict, ActionResult, str], None] | None,
) -> ActionResult:
    spec = registry.get(call.name)
    if spec is None:
        return ActionResult(False, f"Unknown action: {call.name}")

    await _emit(emit, {
        "type": "action_proposed",
        "name": call.name,
        "arguments": call.arguments,
        "risk": spec.risk.value,
        "category": spec.category,
    })

    outcome = "executed"
    if spec.requires_confirmation:
        prompt = spec.describe_confirmation(call.arguments)
        await _emit(emit, {"type": "action_confirming", "name": call.name,
                           "prompt": prompt, "risk": spec.risk.value})
        approved = await confirm(call.name, prompt, call.arguments)
        if not approved:
            log.info("action_declined", action=call.name)
            result = ActionResult(False, "Cancelled - you didn't approve this action.")
            await _emit(emit, {"type": "action_result", "name": call.name, "ok": False,
                               "message": result.message, "declined": True})
            if log_action:
                log_action(call.name, call.arguments, result, "declined")
            return result

    result = await registry.execute(call.name, call.arguments)
    log.info("action_executed", action=call.name, ok=result.ok)
    await _emit(emit, {"type": "action_result", "name": call.name, "ok": result.ok,
                       "message": result.message, "data": result.data})
    if log_action:
        log_action(call.name, call.arguments, result, outcome if result.ok else "failed")
    return result


def agent_system_prompt(registry: Registry) -> str:
    lines = [
        "You can control this Windows PC through tools. When the user asks you to do "
        "something an action below covers, you MUST actually invoke it - do not just "
        "say you are doing it. Use the native tool-calling mechanism if available. "
        "ONLY if your platform completely lacks native tool support, you may emit the call "
        'as a JSON object on its own line and nothing else after it: '
        '{"name": "<action>", "arguments": {<params>}}. A sentence of '
        'narration first is fine ("Opening Chrome…"), but it must be followed by the '
        "actual call. Never describe how the user could do it themselves.",
        "",
        "For anything destructive or high-impact, the system asks the user to confirm - "
        "you don't need to ask separately, just make the call. If a tool result reports "
        "a failure, tell the user plainly. Only use actions that exist below; for "
        "anything else, just answer normally without emitting JSON.",
        "",
        UNTRUSTED_RULE,
        "",
        "Available actions:",
    ]
    for spec in registry.all():
        params = ", ".join((spec.parameters.get("properties") or {}).keys())
        sig = f"({params})" if params else "()"
        lines.append(f"- {spec.name}{sig}: {spec.description}")
    return "\n".join(lines)
