"""Tests for Google OAuth callback."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.api.routes.auth import _create_user_with_plan, _get_user_by_email


def _stub_request(cookies: dict | None = None) -> MagicMock:
    """Stage 1a: google_oauth_callback now takes a Request to read the
    livermore_anon_id cookie for anonymous-merge. Tests that call the route
    directly need a stub with the cookies attribute."""
    req = MagicMock()
    req.cookies = cookies or {}
    return req


_GOOGLE_PAYLOAD = {
    "sub": "google-sub-123",
    "email": "google@example.com",
    "name": "Google User",
    "picture": "https://example.com/pic.jpg",
    "email_verified": True,
}


def test_google_callback_creates_user_on_first_login(db: Session) -> None:
    with patch("app.api.routes.auth.verify_google_id_token", return_value=_GOOGLE_PAYLOAD):
        from app.api.routes.auth import google_oauth_callback
        from app.schemas.identity import OAuthGoogleRequest

        result = google_oauth_callback(
            OAuthGoogleRequest(id_token="fake-token"),
            request=_stub_request(),
            db=db,
        )

    assert result["is_new"] is True
    user = _get_user_by_email(db, "google@example.com")
    assert user is not None
    assert user.oauth_provider == "google"
    assert user.oauth_subject == "google-sub-123"
    assert user.password_hash is None
    assert user.plan.tier == "scout"


def test_google_callback_finds_existing_user_by_oauth_subject(db: Session) -> None:
    # First login — creates user
    with patch("app.api.routes.auth.verify_google_id_token", return_value=_GOOGLE_PAYLOAD):
        from app.api.routes.auth import google_oauth_callback
        from app.schemas.identity import OAuthGoogleRequest

        first = google_oauth_callback(
            OAuthGoogleRequest(id_token="tok1"), request=_stub_request(), db=db
        )

    # Second login — should find and return existing user
    with patch("app.api.routes.auth.verify_google_id_token", return_value=_GOOGLE_PAYLOAD):
        second = google_oauth_callback(
            OAuthGoogleRequest(id_token="tok2"), request=_stub_request(), db=db
        )

    assert second["is_new"] is False
    assert first["user"]["id"] == second["user"]["id"]


def test_google_callback_rejects_invalid_id_token(db: Session) -> None:
    with patch("app.api.routes.auth.verify_google_id_token", side_effect=ValueError("bad token")):
        from app.api.routes.auth import google_oauth_callback
        from app.schemas.identity import OAuthGoogleRequest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            google_oauth_callback(
                OAuthGoogleRequest(id_token="bad"), request=_stub_request(), db=db
            )
        assert exc_info.value.status_code == 400


def test_google_callback_rejects_if_email_has_password_account(db: Session) -> None:
    """Returns 409 when a Google login arrives for an email already registered with a password."""
    from app.services.auth_service import hash_password
    _create_user_with_plan(db, email="clash@example.com", password_hash=hash_password("pw123"))

    payload = {**_GOOGLE_PAYLOAD, "email": "clash@example.com", "sub": "new-google-sub"}
    with patch("app.api.routes.auth.verify_google_id_token", return_value=payload):
        from app.api.routes.auth import google_oauth_callback
        from app.schemas.identity import OAuthGoogleRequest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            google_oauth_callback(
                OAuthGoogleRequest(id_token="tok"), request=_stub_request(), db=db
            )
        assert exc_info.value.status_code == 409
