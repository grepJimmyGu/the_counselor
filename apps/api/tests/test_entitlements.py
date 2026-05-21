"""Unit tests for the Stage 1a entitlements resolver (no HTTP layer)."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services.entitlements import (
    TIER_CAPS,
    get_entitlements,
    get_or_create_current_weekly_usage,
    increment_custom_backtest,
    increment_template_backtest,
)


def test_scout_caps(make_user, db: Session) -> None:
    user = make_user(email="scout@test.com", tier="scout")
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)

    assert ents.tier == "scout"
    assert ents.universe_size_max_custom == 5
    assert ents.history_window_years_custom == 5
    assert ents.custom_backtest_runs_remaining == 5
    assert ents.template_runs_unlimited is True
    assert ents.commodity_framework is False
    assert ents.robustness_tests == []
    assert ents.saved_strategies_max == 10
    assert ents.saved_strategies_always_public is True


def test_custom_runs_remaining_decrements(make_user, db: Session) -> None:
    user = make_user(email="scout2@test.com", tier="scout")
    increment_custom_backtest(db, user.id)
    increment_custom_backtest(db, user.id)
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)

    assert ents.custom_backtest_runs_remaining == 3  # 5 - 2


def test_template_runs_do_not_decrement_custom_quota(make_user, db: Session) -> None:
    """Critical: template runs are unlimited for all tiers — they must not
    count against the Scout's 5 weekly custom runs."""
    user = make_user(email="templator@test.com", tier="scout")
    for _ in range(10):
        increment_template_backtest(db, user.id)

    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)
    assert ents.custom_backtest_runs_remaining == 5  # untouched by template runs
    assert weekly.template_backtest_runs == 10
    assert weekly.custom_backtest_runs == 0


def test_runs_remaining_unlimited_for_paid(make_user, db: Session) -> None:
    for tier in ("strategist", "quant"):
        user = make_user(email=f"{tier}@test.com", tier=tier)
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ents = get_entitlements(user, weekly)
        assert ents.custom_backtest_runs_remaining is None, f"{tier} should be unlimited"


def test_custom_runs_never_negative(make_user, db: Session) -> None:
    user = make_user(email="over@test.com", tier="scout")
    for _ in range(10):
        increment_custom_backtest(db, user.id)
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)
    assert ents.custom_backtest_runs_remaining == 0


def test_quant_caps(make_user, db: Session) -> None:
    user = make_user(email="quant@test.com", tier="quant")
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)

    assert ents.universe_size_max_custom == 100
    assert "a_shares" in ents.asset_classes
    assert "peer_ticker" in ents.robustness_tests
    assert ents.community_badge == "verified"
    assert ents.saved_strategies_always_public is False


def test_strategist_caps(make_user, db: Session) -> None:
    user = make_user(email="strat@test.com", tier="strategist")
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)

    assert ents.universe_size_max_custom == 25
    assert ents.history_window_years_custom == 10
    assert ents.saved_strategies_max == 25
    assert ents.saved_strategies_always_public is False
    assert ents.commodity_framework is True
    assert "parameter_sensitivity" in ents.robustness_tests
    assert "benchmark_comparison" in ents.robustness_tests
    assert "subperiod" not in ents.robustness_tests  # quant-only


def test_no_api_access_field(make_user, db: Session) -> None:
    """api_access was removed in Stage 1a — no tier should expose it."""
    user = make_user(email="noapi@test.com", tier="quant")
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)
    assert not hasattr(ents, "api_access")


def test_tier_caps_dict_has_no_api_access():
    for tier_name, caps in TIER_CAPS.items():
        assert "api_access" not in caps, f"{tier_name} still exposes api_access"


def test_week_start_is_iso_date(make_user, db: Session) -> None:
    """week_start is an ISO-format date string the frontend can parse."""
    from datetime import date

    user = make_user(email="iso@test.com")
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ents = get_entitlements(user, weekly)
    parsed = date.fromisoformat(ents.week_start)
    assert parsed.weekday() == 0  # Monday


def test_weekly_get_or_create_idempotent(make_user, db: Session) -> None:
    user = make_user(email="idem@test.com")
    row1 = get_or_create_current_weekly_usage(db, user.id)
    row2 = get_or_create_current_weekly_usage(db, user.id)
    assert row1.user_id == row2.user_id
    assert row1.week_start == row2.week_start
