"""PRD-16c-3b — Intraday position monitor cron.

Runs every 5 minutes during US market hours. For each open PositionState
belonging to an active-execution strategy (one with `bar_resolution !=
'daily'`), fetches the latest intraday bar via IntradayBarService,
computes pct-change from entry, and walks the strategy's exit_ladder.
The first triggered tier:

  1. Mutates the PositionState (sell_all → close; sell_fraction → reduce
     shares_remaining); appends an event dict to `trade_log`.
  2. Records into the per-position daily throttle so subsequent cron
     ticks don't re-fire the same tier on the same symbol on the same day.
  3. (Future PRD-16c-4) — dispatches the position email + in-app banner.
     For 16c-3b the trade_log update is the source of truth; dispatcher
     wiring follows in 16c-4 alongside the templates.

Avoids `live_quote_service` deliberately — that singleton holds
`asyncio.Lock` instances bound to the main event loop (trap #22). The
cron runs on APScheduler's worker thread (its own loop), so the safe
read path is IntradayBarService.get_bars (pure SQLAlchemy + httpx, no
asyncio primitives).

Trap #21: the public entry point is the sync `monitor_active_positions`
wrapper; `asyncio.run` drives the async core on the worker thread.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy
from app.schemas.strategy import ExitTier, StrategyJSON
from app.services.intraday_bar_service import IntradayBarService
from app.services.notification_throttle import (
    position_throttle_key,
    throttle_position_daily,
)


_log = logging.getLogger("livermore.intraday_jobs")


# ── Public entry point (APScheduler) ────────────────────────────────────────


def monitor_active_positions() -> dict:
    """Sync wrapper. See `_monitor_active_positions_async` for the
    implementation. Returns stats dict."""
    return asyncio.run(_monitor_active_positions_async())


# ── Async core ──────────────────────────────────────────────────────────────


async def _monitor_active_positions_async(
    *,
    bar_service: Optional[IntradayBarService] = None,
    db: Optional[Session] = None,
) -> dict:
    """Walk every active-execution strategy's open positions, evaluate
    each one against its exit_ladder, and mutate PositionState + log
    events when tiers fire.

    `bar_service` and `db` are dependency-injection seams for testing —
    production callers leave them None and the function instantiates
    defaults.
    """
    owned_db = False
    if db is None:
        db = SessionLocal()
        owned_db = True
    bar_svc = bar_service or IntradayBarService()

    today = datetime.utcnow().date()
    stats = {
        "strategies_checked": 0,
        "positions_monitored": 0,
        "events_fired": 0,
        "errors": 0,
    }
    # Pre-seed per-position daily throttle counts from trade_log entries
    # that fired earlier today. Without this, a cron restart between
    # the morning fire and the afternoon would re-fire the same tier.
    position_counts: dict[str, int] = {}
    _seed_position_throttle(db, today, position_counts)

    try:
        strategies = db.execute(select(SavedStrategy)).scalars().all()
        for strat in strategies:
            try:
                sj_dict = strat.strategy_json or {}
                # bar_resolution is persisted as a top-level key on the
                # stored JSON (not part of StrategyJSON itself — the
                # composer writes it next to it). Daily strategies skip.
                bar_resolution = sj_dict.get("bar_resolution", "daily")
                if bar_resolution == "daily":
                    continue

                sj = StrategyJSON.model_validate(sj_dict)
                ladder = sj.risk_management.exit_ladder
                if not ladder:
                    continue
                stats["strategies_checked"] += 1

                positions = db.execute(
                    select(PositionState)
                    .where(PositionState.saved_strategy_id == strat.id)
                    .where(PositionState.is_open == True)  # noqa: E712
                ).scalars().all()

                for pos in positions:
                    fired = await _evaluate_position(
                        db, bar_svc, strat.id, pos, ladder,
                        bar_resolution, today, position_counts,
                    )
                    stats["positions_monitored"] += 1
                    stats["events_fired"] += fired
            except Exception as exc:  # noqa: BLE001
                stats["errors"] += 1
                # logger.exception (not .warning) per trap #20 — include
                # the full traceback so silent failures surface in logs.
                _log.exception(
                    "intraday monitor: strategy %s errored: %s", strat.id, exc
                )
    finally:
        if owned_db:
            db.close()
    return stats


async def _evaluate_position(
    db: Session,
    bar_svc: IntradayBarService,
    strategy_id: str,
    pos: PositionState,
    ladder: list[ExitTier],
    bar_resolution: str,
    today: date,
    position_counts: dict[str, int],
) -> int:
    """Evaluate one position against its exit_ladder. Returns the count
    of tiers that fired this tick (0 or 1 — a single tick fires at most
    one tier per position so subsequent tiers wait for the next tick)."""
    # Recent bar window: trailing 4 hours is enough headroom for any
    # supported resolution to have at least one bar.
    end = datetime.utcnow()
    start = end - timedelta(hours=4)
    frame = await bar_svc.get_bars(db, pos.symbol, bar_resolution, start, end)
    if frame.empty:
        _log.info(
            "intraday monitor: no bars for %s @ %s — skipping",
            pos.symbol, bar_resolution,
        )
        return 0

    current_price = float(frame["close"].iloc[-1])
    pct_change = (current_price - pos.entry_price) / pos.entry_price

    for j, tier in enumerate(ladder):
        triggered = (
            (tier.trigger_pct < 0 and pct_change <= tier.trigger_pct)
            or (tier.trigger_pct > 0 and pct_change >= tier.trigger_pct)
        )
        if not triggered:
            continue
        trigger_type = _tier_trigger_type(tier, j)
        key = position_throttle_key(strategy_id, pos.symbol, trigger_type, today)
        if throttle_position_daily(position_counts.get(key, 0)):
            # Already fired today; skip the rest of the ladder so we
            # don't accidentally fire a higher tier that was also
            # throttled on a prior tick.
            return 0

        _apply_tier(pos, tier, current_price, trigger_type)
        db.commit()
        position_counts[key] = position_counts.get(key, 0) + 1
        return 1

    return 0


def _apply_tier(
    pos: PositionState,
    tier: ExitTier,
    current_price: float,
    trigger_type: str,
) -> None:
    """Mutate the PositionState row in-place to reflect the tier firing.
    Caller commits."""
    now = datetime.utcnow()
    if tier.action == "sell_all":
        shares_sold = pos.shares_remaining
        pos.shares_remaining = 0.0
        pos.is_open = False
        pos.closed_at = now
        pos.final_pnl = (current_price - pos.entry_price) * pos.shares_initial
    else:
        # sell_fraction: shares_sold is `fraction × shares_initial` (the
        # PRD spec — out of the original shares, not the current
        # remaining; matches the SpaceX "+15% sell 1/3" wording).
        fraction = tier.fraction or 0.0
        shares_sold = pos.shares_initial * fraction
        pos.shares_remaining = max(0.0, pos.shares_remaining - shares_sold)

    pos.trade_log = (pos.trade_log or []) + [{
        "event": trigger_type,
        "timestamp": now.isoformat(),
        "price": current_price,
        "shares_sold": shares_sold,
        "tier_label": tier.label,
    }]


def _tier_trigger_type(tier: ExitTier, ladder_index: int) -> str:
    """Map a tier to a stable trigger_type string used by the throttle
    + email/banner dispatch. Stops use the constant 'stop_hit' so a
    single throttle entry covers all stop tiers on the same position;
    take-profit tiers are indexed (`tp0_hit`, `tp1_hit`, ...) so each
    rung has its own daily cap."""
    if tier.trigger_pct < 0:
        return "stop_hit"
    # Count this tier's position among take-profit tiers — but for now
    # use the ladder index directly. Multiple stops would collide on
    # 'stop_hit' (intentional — once stopped, stopped); multiple TPs
    # get unique names ('tp1_hit', 'tp2_hit', ...).
    return f"tp{ladder_index}_hit"


def _seed_position_throttle(
    db: Session,
    today: date,
    counts: dict[str, int],
) -> None:
    """Pre-fill the per-position throttle counter from PositionState
    rows that already have a `trade_log` event for today. Without this,
    a cron restart mid-day would re-fire the same tier on the same
    symbol — the same hazard `_seed_throttle_counters` guards against
    for signal_change.

    Idiom: iterate every position (open or closed). For each
    `trade_log` event that happened today, increment its key. Bound by
    practical position count — even with 10 active strategies × 50
    symbols each, this is ≤500 rows, all in one query.
    """
    start = datetime(today.year, today.month, today.day)
    rows = db.execute(select(PositionState)).scalars().all()
    for pos in rows:
        for event in (pos.trade_log or []):
            ts_raw = event.get("timestamp")
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw)
            except (TypeError, ValueError):
                continue
            if ts < start:
                continue
            trigger = event.get("event")
            if not trigger or trigger == "entry":
                continue
            key = position_throttle_key(
                pos.saved_strategy_id, pos.symbol, trigger, today,
            )
            counts[key] = counts.get(key, 0) + 1
