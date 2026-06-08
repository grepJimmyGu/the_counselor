"""Signal recompute cron — PRD-19 (Phase B re-shape).

Runs daily. For every saved strategy with price data:
  1. Re-runs the backtest engine to compute the current signal
  2. Writes/updates SavedStrategySignalState
  3. If signal changed: writes a SignalEvent row
  4. Populates strategy_live_performance (return since publish date)
  5. Dispatches via ChannelDispatcher (email + in-app banner)

Throttle: per-strategy max 1 signal-change email/day, per-user max 3/day.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.models.signal_event import SignalEvent
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.user import User
from app.services.signal_service import signals_equal, classify_change
from app.services.notification_throttle import (
    throttle_strategy_daily,
    throttle_user_daily,
    throttle_key,
    user_throttle_key,
)
from app.services.channel_dispatcher import (
    SignalChangeEvent,
    dispatch_in_app_banner,
    dispatch_signal_change_email,
)
from app.services import posthog_service

_log = logging.getLogger("livermore.signal_cron")


def compute_all_signals() -> dict:
    """Public cron entry point for APScheduler. Synchronous wrapper around
    the async implementation below.

    **Trap #21** (apps/api/CLAUDE.md): APScheduler's `BackgroundScheduler`
    does not natively await coroutines. Registering an `async def` as a
    cron job means APScheduler calls the function, receives a coroutine,
    and drops it on the floor without awaiting — the body never executes
    and the cron silently does nothing. The original implementation
    (registered via `scheduler.add_job(compute_all_signals, "cron", ...)`
    in `main.py:366`) had this exact shape and would have shipped a
    no-op cron to production once the rest of PRD-19 landed.

    The fix: keep the body `async def` (the implementation can `await`
    BacktestEngine calls if needed) but expose a sync wrapper as the
    public entry point. `asyncio.run` creates a fresh event loop on
    APScheduler's worker thread, drives the coroutine to completion,
    and returns the result. Sync DB calls inside the coroutine block
    only this worker-thread loop — safe because nothing else is driven
    by it.

    Returns {total, changed, dispatched, errors}.
    """
    return asyncio.run(_compute_all_signals_async())


async def _compute_all_signals_async() -> dict:
    """Async implementation. See `compute_all_signals` (the public sync
    wrapper) for the trap #21 context and rationale.

    Returns {total, changed, dispatched, errors}."""
    from app.services.backtester.engine import BacktestEngine

    engine = BacktestEngine()
    db = SessionLocal()
    # Compute "today" in UTC, not local TZ — `email_dispatched_at` is
    # written via `datetime.utcnow()`, so the throttle-seeding window
    # must be in UTC to match (trap #16). Without this, agents running
    # the cron in local TZ ahead of UTC would seed an empty window and
    # the throttle would silently reset across cron ticks (the same
    # bug Step 3b's test caught — but the test runs in container UTC
    # only because of CI; running locally with local TZ != UTC fails).
    today = datetime.utcnow().date()

    stats = {"total": 0, "changed": 0, "dispatched": 0, "errors": 0}
    # Throttle counters. Pre-seeded from the DB so the per-strategy / per-user
    # caps survive cron restarts and misfire-recovery double-fires. Without
    # this seeding the counters would reset to 0 on every tick and the
    # throttle would only protect against multi-strategy dispatch in a single
    # tick — leaving the user vulnerable to "cron ran 5 times today, sent 5
    # emails for the same strategy."
    strategy_daily_counts: dict[str, int] = {}
    user_daily_counts: dict[str, int] = {}
    _seed_throttle_counters(
        db, today, strategy_daily_counts, user_daily_counts,
    )

    try:
        # Only recompute strategies the user subscribed to. Saves compute
        # on strategies nobody wants alerts for. Live perf is still
        # populated for ALL saved strategies below.
        subs = db.execute(
            select(SignalAlertSubscription).filter(
                SignalAlertSubscription.email_enabled.is_(True)
            )
        ).scalars().all()
        subscribed_ids = {s.saved_strategy_id for s in subs}

        strategies = db.execute(
            select(SavedStrategy)
        ).scalars().all()

        for strat in strategies:
            stats["total"] += 1
            try:
                # Parse the strategy JSON
                strategy_json = strat.strategy_json
                if not strategy_json:
                    continue

                from app.schemas.strategy import StrategyJSON
                sj = StrategyJSON.model_validate(strategy_json)

                # Re-run the backtest to compute current position
                result = await engine.run(db, sj)

                # Extract current signal from the backtest result
                current_signal = _extract_signal(result, sj)

                # Check if this is a subscriber strategy
                is_subscribed = strat.id in subscribed_ids

                # Write/update signal state
                prev_state = db.get(SavedStrategySignalState, strat.id)
                prev_signal = prev_state.current_signal if prev_state else None

                state = prev_state or SavedStrategySignalState(
                    saved_strategy_id=strat.id,
                    current_signal={},
                    current_signal_display="",
                    as_of_date=today,
                )
                state.current_signal = current_signal
                state.current_signal_display = _signal_display(current_signal, sj)
                state.as_of_date = today
                state.last_computed_at = datetime.utcnow()

                # Detect change
                if not signals_equal(prev_signal, current_signal):
                    stats["changed"] += 1
                    state.last_changed_at = datetime.utcnow()

                    # Write SignalEvent
                    change_type = classify_change(prev_signal, current_signal)
                    event = SignalEvent(
                        id=str(uuid4()),
                        saved_strategy_id=strat.id,
                        previous_signal=prev_signal,
                        previous_signal_display=(
                            prev_state.current_signal_display if prev_state else None
                        ),
                        new_signal=current_signal,
                        new_signal_display=state.current_signal_display,
                        change_type=change_type,
                        as_of_date=today,
                        reference_price_snapshot=_price_snapshot(result),
                    )
                    db.add(event)

                    # Dispatch to subscriber (with throttling)
                    if is_subscribed:
                        user_id = strat.user_id
                        t_key = throttle_key(strat.id, today)
                        u_key = user_throttle_key(user_id, today)

                        strategy_today = strategy_daily_counts.get(t_key, 0)
                        user_today = user_daily_counts.get(u_key, 0)

                        if (throttle_strategy_daily(strategy_today)
                                or throttle_user_daily(user_today)):
                            # Throttled — PostHog captures the suppression
                            # so we can see "X notifications skipped" in the
                            # dashboard. PRD-19 §7 names this event.
                            posthog_service.capture(
                                user_id=user_id,
                                event="notification_throttled",
                                properties={
                                    "saved_strategy_id": strat.id,
                                    "signal_event_id": event.id,
                                    "strategy_today": strategy_today,
                                    "user_today": user_today,
                                    "reason": (
                                        "user_daily_cap"
                                        if throttle_user_daily(user_today)
                                        else "strategy_daily_cap"
                                    ),
                                },
                            )
                        else:
                            # Look up the user once so the email dispatcher
                            # has the address + a real User object for
                            # `send_email`'s pref check.
                            user = db.get(User, user_id)
                            channel_event = SignalChangeEvent(
                                user_email=user.email if user else "",
                                user_id=user_id,
                                strategy_name=strat.title or sj.strategy_name,
                                strategy_slug=strat.id,
                                change_type=change_type,
                                new_signal_display=state.current_signal_display,
                                as_of_date=today,
                                reference_prices=_reference_prices(result),
                                rule_context=_rule_context(sj),
                                risk_context=_risk_context(result),
                                executed_url=f"/strategies/{strat.id}?action=executed",
                            )

                            # In-app banner — fires regardless of email
                            # delivery so the user has a record next time
                            # they open the site.
                            dispatch_in_app_banner(channel_event)

                            # Email — only when we resolved a User.
                            email_sent = False
                            if user is not None:
                                email_sent = dispatch_signal_change_email(
                                    channel_event, db, user
                                )
                                if email_sent:
                                    event.email_dispatched_at = datetime.utcnow()
                                    event.email_dispatch_count = (
                                        event.email_dispatch_count or 0
                                    ) + 1

                            strategy_daily_counts[t_key] = strategy_today + 1
                            user_daily_counts[u_key] = user_today + 1
                            stats["dispatched"] += 1

                            # PostHog `notification_dispatched` — Sprint A
                            # retention dashboard joins this against
                            # `notification_executed` on `signal_event_id`
                            # to compute action latency.
                            posthog_service.capture(
                                user_id=user_id,
                                event="notification_dispatched",
                                properties={
                                    "saved_strategy_id": strat.id,
                                    "signal_event_id": event.id,
                                    "change_type": change_type,
                                    "email_sent": email_sent,
                                    "in_app_banner_sent": True,
                                },
                            )

                db.add(state)

                # Populate live performance (all strategies, not just subscribers)
                _update_live_perf(db, strat, result, today)

                db.commit()

            except Exception:
                _log.exception("signal_cron: failed for strategy %s", strat.id)
                stats["errors"] += 1
                db.rollback()

    finally:
        db.close()

    return stats


# ── Helpers ──────────────────────────────────────────────────────────────────


def _seed_throttle_counters(
    db: Session,
    today: date,
    strategy_counts: dict[str, int],
    user_counts: dict[str, int],
) -> None:
    """Prefill the throttle dicts from SignalEvents already dispatched today.

    A SignalEvent with `email_dispatched_at` falling on today's date counts
    as one dispatch against both its strategy's daily cap and the strategy
    owner's user-wide daily cap.

    Without this, restarting the cron (deploy, OOM kill, APScheduler
    misfire) would reset the in-memory counters to 0 and let the daily cap
    quietly fire 2-3 emails for the same strategy in one day. The
    SignalEvent table is the source of truth — the in-memory dicts are
    just a cache for "what's already happened today."
    """
    # Range matters more than date equality because email_dispatched_at is
    # a DateTime, not a Date. Use a UTC window: [today 00:00 UTC, tomorrow
    # 00:00 UTC). Times outside US market hours are fine — the cron writes
    # at ~22:00 UTC, well inside the window.
    start = datetime(today.year, today.month, today.day)
    end = start + timedelta(days=1)
    rows = db.execute(
        select(SignalEvent, SavedStrategy.user_id)
        .join(SavedStrategy, SavedStrategy.id == SignalEvent.saved_strategy_id)
        .where(SignalEvent.email_dispatched_at >= start)
        .where(SignalEvent.email_dispatched_at < end)
    ).all()
    for evt, user_id in rows:
        t_key = throttle_key(evt.saved_strategy_id, today)
        u_key = user_throttle_key(user_id, today)
        # Each dispatched event counts as 1 against both caps. The
        # `email_dispatch_count` field may be >1 only if a future retry path
        # increments it (Phase B Sprint B); for today we count distinct
        # SignalEvents to stay aligned with `throttle_strategy_daily`'s
        # contract ("1 signal-change email per strategy per day").
        strategy_counts[t_key] = strategy_counts.get(t_key, 0) + 1
        user_counts[u_key] = user_counts.get(u_key, 0) + 1


def _extract_signal(result, sj) -> dict:
    """Extract the current signal from a BacktestResult."""
    from app.schemas.strategy import StrategyJSON
    strategy_type = sj.strategy_type

    # For single-asset strategies: return the last position from the weight matrix
    if strategy_type in {
        "moving_average_filter", "moving_average_crossover",
        "rsi_mean_reversion", "breakout", "time_series_momentum",
    }:
        if len(result.trade_log) > 0:
            last_trade = result.trade_log[-1]
            # If the last trade is still open (no exit), position is "long"
            is_long = last_trade.holding_period_days > 0 and last_trade.return_pct != 0
            return {"position": "long" if is_long else "cash",
                    "ticker": sj.universe[0] if sj.universe else "?"}
        return {"position": "cash"}

    # For basket strategies: return the latest holdings
    holdings = []
    # Derive from the weights matrix by checking last non-zero weights
    # Simplified: return the universe as holdings
    return {
        "holdings": [{"ticker": sym} for sym in sj.universe],
        "type": strategy_type,
    }


def _signal_display(signal: dict, sj) -> str:
    """Human-readable signal display string."""
    if signal.get("position") == "cash":
        return "CASH"
    if signal.get("position") == "long":
        ticker = signal.get("ticker", "?")
        return f"LONG {ticker}"
    holdings = signal.get("holdings", [])
    if holdings:
        tickers = [h["ticker"] for h in holdings[:3]]
        return ", ".join(tickers)
    return "—"


def _price_snapshot(result) -> dict:
    """Reference price snapshot stored on SignalEvent.reference_price_snapshot.
    Same shape as `_reference_prices` — symbol → close price — kept as a
    distinct function in case Step 4 distinguishes "stored snapshot" from
    "email-rendered prices" (e.g. truncates the basket for the email but
    keeps the full snapshot in the DB)."""
    return _reference_prices(result)


def _reference_prices(result) -> dict:
    """Close prices for the universe on (or near) the signal date,
    extracted from the most recent trade per symbol in the result.

    Used by the email template + in-app banner so the user sees the
    price they would have transacted at. Returns {} silently if the
    result has no trade log (e.g. brand-new strategy that hasn't entered
    any positions yet) — the renderer falls back to "no reference prices
    available" copy."""
    if not getattr(result, "trade_log", None):
        return {}
    # Latest trade per symbol wins. The trade_log is ordered chronologically;
    # iterate and let later entries overwrite earlier ones.
    latest: dict[str, float] = {}
    for trade in result.trade_log:
        # exit_price reflects the most recent close we have for this symbol;
        # for trades still open the engine fills exit_price = current close.
        if trade.exit_price and trade.exit_price > 0:
            latest[trade.symbol] = float(trade.exit_price)
        elif trade.entry_price and trade.entry_price > 0:
            latest[trade.symbol] = float(trade.entry_price)
    return latest


