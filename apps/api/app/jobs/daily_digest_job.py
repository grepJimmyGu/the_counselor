"""Daily digest cron — PRD-19 Step 4b.

Runs each morning AFTER `signal_cron` has written the day's SignalEvents.
For every user with `EmailPreference.daily_digest_enabled=True` and at
least one active SignalAlertSubscription:

  1. Aggregate today's SignalEvents on subscribed strategies
  2. Bucket each strategy as "changed" (SignalEvent today), "stable" (no
     change, currently long), or "cash" (no change, currently cash)
  3. If `silent_days_enabled=True` AND `changed_count == 0` → skip
     (per `notification_throttle.should_skip_digest`)
  4. Build a `DigestEvent`, call `dispatch_digest_email`
  5. PostHog capture `daily_digest_dispatched` for observability

Schedule: 13:00 UTC (~9am ET, ~6am PT) — well after `signal_cron`'s 22:00
UTC tick lands SignalEvents for the previous trading day.

**Trap #21**: APScheduler's BackgroundScheduler does not await coroutines.
The public entry `run_daily_digest_job` is sync; the body is sync DB
queries. No `asyncio.run` wrapper needed because nothing here is async.
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.email_preference import EmailPreference
from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.signal_event import SignalEvent
from app.models.user import User
from app.services import posthog_service
from app.services.channel_dispatcher import DigestEvent, dispatch_digest_email
from app.services.notification_throttle import should_skip_digest

_log = logging.getLogger("livermore.daily_digest")


def run_daily_digest_job() -> dict:
    """Public cron entry point. Returns {users_considered, sent, skipped,
    errors} for observability."""
    db = SessionLocal()
    stats = {"users_considered": 0, "sent": 0, "skipped": 0, "errors": 0}
    # Same UTC date as `signal_cron` so the SignalEvent window aligns
    # (trap #16). The digest summarizes events from `today` UTC — the
    # day the cron already wrote SignalEvents for.
    today = datetime.utcnow().date()

    try:
        # All users who have at least one active signal subscription.
        # We don't enumerate the full users table — most don't get digests.
        user_ids = db.execute(
            select(SignalAlertSubscription.user_id)
            .where(SignalAlertSubscription.email_enabled.is_(True))
            .distinct()
        ).scalars().all()

        for user_id in user_ids:
            stats["users_considered"] += 1
            try:
                _process_user(db, user_id, today, stats)
            except Exception:
                _log.exception("daily_digest: failed for user %s", user_id)
                stats["errors"] += 1
                db.rollback()

    finally:
        db.close()

    _log.info("daily_digest run complete: %s", stats)
    return stats


def _process_user(db: Session, user_id: str, today: date, stats: dict) -> None:
    """Build the digest for one user. Mutates `stats` in place."""
    user = db.get(User, user_id)
    if user is None:
        return

    # Read prefs — gate on daily_digest_enabled + global unsubscribed_at.
    # `_prefs_allow` inside `send_email` will gate again at dispatch time,
    # but we check here to avoid the wasted work of building the event.
    prefs = db.get(EmailPreference, user_id)
    if prefs is not None and not prefs.daily_digest_enabled:
        stats["skipped"] += 1
        return
    if prefs is not None and prefs.unsubscribed_at is not None:
        stats["skipped"] += 1
        return
    silent_days = bool(prefs and prefs.silent_days_enabled)

    # Active subscriptions for this user.
    subs = db.execute(
        select(SignalAlertSubscription)
        .where(SignalAlertSubscription.user_id == user_id)
        .where(SignalAlertSubscription.email_enabled.is_(True))
    ).scalars().all()
    if not subs:
        stats["skipped"] += 1
        return

    strategy_ids = [s.saved_strategy_id for s in subs]

    # Today's SignalEvents for subscribed strategies. We compare against
    # `as_of_date` because that's the trading-day anchor — `created_at`
    # is a UTC timestamp that could fall on either side of a date boundary.
    events = db.execute(
        select(SignalEvent)
        .where(SignalEvent.saved_strategy_id.in_(strategy_ids))
        .where(SignalEvent.as_of_date == today)
    ).scalars().all()
    changed_strategy_ids = {e.saved_strategy_id for e in events}

    # Silent-days skip: if the user opted into "only when there's news" and
    # nothing changed, return without dispatching.
    if should_skip_digest(len(changed_strategy_ids), silent_days):
        stats["skipped"] += 1
        # PostHog event so the dashboard can count "silent days saved".
        posthog_service.capture(
            user_id=user_id,
            event="daily_digest_skipped_silent_day",
            properties={"subscribed_count": len(subs)},
        )
        return

    # Build the row list — one entry per subscribed strategy with its
    # current bucket.
    strategy_rows: list[dict] = []
    changed_count = 0
    stable_count = 0
    cash_count = 0
    for strat_id in strategy_ids:
        strat = db.get(SavedStrategy, strat_id)
        if strat is None:
            continue  # subscription orphan; skip silently
        state = db.get(SavedStrategySignalState, strat_id)
        signal_display = (
            state.current_signal_display if state and state.current_signal_display
            else "—"
        )
        if strat_id in changed_strategy_ids:
            status = "changed"
            changed_count += 1
        elif state and state.current_signal and _is_cash(state.current_signal):
            status = "cash"
            cash_count += 1
        else:
            status = "stable"
            stable_count += 1
        strategy_rows.append({
            "name": strat.title or "(untitled)",
            "slug": strat.id,
            "signal_display": signal_display,
            "status": status,
        })

    digest = DigestEvent(
        user_email=user.email,
        user_id=user_id,
        as_of_date=today,
        changed_count=changed_count,
        stable_count=stable_count,
        cash_count=cash_count,
        headline_counter=_format_headline(changed_count, stable_count, cash_count),
        strategy_rows=strategy_rows,
    )

    sent = dispatch_digest_email(digest, db, user)
    if sent:
        stats["sent"] += 1
        posthog_service.capture(
            user_id=user_id,
            event="daily_digest_dispatched",
            properties={
                "changed_count": changed_count,
                "stable_count": stable_count,
                "cash_count": cash_count,
                "subscribed_count": len(subs),
            },
        )
    else:
        # `send_email` returns False when prefs forbid OR when Resend has
        # no key — both are "couldn't send" but neither is an error per se.
        # `_prefs_allow`'s post-Step-4a check on signal_alerts_enabled is
        # irrelevant here (template is daily_digest), but the marketing
        # gate or unsubscribed_at gate still applies.
        stats["skipped"] += 1


def _format_headline(changed: int, stable: int, cash: int) -> str:
    """Same shape as DigestPayload.headline_counter — used here so the
    DigestEvent (the dispatch protocol shape) and DigestPayload (the
    renderer shape) agree on phrasing."""
    parts = []
    if changed:
        parts.append(f"{changed} changed")
    if stable:
        parts.append(f"{stable} stable")
    if cash:
        parts.append(f"{cash} in cash")
    return " · ".join(parts) if parts else "No active strategies"


def _is_cash(signal: dict) -> bool:
    """The signal payload's shape varies by strategy type. For the single-
    asset strategies signal_cron writes `{"position": "cash"|"long", ...}`.
    For basket strategies the payload has `{"holdings": [...]}` — non-empty
    holdings means not-cash. This helper centralizes the bucket logic so
    the digest doesn't drift from `signal_service.classify_change`."""
    if not isinstance(signal, dict):
        return False
    if signal.get("position") == "cash":
        return True
    holdings = signal.get("holdings")
    if isinstance(holdings, list) and len(holdings) == 0:
        return True
    return False
