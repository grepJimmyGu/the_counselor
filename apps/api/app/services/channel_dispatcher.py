"""Channel dispatcher — PRD-19 (Phase B re-shape).

Protocol for dispatching signal events across channels. Each dispatcher
is a plain function with no shared state. The cron calls dispatch()
which fans out to all configured channels for the event type.

Channels:
  - Email: signal_change + daily_digest (existing SMTP infra)
  - In-app: writes NotificationBannerEntry rows
  - Push/webhook: deferred to Sprint B/C (PRD-20/21)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

from app.services.email_service import send_email

_log = logging.getLogger("livermore.notifications")


# ── Event shape ──────────────────────────────────────────────────────────────


@dataclass
class SignalChangeEvent:
    """Payload for trigger #1 — Signal change."""
    user_email: str
    user_id: str
    strategy_name: str
    strategy_slug: str
    change_type: str               # "flip_to_cash" | "flip_to_long" | "rotation" | "rebalance"
    new_signal_display: str         # human-readable: "LONG NVDA" / "XLU 33%, XLP 33%, XLV 33%"
    as_of_date: date
    reference_prices: dict[str, float]  # symbol → close price
    rule_context: str               # "Top-3 by trailing 6-month return. XLK dropped rank 2 → rank 5."
    risk_context: str               # "YTD +14%. Trailing DD −6%. Signal stability: 0.82."
    executed_url: str               # deep-link to /strategies/{slug}?action=executed


@dataclass
class DigestEvent:
    """Payload for trigger #2 — Daily digest."""
    user_email: str
    user_id: str
    as_of_date: date
    changed_count: int
    stable_count: int
    headline_counter: str           # "1 changed · 4 stable · 0 new alerts"
    strategy_rows: list[dict] = field(default_factory=list)
    # Each row: {name, slug, signal_display, status: "changed"|"stable"|"cash", ytd_return}


# ── Dispatchers ──────────────────────────────────────────────────────────────


def dispatch_signal_change_email(event: SignalChangeEvent) -> bool:
    """Render and send the signal-change email. Returns True on success."""
    subject = _signal_change_subject(event)
    body = _render_signal_change_email(event)
    try:
        send_email(to=event.user_email, subject=subject, body_html=body)
        return True
    except Exception:
        _log.exception("Failed to send signal-change email to %s for %s",
                       event.user_email, event.strategy_slug)
        return False


def dispatch_digest_email(event: DigestEvent) -> bool:
    """Render and send the daily digest email. Returns True on success."""
    subject = f"Your morning brief: {event.headline_counter}"
    body = _render_digest_email(event)
    try:
        send_email(to=event.user_email, subject=subject, body_html=body)
        return True
    except Exception:
        _log.exception("Failed to send digest email to %s", event.user_email)
        return False


def dispatch_in_app_banner(event: SignalChangeEvent) -> bool:
    """Write a NotificationBannerEntry row for the in-app banner.
    Returns True even if the import fails (AKShare-style: lazy import,
    graceful fallback). The cron catches up on the next run."""
    try:
        from app.models.notification_banner import NotificationBannerEntry
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            db.add(NotificationBannerEntry(
                user_id=event.user_id,
                title=f"⚡ {event.strategy_name} — {event.new_signal_display}",
                body=event.rule_context,
                strategy_slug=event.strategy_slug,
            ))
            db.commit()
            return True
        finally:
            db.close()
    except Exception:
        _log.exception("In-app banner dispatch failed for %s/%s",
                       event.user_id, event.strategy_slug)
        return False


# ── Email rendering (inline templates — html files land in step 4) ──────────


def _signal_change_subject(event: SignalChangeEvent) -> str:
    """Subject line. No 'buy' or 'sell' verbs per compliance rules."""
    action_words = {
        "flip_to_cash": "went to cash",
        "flip_to_long": "entered position",
        "rotation": "rebalanced",
        "rebalance": "rebalanced",
    }
    action = action_words.get(event.change_type, "updated")
    return f"⚡ {event.strategy_name} {action} — {event.as_of_date.strftime('%b %-d')}"


def _render_signal_change_email(event: SignalChangeEvent) -> str:
    """Render the signal-change email body. Kept as inline HTML until
    the full Jinja2 template (step 4) lands. Contains all 8 info-architecture
    fields from the framework doc §2."""
    prices_html = "".join(
        f"<li>{sym}: ${price:.2f}</li>"
        for sym, price in event.reference_prices.items()
    )
    return f"""\
<h3>⚡ {event.strategy_name} — {event.new_signal_display}</h3>
<p>As of {event.as_of_date.strftime('%B %-d, %Y')} at 4:00 PM ET close.</p>

<h4>What changed</h4>
<p>{event.rule_context}</p>

<h4>Reference prices</h4>
<ul>{prices_html}</ul>

<h4>Risk context</h4>
<p>{event.risk_context}</p>

<p>
  <a href="{event.executed_url}">View strategy detail →</a>
  &nbsp;·&nbsp;
  <a href="{event.executed_url}&action=executed">I executed this</a>
</p>

<hr>
<p style="font-size:11px;color:#6a7282;">
  Not investment advice. Past performance does not guarantee future results.
  Livermore does not place trades on your behalf. You decide whether to act
  on this signal.<br/>
  <a href="{{unsubscribe_url}}">Unsubscribe from this strategy</a>
  · <a href="{{settings_url}}">Notification settings</a>
</p>
"""


def _render_digest_email(event: DigestEvent) -> str:
    """Render the daily digest email body. Kept inline until step 4."""
    rows_html = ""
    for row in event.strategy_rows:
        color = {"changed": "#d97706", "stable": "#16a34a", "cash": "#6b7280"}.get(
            row["status"], "#6b7280"
        )
        icon = {"changed": "⚠", "stable": "📈", "cash": "💤"}.get(row["status"], "")
        rows_html += (
            f'<li style="border-left:3px solid {color}; padding:8px; margin:4px 0;">'
            f"<strong>{icon} {row['name']}</strong> — {row['signal_display']}"
        )
        if row.get("ytd_return"):
            rows_html += f' · <span style="color: {color};">{row["ytd_return"]}</span>'
        rows_html += "</li>\n"

    return f"""\
<h3>{event.headline_counter}</h3>
<p>Your morning brief for {event.as_of_date.strftime('%B %-d, %Y')}.</p>

<ul style="list-style:none;padding:0;">{rows_html}</ul>

<p>
  <a href="{{base_url}}/strategies">Open My Strategies →</a>
  &nbsp;·&nbsp;
  <a href="{{settings_url}}">Notification settings</a>
</p>

<hr>
<p style="font-size:11px;color:#6a7282;">
  Sent because you opted in to daily digests.
  <a href="{{settings_url}}">Change cadence</a>
  · <a href="{{settings_url}}">Pause all digests</a>
</p>
"""
