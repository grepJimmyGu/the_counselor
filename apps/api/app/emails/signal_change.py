"""Signal-change email template — PRD-19 Step 3b.

Rendered when a saved strategy's signal flips (cron writes a SignalEvent
and the channel dispatcher fires this template). Distinct from `welcome`
in two ways:

  1. **Transactional, not marketing.** The user explicitly subscribed to
     this strategy's alerts via `SignalAlertSubscription`. Sending it is
     a fulfillment of that subscription, not promotional traffic — but we
     still honor the global unsubscribe flag in `email_service.send_email`
     because that's CAN-SPAM table-stakes.
  2. **Per-category unsubscribe.** The footer links a *strategy-scoped*
     unsubscribe URL (token category = `signal_alerts_<strategy_id>`)
     instead of the global one — letting the user mute one strategy
     without nuking all email. Step 4's preferences endpoint reads the
     `signal_alerts_*` flags.

Compliance footer mirrors PRD-19 §"Compliance":
  - "Not investment advice"
  - "Past performance does not guarantee future results"
  - "Livermore does not place trades on your behalf"
  - One-click unsubscribe (strategy-scoped + global)
  - CAN-SPAM postal address
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from app.models.user import User
from app.services.email_service import make_unsub_token

CAN_SPAM_ADDRESS = os.environ.get(
    "CAN_SPAM_ADDRESS",
    "Livermore Alpha · [Update CAN_SPAM_ADDRESS env var before launch] · USA",
)


@dataclass
class SignalChangePayload:
    """Plain-data input for the signal-change template. Built by the cron
    from the SignalEvent + BacktestResult; kept separate from the
    `SignalChangeEvent` dataclass in `channel_dispatcher` because that
    one is the *dispatcher protocol* shape (carries channel-specific
    URLs); this is the *renderer* shape (carries no URLs — those are
    derived from the user_id + strategy_id at render time)."""
    strategy_name: str
    strategy_id: str
    change_type: str
    new_signal_display: str
    as_of_date: date
    reference_prices: dict[str, float]
    rule_context: str
    risk_context: str


def render_signal_change(user: User, payload: SignalChangePayload) -> dict[str, str]:
    """Return {subject, html, text} for the signal-change email."""
    site_url = os.environ.get("NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com")

    # Strategy-scoped unsubscribe — the user can mute this single strategy
    # without losing the rest. Category embeds the strategy_id so verify
    # in the unsub endpoint can flip the right `signal_alerts_<id>` flag.
    strategy_unsub_token = make_unsub_token(
        user.id, f"signal_alerts_{payload.strategy_id}"
    )
    strategy_unsub_url = (
        f"{site_url}/api/email/unsub?token={strategy_unsub_token}"
    )
    settings_url = f"{site_url}/account/notifications"
    detail_url = f"{site_url}/strategies/{payload.strategy_id}"
    executed_url = f"{detail_url}?action=executed"

    action_words = {
        "flip_to_cash": "moved to cash",
        "flip_to_long": "entered position",
        "rotation": "rebalanced",
        "rebalance": "rebalanced",
    }
    action = action_words.get(payload.change_type, "updated its signal")

    subject = (
        f"{payload.strategy_name} {action} — "
        f"{payload.as_of_date.strftime('%b %-d')}"
    )

    prices_text = "\n".join(
        f"  {sym}: ${price:.2f}"
        for sym, price in payload.reference_prices.items()
    ) or "  (no reference prices available)"

    prices_html = "".join(
        f'<li style="margin:2px 0;">{sym}: <strong>${price:.2f}</strong></li>'
        for sym, price in payload.reference_prices.items()
    ) or '<li style="margin:2px 0;color:#94a3b8;">(no reference prices available)</li>'

    text = f"""{payload.strategy_name} — {payload.new_signal_display}

As of {payload.as_of_date.strftime('%B %-d, %Y')} at 4:00 PM ET close.

WHAT CHANGED
{payload.rule_context}

REFERENCE PRICES
{prices_text}

RISK CONTEXT
{payload.risk_context}

View detail: {detail_url}
Mark as executed: {executed_url}

---
Not investment advice. Past performance does not guarantee future results.
Livermore does not place trades on your behalf. You decide whether to act
on this signal.

{CAN_SPAM_ADDRESS}

Unsubscribe from this strategy's alerts: {strategy_unsub_url}
Notification settings: {settings_url}
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
        <tr><td style="padding:24px 32px 8px 32px;">
          <p style="margin:0 0 4px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:#64748b;">
            {payload.as_of_date.strftime('%B %-d, %Y')} · 4:00 PM ET close
          </p>
          <h1 style="margin:0 0 4px;font-size:20px;font-weight:700;">{payload.strategy_name}</h1>
          <p style="margin:0;font-size:16px;color:#0ea5e9;font-weight:600;">{payload.new_signal_display}</p>
        </td></tr>
        <tr><td style="padding:16px 32px 8px 32px;">
          <p style="margin:0 0 4px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">What changed</p>
          <p style="margin:0;font-size:14px;">{payload.rule_context}</p>
        </td></tr>
        <tr><td style="padding:16px 32px 8px 32px;">
          <p style="margin:0 0 4px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">Reference prices</p>
          <ul style="margin:0;padding-left:18px;font-size:14px;">{prices_html}</ul>
        </td></tr>
        <tr><td style="padding:16px 32px 16px 32px;">
          <p style="margin:0 0 4px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">Risk context</p>
          <p style="margin:0;font-size:14px;">{payload.risk_context}</p>
        </td></tr>
        <tr><td style="padding:8px 32px 24px 32px;">
          <a href="{detail_url}" style="display:inline-block;background:#0f172a;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;padding:10px 18px;border-radius:8px;margin-right:8px;">View strategy detail →</a>
          <a href="{executed_url}" style="display:inline-block;color:#0ea5e9;font-size:14px;font-weight:600;text-decoration:none;padding:10px 4px;">I executed this</a>
        </td></tr>
        <tr><td style="padding:16px 32px;border-top:1px solid #e2e8f0;background:#f8fafc;border-radius:0 0 12px 12px;">
          <p style="margin:0 0 8px;font-size:11px;color:#94a3b8;line-height:1.5;">
            Not investment advice. Past performance does not guarantee future results.
            Livermore does not place trades on your behalf. You decide whether to act
            on this signal.
          </p>
          <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.5;">
            {CAN_SPAM_ADDRESS}<br>
            <a href="{strategy_unsub_url}" style="color:#64748b;text-decoration:underline;">Unsubscribe from this strategy</a>
            · <a href="{settings_url}" style="color:#64748b;text-decoration:underline;">Notification settings</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return {"subject": subject, "html": html, "text": text}
