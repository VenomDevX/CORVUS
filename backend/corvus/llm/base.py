"""The single internal LLM interface every provider implements.

Milestone 8 adds OpenAI/Anthropic/Gemini/DeepSeek implementations behind this
same protocol.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolCall:
    """A model request to invoke a registered action."""

    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass(frozen=True)
class Delta:
    """One streamed chunk of assistant output.

    A chunk carries text, tool-call requests, or both: models typically
    narrate ("Let me check…") before requesting a tool.
    """

    content: str
    done: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    # Set on assistant messages that requested tools, and on tool results.
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str | None = None


@dataclass(frozen=True)
class TurnResult:
    """The accumulated outcome of one model turn: everything it said, plus
    every tool it asked for."""

    content: str
    tool_calls: list[ToolCall]


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        """Stream one assistant turn (text only) for the given history."""
        ...

    def stream_chat_with_tools(
        self, messages: list[Message], model: str, tools: list[dict[str, Any]]
    ) -> AsyncIterator[Delta]:
        """Stream one turn that may also request tool calls. The caller runs
        the tools and loops. Providers without tool support just never yield
        tool_calls - graceful degradation to plain chat."""
        ...

    async def list_models(self) -> list[str]:
        """Models this provider can serve right now."""
        ...
