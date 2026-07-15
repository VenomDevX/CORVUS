"""The Corvus action registry.

Every OS capability is a registered ActionSpec - not a giant if/else. A spec
carries its JSON-schema parameters, a risk tier, whether it needs explicit
user confirmation, and a handler. The agent loop (llm/agent.py) exposes specs
to the model as tools, gates high-risk ones behind confirmation, and executes
handlers, so adding a capability is: write a handler, register a spec.
"""

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

    @property
    def requires_confirmation(self) -> bool:
        return self.risk in (Risk.MEDIUM, Risk.HIGH)

    def describe_confirmation(self, args: dict[str, Any]) -> str:
        if self.confirm_prompt:
            return self.confirm_prompt(args)
        return f"Corvus will run {self.name}. Continue?"

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
        try:
            result = spec.handler(**args)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, ActionResult):
                return result
            return ActionResult(True, str(result) if result is not None else "Done.")
        except TypeError as exc:
            return ActionResult(False, f"Invalid arguments for {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface handler failures to the user
            return ActionResult(False, f"{name} failed: {exc}")


def build_default_registry(browser=None, provider=None, get_model=None) -> Registry:
    """Assemble the registry from the handler modules.

    When a browser engine and provider are supplied (the real app), the
    Milestone 7 browser-automation and computer-vision actions are registered
    too; without them, only the OS actions are available (e.g. in tests).
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
    return registry
