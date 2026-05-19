from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from jose import JWTError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, Plan
from app.services.auth_service import decode_session_token

_LEGACY_USER_ID = "legacy-anon-0000"


def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):]
    return None


def _load_user(db: Session, user_id: str) -> Optional[User]:
    return db.get(User, user_id)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Strict dependency — raises 401 if unauthenticated."""
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        payload = decode_session_token(token)
        user_id: str = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    user = _load_user(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user


def get_current_user_or_anonymous(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Permissive dependency — returns authenticated user or the legacy-anon synthetic user.

    Stage 1: every existing endpoint uses this; behaviour is unchanged for anonymous callers.
    Stage 3 will swap metered endpoints to `get_current_user` (strict).
    """
    token = _extract_bearer(request)
    if token:
        try:
            payload = decode_session_token(token)
            user_id: str = payload["sub"]
            user = _load_user(db, user_id)
            if user:
                return user
        except (JWTError, KeyError):
            pass  # fall through to anonymous

    legacy = _load_user(db, _LEGACY_USER_ID)
    if legacy:
        return legacy

    # Fallback: construct a transient anonymous user object (no DB row needed)
    anon = User(
        id=_LEGACY_USER_ID,
        email="legacy@livermore.app",
        locale="en",
    )
    anon.plan = Plan(user_id=_LEGACY_USER_ID, tier="scout", status="active")  # type: ignore[assignment]
    return anon
