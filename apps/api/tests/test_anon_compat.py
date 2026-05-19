"""Integration: anonymous requests still work after Stage 1."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_or_anonymous
from app.models.user import User, Plan


def _make_mock_request(auth_header: str | None = None):
    """Minimal mock of a FastAPI Request for the dep."""
    class _Headers(dict):
        def get(self, key, default=""):
            return super().get(key.lower(), default)

    headers = _Headers()
    if auth_header:
        headers["authorization"] = auth_header

    class _Request:
        def __init__(self):
            self.headers = headers

    return _Request()


def test_anonymous_dep_returns_legacy_user(db: Session) -> None:
    """Unauthenticated request → legacy-anon-0000 user with Scout plan."""
    req = _make_mock_request()
    user = get_current_user_or_anonymous(request=req, db=db)  # type: ignore[arg-type]
    assert user.id == "legacy-anon-0000"
    assert user.plan.tier == "scout"


def test_authenticated_dep_returns_real_user(make_user, db: Session) -> None:
    from app.services.auth_service import create_session_token

    user = make_user(email="authtest@example.com", password="pw")
    token = create_session_token(user.id, user.plan.tier)
    req = _make_mock_request(auth_header=f"Bearer {token}")
    resolved = get_current_user_or_anonymous(request=req, db=db)  # type: ignore[arg-type]
    assert resolved.id == user.id


def test_expired_token_falls_back_to_anon(db: Session) -> None:
    req = _make_mock_request(auth_header="Bearer totally.invalid.token")
    user = get_current_user_or_anonymous(request=req, db=db)  # type: ignore[arg-type]
    # Falls back gracefully without raising
    assert user.id == "legacy-anon-0000"


def test_legacy_user_seeded_in_db(db: Session) -> None:
    """Migration must have inserted the legacy-anon-0000 row."""
    user = db.get(User, "legacy-anon-0000")
    assert user is not None
    assert user.email == "legacy@livermore.app"
    plan = db.get(Plan, "legacy-anon-0000")
    assert plan is not None
    assert plan.tier == "scout"
