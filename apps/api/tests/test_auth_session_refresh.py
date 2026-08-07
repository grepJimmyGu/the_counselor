"""Regression tests for the expired-backendToken bug.

Symptom: running a screen and viewing its results showed the banner
"Couldn't rank by return (Invalid or expired session token.)" for a user who
was signed in. The matched names still rendered, so it degraded rather than
broke and went unnoticed.

Root cause: `create_session_token` mints a 30-day JWT once at sign-in, but
NextAuth re-signs its own session cookie with a fresh 30-day expiry on every
session read, copying `backendToken` through verbatim. Nothing ever re-minted
it. The `auth.ts` self-heal only fired on a *missing* token — an expired one is
still a truthy string — so past day 30 the user held an expired token that
`get_current_user` rejected with 401 "Invalid or expired session token."

`/api/auth/refresh-session-token` is the mint-only endpoint the `jwt()` callback
now calls to re-mint before expiry. These tests pin the two properties the fix
depends on: an expired token really does produce that exact 401 detail, and the
refresh endpoint mints a usable token WITHOUT mutating how the account logs in.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.auth import (
    _create_user_with_plan,
    _RefreshSessionTokenRequest,
    refresh_session_token,
)
from app.core.config import get_settings
from app.services.auth_service import decode_session_token


def _stub_request(token: Optional[str] = None) -> MagicMock:
    req = MagicMock()
    req.headers = {"Authorization": f"Bearer {token}"} if token else {}
    return req


def _expired_token(user_id: str, tier: str = "scout") -> str:
    """A structurally valid, correctly signed token that is simply past `exp`.

    Mirrors `create_session_token` exactly except for the expiry — this is what
    a user who signed in over 30 days ago is holding.
    """
    settings = get_settings()
    payload = {
        "sub": user_id,
        "tier": tier,
        "exp": datetime.utcnow() - timedelta(minutes=1),
    }
    return jwt.encode(payload, settings.nextauth_secret, algorithm="HS256")


# ── The 401 the banner was reporting ──────────────────────────────────────────

def test_expired_token_yields_the_invalid_or_expired_detail(db: Session) -> None:
    """The exact banner text, reproduced.

    `ExpiredSignatureError` subclasses `JWTError`, so an expired token lands on
    the `except (JWTError, KeyError)` branch — NOT the missing-header branch.
    That is what proved the frontend WAS sending an Authorization header and
    ruled out the two `backendToken` plumbing hypotheses (trap #19).
    """
    user = _create_user_with_plan(db, email="expired@example.com")

    with pytest.raises(HTTPException) as exc:
        get_current_user(request=_stub_request(_expired_token(user.id)), db=db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired session token."


def test_missing_header_yields_a_different_detail(db: Session) -> None:
    """The discriminator. If the frontend had failed to send the header at all
    (trap #19), the banner would have read "Authentication required." instead.
    Pinning both messages keeps them distinguishable for the next diagnosis.
    """
    with pytest.raises(HTTPException) as exc:
        get_current_user(request=_stub_request(None), db=db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication required."


# ── The fix: mint-only refresh ────────────────────────────────────────────────

def test_refresh_mints_a_token_that_authenticates(db: Session) -> None:
    """The re-minted token must actually get the user past `get_current_user` —
    the property the whole fix rests on."""
    user = _create_user_with_plan(db, email="refresh@example.com")

    resp = refresh_session_token(
        _RefreshSessionTokenRequest(email="refresh@example.com"), db=db
    )

    assert resp.id == user.id
    payload = decode_session_token(resp.session_token)
    assert payload["sub"] == user.id
    assert payload["tier"] == "scout"

    resolved = get_current_user(request=_stub_request(resp.session_token), db=db)
    assert resolved.id == user.id


def test_refresh_replaces_an_expired_token(db: Session) -> None:
    """End-to-end shape of the bug and its fix: the token the user holds is
    rejected, the refreshed one is accepted."""
    user = _create_user_with_plan(db, email="stale@example.com")
    stale = _expired_token(user.id)

    with pytest.raises(HTTPException):
        get_current_user(request=_stub_request(stale), db=db)

    fresh = refresh_session_token(
        _RefreshSessionTokenRequest(email="stale@example.com"), db=db
    ).session_token

    assert fresh != stale
    assert get_current_user(request=_stub_request(fresh), db=db).id == user.id


def test_refresh_does_not_mutate_how_the_account_logs_in(db: Session) -> None:
    """The reason this is a dedicated endpoint rather than a `sync-user` call.

    Broadening the re-mint trigger from "missing" to "expired" makes this path
    fire for password users too. `sync-user` sets `oauth_provider`/
    `oauth_subject` whenever `oauth_subject` is falsy, so reusing it would have
    silently stamped a password-only account as Google-linked on token refresh.
    """
    user = _create_user_with_plan(
        db, email="pw@example.com", password_hash="$2b$12$fake"
    )
    assert user.oauth_provider is None
    assert user.oauth_subject is None
    before_login_at = user.last_login_at

    refresh_session_token(_RefreshSessionTokenRequest(email="pw@example.com"), db=db)

    db.refresh(user)
    assert user.oauth_provider is None, "refresh must not link the account to an OAuth provider"
    assert user.oauth_subject is None
    assert user.password_hash == "$2b$12$fake"
    assert user.last_login_at == before_login_at, "a token refresh is not a login"


def test_refresh_carries_the_current_tier(db: Session) -> None:
    """The token embeds `tier`, so a re-mint must reflect the user's tier at
    refresh time rather than whatever it was at sign-in."""
    user = _create_user_with_plan(db, email="quant@example.com")
    user.plan.tier = "quant"
    db.commit()

    resp = refresh_session_token(
        _RefreshSessionTokenRequest(email="quant@example.com"), db=db
    )

    assert decode_session_token(resp.session_token)["tier"] == "quant"


def test_refresh_on_orphaned_user_defaults_to_scout_without_writing(db: Session) -> None:
    """An orphaned User without a Plan would AttributeError on `.tier`. The
    endpoint stays read-only (`sync-user` is what heals those rows), so it
    falls back to the same default the anonymous path uses."""
    user = _create_user_with_plan(db, email="orphan@example.com")
    db.delete(user.plan)
    db.commit()
    db.refresh(user)
    assert user.plan is None

    resp = refresh_session_token(
        _RefreshSessionTokenRequest(email="orphan@example.com"), db=db
    )

    assert decode_session_token(resp.session_token)["tier"] == "scout"
    db.refresh(user)
    assert user.plan is None, "refresh must not write a Plan row"


def test_refresh_404s_for_an_unknown_email(db: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        refresh_session_token(
            _RefreshSessionTokenRequest(email="nobody@example.com"), db=db
        )
    assert exc.value.status_code == 404


def test_refresh_endpoint_requires_the_internal_key() -> None:
    """The endpoint trusts the caller's `email` outright, so the internal-key
    guard is the only thing keeping it off the public surface."""
    from app.api.routes.auth import router

    route = next(
        r for r in router.routes
        if getattr(r, "path", None) == "/api/auth/refresh-session-token"
    )
    guards = {getattr(d.dependency, "__name__", "") for d in route.dependencies}
    assert "_verify_internal_key" in guards
