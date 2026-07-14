"""The Corvus agent loop.

Given a conversation, the model may request actions from the registry. This
loop runs those actions - pausing for explicit user confirmation on anything
the action's risk tier requires - and feeds results back until the model
produces a final text answer. Emits structured events so the UI can render
action chips, confirmation cards, and results.

Confirmation is delegated to an injected async `confirm` callback: the WS
layer prompts the user and returns their decision. Providers that don't
support tool calls simply never return tool_calls, so this degrades to plain
chat.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from ..actions.registry import ActionResult, Registry, Risk
from .base import LLMProvider, Message, ToolCall

log = structlog.get_logger("corvus")

MAX_TOOL_ROUNDS = 6

# event: {"type": "action_proposed"|"action_confirming"|"action_result"|"text", ...}
EventSink = Callable[[dict[str, Any]], Awaitable[None] | None]
# confirm(action_name, prompt, args) -> bool
Confirmer = Callable[[str, str, dict[str, Any]], Awaitable[bool]]


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


async def run_agent_turn(
    provider: LLMProvider,
    model: str,
    messages: list[Message],
    registry: Registry,
    confirm: Confirmer,
    emit: EventSink | None = None,
    log_action: Callable[[str, dict, ActionResult, str], None] | None = None,
) -> AgentOutcome:
    """Run one user turn to completion, executing any requested actions."""
    tools = registry.tool_schemas()
    convo = list(messages)
    actions_run: list[dict[str, Any]] = []

    for _round in range(MAX_TOOL_ROUNDS):
        turn = await provider.chat_with_tools(convo, model, tools)

        if not turn.tool_calls:
            if turn.content:
                await _emit(emit, {"type": "text", "content": turn.content})
            return AgentOutcome(text=turn.content, actions_run=actions_run)

        # Record the assistant's tool request in the running history.
        convo.append(Message("assistant", turn.content, tool_calls=turn.tool_calls))

        for call in turn.tool_calls:
            result = await _run_one(call, registry, confirm, emit, log_action)
            actions_run.append({"name": call.name, "arguments": call.arguments, "ok": result.ok, "message": result.message})
            convo.append(Message("tool", json.dumps({"ok": result.ok, "message": result.message, **result.data}), tool_name=call.name))

    # Safety valve: ask for a plain summary after too many rounds.
    convo.append(Message("system", "Stop calling tools now and give the user a short summary of what you did."))
    final = await provider.chat_with_tools(convo, model, [])
    await _emit(emit, {"type": "text", "content": final.content})
    return AgentOutcome(text=final.content, actions_run=actions_run)


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
        await _emit(emit, {"type": "action_confirming", "name": call.name, "prompt": prompt})
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
        "something the tools cover, call the matching tool rather than explaining how. "
        "Announce what you're doing in a short friendly sentence. For anything "
        "destructive or high-impact, the system will ask the user to confirm - you "
        "don't need to ask separately, just call the tool. If a tool result reports a "
        "failure, tell the user plainly. Only use tools that exist.",
        "",
        "Available actions:",
    ]
    for spec in registry.all():
        lines.append(f"- {spec.name}: {spec.description}")
    return "\n".join(lines)
