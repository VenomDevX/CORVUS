"""The Corvus action registry.

Every OS capability is a registered ActionSpec - not a giant if/else. A spec
carries its JSON-schema parameters, a risk tier, whether it needs explicit
user confirmation, and a handler. The agent loop (llm/agent.py) exposes specs
to the model as tools, gates high-risk ones behind confirmation, and executes
handlers, so adding a capability is: write a handler, register a spec.
"""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Risk(str, Enum):
    SAFE = "safe"        # read-only / trivially reversible - no confirmation
    LOW = "low"          # visible, easily undone (open an app, set volume)
    MEDIUM = "medium"    # noticeable side effects (create/move files)
    HIGH = "high"        # destructive or hard to reverse - always confirm


Handler = Callable[..., Any] | Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema (object)
    risk: Risk
    handler: Handler
    # Human sentence stating exactly what will happen, given the arguments.
    # Required for anything that confirms; None for SAFE actions.
    confirm_prompt: Callable[[dict[str, Any]], str] | None = None
    category: str = "general"
    # Sync handler that can take seconds (winget, tree walks, embedding calls):
    # run it on a worker thread so chat, voice and confirmations keep flowing.
    # Opt-in, since some handlers touch the event loop and must stay on it.
    blocking: bool = False

    @property
    def requires_confirmation(self) -> bool:
        return self.risk in (Risk.MEDIUM, Risk.HIGH)

    def describe_confirmation(self, args: dict[str, Any]) -> str:
        if self.confirm_prompt:
            return self.confirm_prompt(args)
        return f"Corvus will run {self.name}. Continue?"

    def argument_error(self, args: dict[str, Any]) -> str | None:
        """Argument names checked against the schema. The text goes back to the
        model, so it names the valid parameters (not a Python TypeError) for a retry."""
        props = self.parameters.get("properties")
        if not isinstance(props, dict):
            return None  # free-form schema (some plugins): let the handler decide
        takes_kwargs = any(p.kind is p.VAR_KEYWORD
                           for p in inspect.signature(self.handler).parameters.values())
        unknown = [] if takes_kwargs else sorted(set(args) - set(props))
        missing = sorted(set(self.parameters.get("required", [])) - set(args))
        if not (unknown or missing):
            return None
        problems = "; ".join(
            p for p in (unknown and f"unknown {', '.join(unknown)}",
                        missing and f"missing {', '.join(missing)}") if p
        )
        return (f"Invalid arguments for {self.name} ({problems}). "
                f"Valid parameters: {', '.join(props) or 'none'}.")

    def tool_schema(self) -> dict[str, Any]:
        """OpenAI/Ollama-style function tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Registry:
    def __init__(self) -> None:
        self._actions: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec) -> None:
        if spec.name in self._actions:
            raise ValueError(f"duplicate action: {spec.name}")
        if spec.requires_confirmation and spec.confirm_prompt is None:
            raise ValueError(f"action {spec.name} needs a confirm_prompt for its risk tier")
        self._actions[spec.name] = spec

    def unregister(self, name: str) -> bool:
        """Remove an action (used when a plugin is disabled)."""
        return self._actions.pop(name, None) is not None

    def get(self, name: str) -> ActionSpec | None:
        return self._actions.get(name)

    def all(self) -> list[ActionSpec]:
        return list(self._actions.values())

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [spec.tool_schema() for spec in self._actions.values()]

    async def execute(self, name: str, args: dict[str, Any]) -> ActionResult:
        spec = self._actions.get(name)
        if spec is None:
            return ActionResult(False, f"Unknown action: {name}")
        if (problem := spec.argument_error(args)) is not None:
            return ActionResult(False, problem)
        try:
            if spec.blocking and not inspect.iscoroutinefunction(spec.handler):
                result = await asyncio.to_thread(spec.handler, **args)
            else:
                result = spec.handler(**args)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, ActionResult):
                return result
            return ActionResult(True, str(result) if result is not None else "Done.")
        except Exception as exc:  # noqa: BLE001 - surface handler failures to the user
            return ActionResult(False, f"{name} failed: {exc}")


def build_default_registry(browser=None, provider=None, get_model=None, notifications=None) -> Registry:
    """Assemble the registry from the handler modules.

    Browser/vision actions (M7) register when a browser engine + provider are
    supplied; notification actions (M8) register when a hub is supplied. Without
    them, only the OS actions are available (e.g. in tests).
    """
    from . import handlers

    registry = Registry()
    handlers.register_all(registry)

    if provider is not None:
        from .browser_handlers import register_vision_actions
        register_vision_actions(registry, provider)
    if browser is not None and provider is not None:
        from .browser_handlers import register_browser_actions
        register_browser_actions(registry, browser, provider, get_model or (lambda: ""))
    if notifications is not None:
        from .notify_handlers import register_notification_actions
        register_notification_actions(registry, notifications)
    return registry
