"""Tests for POST /api/billing/trial/start."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.billing import start_trial
from app.schemas.billing import TrialStartRequest


def test_trial_start_creates_trialing_state(make_user, db: Session) -> None:
    user = make_user(email="trial@test.com", password="pw")
    body = TrialStartRequest(tier="strategist")

    result = start_trial(body=body, current_user=user, db=db)

    db.refresh(user)
    assert user.plan.tier == "strategist"
    assert user.plan.status == "trialing"
    assert user.plan.trial_end is not None
    # trial_end should be ~14 days from now
    days_left = (user.plan.trial_end - datetime.utcnow()).days
    assert 13 <= days_left <= 14
    assert result.tier == "strategist"


def test_trial_start_idempotent_same_session(make_user, db: Session) -> None:
    """Calling /trial/start twice returns 409 on the second call."""
    user = make_user(email="trial2@test.com", password="pw")
    start_trial(body=TrialStartRequest(tier="strategist"), current_user=user, db=db)

    with pytest.raises(HTTPException) as exc_info:
        start_trial(body=TrialStartRequest(tier="quant"), current_user=user, db=db)
    assert exc_info.value.status_code == 409


def test_trial_start_409_if_already_trialed(make_user, db: Session) -> None:
    """User who already had a trial (trial_end in the past) cannot start a new one."""
    from datetime import date
    user = make_user(email="oldtrial@test.com", password="pw")
    # Simulate an expired trial
    user.plan.status = "active"
    user.plan.tier = "scout"
    user.plan.trial_end = datetime(2024, 1, 1)  # past date
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        start_trial(body=TrialStartRequest(tier="strategist"), current_user=user, db=db)
    assert exc_info.value.status_code == 409


def test_trial_start_409_if_paid(make_user, db: Session) -> None:
    user = make_user(email="paid@test.com", password="pw")
    user.plan.status = "active"
    user.plan.tier = "strategist"
    user.plan.stripe_subscription_id = "sub_abc123"
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        start_trial(body=TrialStartRequest(tier="quant"), current_user=user, db=db)
    assert exc_info.value.status_code == 409


def test_trial_start_quant(make_user, db: Session) -> None:
    user = make_user(email="quant_trial@test.com", password="pw")
    result = start_trial(body=TrialStartRequest(tier="quant"), current_user=user, db=db)
    assert result.tier == "quant"
    db.refresh(user)
    assert user.plan.tier == "quant"
