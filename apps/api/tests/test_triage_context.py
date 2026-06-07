"""Tests for the triage context bundle (PR-D).

Pins:
  - The keyword → trap matcher returns the right trap numbers for the
    error strings we see most often in production
  - The composer renders required sections + omits no-data gracefully
  - The `/internal/triage-context` endpoint enforces the token gate
    (403 when not configured, 401 on wrong token, 200 + markdown on
    correct token)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.triage_context_service import (
    _match_traps_for_error,
    compose_triage_context,
)


# ── trap matcher ─────────────────────────────────────────────────────────────


def test_matcher_detects_cross_loop_lock_as_trap_22():
    """The 2026-06-07 actual error string must surface trap #22."""
    err = "RuntimeError: <asyncio.locks.Lock ...> is bound to a different event loop"
    matches = _match_traps_for_error(err)
    nums = {n for n, _ in matches}
    assert 22 in nums, f"expected trap #22 in matches; got {matches}"


def test_matcher_detects_response_validation_as_trap_7():
    """Pydantic v2 ResponseValidationError → trap #7 (FastAPI 0.115 strictness)."""
    err = "fastapi.exceptions.ResponseValidationError: 1 validation errors: string_type"
    matches = _match_traps_for_error(err)
    nums = {n for n, _ in matches}
    assert 7 in nums


def test_matcher_detects_postgres_wedge_as_trap_11():
    """'Waiting for application startup.' is the trap #11 fingerprint."""
    err = "Container hung at Waiting for application startup."
    matches = _match_traps_for_error(err)
    nums = {n for n, _ in matches}
    assert 11 in nums


def test_matcher_returns_empty_for_unknown_error():
    """No keyword match → empty list. The composer falls back to a
    "read the trap catalog top-to-bottom" hint."""
    assert _match_traps_for_error("totally unrelated error string") == []
    assert _match_traps_for_error(None) == []
    assert _match_traps_for_error("") == []


def test_matcher_deduplicates_by_trap_number():
    """Same trap number must appear at most once even if multiple
    keywords match — keeps the prompt readable."""
    err = "RuntimeError ... bound to a different event loop"
    matches = _match_traps_for_error(err)
    nums = [n for n, _ in matches]
    assert nums.count(22) == 1, f"trap #22 should appear once; got {nums}"


# ── composer ─────────────────────────────────────────────────────────────────


def _make_payload(status="degraded", age_seconds=2300, fails=5, error="RuntimeError: cross-loop lock"):
    return {
        "status": status,
        "pulse_warmup": {
            "healthy": status == "ok",
            "last_success_at": "2026-06-07T13:00:00+00:00",
            "age_seconds": age_seconds,
            "consecutive_failures": fails,
            "last_error": error,
        },
    }


def test_composer_renders_required_sections():
    """The output must contain the headline + age + last_error + suspected
    trap + 'Your task' rubric. Anything else is bonus; these are the load-
    bearing parts the agent uses."""
    md = compose_triage_context(_make_payload())

    assert "/health" in md and "DEGRADED" in md
    assert "Last successful warmup tick" in md
    assert "RuntimeError" in md
    assert "Suspected traps" in md
    assert "Trap #22" in md, "the cross-loop error should map to trap #22 in the prompt"
    assert "Recent commits" in md
    assert "Your task" in md
    assert "Do NOT push code" in md  # discipline reminder must survive


def test_composer_handles_missing_error_gracefully():
    """Empty last_error → '(no keyword matches — read … top-to-bottom)'."""
    md = compose_triage_context(_make_payload(error=None))
    assert "(no keyword matches" in md


def test_composer_handles_status_ok_gracefully():
    """If somehow called when status=ok, the bundle still renders (degraded
    headline becomes 'OK'). Useful for manual testing pre-incident."""
    md = compose_triage_context(_make_payload(status="ok", age_seconds=60, fails=0, error=None))
    assert "OK" in md


# ── endpoint ─────────────────────────────────────────────────────────────────


def test_endpoint_403_when_token_not_configured(monkeypatch):
    """No token configured → 403. Refuses to expose the bundle silently."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ops_triage_token", "")
    client = TestClient(app)
    r = client.get("/internal/triage-context?token=anything")
    assert r.status_code == 403
    assert "triage_token_not_configured" in r.text


def test_endpoint_401_on_wrong_token(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ops_triage_token", "secret-good")
    client = TestClient(app)
    r = client.get("/internal/triage-context?token=secret-wrong")
    assert r.status_code == 401


def test_endpoint_200_returns_markdown_with_correct_token(monkeypatch):
    """Correct token → 200 + markdown content-type + triage body."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ops_triage_token", "secret-good")
    client = TestClient(app)
    with patch(
        "app.main.compute_health_state", return_value=_make_payload(),
    ):
        r = client.get("/internal/triage-context?token=secret-good")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "Livermore triage" in r.text
    assert "Trap #22" in r.text
