"""Signal-alert email template (Stage 8 v0 — Phase B).

Plain HTML — matches the `welcome.py` pattern. React Email migration is
deferred until template count grows past ~5 or design polish is needed.

CAN-SPAM compliance:
  - Physical postal address in footer (set CAN_SPAM_ADDRESS env or use the
    placeholder; replace with your real address before scaling >100 users).
  - Two unsubscribe links — single-strategy and all-signals — both HMAC-signed.
  - "From" name + sender domain handled by `email_service.send_email`.

Legal disclaimer text is the canonical wording from spec §11 (Lowe v. SEC
publisher's exclusion). Any future edit must preserve substantive equivalence;
get a securities lawyer to bless any rewording before launch.
"""
from __future__ import annotations

import os
from typing import Optional

from app.models.saved_strategy import SavedStrategy
from app.models.signal_event import SignalEvent
from app.models.user import User

# Same CAN-SPAM footer pattern as welcome.py. Override via env var before scaling.
CAN_SPAM_ADDRESS = os.environ.get(
    "CAN_SPAM_ADDRESS",
    "Livermore Alpha · [Update CAN_SPAM_ADDRESS env var before launch] · USA",
)

# Spec §11 canonical disclaimer text. Substantive changes require a securities-law
# opinion letter; surface this constant in any future edit review.
DISCLAIMER_SHORT = (
    "Research only — not investment advice. Livermore publishes algorithmic "
    "signals from quantitative strategies you choose to follow. We are not a "
    "registered investment adviser. Past performance does not guarantee future "
    "results. You decide what to do — consult a licensed financial advisor "
    "before making investment decisions."
)


def _subject_for(event: SignalEvent) -> str:
    """Per spec §7 — change-type-specific subject line, primary ticker if applicable."""
    ct = event.change_type
    if ct == "flip_to_cash":
        ticker = (event.previous_signal or {}).get("ticker") or "position"
        return f"Your saved strategy signaled SELL {ticker}"
    if ct == "flip_to_long":
        ticker = (event.new_signal or {}).get("ticker") or "position"
        return f"Your saved strategy signaled BUY {ticker}"
    if ct == "rotation":
        return "Your saved strategy rotated holdings"
    if ct == "rebalance":
        return "Your saved strategy rebalanced"
    return "Your saved strategy signal changed"


def _format_prices(prices: Optional[dict]) -> str:
    """One-line reference-price snapshot for the email body."""
    if not prices:
        return "(no reference prices recorded)"
    items = sorted(prices.items())[:6]  # cap so a basket strategy doesn't dump a wall
    return ", ".join(f"{t} ${p:.2f}" for t, p in items)


def render_signal_alert(
    user: User,
    saved_strategy: SavedStrategy,
    event: SignalEvent,
    single_unsub_url: str,
    all_unsub_url: str,
) -> dict[str, str]:
    """Return {subject, html, text} for a signal-change alert email.

    Caller is the daily recompute cron in `jobs/signal_jobs.py`. The cron is
    responsible for HMAC-signing the unsub URLs via
    `email_service.make_signal_unsub_token`.
    """
    site_url = os.environ.get("NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com")
    name = user.display_name or "there"
    strategy_url = f"{site_url}/account/saved/{saved_strategy.id}"
    subject = _subject_for(event)

    previous_display = event.previous_signal_display or "(no prior state — first computation)"
    new_display = event.new_signal_display
    prices_line = _format_prices(event.reference_price_snapshot)
    as_of = event.as_of_date.isoformat() if event.as_of_date else "today"

    text = f"""Hi {name},

Your saved strategy [{saved_strategy.title}] changed its signal today.

  Previous: {previous_display}
  Now:      {new_display}
  As of:    {as_of}
  Reference prices: {prices_line}

This is what the strategy you chose to follow is saying. Livermore is not
recommending you trade — that decision is yours, in your own broker.

View the strategy → {strategy_url}

---
{DISCLAIMER_SHORT}

Stop alerts for this strategy: {single_unsub_url}
Stop all signal alerts:        {all_unsub_url}

---
{CAN_SPAM_ADDRESS}
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
          <p style="margin:0 0 4px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:#64748b;">Signal change · {as_of}</p>
          <h1 style="margin:0 0 8px;font-size:22px;font-weight:700;">{subject}</h1>
          <p style="margin:0;font-size:15px;color:#475569;">Hey {name} — your strategy <strong>{saved_strategy.title}</strong> updated its position.</p>
        </td></tr>
        <tr><td style="padding:24px 32px 8px 32px;">
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="border:1px solid #e2e8f0;border-radius:8px;">
            <tr><td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;background:#f8fafc;">
              <p style="margin:0;font-size:12px;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">Previous</p>
              <p style="margin:4px 0 0;font-size:14px;">{previous_display}</p>
            </td></tr>
            <tr><td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;">
              <p style="margin:0;font-size:12px;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">Now</p>
              <p style="margin:4px 0 0;font-size:14px;font-weight:600;">{new_display}</p>
            </td></tr>
            <tr><td style="padding:12px 16px;">
              <p style="margin:0;font-size:12px;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">Reference prices</p>
              <p style="margin:4px 0 0;font-size:13px;color:#475569;">{prices_line}</p>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:16px 32px 8px 32px;">
          <p style="margin:0 0 16px;font-size:14px;color:#475569;">This is what the strategy you chose to follow is saying. Livermore does not place trades or recommend specific actions to you — that decision is yours, in your own broker.</p>
          <p style="margin:0;"><a href="{strategy_url}" style="display:inline-block;padding:10px 20px;background:#0ea5e9;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;border-radius:6px;">View the strategy →</a></p>
        </td></tr>
        <tr><td style="padding:16px 32px;border-top:1px solid #e2e8f0;background:#f8fafc;">
          <p style="margin:0;font-size:11px;color:#64748b;line-height:1.5;">{DISCLAIMER_SHORT}</p>
        </td></tr>
        <tr><td style="padding:16px 32px;background:#f8fafc;border-radius:0 0 12px 12px;">
          <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.5;">
            {CAN_SPAM_ADDRESS}<br>
            <a href="{single_unsub_url}" style="color:#64748b;text-decoration:underline;">Stop alerts for this strategy</a>
            &nbsp;·&nbsp;
            <a href="{all_unsub_url}" style="color:#64748b;text-decoration:underline;">Stop all signal alerts</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return {"subject": subject, "html": html, "text": text}
