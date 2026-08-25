"""Daily exit monitoring for tracked positions.

One run per session, after the close. For each open position on a
`bar_resolution == 'daily'` strategy, evaluate the strategy's exit ladder
against that session's completed bar; record a pending event and notify.
Livermore never sells — the user acts in their own brokerage the next
morning and confirms.

WHY DAILY IS THE PRIMARY PATH, NOT A LESSER ONE. Everything else in the
product is daily: entry signals come from the daily snapshot, and the
backtester has always run on daily bars (it soft-degrades any intraday
choice, see `engine.run`). The intraday monitor was therefore the ONLY
component measuring something the backtest never measured. On daily bars
the two agree by construction, and most of the intraday path's problems
simply do not exist here:

  - the bar is final, not a ~15-minute-delayed sample of a forming one
  - it carries a real high and low, so a stop can test the session's
    actual extreme rather than a close that may have recovered
  - one run means there are no ticks to miss and no DST-shifted window
  - the user gets the evening to act rather than twenty minutes

This job is deliberately SEPARATE from `intraday_jobs` rather than a
generalisation of it. That module keys its fire-once guard on legacy
`trigger_type` strings already written into live positions' trade logs;
rewriting them mid-flight would make fired tiers look unfired and
re-notify people about exits that already happened. Daily positions are
new, so this path starts clean on the shared evaluator's per-tier
identity (`tier{index}_hit`) and cannot suffer the bug where a second
negative tier disarms the hard stop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy
from app.models.user import User
from app.schemas.strategy import StrategyJSON
from app.services.exit_ladder import (
    Bar,
    TierFire,
    evaluate_bar,
    shares_for,
)

_log = logging.getLogger("livermore.jobs.daily_positions")

# How far back to ask for bars. We only need the newest completed session,
# but a market holiday or a thinly-traded symbol can leave the last few
# calendar days empty, so ask for a fortnight and take the last row.
_LOOKBACK_DAYS = 14


def monitor_daily_positions() -> Dict[str, Any]:
    """Sync wrapper for APScheduler. See `_monitor_daily_positions_async`."""
    return asyncio.run(_monitor_daily_positions_async())


async def _monitor_daily_positions_async(
    *,
    db: Optional[Session] = None,
    market_data: Optional[Any] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Walk open positions on daily strategies; fire and notify.

    `db`, `market_data` and `today` are DI seams for testing; production
    callers leave them None.
    """
    owned_db = False
    if db is None:
        db = SessionLocal()
        owned_db = True
    if market_data is None:
        from app.services.market_data import MarketDataService

        market_data = MarketDataService()

    stats = {
        "strategies_checked": 0,
        "positions_monitored": 0,
        "events_fired": 0,
        "notifications_sent": 0,
        "skipped_no_bar": 0,
        "skipped_corporate_action": 0,
        "errors": 0,
    }

    try:
        # Drive the scan off OPEN POSITIONS, not the SavedStrategy table: a
        # strategy is only work when something is actually held, so the cost
        # tracks monitored positions rather than total saved strategies.
        strat_ids = db.execute(
            select(PositionState.saved_strategy_id)
            .where(PositionState.is_open == True)  # noqa: E712
            .distinct()
        ).scalars().all()
        if not strat_ids:
            return stats

        strategies = db.execute(
            select(SavedStrategy).where(SavedStrategy.id.in_(strat_ids))
        ).scalars().all()

        for strat in strategies:
            try:
                sj_dict = strat.strategy_json or {}
                if sj_dict.get("bar_resolution", "daily") != "daily":
                    continue  # the intraday monitor owns those
                ladder = StrategyJSON.model_validate(
                    sj_dict
                ).risk_management.exit_ladder
                if not ladder:
                    continue
                stats["strategies_checked"] += 1

                owner = db.execute(
                    select(User).where(User.id == strat.user_id)
                ).scalar_one_or_none()

                positions = db.execute(
                    select(PositionState)
                    .where(PositionState.saved_strategy_id == strat.id)
                    .where(PositionState.is_open == True)  # noqa: E712
                ).scalars().all()

                for pos in positions:
                    # Per-POSITION error isolation. The intraday job wraps
                    # only the strategy loop, so one bad symbol kills every
                    # remaining position on that strategy for the run.
                    try:
                        stats["positions_monitored"] += 1
                        fires = await _evaluate_position(
                            db, market_data, pos, ladder, stats, today=today,
                        )
                        for fire in fires:
                            stats["events_fired"] += 1
                            if owner is not None and _dispatch(
                                db, owner, strat, pos, fire
                            ):
                                stats["notifications_sent"] += 1
                    except Exception:  # noqa: BLE001
                        stats["errors"] += 1
                        _log.exception(
                            "daily monitor: position %s (%s) errored",
                            pos.id, pos.symbol,
                        )
            except Exception:  # noqa: BLE001
                stats["errors"] += 1
                _log.exception("daily monitor: strategy %s errored", strat.id)
    finally:
        if owned_db:
            db.close()
    return stats


