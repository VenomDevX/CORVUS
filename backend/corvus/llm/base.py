"""The single internal LLM interface every provider implements.

Milestone 8 adds OpenAI/Anthropic/Gemini/DeepSeek implementations behind this
same protocol; tool-calling will extend Delta with tool-call variants then.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Delta:
    """One streamed chunk of assistant output."""

    content: str
    done: bool = False


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        """Stream one assistant turn for the given message history."""
        ...

    async def list_models(self) -> list[str]:
        """Models this provider can serve right now."""
        ...
