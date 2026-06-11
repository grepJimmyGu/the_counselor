"""Position-event email template — PRD-16c-4.

Rendered when the intraday monitor cron (PRD-16c-3b) fires a tier on
an open PositionState. Single renderer handles all three trigger types
(stop_hit, tp1_hit, tp2_hit, ...) — they share 95% of their content
(strategy name, symbol, entry → current, ladder summary, action). The
3% that differs (subject line emoji, action verb, color) is selected
from `trigger_type`.

Why one renderer instead of 3 files: mirrors `signal_change.py` —
single source of truth keeps the visual style identical across all
three event types and prevents copy drift between templates. Also
matches the JSON-driven catalog approach from PRD-16a where the
editorial content is data, not branching code.

Compliance footer mirrors `signal_change.py`:
  - "Not investment advice"
  - "Past performance does not guarantee future results"
  - "Livermore does not place trades on your behalf"
  - One-click unsubscribe (strategy-scoped + global)
  - CAN-SPAM postal address
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.models.user import User
from app.services.email_service import make_unsub_token

CAN_SPAM_ADDRESS = os.environ.get(
    "CAN_SPAM_ADDRESS",
    "Livermore Alpha · [Update CAN_SPAM_ADDRESS env var before launch] · USA",
)


@dataclass
class PositionEventPayload:
    """Plain-data input for the position-event template. Built by the
    cron from the PositionState + tier + trigger_type.

    Active-execution-v2: the cron does NOT mutate the position — it
    detects the trigger and constructs this payload to SUGGEST an action
    the user executes in their own brokerage. With `is_suggestion=True`
    (the default), the email is framed as advice ("your strategy says
    sell N of your M shares"), not a fait accompli. `is_suggestion=False`
    is reserved for any future replay/backtest surface that wants the
    "sold N shares" past-tense framing.
    """
    strategy_name: str
    strategy_id: str
    symbol: str
    trigger_type: str  # 'stop_hit' | 'tp1_hit' | 'tp2_hit' | ...
    tier_label: Optional[str]  # 'Stop' | 'TP1' | 'TP2' (from ExitTier)
    entry_price: float
    current_price: float
    pct_change: float  # already (current - entry) / entry
    action_taken: str  # 'sold_all' | 'sold_fraction'
    shares_sold: float           # suggested share count when is_suggestion
    shares_remaining: float
    fired_at: datetime
    # True (default) = advice framing; False = past-tense "sold" framing.
    is_suggestion: bool = True
    # Optional context the cron passes when populated; renderer degrades
    # gracefully when empty.
    other_tiers_summary: list[dict] = field(default_factory=list)


# Trigger-type → visual + copy mapping. Keep narrow and explicit so a
# new trigger doesn't silently render with the wrong tone.
_TRIGGER_META = {
    "stop_hit": {
        "verb": "stop hit",
        "color": "#ef4444",      # red
        "action_label": "Sell all",
        "emoji": "🛑",
    },
    "tp1_hit": {
        "verb": "first take-profit",
        "color": "#22c55e",      # green
        "action_label": "Partial out",
        "emoji": "🎯",
    },
    "tp2_hit": {
        "verb": "second take-profit",
        "color": "#10b981",      # green darker
        "action_label": "Close position",
        "emoji": "✅",
    },
}


def _trigger_meta(trigger_type: str) -> dict:
    """Default-safe lookup. Unknown trigger types render with neutral
    copy — covers tp3_hit / tp4_hit / etc. without per-tier hardcoding."""
    return _TRIGGER_META.get(trigger_type, {
        "verb": trigger_type.replace("_", " "),
        "color": "#0ea5e9",       # neutral blue
        "action_label": "Exit tier triggered",
        "emoji": "📍",
    })


def render_position_event(user: User, payload: PositionEventPayload) -> dict[str, str]:
    """Return {subject, html, text} for the position-event email."""
    meta = _trigger_meta(payload.trigger_type)
    site_url = os.environ.get("NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com")

    strategy_unsub_token = make_unsub_token(
        user.id, f"signal_alerts_{payload.strategy_id}"
    )
    strategy_unsub_url = (
        f"{site_url}/api/email/unsub?token={strategy_unsub_token}"
    )
    settings_url = f"{site_url}/account/notifications"
    detail_url = f"{site_url}/strategies/{payload.strategy_id}"
    executed_url = f"{detail_url}?action=executed"

    pct_str = f"{payload.pct_change * 100:+.1f}%"
    tier_str = payload.tier_label or meta["action_label"]
    subject = (
        f"{meta['emoji']} {payload.symbol} {tier_str} on "
        f"{payload.strategy_name} ({pct_str})"
    )

    if payload.is_suggestion:
        # Advice framing — Livermore never sells; the user does.
        action_line = (
            f"Your strategy suggests selling {payload.shares_sold:.4g} of "
            f"your {payload.shares_remaining:.4g} shares. Execute in your "
            "brokerage, then mark it executed in Livermore."
            if payload.action_taken == "sold_fraction"
            else (
                f"Your strategy suggests closing the position — sell all "
                f"{payload.shares_sold:.4g} shares. Execute in your brokerage, "
                "then mark it executed in Livermore."
            )
        )
        action_heading = "Suggested action"
    else:
        # Past-tense framing (replay / backtest surfaces).
        action_line = (
            f"Sold {payload.shares_sold:.4g} shares; "
            f"{payload.shares_remaining:.4g} remaining."
            if payload.action_taken == "sold_fraction"
            else f"Closed full position ({payload.shares_sold:.4g} shares)."
        )
        action_heading = "Action taken"

    text = f"""{payload.symbol} — {tier_str} on {payload.strategy_name}

{payload.fired_at.strftime('%B %-d, %Y %I:%M %p UTC')}

WHAT HAPPENED
{payload.symbol} reached the {meta['verb']} tier of your exit ladder.
Entry: ${payload.entry_price:.2f}
Current: ${payload.current_price:.2f}  ({pct_str})

{action_heading.upper()}
{action_line}

View strategy: {detail_url}
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
            {payload.fired_at.strftime('%B %-d, %Y %I:%M %p UTC')} · Active execution
          </p>
          <h1 style="margin:0 0 4px;font-size:20px;font-weight:700;">
            {meta['emoji']} {payload.symbol} — {tier_str}
          </h1>
          <p style="margin:0;font-size:16px;color:{meta['color']};font-weight:600;">
            {payload.strategy_name} · {pct_str}
          </p>
        </td></tr>
        <tr><td style="padding:16px 32px 8px 32px;">
          <p style="margin:0 0 4px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">What happened</p>
          <p style="margin:0;font-size:14px;">
            {payload.symbol} reached the {meta['verb']} tier of your exit ladder.
          </p>
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin-top:8px;font-size:14px;">
            <tr>
              <td style="padding:2px 16px 2px 0;color:#64748b;">Entry</td>
              <td style="padding:2px 0;font-weight:600;">${payload.entry_price:.2f}</td>
            </tr>
            <tr>
              <td style="padding:2px 16px 2px 0;color:#64748b;">Current</td>
              <td style="padding:2px 0;font-weight:600;color:{meta['color']};">${payload.current_price:.2f} ({pct_str})</td>
            </tr>
          </table>
        </td></tr>
        <tr><td style="padding:16px 32px 8px 32px;">
          <p style="margin:0 0 4px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;">{action_heading}</p>
          <p style="margin:0;font-size:14px;">{action_line}</p>
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
