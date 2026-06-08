"""PRD-19 — Mark-as-Executed endpoint.

Exercises `POST /api/saved-strategies/{strategy_id}/mark-executed` by
invoking the handler directly with `db` + `make_user` fixtures (mirrors
the project's TestClient-free style — see test_signal_routes.py).

Covers:
  - happy path: writes row, returns latency_seconds, idempotent=False
  - idempotency: second click returns the same row, idempotent=True
  - 404 when strategy missing
  - 404 when strategy belongs to a different user (same message as missing
    — does not leak strategy existence to non-owners)
  - 404 when no SignalEvent exists for the strategy yet
  - latency_seconds is non-negative even when clocks momentarily disagree
  - PostHog `notification_executed` event captured on the happy path,
    NOT on the idempotent path (avoids inflating the retention metric)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.saved_strategies import (
    MarkAsExecutedRequest,
    mark_strategy_executed,
)
from app.models.mark_as_executed_event import MarkAsExecutedEvent
from app.models.saved_strategy import SavedStrategy
from app.models.signal_event import SignalEvent
from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest


def _save_strategy(db: Session, user) -> SavedStrategy:
    return saved_strategy_service.save_strategy(
        db,
        user,
        SaveStrategyRequest(
            title="MA filter on NVDA",
            strategy_json={"strategy_type": "moving_average_filter", "universe": ["NVDA"]},
        ),
    )


def _emit_signal_event(
    db: Session,
    strategy: SavedStrategy,
    *,
    created_at: datetime | None = None,
) -> SignalEvent:
    """Synthesize a flip-to-cash SignalEvent so mark-executed has something
    to attest. In production the cron writes these; tests do it inline."""
    evt = SignalEvent(
        id=str(uuid4()),
        saved_strategy_id=strategy.id,
        previous_signal={"action": "long", "weights": {"NVDA": 1.0}},
        previous_signal_display="Long NVDA",
        new_signal={"action": "cash", "weights": {}},
        new_signal_display="Move to cash",
        change_type="flip_to_cash",
        as_of_date=datetime.utcnow().date(),
        reference_price_snapshot={"NVDA": 145.23},
        created_at=created_at or datetime.utcnow(),
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return evt


# ── Happy path ───────────────────────────────────────────────────────────────


def test_mark_executed_writes_row_and_returns_latency(make_user, db: Session) -> None:
    user = make_user(email="mark-happy@test.com")
    strategy = _save_strategy(db, user)
    # SignalEvent created 5 minutes ago — latency should be ~300s.
    signal = _emit_signal_event(
        db, strategy, created_at=datetime.utcnow() - timedelta(seconds=300)
    )

    resp = mark_strategy_executed(
        strategy.id,
        MarkAsExecutedRequest(user_note="Filled at 4:05 via Schwab"),
        current_user=user,
        db=db,
    )

    assert resp.ok is True
    assert resp.idempotent is False
    assert resp.signal_event_id == signal.id
    # ±15s slack — total_seconds is float; we round to int and the test
    # interval may not be exactly 300s due to wall-clock between setup
    # and the endpoint call.
    assert 285 <= resp.latency_seconds <= 360

    # Row persisted.
    row = (
        db.query(MarkAsExecutedEvent)
        .filter(MarkAsExecutedEvent.signal_event_id == signal.id)
        .one()
    )
    assert row.user_id == user.id
    assert row.saved_strategy_id == strategy.id
    assert row.user_note == "Filled at 4:05 via Schwab"


def test_mark_executed_without_user_note_persists_null(make_user, db: Session) -> None:
    user = make_user(email="no-note@test.com")
    strategy = _save_strategy(db, user)
    _emit_signal_event(db, strategy)

    mark_strategy_executed(
        strategy.id,
        MarkAsExecutedRequest(user_note=None),
        current_user=user,
        db=db,
    )

    row = db.query(MarkAsExecutedEvent).one()
    assert row.user_note is None


# ── Idempotency ──────────────────────────────────────────────────────────────


def test_mark_executed_is_idempotent_on_same_signal_event(make_user, db: Session) -> None:
    """Second click on the same notification → no new row, same data,
    `idempotent=True`. UNIQUE index on (user_id, signal_event_id) backs
    this, and the route handles the existing-row case gracefully."""
    user = make_user(email="idem@test.com")
    strategy = _save_strategy(db, user)
    _emit_signal_event(db, strategy)

    first = mark_strategy_executed(
        strategy.id,
        MarkAsExecutedRequest(user_note="first click"),
        current_user=user,
        db=db,
    )
    second = mark_strategy_executed(
        strategy.id,
        MarkAsExecutedRequest(user_note="second click — should not overwrite"),
        current_user=user,
        db=db,
    )

    assert first.idempotent is False
    assert second.idempotent is True
    assert second.executed_at == first.executed_at
    assert second.signal_event_id == first.signal_event_id

    # Exactly one row, with the FIRST user_note (idempotent does not overwrite).
    rows = db.query(MarkAsExecutedEvent).all()
    assert len(rows) == 1
    assert rows[0].user_note == "first click"


def test_mark_executed_new_signal_event_creates_new_row(make_user, db: Session) -> None:
    """If a NEW SignalEvent fires for the same strategy (e.g. the signal
    flipped back), the user can mark-executed again — that's a fresh
    attestation, not a duplicate."""
    user = make_user(email="two-signals@test.com")
    strategy = _save_strategy(db, user)
    first_signal = _emit_signal_event(
        db, strategy, created_at=datetime.utcnow() - timedelta(hours=2)
    )

    first = mark_strategy_executed(
        strategy.id, MarkAsExecutedRequest(), current_user=user, db=db
    )
    assert first.signal_event_id == first_signal.id

    # New signal flips → fresh notification → fresh attestation eligible.
    second_signal = _emit_signal_event(db, strategy)

    second = mark_strategy_executed(
        strategy.id, MarkAsExecutedRequest(), current_user=user, db=db
    )
    assert second.idempotent is False
    assert second.signal_event_id == second_signal.id
    assert db.query(MarkAsExecutedEvent).count() == 2


# ── Authorization ────────────────────────────────────────────────────────────


def test_mark_executed_404s_for_non_owner(make_user, db: Session) -> None:
    """Non-owners see the same 404 as a missing strategy — does not leak
    that the strategy exists. Same pattern as get_signal."""
    owner = make_user(email="owner-me@test.com")
    intruder = make_user(email="intruder-me@test.com")
    strategy = _save_strategy(db, owner)
    _emit_signal_event(db, strategy)

    with pytest.raises(HTTPException) as exc_info:
        mark_strategy_executed(
            strategy.id, MarkAsExecutedRequest(), current_user=intruder, db=db
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Strategy not found."

    # No write happened.
    assert db.query(MarkAsExecutedEvent).count() == 0


def test_mark_executed_404s_for_missing_strategy(make_user, db: Session) -> None:
    user = make_user(email="missing@test.com")
    with pytest.raises(HTTPException) as exc_info:
        mark_strategy_executed(
            "does-not-exist", MarkAsExecutedRequest(), current_user=user, db=db
        )
    assert exc_info.value.status_code == 404


def test_mark_executed_404s_when_no_signal_event_yet(make_user, db: Session) -> None:
    """A user saves a strategy but the cron hasn't fired yet, so no
    SignalEvent exists. Mark-executed has nothing to attest → 404 with
    a clear message (distinct from 'Strategy not found')."""
    user = make_user(email="no-signal@test.com")
    strategy = _save_strategy(db, user)

    with pytest.raises(HTTPException) as exc_info:
        mark_strategy_executed(
            strategy.id, MarkAsExecutedRequest(), current_user=user, db=db
        )
    assert exc_info.value.status_code == 404
    assert "No signal event" in exc_info.value.detail


def test_mark_executed_picks_LATEST_signal_event_not_earliest(
    make_user, db: Session
) -> None:
    """When multiple SignalEvents exist for a strategy, the endpoint
    attests against the *latest* — that's the one the user just got
    notified about. Earlier events stay un-marked unless re-attested
    explicitly (which the v1 API doesn't expose — by design)."""
    user = make_user(email="latest@test.com")
    strategy = _save_strategy(db, user)
    older = _emit_signal_event(
        db, strategy, created_at=datetime.utcnow() - timedelta(days=3)
    )
    newer = _emit_signal_event(
        db, strategy, created_at=datetime.utcnow() - timedelta(minutes=5)
    )

    resp = mark_strategy_executed(
        strategy.id, MarkAsExecutedRequest(), current_user=user, db=db
    )
    assert resp.signal_event_id == newer.id
    assert resp.signal_event_id != older.id


# ── PostHog capture ──────────────────────────────────────────────────────────


def test_mark_executed_captures_posthog_event_on_first_click(
    make_user, db: Session, monkeypatch
) -> None:
    """PRD-19 §7 — emit `notification_executed` to PostHog with
    `latency_seconds`. The capture is fire-and-forget; the test verifies
    the call shape and that errors don't break the endpoint."""
    captured: list[dict] = []

    def fake_ph_capture(*, user_id: str, event: str, properties: dict) -> None:
        captured.append({"user_id": user_id, "event": event, "properties": properties})

    # Patch the actual exported name (`capture`) — the route imports the
    # module and calls `posthog_service.capture(...)`.
    import app.services.posthog_service as ph_mod
    monkeypatch.setattr(ph_mod, "capture", fake_ph_capture)

    user = make_user(email="posthog@test.com")
    strategy = _save_strategy(db, user)
    _emit_signal_event(
        db, strategy, created_at=datetime.utcnow() - timedelta(seconds=120)
    )

    mark_strategy_executed(
        strategy.id,
        MarkAsExecutedRequest(user_note="acted"),
        current_user=user,
        db=db,
    )

    assert len(captured) == 1
    assert captured[0]["event"] == "notification_executed"
    assert captured[0]["user_id"] == user.id
    props = captured[0]["properties"]
    assert "latency_seconds" in props
    assert props["latency_seconds"] >= 0
    assert props["saved_strategy_id"] == strategy.id
    assert props["has_user_note"] is True


def test_mark_executed_does_NOT_capture_posthog_on_idempotent_click(
    make_user, db: Session, monkeypatch
) -> None:
    """Duplicate clicks must not re-fire PostHog — that would inflate the
    retention metric. Only the first click counts."""
    captured: list[dict] = []

    def fake_ph_capture(*, user_id: str, event: str, properties: dict) -> None:
        captured.append({"event": event})

    import app.services.posthog_service as ph_mod
    monkeypatch.setattr(ph_mod, "capture", fake_ph_capture)

    user = make_user(email="posthog-idem@test.com")
    strategy = _save_strategy(db, user)
    _emit_signal_event(db, strategy)

    mark_strategy_executed(strategy.id, MarkAsExecutedRequest(), current_user=user, db=db)
    mark_strategy_executed(strategy.id, MarkAsExecutedRequest(), current_user=user, db=db)

    assert len(captured) == 1  # only first click captured


def test_mark_executed_survives_posthog_failure(
    make_user, db: Session, monkeypatch
) -> None:
    """If PostHog raises (network down, misconfigured), the user's action
    must still complete and the DB row must still be written. DB is the
    metric's source of truth; PostHog is the dashboard view."""
    def angry_ph_capture(**kwargs):
        raise RuntimeError("PostHog is down")

    import app.services.posthog_service as ph_mod
    monkeypatch.setattr(ph_mod, "capture", angry_ph_capture)

    user = make_user(email="posthog-fail@test.com")
    strategy = _save_strategy(db, user)
    _emit_signal_event(db, strategy)

    resp = mark_strategy_executed(
        strategy.id, MarkAsExecutedRequest(), current_user=user, db=db
    )

    assert resp.ok is True
    # Row was still written.
    assert db.query(MarkAsExecutedEvent).count() == 1


# ── Latency edge case ────────────────────────────────────────────────────────


def test_latency_seconds_is_clamped_non_negative(make_user, db: Session) -> None:
    """If for any reason `signal_event.created_at > executed_at` (clock
    skew across containers, manual data insert), `latency_seconds` must
    not go negative — it would corrupt the retention histogram."""
    user = make_user(email="clamp@test.com")
    strategy = _save_strategy(db, user)
    # SignalEvent created 60 seconds in the FUTURE (clock skew simulation).
    _emit_signal_event(
        db, strategy, created_at=datetime.utcnow() + timedelta(seconds=60)
    )

    resp = mark_strategy_executed(
        strategy.id, MarkAsExecutedRequest(), current_user=user, db=db
    )
    assert resp.latency_seconds >= 0
