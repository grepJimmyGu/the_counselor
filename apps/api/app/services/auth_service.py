from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_DAYS = 30
# Reserved handles — case-insensitive
_RESERVED_HANDLES = frozenset(
    "admin livermore claude api support help billing account me settings".split()
)
_HANDLE_RE = __import__("re").compile(r"^[a-z0-9_]{3,32}$")


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """bcrypt at cost 12."""
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plaintext: str, hashed: str) -> bool:
    """Always runs bcrypt (no short-circuit) to prevent timing attacks."""
    try:
        return bcrypt.checkpw(plaintext.encode(), hashed.encode())
    except Exception:
        return False


def verify_password_safe(plaintext: str, hashed: Optional[str]) -> bool:
    """Run bcrypt even when *hashed* is None (unknown email) to normalise timing."""
    _DUMMY = "$2b$12$KIXzRPIi3h.0S6Bcy0X09.rPVqKk8xKVdM8vwJ3ib3BVQzHjHk.ni"
    return verify_password(plaintext, hashed if hashed else _DUMMY) and hashed is not None


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_session_token(user_id: str, tier: str) -> str:
    settings = get_settings()
    exp = datetime.utcnow() + timedelta(days=_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "tier": tier, "exp": exp}
    return jwt.encode(payload, settings.nextauth_secret, algorithm=_ALGORITHM)


def decode_session_token(token: str) -> dict:
    """Returns the decoded payload or raises JWTError."""
    settings = get_settings()
    return jwt.decode(token, settings.nextauth_secret, algorithms=[_ALGORITHM])


# ── Google ID token ───────────────────────────────────────────────────────────

def verify_google_id_token(id_token: str) -> dict:
    """Verify a Google ID token and return its payload.
    Raises ValueError on failure."""
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        settings = get_settings()
        request = google_requests.Request()
        payload = google_id_token.verify_oauth2_token(
            id_token, request, settings.google_client_id
        )
        return payload
    except Exception as exc:
        raise ValueError(f"Invalid Google ID token: {exc}") from exc


# ── Handle validation ─────────────────────────────────────────────────────────

def validate_handle(handle: str) -> Optional[str]:
    """Return an error message if the handle is invalid, else None."""
    if not _HANDLE_RE.match(handle):
        return "Handle must be 3–32 characters: lowercase letters, digits, underscores only."
    if handle.lower() in _RESERVED_HANDLES:
        return f"'{handle}' is a reserved name."
    return None


# ── ID generation ─────────────────────────────────────────────────────────────

def new_user_id() -> str:
    return str(uuid.uuid4())
