"""Direct ops-alert email sender.

Distinct from `email_service.send_email` because:
  - No `User` object — recipient is an env var (`OPS_ALERT_RECIPIENT`)
  - Bypasses user prefs / unsubscribe (ops alerts must always deliver)
  - Uses the transactional sender so it doesn't hit marketing reputation

Wired to Resend (same provider as the existing transactional path) so we
inherit the API key + sender domain already set on Railway. Returns
`True` on attempted send, `False` on no-send (no key, no recipient,
client failure). Failures are logged but never raise — an ops alert
fail must not crash the cron.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import get_settings
from app.services.email_service import _get_client  # type: ignore[attr-defined]

_log = logging.getLogger("livermore.ops_email")


def send_ops_email(*, subject: str, html: str, text: str) -> bool:
    """Send a transactional ops email to `OPS_ALERT_RECIPIENT`.

    Returns True if an attempt was made (Resend.Emails.send was called),
    False if we skipped (no recipient configured, no API key, or client
    init failed). Never raises.
    """
    settings = get_settings()
    recipient: Optional[str] = (settings.ops_alert_recipient or "").strip() or None
    if recipient is None:
        _log.info("ops_email_skipped reason=no_recipient subject=%r", subject)
        return False

    client = _get_client()
    if client is None:
        _log.info("ops_email_noop reason=no_resend_key subject=%r recipient=%s", subject, recipient)
        return False

    sender = settings.resend_from_transactional
    try:
        client.Emails.send({
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "html": html,
            "text": text,
            "tags": [
                {"name": "template", "value": "ops_health_alert"},
                {"name": "category", "value": "ops"},
            ],
        })
        _log.info("ops_email_sent recipient=%s subject=%r", recipient, subject)
        return True
    except Exception:
        # Never raise — caller is a cron that must keep running.
        _log.exception("ops_email_failed recipient=%s subject=%r", recipient, subject)
        return False
