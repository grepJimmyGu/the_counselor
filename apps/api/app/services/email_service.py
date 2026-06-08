"""Resend email service — safe no-op wrapper (Stage 6a).

Wraps the Resend SDK with the same pattern as posthog_service: silently
no-ops when RESEND_API_KEY is missing. Add the key + a verified sender
domain to actually send mail.

Plain-HTML templates (no React Email build step) for v1.

To enable in production:
  1. Sign up for Resend
  2. Verify your sender domain (DKIM + SPF + DMARC)
  3. Set RESEND_API_KEY, RESEND_FROM_TRANSACTIONAL, RESEND_FROM_MARKETING
     in env vars
  4. Redeploy. send_email() calls start sending.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.email_preference import EmailPreference
from app.models.user import User
from app.services.posthog_service import capture as _ph_capture

_log = logging.getLogger("livermore.email")

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is False:
        return None
    if _client is not None:
        return _client
    key = get_settings().resend_api_key
    if not key:
        _client = False
        return None
    try:
        import resend  # type: ignore[import-not-found]
        resend.api_key = key
        _client = resend
        _log.info("email_service: Resend initialized")
        return _client
    except ImportError:
        _log.warning("resend package not installed; email disabled")
        _client = False
        return None
    except Exception as exc:
        _log.warning("email_service init failed: %s", exc)
        _client = False
        return None


def get_or_create_prefs(db: Session, user_id: str) -> EmailPreference:
    row = db.get(EmailPreference, user_id)
    if row is None:
        row = EmailPreference(user_id=user_id)
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except Exception:
            db.rollback()
            row = db.get(EmailPreference, user_id)
    return row


def _prefs_allow(prefs: EmailPreference, template: str, category: str) -> bool:
    """Decide whether to send. Transactional always sends (unless globally
    unsubscribed via Resend complaint). Marketing respects per-category toggle.

    PRD-19 Step 4a: the `signal_change` + `daily_digest` templates honor
    `prefs.signal_alerts_enabled` / `prefs.daily_digest_enabled` BEFORE
    falling through to the transactional default. These two are opt-in
    products — the user explicitly subscribed; explicit opt-out via the
    settings page is honored. Legally-required transactional email
    (password reset, payment failed, account verification) still bypasses
    `unsubscribed_at` because that's CAN-SPAM table stakes.
    """
    # PRD-19 — per-template explicit toggles. Evaluated FIRST so the user's
    # explicit choice wins over the transactional bypass.
    if template == "signal_change" and not prefs.signal_alerts_enabled:
        return False
    if template == "daily_digest" and not prefs.daily_digest_enabled:
        return False

    # Globally unsubscribed = no marketing, but transactional still goes through
    # (legally required for things like password reset, payment failed).
    if category == "transactional":
        return True
    if prefs.unsubscribed_at is not None:
        return False
    # Map template name → category toggle.
    cat_map = {
        "weekly_digest": prefs.weekly_digest,
        "soft_upsell": prefs.upsell_nudges,
        "creator_approved": prefs.creator_program,
        "creator_suspended": prefs.creator_program,
        # "welcome" is borderline — onboarding email, technically marketing.
        # We send unless the user has explicitly globally unsubscribed.
    }
    return cat_map.get(template, True)


def make_unsub_token(user_id: str, category: str) -> str:
    """HMAC-signed token for one-click unsubscribe (CAN-SPAM compliance).
    Token format: <user_id>.<category>.<hmac_hex>."""
    key = get_settings().email_unsub_signing_key or "dev-only-not-secret"
    msg = f"{user_id}.{category}".encode()
    sig = hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()[:16]
    return f"{user_id}.{category}.{sig}"


def verify_unsub_token(token: str) -> Optional[tuple[str, str]]:
    """Verify an HMAC-signed unsub token. Returns (user_id, category) on
    success, None on failure (invalid format or signature mismatch)."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    user_id, category, sig = parts
    expected = make_unsub_token(user_id, category)
    if not hmac.compare_digest(expected, token):
        return None
    return (user_id, category)


def send_email(
    db: Session,
    user: User,
    *,
    template: str,
    subject: str,
    html: str,
    text: str,
    category: str = "marketing",
) -> bool:
    """Send a templated email. Safe no-op when Resend isn't configured or
    user prefs disallow. Returns True on attempted send (whether successful
    or not — fire-and-forget); False on no-send.

    Always fires the email_sent analytics event for visibility regardless
    of whether the actual Resend call succeeded (one less observability
    gap during the no-key period)."""
    settings = get_settings()
    prefs = get_or_create_prefs(db, user.id)
    if not _prefs_allow(prefs, template, category):
        _log.info(
            "email_skipped user=%s template=%s reason=prefs", user.id, template,
        )
        return False

    client = _get_client()
    if client is None:
        # Log so we can see what WOULD have been sent during the
        # pre-Resend-key window. Useful for "DEFERRED_TRIGGER" greps.
        _log.info(
            "email_noop user=%s template=%s category=%s subject=%r",
            user.id, template, category, subject,
        )
        return False

    sender = (
        settings.resend_from_transactional
        if category == "transactional"
        else settings.resend_from_marketing
    )

    try:
        client.Emails.send({
            "from": sender,
            "to": [user.email],
            "subject": subject,
            "html": html,
            "text": text,
            "tags": [
                {"name": "template", "value": template},
                {"name": "category", "value": category},
            ],
        })
        _log.info("email_sent user=%s template=%s", user.id, template)
        _ph_capture(user.id, "email_sent", {
            "template": template,
            "category": category,
        })
        return True
    except Exception as exc:
        _log.warning("email_send_failed user=%s template=%s: %s",
                     user.id, template, exc)
        return False