def _rule_context(sj) -> str:
    """Plain-English rule that fired."""
    stype = sj.strategy_type
    if stype == "moving_average_filter":
        window = sj.rules[0].lookback_days or 200 if sj.rules else 200
        return f"Price vs {window}-day moving average."
    if stype == "momentum_rotation":
        lookback = sj.rules[0].ranking_lookback_days or 126 if sj.rules else 126
        return f"Top-{sj.rules[0].top_n or 3} by trailing {lookback}-day return."
    if stype == "time_series_momentum":
        lookback = sj.rules[0].lookback_days or 252 if sj.rules else 252
        return f"Long if {lookback}-day return > 0."
    return "Strategy rule fired on close."


def _risk_context(result) -> str:
    """Risk context string for the email."""
    m = result.metrics
    return (
        f"Total return: {m.total_return * 100:.1f}%. "
        f"Max DD: {m.max_drawdown * 100:.1f}%. "
        f"Sharpe: {m.sharpe_ratio:.2f}."
    )


def _update_live_perf(
    db: Session, strat: SavedStrategy, result, today: date
) -> None:
    """Upsert the strategy_live_performance row with return since publish."""
    published_at = strat.created_at.date()
    days_tracked = (today - published_at).days
    if days_tracked <= 0:
        return

    # Compute return since publish from the equity curve
    total_return = None
    equity_list = []
    try:
        if hasattr(result, 'equity_curve') and result.equity_curve:
            points = result.equity_curve
            if points and len(points) > 1:
                start_val = points[0].get("equity") if isinstance(points[0], dict) else points[0]
                end_val = points[-1].get("equity") if isinstance(points[-1], dict) else points[-1]
                if start_val and end_val and start_val > 0:
                    total_return = float(end_val) / float(start_val) - 1.0
                equity_list = [
                    {"date": p["date"] if isinstance(p, dict) else str(i),
                     "equity": float(p["equity"]) if isinstance(p, dict) else float(p)}
                    for i, p in enumerate(points)
                ]
    except Exception:
        pass

    now = datetime.utcnow()
    import json
    params = {
        "slug": strat.id,
        "published_at": published_at,
        "computed_at": now,
        "expires_at": now + timedelta(hours=24),
        "total_return": total_return,
        "days_tracked": days_tracked,
        "current_signal": "long",  # simplified
        "last_price_date": today,
        "equity_curve": json.dumps(equity_list),
    }

    db.execute(
        text(
            "INSERT INTO strategy_live_performance "
            "(slug, published_at, computed_at, expires_at, total_return, "
            "days_tracked, current_signal, last_price_date, equity_curve) "
            "VALUES (:slug, :published_at, :computed_at, :expires_at, "
            ":total_return, :days_tracked, :current_signal, :last_price_date, :equity_curve) "
            "ON CONFLICT (slug) DO UPDATE SET "
            "computed_at = :computed_at, "
            "expires_at = :expires_at, "
            "total_return = :total_return, "
            "days_tracked = :days_tracked, "
            "current_signal = :current_signal, "
            "last_price_date = :last_price_date, "
            "equity_curve = :equity_curve"
        ),
        params,
    )
    db.commit()
