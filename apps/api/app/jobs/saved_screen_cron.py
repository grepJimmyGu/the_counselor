"""monitor_saved_screens cron (PRD-23c §3.2).

Re-scans every subscribed saved *screen* on a daily cadence (after the
`signal_snapshot` warm), diffs each basket, and dispatches a PRD-19
notification per NEW entrant — transition-only: a name staying in the basket
fires nothing, a re-entry after an exit fires again. Exits are recorded by
`rescan_and_diff` for the history but are NOT notified.

Reuses the PRD-19 dispatch stack wholesale — `SignalEvent` (source of truth) +
the channel dispatcher (in-app banner + best-effort email) + the per-strategy /
per-user daily throttle. No new notification machinery.

Gated by `SCREENER_SNAPSHOT_ENABLED` (a screen can't be scanned without a
warmed snapshot). This is a plain `def` run by APScheduler's threadpool (like
`compute_all_signals`), so it does not block the event loop and touches no
module-level asyncio primitives (traps #21/#22).
"""
from __future__ import annotations

import logging
import os
from datetime import date
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.saved_strategy import SavedStrategy
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.signal_event import SignalEvent
from app.models.user import User
from app.services import posthog_service
from app.services.channel_dispatcher import (
    SignalChangeEvent,
    dispatch_in_app_banner,
    dispatch_signal_change_email,
)
from app.services.notification_throttle import (
    throttle_key,
    throttle_strategy_daily,
    throttle_user_daily,
    user_throttle_key,
)
from app.services.screener.saved_screen_service import is_screen, rescan_and_diff

logger = logging.getLogger("livermore.screener.cron")

_CHANGE_TYPE = "screen_entrant"


def _enabled() -> bool:
    return os.environ.get("SCREENER_SNAPSHOT_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    )


def monitor_saved_screens() -> dict:
    """Re-scan + diff every subscribed saved screen; notify on each new entrant."""
    stats = {"screens": 0, "entrants": 0, "dispatched": 0, "throttled": 0, "errors": 0}
    if not _enabled():
        logger.info("monitor_saved_screens: SCREENER_SNAPSHOT_ENABLED off — skipping")
        return stats

    # Per-run in-memory throttle counters (the SignalEvent table is the durable
    # source of truth; these mirror signal_cron's intra-run accounting).
    strat_counts: dict = {}
    user_counts: dict = {}

    with SessionLocal() as db:
        screens = (
            db.execute(
                select(SavedStrategy).join(
                    SignalAlertSubscription,
                    SignalAlertSubscription.saved_strategy_id == SavedStrategy.id,
                )
            )
            .scalars()
            .all()
        )

        for saved in screens:
            if not is_screen(saved):
                continue
            stats["screens"] += 1
            # Snapshot scalars before rescan_and_diff commits (trap #17).
            saved_id, title, user_id = saved.id, saved.title, saved.user_id

            try:
                diff = rescan_and_diff(db, saved)
            except Exception:
                stats["errors"] += 1
                logger.exception("screen rescan failed: saved_strategy_id=%s", saved_id)
                db.rollback()
                continue

            if not diff.new_entrants:
                continue

            stats["entrants"] += len(diff.new_entrants)
            user = db.get(User, user_id)
            user_email = user.email if user else ""
            anchor = diff.as_of_date or date.today()

            for symbol in diff.new_entrants:
                display = f"{symbol} entered '{title}'"
                event = SignalEvent(
                    id=str(uuid4()),
                    saved_strategy_id=saved_id,
                    previous_signal=None,
                    previous_signal_display=None,
                    new_signal={"kind": _CHANGE_TYPE, "symbol": symbol},
                    new_signal_display=display,
                    change_type=_CHANGE_TYPE,
                    as_of_date=anchor,
                    reference_price_snapshot=None,
                )
                db.add(event)
                db.commit()
                event_id = event.id

                t_key = throttle_key(saved_id, anchor)
                u_key = user_throttle_key(user_id, anchor)
                if throttle_strategy_daily(
                    strat_counts.get(t_key, 0)
                ) or throttle_user_daily(user_counts.get(u_key, 0)):
                    stats["throttled"] += 1
                    posthog_service.capture(
                        user_id=user_id,
                        event="notification_throttled",
                        properties={
                            "saved_strategy_id": saved_id,
                            "signal_event_id": event_id,
                            "reason": "screen_entrant_throttle",
                        },
                    )
                    continue

                channel_event = SignalChangeEvent(
                    user_email=user_email,
                    user_id=user_id,
                    strategy_name=title,
                    strategy_slug=saved_id,
                    change_type=_CHANGE_TYPE,
                    new_signal_display=display,
                    as_of_date=anchor,
                    reference_prices={},
                    rule_context=f"A new name entered your '{title}' screen.",
                    risk_context="",
                    executed_url=f"/strategies/{saved_id}",
                )
                # In-app banner always fires (the durable record); email is
                # best-effort (the renderer falls back to a generic verb for an
                # unknown change_type, so this can't crash the run).
                dispatch_in_app_banner(channel_event)
                if user is not None:
                    try:
                        dispatch_signal_change_email(channel_event, db, user)
                    except Exception:
                        logger.exception(
                            "screen-entrant email failed: user_id=%s symbol=%s",
                            user_id,
                            symbol,
                        )

                strat_counts[t_key] = strat_counts.get(t_key, 0) + 1
                user_counts[u_key] = user_counts.get(u_key, 0) + 1
                stats["dispatched"] += 1

    logger.info("monitor_saved_screens: %s", stats)
    return stats
