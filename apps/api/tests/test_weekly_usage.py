"""Stage 1a — weekly_usage table and helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.weekly_usage import WeeklyUsage
from app.services.entitlements import (
    get_current_week_start_utc,
    get_or_create_current_weekly_usage,
    increment_custom_backtest,
    increment_template_backtest,
)


def test_week_start_is_monday_utc() -> None:
    week_start = get_current_week_start_utc()
    assert week_start.weekday() == 0  # 0 = Monday


def test_week_start_is_today_or_earlier() -> None:
    week_start = get_current_week_start_utc()
    today = datetime.utcnow().date()
    assert week_start <= today
    assert (today - week_start).days <= 6


def test_increment_creates_row_on_first_call(make_user, db: Session) -> None:
    user = make_user(email="first@test.com")
    assert db.query(WeeklyUsage).filter_by(user_id=user.id).count() == 0

    new_count = increment_custom_backtest(db, user.id)
    assert new_count == 1
    rows = db.query(WeeklyUsage).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert rows[0].custom_backtest_runs == 1
    assert rows[0].template_backtest_runs == 0
    assert rows[0].backtest_runs == 1


def test_increment_idempotent_within_same_week(make_user, db: Session) -> None:
    """Three increments in the same week should NOT create three rows."""
    user = make_user(email="same@test.com")
    increment_custom_backtest(db, user.id)
    increment_custom_backtest(db, user.id)
    increment_custom_backtest(db, user.id)

    rows = db.query(WeeklyUsage).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert rows[0].custom_backtest_runs == 3


def test_new_week_creates_new_row(make_user, db: Session) -> None:
    """A row from a previous week does not satisfy get_or_create for this week."""
    user = make_user(email="newweek@test.com")
    past_week = get_current_week_start_utc() - timedelta(weeks=2)
    db.add(WeeklyUsage(user_id=user.id, week_start=past_week, custom_backtest_runs=5))
    db.commit()

    increment_custom_backtest(db, user.id)
    rows = db.query(WeeklyUsage).filter_by(user_id=user.id).order_by(WeeklyUsage.week_start).all()
    assert len(rows) == 2
    assert rows[0].week_start == past_week
    assert rows[1].week_start == get_current_week_start_utc()
    assert rows[1].custom_backtest_runs == 1


def test_template_and_custom_counters_independent(make_user, db: Session) -> None:
    """Template runs must NOT decrement the custom-strategy quota — Stage 1a invariant."""
    user = make_user(email="split@test.com")
    increment_template_backtest(db, user.id)
    increment_template_backtest(db, user.id)
    increment_custom_backtest(db, user.id)

    row = get_or_create_current_weekly_usage(db, user.id)
    assert row.custom_backtest_runs == 1
    assert row.template_backtest_runs == 2
    assert row.backtest_runs == 3  # total = custom + template


def test_monthly_legacy_counter_still_bumped(make_user, db: Session) -> None:
    """Stage 2 reports still read monthly_usage; weekly increment must keep it populated."""
    from app.services.entitlements import get_or_create_current_usage

    user = make_user(email="legacy@test.com")
    increment_custom_backtest(db, user.id)
    increment_template_backtest(db, user.id)

    monthly = get_or_create_current_usage(db, user.id)
    assert monthly.backtest_runs == 2


def test_get_or_create_idempotent(make_user, db: Session) -> None:
    user = make_user(email="idem-weekly@test.com")
    row1 = get_or_create_current_weekly_usage(db, user.id)
    row2 = get_or_create_current_weekly_usage(db, user.id)
    assert row1.user_id == row2.user_id
    assert row1.week_start == row2.week_start
