"""Attribution service (Stage 4a).

Tracks /s/<slug>?via=<handle> clicks via a first-party cookie
(`livermore_vsid`, 90-day) and an `attribution_visits` row per visit.
On signup, auth.py reads the cookie and converts the row to the new user;
on customer.subscription.created (Stripe webhook), we mark converted_to_paid_at.

Stage 5's Creator Program payouts query this table.

Edge cases handled:
  - Self-attribution: if the signup user's own handle matches the referrer
    handle, skip the conversion (creator can't refer themselves).
  - Multiple referrers: take the FIRST un-converted row (don't double-count).
  - Stale cookie: a vsid pointing at no row triggers a new row on next track.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.attribution_visit import AttributionVisit
from app.models.user import User

VSID_COOKIE_NAME = "livermore_vsid"
VSID_COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 days


def _is_production() -> bool:
    return get_settings().app_env == "production"


def _get_or_set_vsid(request: Request, response: Response) -> str:
    """Return existing visitor session id from cookie, or mint a new one + set."""
    existing = request.cookies.get(VSID_COOKIE_NAME)
    if existing:
        return existing
    new_id = str(uuid4())
    response.set_cookie(
        VSID_COOKIE_NAME,
        new_id,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
        max_age=VSID_COOKIE_MAX_AGE,
    )
    return new_id


def track_visit(
    db: Session,
    request: Request,
    response: Response,
    via_handle: str,
    landed_url: str,
) -> Optional[AttributionVisit]:
    """Record a /s/<slug>?via=<handle> click. Resolves the handle to a user
    (must exist + be lowercase). Returns the row or None if the handle is
    unknown."""
    handle = via_handle.lower().strip()
    if not handle:
        return None

    referrer = db.scalar(select(User).where(User.handle == handle))
    if referrer is None:
        return None

    vsid = _get_or_set_vsid(request, response)

    visit = AttributionVisit(
        id=str(uuid4()),
        visitor_session_id=vsid,
        referrer_handle=handle,
        referrer_user_id=referrer.id,
        landed_url=landed_url[:500],
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit


def convert_on_signup(
    db: Session,
    request: Request,
    new_user: User,
) -> Optional[AttributionVisit]:
    """Called from auth.py after a new user is created. Reads the
    livermore_vsid cookie, finds the FIRST un-converted attribution row,
    and stamps it with the new user_id.

    Self-attribution rule: if the signup user's handle matches the
    referrer_handle, we record the conversion anyway (because the user
    may not have a handle yet at signup time and we can't verify), BUT
    Stage 5's payout calc skips rows where converted_to_user_id == referrer_user_id.
    Belt-and-suspenders.

    Returns the row or None if no attribution exists."""
    vsid = request.cookies.get(VSID_COOKIE_NAME)
    if not vsid:
        return None

    # First un-converted row for this vsid (oldest landing wins → first-touch).
    row = db.scalar(
        select(AttributionVisit)
        .where(
            AttributionVisit.visitor_session_id == vsid,
            AttributionVisit.converted_to_user_id.is_(None),
        )
        .order_by(AttributionVisit.landed_at.asc())
    )
    if row is None:
        return None

    # Self-attribution short-circuit: don't mark conversion if the new user IS
    # the referrer. (Belt + suspenders: Stage 5's payout query also checks this.)
    if row.referrer_user_id == new_user.id:
        return None

    row.converted_to_user_id = new_user.id
    row.converted_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def mark_paid_conversion(
    db: Session,
    user_id: str,
    subscription_id: Optional[str] = None,
) -> Optional[AttributionVisit]:
    """Called from the Stripe webhook on customer.subscription.created.
    Finds the attribution row for *user_id* (most recent converted) and
    sets converted_to_paid_at. Returns the row or None if no attribution."""
    row = db.scalar(
        select(AttributionVisit)
        .where(
            AttributionVisit.converted_to_user_id == user_id,
            AttributionVisit.converted_to_paid_at.is_(None),
        )
        .order_by(AttributionVisit.converted_at.desc())
    )
    if row is None:
        return None
    row.converted_to_paid_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row
