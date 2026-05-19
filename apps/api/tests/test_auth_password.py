"""Tests for password-based signup and login."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.models.user import User, Plan
from app.services.auth_service import hash_password, verify_password


# ── Unit: password hashing ────────────────────────────────────────────────────

def test_password_hashing_uses_bcrypt() -> None:
    hashed = hash_password("secret123")
    assert hashed.startswith("$2b$")
    cost = int(hashed.split("$")[2])
    assert cost >= 12


def test_verify_password_correct() -> None:
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed) is True


def test_verify_password_wrong() -> None:
    hashed = hash_password("mypassword")
    assert verify_password("wrongpassword", hashed) is False


# ── Integration: signup / login via DB ───────────────────────────────────────

def test_signup_creates_user_and_plan(make_user, db: Session) -> None:
    user = make_user(email="new@example.com", password="password123")
    assert user.id is not None
    assert user.email == "new@example.com"
    assert user.password_hash is not None
    assert user.password_hash.startswith("$2b$")
    # Plan defaults to scout / active
    assert user.plan is not None
    assert user.plan.tier == "scout"
    assert user.plan.status == "active"


def test_signup_duplicate_email_rejected(make_user, db: Session) -> None:
    make_user(email="dupe@example.com", password="pass1")
    from app.api.routes.auth import _create_user_with_plan
    import sqlalchemy.exc
    with pytest.raises(Exception):
        # Second insert with same email must fail at DB level
        _create_user_with_plan(db, email="dupe@example.com", password_hash=hash_password("pass2"))


def test_login_wrong_password_returns_false(make_user, db: Session) -> None:
    user = make_user(email="login@example.com", password="correct_pw")
    assert verify_password("wrong_pw", user.password_hash) is False


def test_plan_defaults_to_scout(make_user, db: Session) -> None:
    user = make_user(email="plantest@example.com", password="pw123")
    plan = db.get(Plan, user.id)
    assert plan is not None
    assert plan.tier == "scout"
    assert plan.status == "active"
    assert plan.billing_cycle is None
    assert plan.stripe_customer_id is None


def test_email_stored_lowercase(make_user, db: Session) -> None:
    user = make_user(email="Upper@Example.COM", password="pw")
    assert user.email == "upper@example.com"
