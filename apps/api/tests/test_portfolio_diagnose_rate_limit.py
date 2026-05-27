"""PRD-13b — per-tier hourly rate-limit on /api/portfolio/diagnose.

Direct tests of `increment_portfolio_diagnose_run`,
`get_portfolio_diagnose_runs_used`, and the route's enforce helper.
Uses the conftest `db` fixture (fresh in-memory SQLite per test).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.routes import portfolio as portfolio_route
from app.models.user import User, Plan
from app.services.entitlements import (
    PORTFOLIO_DIAGNOSE_HOURLY_CAPS,
    get_or_create_current_weekly_usage,
    get_portfolio_diagnose_runs_used,
    increment_portfolio_diagnose_run,
)


def _make_user(db, user_id: str, tier: str = "scout") -> User:
    user = User(id=user_id, email=f"{user_id}@test.local", locale="en")
    db.add(user)
    db.add(Plan(user_id=user_id, tier=tier, status="active"))
    db.commit()
    db.refresh(user)
    return user


def test_increment_starts_at_one_then_two(db):
    user = _make_user(db, "rate-1")
    assert get_portfolio_diagnose_runs_used(db, user.id) == 0
    assert increment_portfolio_diagnose_run(db, user.id) == 1
    assert increment_portfolio_diagnose_run(db, user.id) == 2
    assert get_portfolio_diagnose_runs_used(db, user.id) == 2


def test_counter_resets_when_hour_rolls(db):
    user = _make_user(db, "rate-2")
    increment_portfolio_diagnose_run(db, user.id)
    increment_portfolio_diagnose_run(db, user.id)
    assert get_portfolio_diagnose_runs_used(db, user.id) == 2

    # Manually age the row so last_reset_hour is in the previous hour.
    row = get_or_create_current_weekly_usage(db, user.id)
    row.last_reset_hour = datetime.utcnow() - timedelta(hours=2)
    db.commit()

    # Reading now (current hour) → reports 0.
    assert get_portfolio_diagnose_runs_used(db, user.id) == 0
    # Next increment resets the counter to 1.
    assert increment_portfolio_diagnose_run(db, user.id) == 1


def test_scout_cap_blocks_after_5(db):
    user = _make_user(db, "rate-scout", tier="scout")
    cap = PORTFOLIO_DIAGNOSE_HOURLY_CAPS["scout"]
    for _ in range(cap):
        increment_portfolio_diagnose_run(db, user.id)
    # The enforce helper raises 402 when the cap is reached.
    with pytest.raises(HTTPException) as excinfo:
        portfolio_route._enforce_diagnose_rate_limit(db, user.id, "scout")
    assert excinfo.value.status_code == 402
    detail = excinfo.value.detail
    code = detail["entitlement"]["code"] if isinstance(detail, dict) else None
    assert code == "portfolio_diagnose_rate_limit"


def test_strategist_higher_cap(db):
    user = _make_user(db, "rate-strategist", tier="strategist")
    # 5 increments is below the strategist 50/h cap.
    for _ in range(5):
        increment_portfolio_diagnose_run(db, user.id)
    # Strategist must NOT be rate-limited here.
    portfolio_route._enforce_diagnose_rate_limit(db, user.id, "strategist")


def test_quant_effectively_unlimited(db):
    user = _make_user(db, "rate-quant", tier="quant")
    for _ in range(100):
        increment_portfolio_diagnose_run(db, user.id)
    portfolio_route._enforce_diagnose_rate_limit(db, user.id, "quant")
