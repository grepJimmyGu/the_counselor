"""Tests for chat guardrails (Stage 7 / ticket #9).

Three layers:

  * Pure scanners — classify_refusal, detect_uncited_numerics. No I/O.
  * Reprompt + integration — attempt_citation_reprompt with mocked LLM,
    end-to-end _apply_guardrails behavior verified via the chat endpoint.
  * Job entry points — audit_chat_responses_job and chat_guardrails_digest_job
    smoke-tested with mocked LLM + in-memory DB.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncIterator, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.chat import ChatConversation, ChatMessage
from app.services.chat_guardrails import (
    append_redaction_warning,
    attempt_citation_reprompt,
    classify_refusal,
    detect_uncited_numerics,
)
from app.services.llm_adapter import ChatDone, ChatToken


# ── classify_refusal (pure regex scanner) ────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I can't execute trades — Livermore is research-only.", "trade_execution"),
        ("I do not execute trades for users.", "trade_execution"),
        ("I can't tell you whether to buy AAPL.", "personalized_advice"),
        ("That depends on your goals and risk tolerance.", "personalized_advice"),
        ("I cannot give personalized financial advice.", "personalized_advice"),
        ("I can't predict future prices.", "forward_prediction"),
        ("I don't make forward-looking predictions about NVDA.", "forward_prediction"),
        ("I can only help with investment research.", "off_topic"),
        ("That's outside my scope.", "off_topic"),
    ],
)
def test_classify_refusal_matches_known_shapes(text, expected):
    assert classify_refusal(text) == expected


def test_classify_refusal_returns_none_on_non_refusal():
    """Normal informational responses should NOT register as refusals."""
    text = "AAPL's Sharpe ratio over the last 5 years was approximately 0.83."
    assert classify_refusal(text) is None


def test_classify_refusal_handles_empty_string():
    assert classify_refusal("") is None
    assert classify_refusal(None) is None  # type: ignore[arg-type]


def test_classify_refusal_is_case_insensitive():
    assert classify_refusal("I CANNOT EXECUTE TRADES") == "trade_execution"


# ── detect_uncited_numerics (pure scanner) ───────────────────────────────────


def test_uncited_numerics_finds_percentages_and_ratios_without_cites():
    text = "AAPL had a 12.3% return with a Sharpe of 0.83."
    found = detect_uncited_numerics(text)
    assert "12.3%" in found
    assert "0.83" in found


def test_uncited_numerics_skips_years():
    """4-digit years 1900-2099 are excluded — they're not factual claims to cite."""
    text = "Between 2020 and 2024, the strategy returned 15.2%."
    found = detect_uncited_numerics(text)
    assert "2020" not in found
    assert "2024" not in found
    assert "15.2%" in found


def test_uncited_numerics_skipped_when_cite_chip_nearby():
    """A numeric token followed by a <cite> chip within the window is cited."""
    text = "Sharpe ratio was 0.83 <cite source=\"backtest\" id=\"bt_abc\"/>."
    found = detect_uncited_numerics(text)
    assert found == []


def test_uncited_numerics_distance_window():
    """A cite chip too far from the number does NOT cover it."""
    text = (
        "AAPL's return was 12.3% in 2024. " + ("blah " * 40)
        + "<cite source=\"backtest\"/>"
    )
    found = detect_uncited_numerics(text)
    # The cite is >80 chars after "12.3%" so it doesn't cover.
    assert "12.3%" in found


def test_uncited_numerics_handles_dollar_amounts_and_multipliers():
    text = "Revenue was $1.5B; the stock trades at 3.2x book value."
    found = detect_uncited_numerics(text)
    assert "$1.5B" in found
    assert "3.2x" in found


def test_uncited_numerics_empty_string():
    assert detect_uncited_numerics("") == []
    assert detect_uncited_numerics(None) == []  # type: ignore[arg-type]


# ── append_redaction_warning ──────────────────────────────────────────────────


def test_append_redaction_warning_adds_note():
    out = append_redaction_warning("AAPL gained 12.3%.", uncited=["12.3%"])
    assert "12.3%" in out  # original text preserved
    assert "could not be sourced" in out


def test_append_redaction_warning_noop_when_clean():
    text = "AAPL gained 12.3%."
    assert append_redaction_warning(text, uncited=[]) == text


# ── attempt_citation_reprompt (mocked LLM) ───────────────────────────────────


@pytest.mark.asyncio
async def test_citation_reprompt_returns_rewritten_text_on_success():
    """LLM returns clean text with citations → reprompt returns it."""
    async def _stream(**_kwargs):
        async def _it():
            yield ChatToken(text="Sharpe was 0.83 <cite source=\"backtest\"/>.")
            yield ChatDone(finish_reason="stop")
        async for e in _it():
            yield e

    gateway = MagicMock()
    gateway.is_enabled = True
    gateway.chat_completion_with_tools = _stream

    with patch("app.services.chat_guardrails.get_llm_gateway", return_value=gateway):
        result = await attempt_citation_reprompt(
            messages=[{"role": "user", "content": "what was AAPL Sharpe"}],
            response_text="Sharpe was 0.83.",
            uncited=["0.83"],
        )

    assert result is not None
    assert "<cite" in result


