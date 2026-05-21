"""Unit tests for `chat_completion_with_tools` and `_events_from_chunks`
(Stage 7 / ticket #2).

Two layers tested separately:

  * `_events_from_chunks` — pure logic mapping OpenAI streaming chunks to
    normalized ChatEvent's. No HTTP, no settings. Exhaustive coverage here
    is the cheapest place to catch parsing bugs (tool-call fragment
    assembly, finish-reason ordering, etc).

  * `chat_completion_with_tools` — the gateway-level entry point. Two
    integration-style tests with a fake provider injected into the gateway.

Skips httpx-level mocking — the chat endpoint (ticket #5) will exercise
the full HTTP path with respx if/when we want that coverage.
"""
from __future__ import annotations

from typing import AsyncIterable, AsyncIterator
from unittest.mock import patch

import pytest

from app.services.llm_adapter import (
    ChatDone,
    ChatEvent,
    ChatToken,
    ChatToolCall,
    LLMAdapterError,
    LLMGateway,
    _events_from_chunks,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _aiter(chunks: list[dict]) -> AsyncIterator[dict]:
    for c in chunks:
        yield c


async def _collect(events: AsyncIterable[ChatEvent]) -> list[ChatEvent]:
    out = []
    async for e in events:
        out.append(e)
    return out


# ── _events_from_chunks: text-only streams ────────────────────────────────────


@pytest.mark.asyncio
async def test_text_only_stream_yields_tokens_then_done():
    chunks = [
        {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": " "}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "world."}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    assert events == [
        ChatToken(text="Hello"),
        ChatToken(text=" "),
        ChatToken(text="world."),
        ChatDone(finish_reason="stop"),
    ]


@pytest.mark.asyncio
async def test_empty_content_chunks_do_not_emit_tokens():
    """Some providers send `{"content": ""}` heartbeat chunks. Ignore them."""
    chunks = [
        {"choices": [{"delta": {"content": ""}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "ok"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    assert events == [ChatToken(text="ok"), ChatDone(finish_reason="stop")]


@pytest.mark.asyncio
async def test_done_carries_usage_if_provided():
    chunks = [
        {"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
        {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13},
        },
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    assert isinstance(events[-1], ChatDone)
    assert events[-1].usage == {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13}


# ── _events_from_chunks: tool-call assembly ──────────────────────────────────


@pytest.mark.asyncio
async def test_tool_call_assembled_from_split_fragments():
    """OpenAI streams tool-call name and args in fragments — function.name in
    one chunk, function.arguments split across several. Assembly must work
    even when arguments arrive byte-by-byte (the worst-case real-world shape)."""
    chunks = [
        # First fragment: id + name
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "id": "call_abc123",
            "type": "function",
            "function": {"name": "stock_lookup", "arguments": ""},
        }]}, "finish_reason": None}]},
        # Args streamed in pieces
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "function": {"arguments": '{"tic'},
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "function": {"arguments": 'ker": "AA'},
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0,
            "function": {"arguments": 'PL"}'},
        }]}, "finish_reason": None}]},
        # Finish reason on a chunk with no content
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    assert events == [
        ChatToolCall(call_id="call_abc123", name="stock_lookup", arguments={"ticker": "AAPL"}),
        ChatDone(finish_reason="tool_calls"),
    ]


@pytest.mark.asyncio
async def test_multiple_parallel_tool_calls_assemble_by_index():
    """Assistant calls two tools in parallel — chunks interleave by index."""
    chunks = [
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c0", "function": {"name": "concept_explainer", "arguments": ""}},
            {"index": 1, "id": "c1", "function": {"name": "template_search", "arguments": ""}},
        ]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": '{"concept": "sharpe"}'}},
        ]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [
            {"index": 1, "function": {"arguments": '{"query": "momentum"}'}},
        ]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    tool_events = [e for e in events if isinstance(e, ChatToolCall)]
    assert len(tool_events) == 2
    by_name = {e.name: e for e in tool_events}
    assert by_name["concept_explainer"].arguments == {"concept": "sharpe"}
    assert by_name["template_search"].arguments == {"query": "momentum"}
    assert by_name["concept_explainer"].call_id == "c0"
    assert by_name["template_search"].call_id == "c1"


@pytest.mark.asyncio
async def test_tool_call_with_unparseable_json_does_not_explode():
    """If the LLM emits malformed JSON for arguments, we yield the tool call
    with `_unparseable_json` rather than raising — the endpoint can decide
    how to handle (likely reprompt). Mid-stream JSON validity isn't the
    adapter's job to enforce."""
    chunks = [
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "c0",
            "function": {"name": "stock_lookup", "arguments": '{"ticker": "AAP'},
        }]}, "finish_reason": None}]},
        # Stream ends without closing the JSON
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    tool_call = events[0]
    assert isinstance(tool_call, ChatToolCall)
    assert tool_call.name == "stock_lookup"
    assert "_unparseable_json" in tool_call.arguments


