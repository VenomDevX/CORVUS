import json

import httpx
import pytest

from corvus.llm.base import Message
from corvus.llm.ollama import OllamaProvider


def ndjson_response(chunks: list[dict]) -> httpx.Response:
    body = "\n".join(json.dumps(c) for c in chunks)
    return httpx.Response(200, content=body.encode(), headers={"content-type": "application/x-ndjson"})


def make_provider(handler) -> OllamaProvider:
    return OllamaProvider(base_url="http://ollama.test", transport=httpx.MockTransport(handler))


async def test_stream_chat_yields_deltas_until_done():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["messages"][0]["role"] == "system"
        return ndjson_response(
            [
                {"message": {"content": "Hel"}, "done": False},
                {"message": {"content": "lo"}, "done": False},
                {"message": {"content": ""}, "done": True},
            ]
        )

    provider = make_provider(handler)
    deltas = [
        d
        async for d in provider.stream_chat(
            [Message("system", "s"), Message("user", "hi")], "test-model"
        )
    ]
    assert "".join(d.content for d in deltas) == "Hello"
    assert deltas[-1].done is True


async def test_stream_chat_raises_on_ollama_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response([{"error": "model not found"}])

    provider = make_provider(handler)
    with pytest.raises(RuntimeError, match="model not found"):
        async for _ in provider.stream_chat([Message("user", "hi")], "missing"):
            pass


async def test_stream_chat_with_tools_streams_text_and_collects_calls():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True  # text must arrive as it is generated
        assert payload["tools"][0]["function"]["name"] == "open_app"
        return ndjson_response(
            [
                {"message": {"content": "Opening "}, "done": False},
                {"message": {"content": "Chrome."}, "done": False},
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "open_app", "arguments": {"app": "chrome"}}}
                        ],
                    },
                    "done": True,
                },
            ]
        )

    tools = [{"type": "function", "function": {"name": "open_app", "parameters": {}}}]
    provider = make_provider(handler)
    deltas = [
        d async for d in provider.stream_chat_with_tools([Message("user", "open chrome")], "m", tools)
    ]
    assert "".join(d.content for d in deltas) == "Opening Chrome."
    calls = [c for d in deltas for c in d.tool_calls]
    assert len(calls) == 1
    assert calls[0].name == "open_app"
    assert calls[0].arguments == {"app": "chrome"}


async def test_tool_call_written_as_json_content_is_recovered():
    # qwen2.5-coder and similar emit the call as JSON *content*, not the
    # structured field. It must be recovered as a tool call, and the raw JSON
    # must never leak to the user as assistant text.
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response(
            [
                {"message": {"content": '{"name": "system_status",'}, "done": False},
                {"message": {"content": ' "arguments": {}}'}, "done": True},
            ]
        )

    tools = [{"type": "function", "function": {"name": "system_status", "parameters": {}}}]
    provider = make_provider(handler)
    deltas = [
        d async for d in provider.stream_chat_with_tools([Message("user", "status?")], "m", tools)
    ]
    assert "".join(d.content for d in deltas) == ""  # no JSON leaked as text
    calls = [c for d in deltas for c in d.tool_calls]
    assert len(calls) == 1 and calls[0].name == "system_status"


async def test_narration_then_json_tool_call_streams_prose_and_recovers_call():
    # The real qwen2.5-coder pattern: a sentence of narration, then the call as
    # a JSON object. The prose must stream to the user; the JSON must not.
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response(
            [
                {"message": {"content": "Getting system status..."}, "done": False},
                {"message": {"content": '\n\n{"name": "system_status",'}, "done": False},
                {"message": {"content": ' "arguments": {}}'}, "done": True},
            ]
        )

    tools = [{"type": "function", "function": {"name": "system_status", "parameters": {}}}]
    provider = make_provider(handler)
    deltas = [
        d async for d in provider.stream_chat_with_tools([Message("user", "status?")], "m", tools)
    ]
    text = "".join(d.content for d in deltas)
    assert text.strip() == "Getting system status..."  # prose kept, JSON dropped
    assert "{" not in text
    calls = [c for d in deltas for c in d.tool_calls]
    assert len(calls) == 1 and calls[0].name == "system_status"


async def test_code_block_reply_still_streams_and_is_not_a_tool_call():
    # A python code fence must not be mistaken for a tool call or buffered.
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response(
            [
                {"message": {"content": "Here you go:\n"}, "done": False},
                {"message": {"content": "```python\n"}, "done": False},
                {"message": {"content": "print({1: 2})\n```"}, "done": True},
            ]
        )

    tools = [{"type": "function", "function": {"name": "open_app", "parameters": {}}}]
    provider = make_provider(handler)
    deltas = [
        d async for d in provider.stream_chat_with_tools([Message("user", "code")], "m", tools)
    ]
    text = "".join(d.content for d in deltas)
    assert "print({1: 2})" in text
    assert [c for d in deltas for c in d.tool_calls] == []
    # Code streamed incrementally rather than arriving in one blob at the end.
    assert sum(1 for d in deltas if d.content) >= 2


