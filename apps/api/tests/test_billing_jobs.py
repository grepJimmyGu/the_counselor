"""Tests for billing APScheduler jobs."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.jobs.billing_jobs import dunning_expiry_job, expire_trials_job
from app.models.user import Plan


def _plan_row(db: Session, user_id: str) -> dict:
    """Read plan columns via raw SQL — avoids ORM relationship lazy-loads after db.close()."""
    row = db.execute(
        text("SELECT tier, status, stripe_subscription_id FROM plans WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchone()
    assert row is not None
    return row._mapping  # type: ignore[return-value]


def test_expire_trials_job_reverts_to_scout(make_user, db: Session) -> None:
    user = make_user(email="expired_trial@test.com", password="pw")
    user_id = user.id  # capture before session close
    user.plan.status = "trialing"
    user.plan.tier = "strategist"
    user.plan.trial_end = datetime.utcnow() - timedelta(days=2)
    user.plan.stripe_subscription_id = None
    db.commit()

    with patch("app.db.session.SessionLocal", MagicMock(return_value=db)):
        expire_trials_job()

    plan = _plan_row(db, user_id)
    assert plan["tier"] == "scout"
    assert plan["status"] == "active"


def test_expire_trials_active_subscription_not_touched(make_user, db: Session) -> None:
    """User with a paid sub whose trial_end is past should not be reverted."""
    user = make_user(email="paid_trial@test.com", password="pw")
    user_id = user.id
    user.plan.status = "active"
    user.plan.tier = "strategist"
    user.plan.trial_end = datetime.utcnow() - timedelta(days=1)
    user.plan.stripe_subscription_id = "sub_xyz"
    db.commit()

    with patch("app.db.session.SessionLocal", MagicMock(return_value=db)):
        expire_trials_job()

    plan = _plan_row(db, user_id)
    assert plan["tier"] == "strategist"
    assert plan["status"] == "active"


def test_dunning_expiry_job_cancels_after_7d(make_user, db: Session) -> None:
    user = make_user(email="dunning@test.com", password="pw")
    user_id = user.id
    user.plan.status = "past_due"
    user.plan.tier = "strategist"
    user.plan.stripe_subscription_id = "sub_dunning"
    user.plan.updated_at = datetime.utcnow() - timedelta(days=8)
    db.commit()

    mock_cancel = MagicMock()
    with patch("app.db.session.SessionLocal", MagicMock(return_value=db)), \
         patch("app.services.stripe_service.cancel_subscription", mock_cancel):
        dunning_expiry_job()

    plan = _plan_row(db, user_id)
    assert plan["tier"] == "scout"
    assert plan["status"] == "active"
    mock_cancel.assert_called_once_with("sub_dunning")


def test_dunning_expiry_job_ignores_recent_past_due(make_user, db: Session) -> None:
    """Users past_due for less than 7 days should not be cancelled."""
    user = make_user(email="recent_dunning@test.com", password="pw")
    user_id = user.id
    user.plan.status = "past_due"
    user.plan.tier = "strategist"
    user.plan.stripe_subscription_id = "sub_recent"
    user.plan.updated_at = datetime.utcnow() - timedelta(days=3)
    db.commit()

    mock_cancel = MagicMock()
    with patch("app.db.session.SessionLocal", MagicMock(return_value=db)), \
         patch("app.services.stripe_service.cancel_subscription", mock_cancel):
        dunning_expiry_job()

    plan = _plan_row(db, user_id)
    assert plan["status"] == "past_due"
    mock_cancel.assert_not_called()
