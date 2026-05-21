"""Welcome email template (Stage 6a).

Plain HTML — no React Email build step in v1. When the template count
grows past ~5 OR we need design polish, migrate to react-email + an
appropriate build pipeline.

CAN-SPAM compliance:
  - Physical postal address in footer (set CAN_SPAM_ADDRESS env or use the
    placeholder; replace with your real address before scaling >100 users)
  - One-click unsubscribe link with HMAC-signed token
  - "From" name + sender domain (set in resend_from_*)
"""
from __future__ import annotations

import os

from app.core.config import get_settings
from app.models.user import User
from app.services.email_service import make_unsub_token

# Override via env var before scaling. CAN-SPAM requires a valid US postal
# address in every marketing email.
CAN_SPAM_ADDRESS = os.environ.get(
    "CAN_SPAM_ADDRESS",
    "Livermore Alpha · [Update CAN_SPAM_ADDRESS env var before launch] · USA",
)


def render_welcome(user: User) -> dict[str, str]:
    """Return {subject, html, text} for the welcome email."""
    settings = get_settings()
    site_url = os.environ.get("NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com")
    name = user.display_name or "there"
    unsub_token = make_unsub_token(user.id, "all")
    unsub_url = f"{site_url}/api/email/unsub?token={unsub_token}"

    subject = "Welcome to Livermore Alpha — your first backtest is one click away"

    text = f"""Hey {name},

Welcome to Livermore. You're set up on the free Scout tier — 5 custom
backtests per week, unlimited templates, full access to the strategy
library.

A few things to try first:

1. Run a template
   {site_url}/templates
   22 pre-built strategies. They take 5 seconds to run on real market data.

2. Build a custom strategy via chat
   {site_url}/workspace
   Describe your idea in plain English; we parse it into runnable code.

3. Browse the community
   {site_url}/community
   See what other Livermore users are publishing.

If anything's confusing, reply to this email — it's a real inbox.

— The Livermore team

---
{CAN_SPAM_ADDRESS}

You're receiving this because you signed up at livermorealpha.com.
Unsubscribe from all marketing: {unsub_url}
"""

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.55;color:#0f172a;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#f6f7f9;">
    <tr><td>
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" width="560" style="max-width:560px;margin:32px auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;">
        <tr><td style="padding:32px 32px 0 32px;">
          <h1 style="margin:0 0 8px;font-size:22px;font-weight:700;">Welcome to Livermore</h1>
          <p style="margin:0;font-size:15px;color:#475569;">Hey {name} — you're set up on the free Scout tier.</p>
        </td></tr>
        <tr><td style="padding:24px 32px 8px 32px;">
          <p style="margin:0 0 16px;font-size:14px;">A few things to try first:</p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            <tr><td style="padding:12px 0;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:14px;font-weight:600;">1. Run a template</p>
              <p style="margin:4px 0 0;font-size:13px;color:#475569;">22 pre-built strategies. ~5 seconds on real market data.</p>
              <p style="margin:6px 0 0;"><a href="{site_url}/templates" style="color:#0ea5e9;text-decoration:none;font-size:13px;font-weight:600;">Browse templates →</a></p>
            </td></tr>
            <tr><td style="padding:12px 0;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:14px;font-weight:600;">2. Build a custom strategy via chat</p>
              <p style="margin:4px 0 0;font-size:13px;color:#475569;">Describe your idea in plain English; we parse it into runnable code.</p>
              <p style="margin:6px 0 0;"><a href="{site_url}/workspace" style="color:#0ea5e9;text-decoration:none;font-size:13px;font-weight:600;">Open the workspace →</a></p>
            </td></tr>
            <tr><td style="padding:12px 0;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:14px;font-weight:600;">3. Browse the community</p>
              <p style="margin:4px 0 0;font-size:13px;color:#475569;">See what other Livermore users are publishing.</p>
              <p style="margin:6px 0 0;"><a href="{site_url}/community" style="color:#0ea5e9;text-decoration:none;font-size:13px;font-weight:600;">Visit /community →</a></p>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:16px 32px 32px 32px;">
          <p style="margin:0;font-size:13px;color:#475569;">If anything's confusing, reply to this email — it's a real inbox.</p>
          <p style="margin:12px 0 0;font-size:13px;color:#475569;">— The Livermore team</p>
        </td></tr>
        <tr><td style="padding:16px 32px;border-top:1px solid #e2e8f0;background:#f8fafc;border-radius:0 0 12px 12px;">
          <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.5;">
            {CAN_SPAM_ADDRESS}<br>
            You're receiving this because you signed up at livermorealpha.com.<br>
            <a href="{unsub_url}" style="color:#64748b;text-decoration:underline;">Unsubscribe from all marketing</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return {"subject": subject, "html": html, "text": text}