async def test_fenced_json_tool_call_is_recovered_with_args():
    def handler(request: httpx.Request) -> httpx.Response:
        blob = '```json\n{"name": "open_app", "arguments": {"app": "Chrome"}}\n```'
        return ndjson_response([{"message": {"content": blob}, "done": True}])

    tools = [{"type": "function", "function": {"name": "open_app", "parameters": {}}}]
    provider = make_provider(handler)
    calls = [
        c
        async for d in provider.stream_chat_with_tools([Message("user", "open chrome")], "m", tools)
        for c in d.tool_calls
    ]
    assert calls[0].name == "open_app"
    assert calls[0].arguments == {"app": "Chrome"}


async def test_json_content_not_matching_a_tool_is_left_as_text():
    # Ordinary JSON the user asked for must pass through as text, not be
    # misread as an action.
    def handler(request: httpx.Request) -> httpx.Response:
        blob = '{"name": "not_a_registered_action", "arguments": {}}'
        return ndjson_response([{"message": {"content": blob}, "done": True}])

    tools = [{"type": "function", "function": {"name": "open_app", "parameters": {}}}]
    provider = make_provider(handler)
    deltas = [
        d async for d in provider.stream_chat_with_tools([Message("user", "give me json")], "m", tools)
    ]
    assert "not_a_registered_action" in "".join(d.content for d in deltas)
    assert [c for d in deltas for c in d.tool_calls] == []


async def test_plain_text_streams_incrementally_with_tools_available():
    # A normal prose reply must still stream chunk-by-chunk, not buffer.
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response(
            [
                {"message": {"content": "Your CPU "}, "done": False},
                {"message": {"content": "looks fine."}, "done": False},
                {"message": {"content": ""}, "done": True},
            ]
        )

    tools = [{"type": "function", "function": {"name": "system_status", "parameters": {}}}]
    provider = make_provider(handler)
    text_deltas = [
        d.content
        async for d in provider.stream_chat_with_tools([Message("user", "hi")], "m", tools)
        if d.content
    ]
    assert text_deltas == ["Your CPU ", "looks fine."]  # streamed, not coalesced


async def test_stream_chat_with_tools_accepts_stringified_arguments():
    # Some models emit `arguments` as a JSON string rather than an object.
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response(
            [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"function": {"name": "web_search", "arguments": '{"query": "corvus"}'}}
                        ],
                    },
                    "done": True,
                }
            ]
        )

    provider = make_provider(handler)
    calls = [
        c
        async for d in provider.stream_chat_with_tools([Message("user", "s")], "m", [])
        for c in d.tool_calls
    ]
    assert calls[0].arguments == {"query": "corvus"}


async def test_model_without_tool_support_falls_back_and_is_remembered():
    # deepseek-coder-class models: Ollama 400s the whole request when `tools`
    # is present. The provider must retry without tools (text-JSON recovery
    # still enables actions) and skip the doomed attempt on later turns.
    from corvus.llm import ollama as ollama_module

    ollama_module._no_tools_models.discard("no-tools-model")
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if "tools" in payload:
            return httpx.Response(
                400, json={"error": "registry.ollama.ai/library/no-tools-model does not support tools"}
            )
        return ndjson_response(
            [
                {"message": {"content": "Hello from deepseek."}, "done": False},
                {"message": {"content": ""}, "done": True},
            ]
        )

    tools = [{"type": "function", "function": {"name": "open_app", "parameters": {}}}]
    provider = make_provider(handler)

    deltas = [
        d async for d in provider.stream_chat_with_tools([Message("user", "hi")], "no-tools-model", tools)
    ]
    assert "".join(d.content for d in deltas) == "Hello from deepseek."
    assert len(requests) == 2 and "tools" in requests[0] and "tools" not in requests[1]

    # Second turn goes straight to the no-tools request.
    deltas = [
        d async for d in provider.stream_chat_with_tools([Message("user", "again")], "no-tools-model", tools)
    ]
    assert "".join(d.content for d in deltas) == "Hello from deepseek."
    assert len(requests) == 3 and "tools" not in requests[2]
    ollama_module._no_tools_models.discard("no-tools-model")


async def test_unrelated_400_is_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid request shape"})

    tools = [{"type": "function", "function": {"name": "open_app", "parameters": {}}}]
    provider = make_provider(handler)
    with pytest.raises(RuntimeError, match="invalid request shape"):
        async for _ in provider.stream_chat_with_tools([Message("user", "hi")], "m-400", tools):
            pass


async def test_complete_concatenates():
    def handler(request: httpx.Request) -> httpx.Response:
        return ndjson_response(
            [{"message": {"content": "a"}, "done": False}, {"message": {"content": "b"}, "done": True}]
        )

    provider = make_provider(handler)
    assert await provider.complete([Message("user", "x")], "m") == "ab"


async def test_list_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:latest"}]})

    provider = make_provider(handler)
    assert await provider.list_models() == ["qwen2.5-coder:latest"]
