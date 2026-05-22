"""Stage 8 v0 Phase A — signal routes.

Exercises the handler functions directly with the `db` and `make_user`
fixtures from conftest. Mirrors the project's TestClient-free style.

Covers acceptance §10:
  #1  first-compute returns null state (cron-populated in Phase B)
  #6  subscribe is idempotent; unsubscribe deletes the row
  #8  acknowledge updates the timestamp
  (+) feature-flag enforcement: router absent when settings.signal_alerts_enabled=False
  (+) ownership: 404 when a different user requests another user's strategy signal
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.signals import (
    acknowledge_signal,
    get_signal,
    subscribe_signal,
    unsubscribe_signal,
)
from app.core.config import get_settings
from app.models.saved_strategy import SavedStrategy
from app.models.signal_alert_subscription import SignalAlertSubscription
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


# ── GET /signal ──────────────────────────────────────────────────────────────


def test_get_signal_returns_null_state_before_first_cron(make_user, db: Session) -> None:
    user = make_user(email="get-signal@test.com")
    strategy = _save_strategy(db, user)

    resp = get_signal(strategy.id, current_user=user, db=db)
    assert resp.current_signal is None
    assert resp.current_signal_display is None
    assert resp.subscription_active is False
    assert resp.recent_events == []


def test_get_signal_404s_for_non_owner(make_user, db: Session) -> None:
    owner = make_user(email="owner@test.com")
    intruder = make_user(email="intruder@test.com")
    strategy = _save_strategy(db, owner)

    with pytest.raises(HTTPException) as exc_info:
        get_signal(strategy.id, current_user=intruder, db=db)
    assert exc_info.value.status_code == 404


def test_get_signal_404s_for_missing_strategy(make_user, db: Session) -> None:
    user = make_user(email="missing-strategy@test.com")
    with pytest.raises(HTTPException) as exc_info:
        get_signal("does-not-exist", current_user=user, db=db)
    assert exc_info.value.status_code == 404


# ── POST /signal/subscribe + DELETE /signal/subscribe ────────────────────────


def test_subscribe_creates_row(make_user, db: Session) -> None:
    user = make_user(email="sub-create@test.com")
    strategy = _save_strategy(db, user)

    resp = subscribe_signal(strategy.id, current_user=user, db=db)
    assert resp.subscription_active is True

    sub = db.get(SignalAlertSubscription, (user.id, strategy.id))
    assert sub is not None
    assert sub.email_enabled is True


def test_subscribe_is_idempotent(make_user, db: Session) -> None:
    """Re-toggling on twice must produce exactly one subscription row (§10 #6)."""
    user = make_user(email="sub-idem@test.com")
    strategy = _save_strategy(db, user)

    subscribe_signal(strategy.id, current_user=user, db=db)
    subscribe_signal(strategy.id, current_user=user, db=db)

    count = (
        db.query(SignalAlertSubscription)
        .filter(
            SignalAlertSubscription.user_id == user.id,
            SignalAlertSubscription.saved_strategy_id == strategy.id,
        )
        .count()
    )
    assert count == 1


def test_unsubscribe_deletes_row(make_user, db: Session) -> None:
    user = make_user(email="unsub@test.com")
    strategy = _save_strategy(db, user)
    subscribe_signal(strategy.id, current_user=user, db=db)

    unsubscribe_signal(strategy.id, current_user=user, db=db)

    sub = db.get(SignalAlertSubscription, (user.id, strategy.id))
    assert sub is None


def test_unsubscribe_is_noop_when_not_subscribed(make_user, db: Session) -> None:
    user = make_user(email="unsub-noop@test.com")
    strategy = _save_strategy(db, user)

    resp = unsubscribe_signal(strategy.id, current_user=user, db=db)
    assert resp.status_code == 204


def test_subscribe_404s_for_non_owner(make_user, db: Session) -> None:
    owner = make_user(email="sub-owner@test.com")
    intruder = make_user(email="sub-intruder@test.com")
    strategy = _save_strategy(db, owner)

    with pytest.raises(HTTPException) as exc_info:
        subscribe_signal(strategy.id, current_user=intruder, db=db)
    assert exc_info.value.status_code == 404


# ── POST /signal/acknowledge ─────────────────────────────────────────────────


def test_acknowledge_updates_last_acted_at(make_user, db: Session) -> None:
    user = make_user(email="ack@test.com")
    strategy = _save_strategy(db, user)
    subscribe_signal(strategy.id, current_user=user, db=db)

    resp = acknowledge_signal(strategy.id, current_user=user, db=db)
    assert resp.last_acted_at is not None

    sub = db.get(SignalAlertSubscription, (user.id, strategy.id))
    assert sub.last_acted_at == resp.last_acted_at


def test_acknowledge_409s_without_subscription(make_user, db: Session) -> None:
    """Acknowledging requires an active subscription — the UI surfaces the button
    only when subscribed, but the backend enforces it independently."""
    user = make_user(email="ack-no-sub@test.com")
    strategy = _save_strategy(db, user)

    with pytest.raises(HTTPException) as exc_info:
        acknowledge_signal(strategy.id, current_user=user, db=db)
    assert exc_info.value.status_code == 409


# ── Feature-flag enforcement ─────────────────────────────────────────────────


def test_feature_flag_defaults_to_false() -> None:
    """Production safety: routes must be absent unless the operator explicitly
    flips signal_alerts_enabled. Disclaimer copy still requires lawyer review
    (build_specs/research_execution_v0_signals_and_alerts.md §11, §15)."""
    # Clear the lru_cache so we observe the actual default rather than a
    # value cached by an earlier test process.
    get_settings.cache_clear()
    assert get_settings().signal_alerts_enabled is False
