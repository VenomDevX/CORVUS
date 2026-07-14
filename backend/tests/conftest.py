import asyncio
import os
from collections.abc import AsyncIterator

import pytest

# Redirect all Corvus state into a per-session temp dir before corvus.config
# is imported by the tests below.
_tmp = None


def pytest_configure(config):
    global _tmp
    import tempfile

    _tmp = tempfile.mkdtemp(prefix="corvus-test-")
    os.environ["CORVUS_DATA_DIR"] = _tmp


from corvus.llm.base import Delta, Message, ToolCall, TurnResult  # noqa: E402
from corvus.memory.repository import Repository  # noqa: E402


class FakeProvider:
    """Deterministic in-memory LLMProvider for API tests.

    tool_script: optional list of TurnResult driving successive
    stream_chat_with_tools turns, so the agent loop runs deterministically.
    Unscripted turns stream `chunks`, so deltas concatenate back to the
    original text exactly.
    """

    name = "fake"

    def __init__(
        self,
        chunks: list[str] | None = None,
        extraction: str = '{"store": false}',
        tool_script: list[TurnResult] | None = None,
        chunk_delay: float = 0.0,
    ):
        self.chunks = chunks if chunks is not None else ["Hello", " from", " Corvus"]
        self.extraction = extraction
        self.tool_script = tool_script
        self.chunk_delay = chunk_delay
        self.calls: list[list[Message]] = []
        self._tool_index = 0

    async def _pace(self) -> None:
        """Stand in for network latency, so the server's event loop gets a
        chance to notice client frames (e.g. cancel) mid-stream."""
        if self.chunk_delay:
            await asyncio.sleep(self.chunk_delay)

    async def stream_chat(self, messages: list[Message], model: str) -> AsyncIterator[Delta]:
        self.calls.append(messages)
        for chunk in self.chunks:
            await self._pace()
            yield Delta(content=chunk)
        yield Delta(content="", done=True)

    async def stream_chat_with_tools(self, messages, model, tools) -> AsyncIterator[Delta]:
        self.calls.append(messages)
        if self.tool_script and self._tool_index < len(self.tool_script):
            turn = self.tool_script[self._tool_index]
            self._tool_index += 1
            if turn.content:
                yield Delta(content=turn.content)
            yield Delta(content="", done=True, tool_calls=list(turn.tool_calls))
            return
        for chunk in self.chunks:
            await self._pace()
            yield Delta(content=chunk)
        yield Delta(content="", done=True)

    async def complete(self, messages: list[Message], model: str) -> str:
        self.calls.append(messages)
        return self.extraction

    async def list_models(self) -> list[str]:
        return ["fake-model:latest"]


@pytest.fixture
def repo(tmp_path) -> Repository:
    r = Repository(tmp_path / "test.db")
    yield r
    r.close()


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()
