"""We don't send `temperature` to the provider.

SYMPTOM: every LLM call against gpt-5 400s —

    Unsupported value: 'temperature' does not support 0.1 with this model.
    Only the default (1) value is supported.

surfacing as `LLMAdapterError: LLM request failed: ...`, which says nothing
about the model being the cause. Found by probing gpt-5 with our exact request
body before wiring the daily share card.

ROOT CAUSE: `OpenAICompatibleProvider` hard-coded `"temperature": temperature`
into both request bodies.

FIX: don't send it. Every model uses its own default.

The trade, recorded so it isn't rediscovered as a mystery: extraction-shaped
tasks that asked for near-zero temperature (competitor grouping 0.0, BI
extraction 0.1) now run at the model default and are correspondingly less
repeatable. Jimmy's call, made with that consequence stated.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.services.llm_adapter import OpenAICompatibleProvider

OK_BODY = {"choices": [{"message": {"content": '{"ok": true}'}}]}


def _provider(monkeypatch):
    sent = []

    async def _post(self, url, headers=None, json=None, **kw):  # noqa: A002
        sent.append(dict(json))
        return httpx.Response(200, json=OK_BODY, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    settings = Settings(llm_provider="openai_compatible", llm_api_key="k", llm_model="gpt-5")
    return OpenAICompatibleProvider(settings), sent


def test_temperature_is_never_in_the_request_body(monkeypatch):
    provider, sent = _provider(monkeypatch)
    asyncio.run(
        provider.generate(
            model="gpt-5", system_prompt="s", user_prompt="u", temperature=0.1
        )
    )
    assert "temperature" not in sent[0]


def test_a_caller_passing_zero_still_does_not_send_it(monkeypatch):
    """0.0 is falsy — a truthiness check would have "worked" here by accident
    and broken for 0.2. The parameter is dropped unconditionally."""
    provider, sent = _provider(monkeypatch)
    asyncio.run(
        provider.generate(
            model="gpt-5", system_prompt="s", user_prompt="u", temperature=0.0
        )
    )
    assert "temperature" not in sent[0]


def test_the_rest_of_the_body_is_untouched(monkeypatch):
    """Only `temperature` comes off. `response_format` is what makes
    `generate_json` parseable — dropping it too would trade one failure for a
    subtler one."""
    provider, sent = _provider(monkeypatch)
    asyncio.run(
        provider.generate(
            model="gpt-5", system_prompt="sys", user_prompt="usr", temperature=0.1
        )
    )
    body = sent[0]
    assert body["model"] == "gpt-5"
    assert body["response_format"] == {"type": "json_object"}
    assert [m["content"] for m in body["messages"]] == ["sys", "usr"]


def test_callers_keep_compiling_against_the_parameter(monkeypatch):
    """The signature still accepts `temperature` on purpose: six services pass
    a considered value, and removing it would be a six-service refactor for no
    behavioural gain. This pins that the keyword is still accepted."""
    provider, _ = _provider(monkeypatch)
    out = asyncio.run(
        provider.generate(model="m", system_prompt="s", user_prompt="u", temperature=0.2)
    )
    assert out == '{"ok": true}'


def test_stream_chat_also_omits_it(monkeypatch):
    """The streaming path built its own body and would otherwise still 400."""
    import inspect

    src = inspect.getsource(OpenAICompatibleProvider.stream_chat)
    assert '"temperature"' not in src
