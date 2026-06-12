"""PRD-16c-3b + active-execution-v2 — Intraday position monitor cron.

Runs every 5 minutes during US market hours. For each OPEN PositionState
belonging to an active-execution strategy (`bar_resolution != 'daily'`
with an `exit_ladder`), fetches the latest intraday bar via
IntradayBarService, computes pct-change from the user's entry price, and
walks the strategy's exit_ladder.

**The cron DETECTS and NOTIFIES — it never mutates the position.**
(active-execution-v2 decision: Livermore tracks real user-held positions
and never simulates a sale.) When a tier triggers, the cron:

  1. Appends a `{status: "pending_confirmation"}` event to the
     PositionState's `trade_log` — recording that the tier fired + the
     SUGGESTED action, WITHOUT changing `shares_remaining`, `is_open`,
     `closed_at`, or `final_pnl`.
  2. Dispatches a notification (email via `render_position_event` +
     in-app `NotificationBannerEntry`) telling the user "your strategy
     says sell N of your M shares."
  3. The user executes in their own brokerage and confirms via the
     Mark-as-Executed flow (PR3), which is what actually decrements
     `shares_remaining` / closes the position.

A tier fires AT MOST ONCE per PositionState (per entry) — the permanent
`_tier_already_fired` guard reads the trade_log so a fired tier never
re-notifies, even across days / cron restarts. A fresh entry is a new
PositionState row with an empty trade_log, so its tiers re-arm.

Avoids `live_quote_service` deliberately (trap #22 — singleton holds
`asyncio.Lock` bound to the main loop; the cron runs on a worker-thread
loop). `IntradayBarService` holds no asyncio primitives, so it's safe.

Trap #21: the public entry point is the sync `monitor_active_positions`
wrapper; `asyncio.run` drives the async core on the worker thread.
Trap #20: caught errors use `_log.exception`, not `.warning`.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy
from app.models.user import User
from app.schemas.strategy import ExitTier, StrategyJSON
from app.services.intraday_bar_service import IntradayBarService


_log = logging.getLogger("livermore.intraday_jobs")


# ── Pending-fire payload (cron → dispatch) ──────────────────────────────────


@dataclass
class PendingFire:
    """A tier that triggered this tick. Carries everything the notifier
    + the trade_log event need. NO mutation has happened to the position
    when this is constructed — the cron only appends a pending event +
    notifies."""
    trigger_type: str          # 'stop_hit' | 'tp0_hit' | 'tp1_hit' | ...
    tier: ExitTier
    current_price: float
    pct_change: float
    suggested_action: str      # 'sell_all' | 'sell_fraction'
    suggested_shares: float


# ── Public entry point (APScheduler) ────────────────────────────────────────


def monitor_active_positions() -> dict:
    """Sync wrapper. See `_monitor_active_positions_async`. Returns stats."""
    return asyncio.run(_monitor_active_positions_async())


# ── Async core ──────────────────────────────────────────────────────────────


async def _monitor_active_positions_async(
    *,
    bar_service: Optional[IntradayBarService] = None,
    db: Optional[Session] = None,
) -> dict:
    """Walk every active-execution strategy's open positions, detect
    exit-ladder triggers, record pending events + dispatch notifications.

    `bar_service` and `db` are DI seams for testing — production callers
    leave them None and the function instantiates defaults.
    """
    owned_db = False
    if db is None:
        db = SessionLocal()
        owned_db = True
    bar_svc = bar_service or IntradayBarService()

    stats = {
        "strategies_checked": 0,
        "positions_monitored": 0,
        "events_fired": 0,      # tiers that triggered + got a pending event
        "notifications_sent": 0,
        "errors": 0,
    }

    try:
        # SCALE: a strategy only becomes "work" when it has an OPEN
        # position. Drive the scan off open positions, not the whole
        # SavedStrategy table — so the cron's cost scales with monitored
        # positions (small), NOT total saved strategies (potentially huge).
        # A user with 5,000 saved strategies but 3 open positions → we
        # touch 3 strategies, not 5,000.
        strat_ids = db.execute(
            select(PositionState.saved_strategy_id)
            .where(PositionState.is_open == True)  # noqa: E712
            .distinct()
        ).scalars().all()
        if not strat_ids:
            return stats  # nothing open — the common, near-free case

        strategies = db.execute(
            select(SavedStrategy).where(SavedStrategy.id.in_(strat_ids))
        ).scalars().all()
        for strat in strategies:
            try:
                sj_dict = strat.strategy_json or {}
                # bar_resolution may be a top-level key on the stored JSON
                # OR (post active-exec plumbing) a real StrategyJSON field.
                bar_resolution = sj_dict.get("bar_resolution", "daily")
                if bar_resolution == "daily":
                    continue

                sj = StrategyJSON.model_validate(sj_dict)
                ladder = sj.risk_management.exit_ladder
                if not ladder:
                    continue
                stats["strategies_checked"] += 1

                # Resolve the strategy owner once (for notification
                # dispatch). Missing user → still record pending events,
                # just skip the email/banner.
                owner = db.execute(
                    select(User).where(User.id == strat.user_id)
                ).scalar_one_or_none()

                positions = db.execute(
                    select(PositionState)
                    .where(PositionState.saved_strategy_id == strat.id)
                    .where(PositionState.is_open == True)  # noqa: E712
                ).scalars().all()

                for pos in positions:
                    stats["positions_monitored"] += 1
                    fire = await _evaluate_position(
                        db, bar_svc, pos, ladder, bar_resolution,
                    )
                    if fire is None:
                        continue
                    stats["events_fired"] += 1
                    if owner is not None:
                        sent = _dispatch_position_event(
                            db, owner, strat, pos, fire,
                        )
                        if sent:
                            stats["notifications_sent"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["errors"] += 1
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
    pos: PositionState,
    ladder: list[ExitTier],
    bar_resolution: str,
) -> Optional[PendingFire]:
    """Evaluate one open position against its exit_ladder. If a tier
    triggers (and hasn't already fired for this position), append a
    `pending_confirmation` event to the trade_log and return a
    `PendingFire`. Otherwise return None.

    The position's shares / is_open / final_pnl are NOT modified — only
    `trade_log` gets the pending event. The user confirms the actual
    sale via Mark-as-Executed (PR3)."""
    # ALWAYS pull the freshest intraday bars each tick (FMP, ~15-min delayed
    # during market hours) so exit-tier checks AND the dashboard/chart see
    # live prices — not a cache that only refreshes when >2× resolution
    # stale. `ensure_recent_bars` fetches unconditionally + writes the cache,
    # windowing in ET (see et_now_naive).
    frame = await bar_svc.ensure_recent_bars(
        db, pos.symbol, bar_resolution, lookback_minutes=360,
    )
    if frame.empty:
        _log.info(
            "intraday monitor: no bars for %s @ %s — skipping",
            pos.symbol, bar_resolution,
        )
        return None

    current_price = float(frame["close"].iloc[-1])
    if not pos.entry_price:
        return None
    pct_change = (current_price - pos.entry_price) / pos.entry_price

    for j, tier in enumerate(ladder):
        triggered = (
            (tier.trigger_pct < 0 and pct_change <= tier.trigger_pct)
            or (tier.trigger_pct > 0 and pct_change >= tier.trigger_pct)
        )
        if not triggered:
            continue
        trigger_type = _tier_trigger_type(tier, j)
        # Permanent per-entry guard: a tier that already fired (pending
        # OR executed) for THIS position never re-notifies — not just
        # same-day. Reading the trade_log makes this survive cron
        # restarts without a separate throttle table.
        if _tier_already_fired(pos, trigger_type):
            continue

        suggested_action = tier.action
        if tier.action == "sell_all":
            suggested_shares = pos.shares_remaining
        else:
            fraction = tier.fraction or 0.0
            # Suggest selling `fraction × shares_initial` (the SpaceX
            # "+15% sell 1/3 of original" wording), capped at what's left.
            suggested_shares = min(
                pos.shares_initial * fraction, pos.shares_remaining
            )

        _record_pending_tier(
            pos, trigger_type, tier, current_price, pct_change,
            suggested_action, suggested_shares,
        )
        db.commit()
        return PendingFire(
            trigger_type=trigger_type,
            tier=tier,
            current_price=current_price,
            pct_change=pct_change,
            suggested_action=suggested_action,
            suggested_shares=suggested_shares,
        )

    return None


def _record_pending_tier(
    pos: PositionState,
    trigger_type: str,
    tier: ExitTier,
    current_price: float,
    pct_change: float,
    suggested_action: str,
    suggested_shares: float,
) -> None:
    """Append a `pending_confirmation` event to the position's trade_log.
    Does NOT mutate shares_remaining / is_open / final_pnl — the user
    confirms the actual sale via Mark-as-Executed (PR3), which is what
    decrements shares. Caller commits."""
    pos.trade_log = (pos.trade_log or []) + [{
        "event": trigger_type,
        "status": "pending_confirmation",
        "timestamp": datetime.utcnow().isoformat(),
        "price": current_price,
        "pct_change": pct_change,
        "tier_label": tier.label,
        "suggested_action": suggested_action,
        "suggested_shares": suggested_shares,
    }]


def _tier_already_fired(pos: PositionState, trigger_type: str) -> bool:
    """True if this trigger_type already has an event (pending or
    executed) in the position's trade_log. The permanent per-entry
    guard against re-notification."""
    for event in (pos.trade_log or []):
        if event.get("event") == trigger_type:
            return True
    return False


def _dispatch_position_event(
    db: Session,
    user: User,
    strat: SavedStrategy,
    pos: PositionState,
    fire: PendingFire,
) -> bool:
    """Render + send the position-event email and write an in-app banner.
    Best-effort: a failed email doesn't lose the signal (it's in the
    trade_log + dashboard). Returns True if the email dispatch was
    attempted."""
    from app.emails.position_event import (
        PositionEventPayload,
        render_position_event,
    )
    from app.services.email_service import send_email

    strategy_name = strat.title or "Your strategy"
    payload = PositionEventPayload(
        strategy_name=strategy_name,
        strategy_id=strat.id,
        symbol=pos.symbol,
        trigger_type=fire.trigger_type,
        tier_label=fire.tier.label,
        entry_price=pos.entry_price,
        current_price=fire.current_price,
        pct_change=fire.pct_change,
        action_taken=(
            "sold_all" if fire.suggested_action == "sell_all"
            else "sold_fraction"
        ),
        shares_sold=fire.suggested_shares,
        shares_remaining=pos.shares_remaining,
        fired_at=datetime.utcnow(),
        is_suggestion=True,   # notify-and-confirm model — this is advice
    )
    rendered = render_position_event(user, payload)

    # In-app banner first (DB write, very unlikely to fail) so the user
    # gets the in-app notification even if email is down.
    _write_position_banner(db, user.id, strategy_name, pos.symbol, rendered["subject"])

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
    except Exception:
        _log.exception(
            "position-event email failed user=%s strat=%s symbol=%s",
            user.id, strat.id, pos.symbol,
        )
        return False


def _write_position_banner(
    db: Session, user_id: str, strategy_name: str, symbol: str, subject: str,
) -> None:
    """Write a NotificationBannerEntry for the in-app surface. Reuses a
    fresh SessionLocal so a banner-write failure can't poison the cron's
    main transaction. Best-effort."""
    try:
        from app.models.notification_banner import NotificationBannerEntry
        with SessionLocal() as banner_db:
            banner_db.add(NotificationBannerEntry(
                user_id=user_id,
                title=subject,
                body=(
                    f"Your strategy '{strategy_name}' signalled an exit on "
                    f"{symbol}. Review the suggested action and mark it "
                    "executed once you've acted."
                ),
                strategy_slug=None,
            ))
            banner_db.commit()
    except Exception:
        _log.exception(
            "position-event banner write failed user=%s symbol=%s",
            user_id, symbol,
        )


def _tier_trigger_type(tier: ExitTier, ladder_index: int) -> str:
    """Map a tier to a stable trigger_type string. Stops use the constant
    'stop_hit' (once stopped, stopped); take-profit tiers are indexed
    ('tp1_hit', 'tp2_hit', ...) so each rung is distinct."""
    if tier.trigger_pct < 0:
        return "stop_hit"
    return f"tp{ladder_index}_hit"
