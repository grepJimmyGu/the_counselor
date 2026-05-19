"""Unit tests for the entitlements resolver (no HTTP layer)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.user import MonthlyUsage
from app.services.entitlements import (
    TIER_CAPS,
    get_entitlements,
    get_or_create_current_usage,
    increment_backtest_runs,
)


def test_scout_caps(make_user, db: Session) -> None:
    user = make_user(email="scout@test.com", tier="scout")
    usage = get_or_create_current_usage(db, user.id)
    ents = get_entitlements(user, usage)

    assert ents.tier == "scout"
    assert ents.universe_size_max == 5
    assert ents.history_window_years == 5
    assert ents.backtest_runs_remaining == 5
    assert ents.api_access is False
    assert ents.commodity_framework is False
    assert ents.robustness_tests == []


def test_runs_remaining_decrements(make_user, db: Session) -> None:
    user = make_user(email="scout2@test.com", tier="scout")
    increment_backtest_runs(db, user.id)
    increment_backtest_runs(db, user.id)
    usage = get_or_create_current_usage(db, user.id)
    ents = get_entitlements(user, usage)

    assert ents.backtest_runs_remaining == 3  # 5 - 2


def test_runs_remaining_unlimited_for_paid(make_user, db: Session) -> None:
    for tier in ("strategist", "quant"):
        user = make_user(email=f"{tier}@test.com", tier=tier)
        usage = get_or_create_current_usage(db, user.id)
        ents = get_entitlements(user, usage)
        assert ents.backtest_runs_remaining is None, f"{tier} should be unlimited"


def test_runs_never_negative(make_user, db: Session) -> None:
    """Runs remaining never goes below 0."""
    user = make_user(email="over@test.com", tier="scout")
    for _ in range(10):
        increment_backtest_runs(db, user.id)
    usage = get_or_create_current_usage(db, user.id)
    ents = get_entitlements(user, usage)
    assert ents.backtest_runs_remaining == 0


def test_new_month_resets_implicitly(make_user, db: Session) -> None:
    """Usage in a past month does not count against the current month."""
    user = make_user(email="monthly@test.com", tier="scout")

    # Manually insert a row for a previous month
    past = date(2024, 1, 1)
    db.add(MonthlyUsage(user_id=user.id, period_start=past, backtest_runs=5))
    db.commit()

    # Current month should start at 0
    usage = get_or_create_current_usage(db, user.id)
    ents = get_entitlements(user, usage)
    assert ents.backtest_runs_remaining == 5


def test_quant_caps(make_user, db: Session) -> None:
    user = make_user(email="quant@test.com", tier="quant")
    usage = get_or_create_current_usage(db, user.id)
    ents = get_entitlements(user, usage)

    assert ents.universe_size_max == 100
    assert ents.api_access is True
    assert "a_shares" in ents.asset_classes
    assert "peer_ticker" in ents.robustness_tests
    assert ents.community_badge == "verified"


def test_get_or_create_idempotent(make_user, db: Session) -> None:
    user = make_user(email="idem@test.com")
    row1 = get_or_create_current_usage(db, user.id)
    row2 = get_or_create_current_usage(db, user.id)
    assert row1.user_id == row2.user_id
    assert row1.period_start == row2.period_start
