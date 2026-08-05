"""monitor_ticker_subscriptions cron (PRD-28).

Per-TICKER alerts. `monitor_saved_screens` (PRD-23c) already notifies when any
new name enters a saved screen — basket-scoped, and **entrants only**. A user
watching one name wants the opposite shape: nothing about the other 40 names,
but a notification in **both** directions, because "NVDA dropped out of my
reading" is the signal they actually can't get today.

Cheap by construction: `monitor_saved_screens` runs at 23:30 UTC and maintains
`screen_basket_members` (entered_date / exited_date). This job runs at 23:45,
*reads* that membership, and diffs it against each subscription's `last_state`.
No re-scan, no backtest, no LLM — a couple of indexed reads per subscription.

Emission reuses the PRD-19 stack verbatim: a real `SignalEvent` (valid because
`saved_screen_id` IS a `saved_strategies.id` — screens are stored as
SavedStrategy rows), the in-app banner, best-effort email, and the existing
per-strategy / per-user daily throttles.

Gated by `SCREENER_SNAPSHOT_ENABLED` — the same gate as the warm and the screen
monitor this job depends on. Plain `def` on APScheduler's threadpool, holding no
module-level asyncio primitives (traps #21 / #22).
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.saved_strategy import SavedStrategy
from app.models.screen_basket_member import ScreenBasketMember
from app.models.signal_event import SignalEvent
from app.models.ticker_signal_subscription import TickerSignalSubscription
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

logger = logging.getLogger("livermore.signals.ticker_cron")

STATE_IN = "in_basket"
STATE_OUT = "out_of_basket"

_CHANGE_ENTERED = "ticker_entered"
_CHANGE_EXITED = "ticker_exited"


def _enabled() -> bool:
    return os.environ.get("SCREENER_SNAPSHOT_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    )


def current_state(db, saved_screen_id: str, symbol: str) -> str:
    """Membership per `screen_basket_members`: a row with no `exited_date` means
    the name currently passes the screen's reading."""
    row = db.execute(
        select(ScreenBasketMember).filter(
            ScreenBasketMember.saved_strategy_id == saved_screen_id,
            ScreenBasketMember.symbol == symbol,
            ScreenBasketMember.exited_date.is_(None),
        )
    ).scalars().first()
    return STATE_IN if row is not None else STATE_OUT


def classify_ticker_change(previous: Optional[str], new: str) -> Optional[str]:
    """Transition type, or None when nothing should be emitted.

    `previous is None` is the first evaluation for a new subscription: record
    state silently, because firing on subscribe would notify the user about a
    condition that was already true when they asked to watch it.
    """
    if previous is None or previous == new:
        return None
    return _CHANGE_ENTERED if new == STATE_IN else _CHANGE_EXITED


def _display(symbol: str, change_type: str, screen_title: str) -> str:
    verb = "entered" if change_type == _CHANGE_ENTERED else "left"
    return f"{symbol} {verb} '{screen_title}'"


def monitor_ticker_subscriptions() -> dict:
    """Diff each per-ticker subscription against current basket membership;
    notify on transitions in both directions."""
    stats = {
        "subscriptions": 0,
        "entered": 0,
        "exited": 0,
        "dispatched": 0,
        "throttled": 0,
        "errors": 0,
    }
    if not _enabled():
        logger.info(
            "monitor_ticker_subscriptions: SCREENER_SNAPSHOT_ENABLED off — skipping"
        )
        return stats

    strat_counts: dict = {}
    user_counts: dict = {}
    today = date.today()

    with SessionLocal() as db:
        subs = db.execute(select(TickerSignalSubscription)).scalars().all()

        for sub in subs:
            stats["subscriptions"] += 1
            # Snapshot scalars before any commit expires the instance (trap #17).
            user_id = sub.user_id
            symbol = sub.symbol
            screen_id = sub.saved_screen_id
            previous = sub.last_state
            email_enabled = sub.email_enabled

            try:
                screen = db.get(SavedStrategy, screen_id)
                if screen is None:
                    # Screen deleted; the FK cascade normally removes the
                    # subscription, so this is belt-and-braces.
                    continue
                screen_title = screen.title

                new_state = current_state(db, screen_id, symbol)
                change_type = classify_ticker_change(previous, new_state)

                # Always persist the observed state, even with nothing to emit —
                # that's what makes the first pass silent and the second one
                # able to detect a transition.
                sub.last_state = new_state
                sub.last_as_of = today
                db.commit()

                if change_type is None:
                    continue

                stats["entered" if change_type == _CHANGE_ENTERED else "exited"] += 1

                display = _display(symbol, change_type, screen_title)
                event = SignalEvent(
                    id=str(uuid4()),
                    saved_strategy_id=screen_id,
                    previous_signal={"kind": "ticker_state", "state": previous},
                    previous_signal_display=None,
                    new_signal={
                        "kind": "ticker_state",
                        "symbol": symbol,
                        "state": new_state,
                    },
                    new_signal_display=display,
                    change_type=change_type,
                    as_of_date=today,
                    reference_price_snapshot=None,
                )
                db.add(event)
                db.commit()
                event_id = event.id

                t_key = throttle_key(screen_id, today)
                u_key = user_throttle_key(user_id, today)
                if throttle_strategy_daily(
                    strat_counts.get(t_key, 0)
                ) or throttle_user_daily(user_counts.get(u_key, 0)):
                    stats["throttled"] += 1
                    posthog_service.capture(
                        user_id=user_id,
                        event="notification_throttled",
                        properties={
                            "saved_strategy_id": screen_id,
                            "signal_event_id": event_id,
                            "symbol": symbol,
                            "reason": "ticker_alert_throttle",
                        },
                    )
                    continue

                user = db.get(User, user_id)
                channel_event = SignalChangeEvent(
                    user_email=user.email if user else "",
                    user_id=user_id,
                    strategy_name=screen_title,
                    strategy_slug=screen_id,
                    change_type=change_type,
                    new_signal_display=display,
                    as_of_date=today,
                    reference_prices={},
                    rule_context=(
                        f"{symbol} now passes your '{screen_title}' reading."
                        if change_type == _CHANGE_ENTERED
                        else f"{symbol} no longer passes your '{screen_title}' reading."
                    ),
                    risk_context="",
                    executed_url=f"/screens/{screen_id}",
                )
                # Banner is the durable record and always fires; email is
                # best-effort and must never break the run (the renderer falls
                # back to a generic verb for an unknown change_type).
                dispatch_in_app_banner(channel_event)
                if user is not None and email_enabled:
                    try:
                        dispatch_signal_change_email(channel_event, db, user)
                    except Exception:
                        logger.exception(
                            "ticker-alert email failed: user_id=%s symbol=%s",
                            user_id,
                            symbol,
                        )

                strat_counts[t_key] = strat_counts.get(t_key, 0) + 1
                user_counts[u_key] = user_counts.get(u_key, 0) + 1
                stats["dispatched"] += 1

            except Exception:
                stats["errors"] += 1
                logger.exception(
                    "ticker subscription check failed: user_id=%s symbol=%s screen=%s",
                    user_id,
                    symbol,
                    screen_id,
                )
                db.rollback()
                continue

    logger.info("monitor_ticker_subscriptions: %s", stats)
    return stats
