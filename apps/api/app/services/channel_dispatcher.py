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


def dispatch_signal_change_email(event: SignalChangeEvent, db, user) -> bool:
    """Render and send the signal-change email. Returns True if `send_email`
    attempted the dispatch (matches its fire-and-forget contract — the
    actual Resend call may still no-op if the user has globally
    unsubscribed or Resend isn't configured).

    PRD-19 Step 3b note: this used to call `send_email(to=..., subject=...,
    body_html=...)` — a signature that never existed. The real
    `email_service.send_email` takes `(db, user, *, template, subject,
    html, text, category)`. Step 3a/3b is the first wiring that actually
    reaches the dispatcher; the broken signature would have raised
    TypeError on every invocation, been swallowed by this function's
    try/except, and logged once per cron tick. The fix is to call
    `send_email` correctly + render via `render_signal_change` (a real
    Jinja-free html+text pair, not the inline body fragment that used
    `{{unsubscribe_url}}` literals).

    Signal-change emails are marked `category="transactional"` because the
    user explicitly subscribed via `SignalAlertSubscription` — that path
    bypasses the marketing unsubscribe flag in `_prefs_allow` while still
    honoring the per-category flags Step 4 will add."""
    from app.emails.signal_change import render_signal_change, SignalChangePayload

    payload = SignalChangePayload(
        strategy_name=event.strategy_name,
        strategy_id=event.strategy_slug,
        change_type=event.change_type,
        new_signal_display=event.new_signal_display,
        as_of_date=event.as_of_date,
        reference_prices=event.reference_prices,
        rule_context=event.rule_context,
        risk_context=event.risk_context,
    )
    rendered = render_signal_change(user, payload)
    try:
        return send_email(
            db,
            user,
            template="signal_change",
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            category="transactional",
        )
    except Exception:
        _log.exception("Failed to send signal-change email to %s for %s",
                       user.id, event.strategy_slug)
        return False


def dispatch_digest_email(event: DigestEvent, db, user) -> bool:
    """Render and send the daily digest email. Returns True if send_email
    attempted dispatch. Same signature-fix story as
    `dispatch_signal_change_email` — Step 4 lands the real renderer."""
    subject = f"Your morning brief: {event.headline_counter}"
    body = _render_digest_email(event)
    try:
        return send_email(
            db,
            user,
            template="daily_digest",
            subject=subject,
            html=body,
            text=_strip_html(body),
            category="marketing",
        )
    except Exception:
        _log.exception("Failed to send digest email to %s", user.id)
        return False


def _strip_html(html: str) -> str:
    """Minimal HTML → plain-text for the digest fallback. Step 4 replaces
    this with a real plain-text render. Until then, this strips tags and
    collapses whitespace so the text body isn't empty (Resend rejects)."""
    import re
    no_tags = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", no_tags).strip()


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