@pytest.mark.asyncio
async def test_citation_reprompt_returns_none_when_llm_disabled():
    gateway = MagicMock()
    gateway.is_enabled = False

    with patch("app.services.chat_guardrails.get_llm_gateway", return_value=gateway):
        result = await attempt_citation_reprompt(
            messages=[], response_text="0.83.", uncited=["0.83"],
        )

    assert result is None


@pytest.mark.asyncio
async def test_citation_reprompt_returns_none_when_rewrite_still_uncited():
    """LLM rewrites but the rewrite ALSO lacks citations → fail (no retry).
    Caller falls back to append_redaction_warning."""
    async def _stream(**_kwargs):
        async def _it():
            yield ChatToken(text="Still 0.83 without citation.")
            yield ChatDone(finish_reason="stop")
        async for e in _it():
            yield e

    gateway = MagicMock()
    gateway.is_enabled = True
    gateway.chat_completion_with_tools = _stream

    with patch("app.services.chat_guardrails.get_llm_gateway", return_value=gateway):
        result = await attempt_citation_reprompt(
            messages=[], response_text="0.83.", uncited=["0.83"],
        )

    assert result is None


# ── End-to-end guardrails behavior via chat endpoint ─────────────────────────


@pytest.mark.asyncio
async def test_guardrails_emit_refusal_event_when_assistant_refuses(db: Session, caplog):
    """Direct call to _apply_guardrails — the integration into the chat
    endpoint is exercised in test_chat_endpoint.py via the loop. Here we
    verify the guardrail's own contract: a canonical refusal text produces
    a chat_refusal log line + a `guardrail` SSE frame."""
    import logging

    from app.api.routes.chat import _apply_guardrails

    # Seed a conversation + assistant row so the DB-update branch has
    # something to read/write.
    conv = ChatConversation(
        id="conv-refuse", user_id="u1", anon_session_id=None, title="x",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.add(ChatMessage(
        id="m1", conversation_id="conv-refuse", role="assistant",
        content="I can't tell you whether to buy AAPL.",
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()

    caplog.set_level(logging.INFO, logger="livermore.chat.guardrails")

    frames: List[str] = []
    async for frame in _apply_guardrails(
        db=db,
        conversation_id="conv-refuse",
        messages=[],
        response_text="I can't tell you whether to buy AAPL.",
        tool_names_used=[],  # no tools → citation check skipped
        user_id="u1",
        anon_session_id=None,
        tier="scout",
        user_message="should I buy AAPL?",
    ):
        frames.append(frame)

    # Refusal classification fired
    refusal_logs = [r for r in caplog.records if "chat_refusal" in r.getMessage()]
    assert len(refusal_logs) == 1
    assert "personalized_advice" in refusal_logs[0].getMessage()
    # And the SSE frame surfaced it
    assert any("refusal_logged" in f for f in frames)
    assert any("personalized_advice" in f for f in frames)


@pytest.mark.asyncio
async def test_guardrails_skip_citation_check_when_no_tools_used(db: Session, caplog):
    """No tools used this turn → citation enforcement is a no-op, even if
    the text has uncited numerics (those would be general-knowledge claims,
    not tool-grounded)."""
    import logging

    from app.api.routes.chat import _apply_guardrails

    caplog.set_level(logging.WARNING, logger="livermore.chat.guardrails")

    frames: List[str] = []
    async for frame in _apply_guardrails(
        db=db,
        conversation_id="conv-no-tools",
        messages=[],
        response_text="The Sharpe ratio is approximately 0.83 historically.",
        tool_names_used=[],  # the trigger — no tools → skip
        user_id="u1",
        anon_session_id=None,
        tier="scout",
        user_message="what's a typical sharpe",
    ):
        frames.append(frame)

    # No numeric_uncited log expected
    assert not any("numeric_uncited" in r.getMessage() for r in caplog.records)
    assert frames == []


# ── Job entry points (smoke) ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_job_no_op_when_llm_disabled(caplog):
    """The auditor job must short-circuit gracefully when no LLM is configured —
    otherwise it would hang the scheduler. Verify it logs + returns."""
    import logging

    from app.jobs.qa_jobs import audit_chat_responses_job

    gateway = MagicMock()
    gateway.is_enabled = False

    caplog.set_level(logging.INFO, logger="app.jobs.qa_jobs")
    with patch("app.services.llm_adapter.get_llm_gateway", return_value=gateway):
        await audit_chat_responses_job()

    assert any("CHAT_AUDIT skipped" in r.getMessage() for r in caplog.records)


def test_digest_job_emits_heartbeat(caplog):
    """The weekly digest is a stub for v1 — it logs an aggregation command
    rather than emailing. Verify the log line lands."""
    import logging

    from app.jobs.qa_jobs import chat_guardrails_digest_job

    caplog.set_level(logging.INFO, logger="app.jobs.qa_jobs")
    chat_guardrails_digest_job()

    assert any("CHAT_DIGEST" in r.getMessage() for r in caplog.records)
