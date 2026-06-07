"""Tests for the `/health` warmup freshness signal.

**Why this exists.** The 2026-06-07 outage failed every warmup tick for
28+ minutes. The only signal was `logger.exception` lines nobody was
watching. Trap #20 had already taught us "log exceptions, not warnings,"
but `logger.exception` in a log nobody scrapes is functionally invisible.

PR-A surfaces warmup failures on `/health` as a programmatic signal — a
one-minute external scraper now flips to "degraded" within ~12 minutes of
the first tick failure (3 consecutive 4-min ticks). PR-C will wire that
into the email alerter so Jimmy gets paged before users see breakage.

These tests pin the post-fix invariants:
  - The warmup state updates on success (resets `consecutive_failures`,
    clears `last_error`, stamps `last_success_at` in UTC)
  - The warmup state updates on failure (increments counter, captures
    a one-line error summary)
  - `/health` reports `status: "ok"` and `pulse_warmup.healthy: true`
    when warmup is fresh + has no consecutive failures
  - `/health` flips to `status: "degraded"` when warmup is stale OR
    consecutive_failures crosses the threshold OR never succeeded yet
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import (
    _PULSE_WARMUP_MAX_AGE_SECONDS,
    _PULSE_WARMUP_MAX_FAILURES,
    _pulse_warmup_state,
    _record_pulse_warmup_failure,
    _record_pulse_warmup_success,
    app,
)


@pytest.fixture(autouse=True)
def _reset_warmup_state():
    """Each test starts from a clean warmup state so prior tests don't leak in."""
    snapshot = dict(_pulse_warmup_state)
    _pulse_warmup_state["last_success_at"] = None
    _pulse_warmup_state["consecutive_failures"] = 0
    _pulse_warmup_state["last_error"] = None
    yield
    _pulse_warmup_state.update(snapshot)


def test_record_success_stamps_utc_timestamp_and_resets_failures() -> None:
    """Success must zero `consecutive_failures`, clear `last_error`, and
    stamp `last_success_at` as a tz-aware UTC datetime."""
    _pulse_warmup_state["consecutive_failures"] = 5
    _pulse_warmup_state["last_error"] = "RuntimeError: previous"

    before = datetime.now(timezone.utc)
    _record_pulse_warmup_success()
    after = datetime.now(timezone.utc)

    ts = _pulse_warmup_state["last_success_at"]
    assert ts is not None
    assert ts.tzinfo is not None, "last_success_at must be tz-aware (UTC) — "
    assert before <= ts <= after
    assert _pulse_warmup_state["consecutive_failures"] == 0
    assert _pulse_warmup_state["last_error"] is None


def test_record_failure_increments_counter_and_captures_error() -> None:
    """Failure must NOT touch `last_success_at` (the staleness signal),
    must increment `consecutive_failures`, and must capture a one-line
    error summary (full traceback already lives in the log)."""
    prior_success = datetime.now(timezone.utc) - timedelta(seconds=120)
    _pulse_warmup_state["last_success_at"] = prior_success
    _pulse_warmup_state["consecutive_failures"] = 1

    exc = RuntimeError("the 2026-06-07 cross-loop lock thing")
    _record_pulse_warmup_failure(exc)

    assert _pulse_warmup_state["consecutive_failures"] == 2
    assert _pulse_warmup_state["last_success_at"] == prior_success, (
        "last_success_at must not be touched on failure — that's the "
        "staleness signal /health reads to detect 'haven't seen a good "
        "tick in N minutes'"
    )
    assert _pulse_warmup_state["last_error"] is not None
    assert "RuntimeError" in _pulse_warmup_state["last_error"]
    assert "2026-06-07" in _pulse_warmup_state["last_error"]


def test_health_reports_healthy_when_warmup_fresh() -> None:
    """Recent successful tick + zero consecutive failures → `status: ok`,
    `pulse_warmup.healthy: true`."""
    _pulse_warmup_state["last_success_at"] = datetime.now(timezone.utc) - timedelta(seconds=60)
    _pulse_warmup_state["consecutive_failures"] = 0
    _pulse_warmup_state["last_error"] = None

    client = TestClient(app)
    r = client.get("/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["pulse_warmup"]["healthy"] is True
    assert body["pulse_warmup"]["age_seconds"] is not None
    assert body["pulse_warmup"]["age_seconds"] < 120  # ~60s give or take
    assert body["pulse_warmup"]["consecutive_failures"] == 0
    assert body["pulse_warmup"]["last_error"] is None
    # Thresholds surfaced so external scrapers don't have to hardcode them
    assert body["pulse_warmup"]["thresholds"]["max_age_seconds"] == _PULSE_WARMUP_MAX_AGE_SECONDS
    assert body["pulse_warmup"]["thresholds"]["max_consecutive_failures"] == _PULSE_WARMUP_MAX_FAILURES


def test_health_reports_degraded_when_warmup_stale() -> None:
    """Last successful tick > max_age_seconds → `status: degraded`,
    `pulse_warmup.healthy: false`. Simulates the 2026-06-04-style scenario
    where the warmup loop died silently and `last_success_at` ages out."""
    _pulse_warmup_state["last_success_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=_PULSE_WARMUP_MAX_AGE_SECONDS + 60)
    )
    _pulse_warmup_state["consecutive_failures"] = 0  # not failing — just silent

    client = TestClient(app)
    r = client.get("/health")

    body = r.json()
    assert body["status"] == "degraded"
    assert body["pulse_warmup"]["healthy"] is False
    assert body["pulse_warmup"]["age_seconds"] > _PULSE_WARMUP_MAX_AGE_SECONDS


def test_health_reports_degraded_after_threshold_consecutive_failures() -> None:
    """Simulates the 2026-06-07 pattern: tick fires every 4 min and fails
    every time. After `_PULSE_WARMUP_MAX_FAILURES` ticks, `/health` flips
    to degraded — even if the most recent ATTEMPT was just now."""
    _pulse_warmup_state["last_success_at"] = datetime.now(timezone.utc) - timedelta(seconds=120)
    _pulse_warmup_state["consecutive_failures"] = _PULSE_WARMUP_MAX_FAILURES
    _pulse_warmup_state["last_error"] = "RuntimeError: cross-loop lock"

    client = TestClient(app)
    r = client.get("/health")

    body = r.json()
    assert body["status"] == "degraded"
    assert body["pulse_warmup"]["healthy"] is False
    assert body["pulse_warmup"]["consecutive_failures"] >= _PULSE_WARMUP_MAX_FAILURES
    assert "RuntimeError" in body["pulse_warmup"]["last_error"]


def test_health_reports_degraded_when_warmup_never_ran() -> None:
    """Fresh container, warmup never completed its first tick — `/health`
    reports degraded with `age_seconds: null`. Avoids the boot window
    looking healthy when in fact we have no signal yet.

    Tradeoff: the first ~30s after deploy will report degraded. That's
    fine — Railway uses container status to route traffic, not this field.
    External scrapers can ignore the alert for the first few minutes of
    each deploy.
    """
    _pulse_warmup_state["last_success_at"] = None
    _pulse_warmup_state["consecutive_failures"] = 0
    _pulse_warmup_state["last_error"] = None

    client = TestClient(app)
    r = client.get("/health")

    body = r.json()
    assert body["status"] == "degraded"
    assert body["pulse_warmup"]["healthy"] is False
    assert body["pulse_warmup"]["age_seconds"] is None
    assert body["pulse_warmup"]["last_success_at"] is None
