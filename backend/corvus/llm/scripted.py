"""Deterministic provider for end-to-end tests (CORVUS_TEST_PROVIDER=scripted).

Never used in a frozen build: ProviderManager only honors the env var when
running from source. Behavior:
  "e2e create folder <path>"  -> one create_folder tool call, then "Done."
  anything else               -> streams "Scripted reply: <text>"
"""

from collections.abc import AsyncIterator

from .base import Delta, Message, ToolCall

PREFIX = "e2e create folder "


class ScriptedProvider:
    name = "scripted"

    def _last_user(self, messages: list[Message]) -> str:
        return next((m.content for m in reversed(messages) if m.role == "user"), "")

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        yield Delta(content=f"Scripted reply: {self._last_user(messages)}")
        yield Delta(content="", done=True)

    async def stream_chat_with_tools(self, messages, model, tools) -> AsyncIterator[Delta]:
        text = self._last_user(messages)
        if messages and messages[-1].role == "tool":
            yield Delta(content="Done.")
        elif text.lower().startswith(PREFIX) and tools:
            path = text[len(PREFIX):].strip()
            yield Delta(content="", done=True,
                        tool_calls=[ToolCall("create_folder", {"path": path}, "e2e-1")])
            return
        else:
            yield Delta(content=f"Scripted reply: {text}")
        yield Delta(content="", done=True)

    async def complete(self, messages: list[Message], model: str) -> str:
        return '{"store": false}'

    async def list_models(self) -> list[str]:
        return ["scripted"]