async def _evaluate_position(
    db: Session,
    market_data: Any,
    pos: PositionState,
    ladder: List[Any],
    stats: Dict[str, Any],
    *,
    today: Optional[date] = None,
) -> List[TierFire]:
    """Evaluate one position against the newest completed daily bar.

    Returns every tier that fired (a gap can clear more than one rung).
    Records a pending event per fire; never mutates shares or `is_open`.
    """
    end = today or date.today()
    frame = await market_data.get_price_frame(
        db, pos.symbol, end - timedelta(days=_LOOKBACK_DAYS), end,
    )
    if frame is None or frame.empty:
        stats["skipped_no_bar"] += 1
        _log.info("daily monitor: no bar for %s — skipping", pos.symbol)
        return []

    row = frame.iloc[-1]

    # CORPORATE ACTIONS. The position's entry_price is the user's real fill
    # in real dollars, and the bar's raw prices are too — so they compare
    # directly, EXCEPT across a split. A 2:1 split halves the raw price and
    # would read as a -50% move: a fabricated "sell everything" on a
    # position that did not move at all. Refuse to evaluate rather than
    # fire, and say so loudly; a missed day is recoverable, a false
    # liquidation instruction is not.
    split = float(row.get("split_coefficient", 1.0) or 1.0)
    if abs(split - 1.0) > 1e-9:
        stats["skipped_corporate_action"] += 1
        _log.warning(
            "daily monitor: %s has split_coefficient=%s on %s — not "
            "evaluating; entry_price needs re-basing before this position "
            "can be monitored again",
            pos.symbol, split, row.name,
        )
        return []

    close = float(row["close"])
    # High/low are real here — a daily bar is final. Passing them means the
    # evaluator tests the session's true extreme the moment TRIGGER_FIELD
    # flips to "extremes", with no change needed in this job.
    bar = Bar(
        high=float(row.get("high", close) or close),
        low=float(row.get("low", close) or close),
        close=close,
    )

    already = {
        e.get("event") for e in (pos.trade_log or []) if e.get("event")
    }
    fires = evaluate_bar(
        ladder=ladder,
        entry_price=pos.entry_price,
        bar=bar,
        already_fired=already,
    )
    if not fires:
        return []

    bar_date = getattr(row.name, "date", lambda: row.name)()
    for fire in fires:
        _record_pending(pos, fire, bar=bar, bar_date=bar_date)
    db.commit()
    return fires


def _record_pending(
    pos: PositionState,
    fire: TierFire,
    *,
    bar: Bar,
    bar_date: Any,
) -> None:
    """Append a `pending_confirmation` event. Does NOT touch
    shares_remaining / is_open / final_pnl — the user confirms the real
    sale, and until they do we have not observed one. Caller commits."""
    shares = shares_for(
        fire,
        shares_initial=pos.shares_initial,
        shares_remaining=pos.shares_remaining,
    )
    pct = (fire.observed_price - pos.entry_price) / pos.entry_price
    pos.trade_log = (pos.trade_log or []) + [{
        "event": fire.trigger_type,
        "status": "pending_confirmation",
        "timestamp": datetime.utcnow().isoformat(),
        "bar_date": str(bar_date),
        "price": fire.observed_price,
        "bar_close": bar.close,
        "pct_change": pct,
        "tier_index": fire.tier_index,
        "action": fire.action,
        "shares": shares,
    }]


def _dispatch(
    db: Session,
    user: User,
    strat: SavedStrategy,
    pos: PositionState,
    fire: TierFire,
) -> bool:
    """Email + in-app banner. Best-effort: a failed send must not lose the
    recorded event, which is the durable half."""
    from app.emails.position_event import (
        PositionEventPayload,
        render_position_event,
    )
    from app.services.email_service import send_email

    strategy_name = strat.title or "Your strategy"
    shares = shares_for(
        fire,
        shares_initial=pos.shares_initial,
        shares_remaining=pos.shares_remaining,
    )
    pct = (fire.observed_price - pos.entry_price) / pos.entry_price
    payload = PositionEventPayload(
        strategy_name=strategy_name,
        strategy_id=strat.id,
        symbol=pos.symbol,
        trigger_type=fire.trigger_type,
        tier_label=fire.tier_label or _tier_label(fire),
        entry_price=pos.entry_price,
        current_price=fire.observed_price,
        pct_change=pct,
        action_taken=(
            "sold_all" if fire.action == "sell_all" else "sold_fraction"
        ),
        shares_sold=shares,
        shares_remaining=pos.shares_remaining,
        fired_at=datetime.utcnow(),
        is_suggestion=True,
    )
    rendered = render_position_event(user, payload)

    # Banner first: it is a local DB write and very unlikely to fail, so the
    # user still has an in-app record even when mail is down.
    _write_banner(db, user.id, strat, pos, rendered["subject"])

    try:
        return send_email(
            db,
            user,
            template="position_event",
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            category="transactional",
        )
    except Exception:  # noqa: BLE001
        _log.exception(
            "daily position email failed user=%s strat=%s symbol=%s",
            user.id, strat.id, pos.symbol,
        )
        return False


def _tier_label(fire: TierFire) -> str:
    return "Stop" if fire.trigger_pct < 0 else "Target"


def _write_banner(
    db: Session,
    user_id: str,
    strat: SavedStrategy,
    pos: PositionState,
    subject: str,
) -> None:
    """In-app banner for the exit.

    Carries the real `strategy_slug`. The intraday job passes None, which
    renders a banner with nowhere to go — the user is told an exit fired
    and given no way to act on it. Fresh session so a banner failure cannot
    poison the monitor's transaction.
    """
    try:
        from app.models.notification_banner import NotificationBannerEntry

        with SessionLocal() as banner_db:
            banner_db.add(NotificationBannerEntry(
                user_id=user_id,
                title=subject,
                body=(
                    f"{pos.symbol} reached a level your strategy "
                    f"'{strat.title or 'Your strategy'}' defines as an exit. "
                    "Nothing has been sold — no order goes out unless you send it."
                ),
                strategy_slug=strat.id,
            ))
            banner_db.commit()
    except Exception:  # noqa: BLE001
        _log.exception(
            "daily position banner failed user=%s symbol=%s", user_id, pos.symbol
        )
