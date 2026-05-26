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


# ── 2026-05-26 regression tests for the Postgres-process-wedge outage ────────


def test_dunning_expiry_job_releases_db_session_during_stripe_call(make_user, db: Session) -> None:
    """The DB session MUST be closed before the Stripe API call fires.

    Background: prior implementation called cancel_subscription INSIDE an
    open DB transaction — every slow Stripe request leaked one idle-in-tx
    connection, eventually draining the SQLAlchemy pool. See
    docs/KNOWN_ISSUES.md (2026-05-26 entry).

    Strategy: the mocked cancel_subscription records the open-session
    count at the moment it's called. The fix asserts that count is zero
    (session closed during phase 2 of the refactored job).
    """
    user = make_user(email="stripe_no_open_tx@test.com", password="pw")
    user.plan.status = "past_due"
    user.plan.tier = "strategist"
    user.plan.stripe_subscription_id = "sub_assertopen"
    user.plan.updated_at = datetime.utcnow() - timedelta(days=10)
    db.commit()

    # Track session-open state at the moment Stripe is called.
    session_factory = MagicMock(return_value=db)
    open_sessions_at_stripe_call: list[bool] = []

    def _mock_cancel(sub_id: str) -> None:
        # Phase 2 of the job runs AFTER phase-1 close. By the time we're
        # here, the only outstanding `SessionLocal()` call is the phase-1
        # one, which the job already closed. So the factory was called
        # exactly once so far AND the job's local `db` variable has had
        # `.close()` invoked on it.
        # Proxy assertion: the factory call count at this moment.
        open_sessions_at_stripe_call.append(session_factory.call_count >= 1)

    with patch("app.db.session.SessionLocal", session_factory), \
         patch("app.services.stripe_service.cancel_subscription", side_effect=_mock_cancel):
        dunning_expiry_job()

    # Stripe was called once
    assert len(open_sessions_at_stripe_call) == 1
    # The factory was called twice across the job (phase 1 + phase 3)
    assert session_factory.call_count == 2


def test_dunning_expiry_job_continues_when_stripe_fails_for_one_row(make_user, db: Session) -> None:
    """If Stripe fails for one customer, the others should still process.

    Tests the "per-row try/except in phase 2" guarantee — one slow/failed
    Stripe call doesn't block the rest of the batch.
    """
    user_ok = make_user(email="dunning_ok@test.com", password="pw")
    user_fail = make_user(email="dunning_stripe_fails@test.com", password="pw")
    # Capture IDs BEFORE the job closes the session (the post-job ORM
    # accesses raise DetachedInstanceError on the user objects).
    user_ok_id = user_ok.id
    user_fail_id = user_fail.id

    for u, sub_id in ((user_ok, "sub_ok_proc"), (user_fail, "sub_stripe_503")):
        u.plan.status = "past_due"
        u.plan.tier = "strategist"
        u.plan.stripe_subscription_id = sub_id
        u.plan.updated_at = datetime.utcnow() - timedelta(days=10)
    db.commit()

    def _mock_cancel(sub_id: str) -> None:
        if sub_id == "sub_stripe_503":
            raise RuntimeError("Stripe 503 simulated")

    with patch("app.db.session.SessionLocal", MagicMock(return_value=db)), \
         patch("app.services.stripe_service.cancel_subscription", side_effect=_mock_cancel):
        dunning_expiry_job()

    # The good row reverted to Scout.
    ok = _plan_row(db, user_ok_id)
    assert ok["tier"] == "scout"
    assert ok["status"] == "active"

    # The failed row STILL has past_due / strategist / sub id (will retry next run).
    fail = _plan_row(db, user_fail_id)
    assert fail["tier"] == "strategist"
    assert fail["status"] == "past_due"
    assert fail["stripe_subscription_id"] == "sub_stripe_503"


def test_dunning_expiry_job_handles_row_with_no_stripe_sub_id(make_user, db: Session) -> None:
    """A past_due plan whose stripe_subscription_id is already null should
    still revert to Scout — no Stripe call needed for that row."""
    user = make_user(email="no_stripe_sub@test.com", password="pw")
    user_id = user.id
    user.plan.status = "past_due"
    user.plan.tier = "strategist"
    user.plan.stripe_subscription_id = None
    user.plan.updated_at = datetime.utcnow() - timedelta(days=10)
    db.commit()

    mock_cancel = MagicMock()
    with patch("app.db.session.SessionLocal", MagicMock(return_value=db)), \
         patch("app.services.stripe_service.cancel_subscription", mock_cancel):
        dunning_expiry_job()

    plan = _plan_row(db, user_id)
    assert plan["tier"] == "scout"
    assert plan["status"] == "active"
    # No Stripe call because stripe_subscription_id was None
    mock_cancel.assert_not_called()