# ── _events_from_chunks: mixed text + tool calls ─────────────────────────────


@pytest.mark.asyncio
async def test_text_then_tool_call_emits_both():
    """Assistant says something, then decides to call a tool — both events fire."""
    chunks = [
        {"choices": [{"delta": {"content": "Let me check. "}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "c0",
            "function": {"name": "stock_lookup", "arguments": '{"ticker": "AAPL"}'},
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    assert events == [
        ChatToken(text="Let me check. "),
        ChatToolCall(call_id="c0", name="stock_lookup", arguments={"ticker": "AAPL"}),
        ChatDone(finish_reason="tool_calls"),
    ]


# ── _events_from_chunks: edge cases ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_chunk_without_choices_is_skipped():
    """Some providers emit final usage-only chunks with no `choices`. Don't crash."""
    chunks = [
        {"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
        {"usage": {"total_tokens": 5}},  # no choices key
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    assert events == [ChatToken(text="hi"), ChatDone(finish_reason="stop")]


@pytest.mark.asyncio
async def test_iteration_stops_at_finish_reason_even_if_more_chunks_follow():
    """The provider may keep yielding after `finish_reason` (usage-only chunks).
    Our iterator must terminate at the first finish_reason so the consumer
    can release its connection."""
    chunks = [
        {"choices": [{"delta": {"content": "ok"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        # Trailing chunk that should NOT be consumed:
        {"choices": [{"delta": {"content": "should not appear"}, "finish_reason": None}]},
    ]
    events = await _collect(_events_from_chunks(_aiter(chunks)))

    assert events == [ChatToken(text="ok"), ChatDone(finish_reason="stop")]


# ── chat_completion_with_tools (gateway-level integration) ────────────────────


class _FakeStreamingProvider:
    """Minimal provider stand-in. Captures call args, yields a canned chunk stream."""

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.last_call: dict | None = None

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
    ) -> AsyncIterator[dict]:
        self.last_call = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
        }
        for c in self.chunks:
            yield c


def _gateway_with_fake_provider(chunks: list[dict]) -> tuple[LLMGateway, _FakeStreamingProvider]:
    from app.core.config import get_settings

    gateway = LLMGateway(get_settings())
    fake = _FakeStreamingProvider(chunks)
    gateway.provider = fake  # bypass _build_provider; settings.llm_model still required
    return gateway, fake


@pytest.mark.asyncio
async def test_gateway_chat_completion_with_tools_passes_through_events():
    chunks = [
        {"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    gateway, fake = _gateway_with_fake_provider(chunks)

    with patch.object(gateway.settings, "llm_model", "gpt-4o-mini"):
        events = await _collect(gateway.chat_completion_with_tools(
            messages=[{"role": "user", "content": "say hi"}],
            tools=[{"type": "function", "function": {"name": "stock_lookup"}}],
        ))

    assert events == [ChatToken(text="hi"), ChatDone(finish_reason="stop")]
    assert fake.last_call is not None
    assert fake.last_call["model"] == "gpt-4o-mini"
    assert fake.last_call["tools"] == [{"type": "function", "function": {"name": "stock_lookup"}}]
    assert fake.last_call["messages"] == [{"role": "user", "content": "say hi"}]


@pytest.mark.asyncio
async def test_gateway_raises_when_no_provider_configured():
    """If `llm_provider=disabled` (or no API key), the gateway has provider=None.
    chat_completion_with_tools must fail loudly on first __anext__."""
    from app.core.config import get_settings

    gateway = LLMGateway(get_settings())
    gateway.provider = None

    iterator = gateway.chat_completion_with_tools(
        messages=[{"role": "user", "content": "hello"}],
    )
    with pytest.raises(LLMAdapterError, match="not configured"):
        async for _ in iterator:
            pass


@pytest.mark.asyncio
async def test_gateway_rejects_stream_false():
    """Non-streaming mode is intentionally unsupported. Surface the error
    immediately rather than silently returning an empty iterator."""
    gateway, _ = _gateway_with_fake_provider([])

    iterator = gateway.chat_completion_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        stream=False,
    )
    with pytest.raises(LLMAdapterError, match="requires stream=True"):
        async for _ in iterator:
            pass


@pytest.mark.asyncio
async def test_gateway_raises_when_no_model_configured():
    chunks = [{"choices": [{"delta": {}, "finish_reason": "stop"}]}]
    gateway, _ = _gateway_with_fake_provider(chunks)

    with patch.object(gateway.settings, "llm_model", ""):
        iterator = gateway.chat_completion_with_tools(
            messages=[{"role": "user", "content": "hi"}],
        )
        with pytest.raises(LLMAdapterError, match="No model configured"):
            async for _ in iterator:
                pass
