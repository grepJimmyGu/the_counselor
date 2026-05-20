"""Anonymous session service (Stage 1a).

Backs the one-fresh-backtest-per-anonymous flow. Uses an HttpOnly cookie
(`livermore_anon_id`) to identify the visitor across requests; preserves
referrer attribution from /s/<slug>?via=<handle> through the anonymous →
signup → paid funnel.

Cookie semantics:
  - HttpOnly, SameSite=Lax, Secure in production only.
  - 90-day Max-Age.
  - Stored UUID corresponds to anonymous_sessions.id.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.anonymous_session import AnonymousSession
from app.models.backtest import BacktestRecord

COOKIE_NAME = "livermore_anon_id"
COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 days


def _is_production() -> bool:
    return get_settings().app_env == "production"


def get_or_create_anonymous_session(
    request: Request,
    response: Response,
    db: Session,
) -> AnonymousSession:
    """Return the AnonymousSession for the cookie on *request*; create + set
    cookie on *response* if missing. Always refreshes ip_last_seen / last_seen_at
    on returning visitors."""
    sid = request.cookies.get(COOKIE_NAME)
    client_ip = request.client.host if request.client else "unknown"

    if sid:
        session = db.get(AnonymousSession, sid)
        if session:
            session.ip_last_seen = client_ip
            session.last_seen_at = datetime.utcnow()
            db.commit()
            return session
        # Cookie present but stale — fall through to create a new session.

    sid = str(uuid4())
    locale = (request.headers.get("accept-language", "en")[:8].split(",")[0]) or "en"
    session = AnonymousSession(
        id=sid,
        ip_first_seen=client_ip,
        ip_last_seen=client_ip,
        user_agent=(request.headers.get("user-agent") or "")[:500],
        locale=locale,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    response.set_cookie(
        COOKIE_NAME,
        sid,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
    )
    return session


def increment_anonymous_run(
    db: Session,
    session: AnonymousSession,
    backtest_id: Optional[str] = None,
) -> int:
    """Bump runs_used and (optionally) attach the most recent backtest id."""
    session.runs_used += 1
    if backtest_id is not None:
        session.last_backtest_id = backtest_id
    db.commit()
    return session.runs_used


def record_anonymous_referrer(
    db: Session,
    session: AnonymousSession,
    via_handle: str,
) -> None:
    """Persist a creator's handle from /s/<slug>?via=<handle>. First-touch
    wins — once set, we don't overwrite it (so a second visit via a different
    handle doesn't steal the credit)."""
    if not session.via_handle:
        session.via_handle = via_handle
        db.commit()


def merge_anonymous_into_user(
    db: Session,
    session: AnonymousSession,
    user_id: str,
) -> None:
    """Called from auth/signup. Attaches the anonymous one-shot backtest result
    to the new user (so 'your first backtest is already in your saved list'
    works) and marks the session as converted.

    Idempotent: re-running is a no-op once converted_to_user_id is set."""
    if session.converted_to_user_id == user_id:
        return  # already merged

    if session.last_backtest_id:
        backtest = db.get(BacktestRecord, session.last_backtest_id)
        if backtest and backtest.user_id is None:
            backtest.user_id = user_id

    session.converted_to_user_id = user_id
    session.converted_at = datetime.utcnow()
    db.commit()


def get_anonymous_session_by_user_id(
    db: Session,
    user_id: str,
) -> Optional[AnonymousSession]:
    """Look up the anonymous session that converted to *user_id*. Used by the
    Stripe webhook to preserve via_handle through the anonymous → paid funnel."""
    return (
        db.query(AnonymousSession)
        .filter(AnonymousSession.converted_to_user_id == user_id)
        .order_by(AnonymousSession.converted_at.desc())
        .first()
    )
