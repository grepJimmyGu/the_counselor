"""Email preferences + one-click unsubscribe (Stage 6a).

  GET   /api/me/email-preferences  — authenticated; returns current toggles
  PATCH /api/me/email-preferences  — authenticated; updates toggles
  GET   /api/email/unsub?token=... — public; HMAC-signed CAN-SPAM unsub
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.email_preference import EmailPreference
from app.models.user import User
from app.services.email_service import get_or_create_prefs, verify_unsub_token

prefs_router = APIRouter(prefix="/api/me/email-preferences", tags=["email"])
unsub_router = APIRouter(prefix="/api/email", tags=["email"])


class EmailPreferenceResponse(BaseModel):
    transactional: bool
    weekly_digest: bool
    upsell_nudges: bool
    creator_program: bool
    unsubscribed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmailPreferenceUpdate(BaseModel):
    weekly_digest: Optional[bool] = None
    upsell_nudges: Optional[bool] = None
    creator_program: Optional[bool] = None


@prefs_router.get("", response_model=EmailPreferenceResponse)
def get_email_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailPreferenceResponse:
    prefs = get_or_create_prefs(db, current_user.id)
    return EmailPreferenceResponse.model_validate(prefs)


@prefs_router.patch("", response_model=EmailPreferenceResponse)
def update_email_preferences(
    payload: EmailPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailPreferenceResponse:
    prefs = get_or_create_prefs(db, current_user.id)
    if payload.weekly_digest is not None:
        prefs.weekly_digest = payload.weekly_digest
    if payload.upsell_nudges is not None:
        prefs.upsell_nudges = payload.upsell_nudges
    if payload.creator_program is not None:
        prefs.creator_program = payload.creator_program
    # If user re-enables anything, clear the global unsubscribe.
    if any(x is True for x in (payload.weekly_digest, payload.upsell_nudges, payload.creator_program)):
        if prefs.unsubscribed_at is not None:
            prefs.unsubscribed_at = None
    db.commit()
    db.refresh(prefs)
    # Stage 6a: analytics event
    try:
        from app.services.posthog_service import capture
        capture(current_user.id, "email_preferences_updated", {
            "weekly_digest": prefs.weekly_digest,
            "upsell_nudges": prefs.upsell_nudges,
            "creator_program": prefs.creator_program,
        })
    except Exception:
        pass
    return EmailPreferenceResponse.model_validate(prefs)


_UNSUB_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Unsubscribed — Livermore Alpha</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:48px 16px;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:32px;text-align:center;">
    <h1 style="margin:0 0 12px;font-size:22px;">You're unsubscribed</h1>
    <p style="margin:0 0 24px;color:#475569;font-size:14px;line-height:1.55;">{message}</p>
    <p style="margin:0;font-size:13px;color:#94a3b8;">
      Change your mind? Visit your <a href="/account/email" style="color:#0ea5e9;text-decoration:none;">email preferences</a> to re-subscribe.
    </p>
  </div>
</body>
</html>
"""


@unsub_router.get("/unsub", response_class=Response)
def unsubscribe(
    token: str = Query(..., min_length=10, max_length=200),
    db: Session = Depends(get_db),
) -> Response:
    """CAN-SPAM one-click unsub. Token is HMAC-signed user_id + category.
    Always returns a friendly HTML page (200) — never reveals whether the
    token was valid (anti-enumeration)."""
    parsed = verify_unsub_token(token)
    if parsed is None:
        return Response(
            content=_UNSUB_PAGE_HTML.format(message="The link has expired or is invalid."),
            media_type="text/html",
            status_code=200,
        )
    user_id, category = parsed
    prefs = get_or_create_prefs(db, user_id)

    if category == "all":
        # Global unsubscribe — flip every marketing category off.
        prefs.weekly_digest = False
        prefs.upsell_nudges = False
        prefs.creator_program = False
        prefs.unsubscribed_at = datetime.utcnow()
        msg = "We won't send you marketing email anymore."
    elif category == "weekly_digest":
        prefs.weekly_digest = False
        msg = "You won't receive the weekly digest anymore."
    elif category == "upsell_nudges":
        prefs.upsell_nudges = False
        msg = "You won't receive upgrade nudges anymore."
    elif category == "creator_program":
        prefs.creator_program = False
        msg = "You won't receive creator-program emails anymore."
    else:
        msg = "The link has expired or is invalid."

    db.commit()
    return Response(
        content=_UNSUB_PAGE_HTML.format(message=msg),
        media_type="text/html",
        status_code=200,
    )
