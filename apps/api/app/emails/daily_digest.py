"""Daily digest email template — PRD-19 Step 4b.

Rendered each morning by `daily_digest_job` for users with
`EmailPreference.daily_digest_enabled=True`. Aggregates all of yesterday's
signal changes for the user's subscribed strategies into a single email so
they get one summary instead of N per-strategy alerts.

Distinct from `signal_change.py`:
  - `category="marketing"` (not transactional) — the user opted in via the
    settings page, so this is promotional under CAN-SPAM and respects
    `unsubscribed_at` even without the per-template flag.
  - One row per subscribed strategy, status-color-coded (changed / stable
    / cash).
  - Compliance footer is the same "not investment advice" boilerplate +
    a signed `daily_digest` unsubscribe token (separate from the
    `signal_alerts_<id>` strategy-scoped tokens Step 4c will route).

Step 4c lands the unsub webhook side that turns
`category="daily_digest"` tokens into `daily_digest_enabled=False`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

from app.models.user import User
from app.services.email_service import make_unsub_token

CAN_SPAM_ADDRESS = os.environ.get(
    "CAN_SPAM_ADDRESS",
    "Livermore Alpha · [Update CAN_SPAM_ADDRESS env var before launch] · USA",
)


@dataclass
class DigestPayload:
    """Plain-data input for the digest renderer. Built by the cron from
    the user's SignalAlertSubscriptions + today's SignalEvents."""
    as_of_date: date
    changed_count: int
    stable_count: int
    cash_count: int = 0
    strategy_rows: list[dict] = field(default_factory=list)
    # Each row: {name, slug, signal_display, status, ytd_return}
    #   status ∈ {"changed", "stable", "cash"}
    #   ytd_return is optional (e.g. "+3.2% YTD"); rendered when present.

    @property
    def headline_counter(self) -> str:
        """The summary line at the top — "1 changed · 4 stable · 0 in cash"."""
        parts = []
        if self.changed_count:
            parts.append(f"{self.changed_count} changed")
        if self.stable_count:
            parts.append(f"{self.stable_count} stable")
        if self.cash_count:
            parts.append(f"{self.cash_count} in cash")
        return " · ".join(parts) if parts else "No active strategies"


def render_daily_digest(user: User, payload: DigestPayload) -> dict[str, str]:
    """Return {subject, html, text} for the morning-brief email."""
    site_url = os.environ.get("NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com")

    unsub_token = make_unsub_token(user.id, "daily_digest")
    unsub_url = f"{site_url}/api/email/unsub?token={unsub_token}"
    settings_url = f"{site_url}/account/notifications"
    library_url = f"{site_url}/strategies"

    subject = f"Your morning brief: {payload.headline_counter}"

    # Plain-text body — Resend rejects empty text bodies, and a real
    # render beats the html-stripper fallback for screen-reader users.
    rows_text = "\n".join(
        f"  - {row['name']}: {row['signal_display']}"
        + (f"  ({row['ytd_return']})" if row.get("ytd_return") else "")
        for row in payload.strategy_rows
    )
    if not rows_text:
        rows_text = "  (no strategies tracked)"

    text = f"""{payload.headline_counter}

Your morning brief for {payload.as_of_date.strftime('%B %-d, %Y')}.

{rows_text}

Open My Strategies: {library_url}
Notification settings: {settings_url}

---
Not investment advice. Past performance does not guarantee future results.
Livermore does not place trades on your behalf. You decide whether to act
on any signal.

{CAN_SPAM_ADDRESS}

Sent because you opted in to daily digests.
Change cadence: {settings_url}
Unsubscribe from digests: {unsub_url}
"""

    rows_html = ""
    for row in payload.strategy_rows:
        color = {
            "changed": "#d97706",  # amber-600
            "stable": "#16a34a",   # green-600
            "cash": "#6b7280",     # slate-500
        }.get(row.get("status", ""), "#6b7280")
        icon = {"changed": "⚠", "stable": "📈", "cash": "💤"}.get(
            row.get("status", ""), ""
        )
        rows_html += (
            f'<li style="border-left:3px solid {color};padding:8px 12px;margin:8px 0;'
            f'background:#fafbfc;border-radius:0 6px 6px 0;list-style:none;">'
            f'<strong style="font-size:14px;">{icon} {row["name"]}</strong> '
            f'<span style="color:#475569;font-size:13px;">— {row["signal_display"]}</span>'
        )
        if row.get("ytd_return"):
            rows_html += (
                f' <span style="color:{color};font-size:12px;font-weight:600;">'
                f'· {row["ytd_return"]}</span>'
            )
        rows_html += "</li>\n"

    if not rows_html:
        rows_html = (
            '<li style="color:#94a3b8;padding:12px;text-align:center;list-style:none;">'
            "(no strategies tracked)</li>"
        )

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
        <tr><td style="padding:24px 32px 4px 32px;">
          <p style="margin:0 0 4px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:#64748b;">
            {payload.as_of_date.strftime('%B %-d, %Y')} · Morning brief
          </p>
          <h1 style="margin:0;font-size:20px;font-weight:700;">{payload.headline_counter}</h1>
        </td></tr>
        <tr><td style="padding:8px 32px 8px 32px;">
          <ul style="margin:0;padding:0;">{rows_html}</ul>
        </td></tr>
        <tr><td style="padding:12px 32px 24px 32px;">
          <a href="{library_url}" style="display:inline-block;background:#0f172a;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;padding:10px 18px;border-radius:8px;margin-right:8px;">Open My Strategies →</a>
          <a href="{settings_url}" style="display:inline-block;color:#0ea5e9;font-size:14px;font-weight:600;text-decoration:none;padding:10px 4px;">Notification settings</a>
        </td></tr>
        <tr><td style="padding:16px 32px;border-top:1px solid #e2e8f0;background:#f8fafc;border-radius:0 0 12px 12px;">
          <p style="margin:0 0 8px;font-size:11px;color:#94a3b8;line-height:1.5;">
            Not investment advice. Past performance does not guarantee future results.
            Livermore does not place trades on your behalf. You decide whether to act
            on any signal.
          </p>
          <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.5;">
            {CAN_SPAM_ADDRESS}<br>
            Sent because you opted in to daily digests.
            <a href="{settings_url}" style="color:#64748b;text-decoration:underline;">Change cadence</a>
            · <a href="{unsub_url}" style="color:#64748b;text-decoration:underline;">Unsubscribe</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return {"subject": subject, "html": html, "text": text}
