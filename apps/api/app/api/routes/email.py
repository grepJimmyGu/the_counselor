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
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.user import User
from app.services.email_service import get_or_create_prefs, verify_unsub_token

prefs_router = APIRouter(prefix="/api/me/email-preferences", tags=["email"])
unsub_router = APIRouter(prefix="/api/email", tags=["email"])


class EmailPreferenceResponse(BaseModel):
    transactional: bool
    weekly_digest: bool
    upsell_nudges: bool
    creator_program: bool
    # PRD-19 Step 4a — signal alerts + daily digest + silent days
    signal_alerts_enabled: bool
    daily_digest_enabled: bool
    silent_days_enabled: bool
    unsubscribed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmailPreferenceUpdate(BaseModel):
    weekly_digest: Optional[bool] = None
    upsell_nudges: Optional[bool] = None
    creator_program: Optional[bool] = None
    # PRD-19 Step 4a — partial-update support for the three new flags. Each
    # is independently togglable; `None` means "don't change this flag."
    signal_alerts_enabled: Optional[bool] = None
    daily_digest_enabled: Optional[bool] = None
    silent_days_enabled: Optional[bool] = None


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
    # PRD-19 Step 4a — apply signal-alert + digest + silent-days toggles.
    if payload.signal_alerts_enabled is not None:
        prefs.signal_alerts_enabled = payload.signal_alerts_enabled
    if payload.daily_digest_enabled is not None:
        prefs.daily_digest_enabled = payload.daily_digest_enabled
    if payload.silent_days_enabled is not None:
        prefs.silent_days_enabled = payload.silent_days_enabled
    # If user re-enables ANY category (legacy marketing or PRD-19 alerts),
    # clear the global unsubscribe — re-enabling implies they want email again.
    if any(x is True for x in (
        payload.weekly_digest,
        payload.upsell_nudges,
        payload.creator_program,
        payload.signal_alerts_enabled,
        payload.daily_digest_enabled,
    )):
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
            "signal_alerts_enabled": prefs.signal_alerts_enabled,
            "daily_digest_enabled": prefs.daily_digest_enabled,
            "silent_days_enabled": prefs.silent_days_enabled,
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
        # Global unsubscribe — flip every marketing category off, plus the
        # PRD-19 categories that the user explicitly subscribed to. The
        # signal-change emails are `category="transactional"`; the legacy
        # `unsubscribed_at` set here does NOT block them on its own, but
        # `signal_alerts_enabled=False` does (via Step 4a's _prefs_allow).
        # Same for `daily_digest_enabled=False`.
        prefs.weekly_digest = False
        prefs.upsell_nudges = False
        prefs.creator_program = False
        prefs.signal_alerts_enabled = False
        prefs.daily_digest_enabled = False
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
    elif category == "daily_digest":
        # PRD-19 Step 4c — `daily_digest` unsub token (from the daily-digest
        # email footer). Flips the global digest flag; the daily_digest_job
        # checks this on every tick and skips the user.
        prefs.daily_digest_enabled = False
        msg = "You won't receive the daily digest anymore."
    elif category.startswith("signal_alerts_"):
        # PRD-19 Step 4c — per-strategy mute. Token category is
        # `signal_alerts_<strategy_id>`; the suffix is the saved-strategy
        # UUID this token authorizes muting. Because the HMAC binds
        # (user_id, category) and the signing key is server-side, the
        # only way to land here is with a token Livermore itself
        # generated for THIS user + THIS strategy. So flipping
        # `SignalAlertSubscription.email_enabled = False` is safe — we
        # don't need to re-check ownership of the strategy.
        strategy_id = category[len("signal_alerts_"):]
        sub = db.get(SignalAlertSubscription, (user_id, strategy_id))
        if sub is not None:
            sub.email_enabled = False
        # Generic message either way — anti-enumeration: same response
        # whether the subscription existed or had already been muted.
        msg = "You won't receive alerts for that strategy anymore."
    else:
        msg = "The link has expired or is invalid."

    db.commit()
    return Response(
        content=_UNSUB_PAGE_HTML.format(message=msg),
        media_type="text/html",
        status_code=200,
    )
