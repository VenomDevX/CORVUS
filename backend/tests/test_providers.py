"""Provider wire-format tests with mocked HTTP transports (no network/keys)."""

import json

import httpx

from corvus.llm.anthropic import AnthropicProvider
from corvus.llm.base import Message, ToolCall
from corvus.llm.gemini import GeminiProvider
from corvus.llm.openai_compat import OpenAICompatProvider


def sse(*lines: str) -> httpx.Response:
    body = "".join(f"data: {ln}\n\n" for ln in lines)
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


# -- OpenAI-compatible (OpenAI + DeepSeek) ------------------------------------

async def test_openai_streams_text():
    def handler(req):
        assert req.headers["authorization"] == "Bearer sk-x"
        assert json.loads(req.content)["stream"] is True
        return sse(
            json.dumps({"choices": [{"delta": {"content": "Hel"}}]}),
            json.dumps({"choices": [{"delta": {"content": "lo"}}]}),
            "[DONE]",
        )

    p = OpenAICompatProvider("openai", "https://api.openai.com/v1", "sk-x",
                             transport=httpx.MockTransport(handler))
    out = "".join([d.content async for d in p.stream_chat([Message("user", "hi")], "gpt-4o")])
    assert out == "Hello"


async def test_openai_reassembles_streamed_tool_call():
    def handler(req):
        return sse(
            json.dumps({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"name": "open_app", "arguments": '{"ap'}}]}}]}),
            json.dumps({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": 'p": "chrome"}'}}]}}]}),
            "[DONE]",
        )

    p = OpenAICompatProvider("openai", "https://api.openai.com/v1", "sk-x",
                             transport=httpx.MockTransport(handler))
    calls = [c async for d in p.stream_chat_with_tools([Message("user", "x")], "gpt-4o",
                                                       [{"function": {"name": "open_app"}}])
             for c in d.tool_calls]
    assert calls == [ToolCall(name="open_app", arguments={"app": "chrome"})]


async def test_openai_lists_models():
    def handler(req):
        return httpx.Response(200, json={"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]})

    p = OpenAICompatProvider("openai", "https://api.openai.com/v1", "sk-x",
                             transport=httpx.MockTransport(handler))
    assert "gpt-4o" in await p.list_models()


# -- Anthropic ----------------------------------------------------------------

async def test_anthropic_streams_text_and_separates_system():
    captured = {}

    def handler(req):
        captured["body"] = json.loads(req.content)
        assert req.headers["x-api-key"] == "ak"
        return sse(
            json.dumps({"type": "content_block_start", "index": 0,
                        "content_block": {"type": "text"}}),
            json.dumps({"type": "content_block_delta", "index": 0,
                        "delta": {"type": "text_delta", "text": "Hi there"}}),
        )

    p = AnthropicProvider("ak", transport=httpx.MockTransport(handler))
    out = "".join([d.content async for d in p.stream_chat(
        [Message("system", "be nice"), Message("user", "hi")], "claude-sonnet-4-5")])
    assert out == "Hi there"
    assert captured["body"]["system"] == "be nice"
    assert captured["body"]["messages"][0]["role"] == "user"


async def test_anthropic_parses_tool_use_block():
    def handler(req):
        return sse(
            json.dumps({"type": "content_block_start", "index": 0,
                        "content_block": {"type": "tool_use", "id": "t1", "name": "web_search"}}),
            json.dumps({"type": "content_block_delta", "index": 0,
                        "delta": {"type": "input_json_delta", "partial_json": '{"query":"corvus"}'}}),
        )

    p = AnthropicProvider("ak", transport=httpx.MockTransport(handler))
    calls = [c async for d in p.stream_chat_with_tools([Message("user", "x")], "m",
                                                       [{"function": {"name": "web_search"}}])
             for c in d.tool_calls]
    assert calls[0].name == "web_search"
    assert calls[0].arguments == {"query": "corvus"}


# -- Gemini -------------------------------------------------------------------

async def test_gemini_streams_and_maps_roles():
    captured = {}

    def handler(req):
        captured["body"] = json.loads(req.content)
        assert req.headers["x-goog-api-key"] == "gk"
        return sse(
            json.dumps({"candidates": [{"content": {"parts": [{"text": "Sure"}]}}]}),
            json.dumps({"candidates": [{"content": {"parts": [{"text": " thing"}]}}]}),
        )

    p = GeminiProvider("gk", transport=httpx.MockTransport(handler))
    out = "".join([d.content async for d in p.stream_chat(
        [Message("system", "sys"), Message("assistant", "prev"), Message("user", "hi")],
        "gemini-2.5-flash")])
    assert out == "Sure thing"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "sys"
    assert captured["body"]["contents"][0]["role"] == "model"  # assistant -> model


async def test_gemini_parses_function_call():
    def handler(req):
        return sse(json.dumps({"candidates": [{"content": {"parts": [
            {"functionCall": {"name": "system_status", "args": {}}}]}}]}))

    p = GeminiProvider("gk", transport=httpx.MockTransport(handler))
    calls = [c async for d in p.stream_chat_with_tools([Message("user", "x")], "m",
                                                       [{"function": {"name": "system_status"}}])
             for c in d.tool_calls]
    assert calls[0].name == "system_status"
