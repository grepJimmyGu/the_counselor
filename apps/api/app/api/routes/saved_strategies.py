"""Saved strategies CRUD (Stage 1a).

POST   /api/strategies          — create (Scout cap + auto-public enforced)
GET    /api/strategies          — list current user's saves
GET    /api/strategies/{id}     — read (owner or public)
DELETE /api/strategies/{id}     — delete (owner only)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest
from app.services.screener.saved_screen_service import is_screen

# NOTE: mounted at /api/saved-strategies (not /api/strategies) to avoid colliding
# with the legacy PRD-02 strategy_storage.py routes which still serve the slug-based
# Workspace flow. Stage 4 will reconcile the two surfaces.
router = APIRouter(prefix="/api/saved-strategies", tags=["saved_strategies"])


class SavedStrategyResponse(BaseModel):
    id: str
    user_id: str
    title: str
    strategy_json: dict
    is_public: bool
    backtest_record_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=SavedStrategyResponse, status_code=201)
def create_saved_strategy(
    payload: SaveStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedStrategyResponse:
    """Save a strategy. Scout: forced public + 10 cap; Strategist+: respects is_public + 25/unlimited cap."""
    strategy = saved_strategy_service.save_strategy(db, current_user, payload)
    return SavedStrategyResponse.model_validate(strategy)


@router.get("", response_model=list[SavedStrategyResponse])
def list_saved_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedStrategyResponse]:
    rows = saved_strategy_service.list_user_strategies(db, current_user.id)
    # Exclude saved *screens* (PRD-23c) — they're SavedStrategy rows with
    # kind=="screen" but have no backtest, so they'd render broken on the
    # strategy-detail page. They have their own surface at /screens.
    return [SavedStrategyResponse.model_validate(r) for r in rows if not is_screen(r)]


class UnresolvedExit(BaseModel):
    """An exit tier that fired and the user has neither acted on nor
    consciously declined."""
    strategy_id: str
    strategy_title: str
    position_id: str
    symbol: str
    trigger_type: str
    tier_label: Optional[str] = None
    signaled_at: Optional[str] = None
    price: Optional[float] = None
    pct_change: Optional[float] = None
    action: Optional[str] = None
    shares: Optional[float] = None
    shares_remaining: float
    shares_initial: float
    entry_price: float
    # Which staleness story the ticket must tell. A daily exit was measured
    # on a COMPLETED session's bar and acted on at the next open; an
    # intraday one was sampled from a ~15-min-delayed feed. Same field,
    # opposite caveats — and telling a daily user their price is "delayed 20
    # minutes" would be both wrong and less useful than the truth.
    bar_resolution: str = "daily"
    # The session the tier was measured on (daily path records it). The
    # signal timestamp is when the CRON ran, which is not the same thing and
    # is the less meaningful of the two on a bar the market already closed.
    bar_date: Optional[str] = None


# DECLARED BEFORE `/{strategy_id}`. FastAPI matches in declaration order, so
# below that route this path would be swallowed as a strategy id and 404.
@router.get("/unresolved-exits", response_model=list[UnresolvedExit])
def list_unresolved_exits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UnresolvedExit]:
    """Every exit the user has been told about and not yet resolved.

    DERIVED, NOT STORED — and that is the point. An exit alert is delivered
    as a `NotificationBannerEntry`, which the user can dismiss; dismissing
    is how you clear a notice, not how you decide about a position. Until
    now that was the same gesture, so an exit could be tidied away and the
    fact that a stop had fired went with it.

    Reading the state back out of `trade_log` means it cannot be dismissed
    away. A `pending_confirmation` event stays visible here until it becomes
    `executed` (the user sold — see confirm-exit) or `held` (the user
    consciously kept the position — see the hold endpoint below). Missing
    the email now makes an exit LATE rather than LOST, which is the whole
    difference between a monitor you can rely on and one you cannot.

    Cheap by construction: only OPEN positions carry unresolved tiers, and
    a user with nothing open pays one indexed query.
    """
    from sqlalchemy import select
    from app.models.position_state import PositionState

    strategy_ids = [
        r.id for r in saved_strategy_service.list_user_strategies(db, current_user.id)
    ]
    if not strategy_ids:
        return []

    positions = db.execute(
        select(PositionState)
        .where(PositionState.saved_strategy_id.in_(strategy_ids))
        .where(PositionState.is_open == True)  # noqa: E712
    ).scalars().all()
    if not positions:
        return []

    rows = saved_strategy_service.list_user_strategies(db, current_user.id)
    titles = {r.id: (r.title or "Your strategy") for r in rows}
    resolutions = {
        r.id: ((r.strategy_json or {}).get("bar_resolution") or "daily")
        for r in rows
    }

    out: list[UnresolvedExit] = []
    for pos in positions:
        for ev in (pos.trade_log or []):
            if ev.get("status") != "pending_confirmation":
                continue
            out.append(UnresolvedExit(
                strategy_id=pos.saved_strategy_id,
                strategy_title=titles.get(pos.saved_strategy_id, "Your strategy"),
                position_id=pos.id,
                symbol=pos.symbol,
                trigger_type=ev.get("event", ""),
                tier_label=ev.get("tier_label"),
                signaled_at=ev.get("timestamp"),
                price=ev.get("price"),
                pct_change=ev.get("pct_change"),
                action=ev.get("action") or ev.get("suggested_action"),
                shares=ev.get("shares", ev.get("suggested_shares")),
                shares_remaining=pos.shares_remaining,
                shares_initial=pos.shares_initial,
                entry_price=pos.entry_price,
                bar_resolution=resolutions.get(pos.saved_strategy_id, "daily"),
                bar_date=ev.get("bar_date"),
            ))

    # Most recent first — a stop that fired this afternoon matters more than
    # a target from last week.
    out.sort(key=lambda u: u.signaled_at or "", reverse=True)
    return out


# ── PRD-28 Step 4: every tracked position, across every strategy ────────────
#
# DECLARED BEFORE `/{strategy_id}` — FastAPI matches in declaration order, so
# below that route this path would be swallowed as a strategy id and 404.


class TierMarker(BaseModel):
    """One rung, priced. `distance_pct` is how far the price must move FROM
    HERE to reach it — which is the number a holder actually wants, and is
    not the same as the tier's trigger (that one is measured from entry)."""
    label: Optional[str] = None
    trigger_pct: float
    price: float
    distance_pct: Optional[float] = None


class TrackedPosition(BaseModel):
    strategy_id: str
    strategy_title: str
    position_id: str
    symbol: str
    entered_at: datetime
    entry_price: float
    shares_initial: float
    shares_remaining: float
    latest_price: Optional[float] = None
    # Which price this is. A daily strategy is monitored on the CLOSE, so a
    # fresher intraday quote is worth showing but is not what the ladder will
    # be evaluated against — the UI needs to be able to say which it has.
    price_source: str = "none"          # "intraday" | "daily_close" | "none"
    price_at: Optional[str] = None
    pct_change_from_entry: Optional[float] = None
    # BOTH directions, deliberately. PRD-28 says "next tier", but a position
    # has a live stop AND a live target at the same time and picking one
    # would be arbitrary — the stop is the one that can hurt you, the target
    # is the one you are waiting for.
    stop: Optional[TierMarker] = None
    next_target: Optional[TierMarker] = None
    # Tiers that fired and the user has neither acted on nor declined. Shown
    # so a position with an open decision cannot look settled.
    unresolved_count: int = 0
    bar_resolution: str = "daily"


def _latest_prices(db: Session, symbols) -> dict:
    """Most recent price per symbol: intraday cache first, daily close after.

    THE FALLBACK IS THE POINT. `get_strategy_positions` read only
    `IntradayBar`, and a daily strategy has no intraday bars — so
    `latest_price` and `pct_change_from_entry` came back None for every
    daily position, on the one configuration the product supports. The
    dashboard's distance-to-tier bars had nothing to render.

    Returns {symbol: (price, iso_timestamp, source)}.
    """
    from sqlalchemy import select, desc
    from app.models.intraday_bar import IntradayBar
    from app.models.price_bar import PriceBar

    out = {}
    for sym in symbols:
        bar = db.execute(
            select(IntradayBar)
            .where(IntradayBar.symbol == sym)
            .order_by(desc(IntradayBar.bar_time))
            .limit(1)
        ).scalar_one_or_none()
        if bar is not None:
            out[sym] = (float(bar.close), bar.bar_time.isoformat(), "intraday")
            continue
        daily = db.execute(
            select(PriceBar)
            .where(PriceBar.symbol == sym)
            .order_by(desc(PriceBar.trading_date))
            .limit(1)
        ).scalar_one_or_none()
        if daily is not None:
            out[sym] = (
                float(daily.close), daily.trading_date.isoformat(), "daily_close",
            )
    return out


def _tier_markers(ladder, *, entry_price: float, latest_price, fired):
    """The live stop and the next live target, priced.

    Fired tiers are excluded using the SAME `trigger_type_for` indexing the
    monitor and the backtester use. Re-deriving "has this rung gone yet"
    with a local rule is exactly the divergence `exit_ladder.py` exists to
    prevent — a stop that shows as live here after firing would tell a user
    they are protected when they are not.
    """
    from app.services.exit_ladder import trigger_type_for

    stop = None
    target = None
    for index, tier in enumerate(ladder or []):
        try:
            trigger = float(tier.get("trigger_pct"))
        except (TypeError, ValueError):
            continue
        if trigger_type_for(index) in fired:
            continue
        price = entry_price * (1.0 + trigger)
        distance = (
            (price - latest_price) / latest_price
            if latest_price else None
        )
        marker = TierMarker(
            label=tier.get("label"), trigger_pct=trigger,
            price=round(price, 4),
            distance_pct=distance,
        )
        # Ladder order is ascending, so the first unfired negative tier is the
        # nearest stop and the first unfired positive one is the next target.
        if trigger < 0 and stop is None:
            stop = marker
        elif trigger > 0 and target is None:
            target = marker
    return stop, target


@router.get("/open-positions", response_model=list[TrackedPosition])
def list_open_positions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TrackedPosition]:
    """Every open position the user tracks, across every strategy.

    The per-strategy dashboard answers "how is THIS strategy doing". Nothing
    answered "what am I holding, and what happens next" without knowing
    which strategy to open first — which is the question someone actually
    has when they sit down.
    """
    from sqlalchemy import select
    from app.models.position_state import PositionState

    rows = saved_strategy_service.list_user_strategies(db, current_user.id)
    by_id = {r.id: r for r in rows}
    if not by_id:
        return []

    positions = db.execute(
        select(PositionState)
        .where(PositionState.saved_strategy_id.in_(list(by_id.keys())))
        .where(PositionState.is_open == True)  # noqa: E712
    ).scalars().all()
    if not positions:
        return []

    prices = _latest_prices(db, {p.symbol for p in positions})

    out: list[TrackedPosition] = []
    for pos in positions:
        strategy = by_id.get(pos.saved_strategy_id)
        sj = (strategy.strategy_json or {}) if strategy else {}
        ladder = (sj.get("risk_management") or {}).get("exit_ladder") or []

        price_row = prices.get(pos.symbol)
        latest = price_row[0] if price_row else None
        pct = (
            (latest - pos.entry_price) / pos.entry_price
            if latest is not None and pos.entry_price else None
        )

        log = pos.trade_log or []
        fired = {e.get("event") for e in log if e.get("event")}
        stop, target = _tier_markers(
            ladder, entry_price=pos.entry_price, latest_price=latest, fired=fired,
        )

        out.append(TrackedPosition(
            strategy_id=pos.saved_strategy_id,
            strategy_title=(strategy.title if strategy else None) or "Your strategy",
            position_id=pos.id,
            symbol=pos.symbol,
            entered_at=pos.entered_at,
            entry_price=pos.entry_price,
            shares_initial=pos.shares_initial,
            shares_remaining=pos.shares_remaining,
            latest_price=latest,
            price_source=price_row[2] if price_row else "none",
            price_at=price_row[1] if price_row else None,
            pct_change_from_entry=pct,
            stop=stop,
            next_target=target,
            unresolved_count=sum(
                1 for e in log if e.get("status") == "pending_confirmation"
            ),
            bar_resolution=sj.get("bar_resolution") or "daily",
        ))

    # Positions with an open decision first, then the ones closest to a stop.
    out.sort(key=lambda p: (
        -p.unresolved_count,
        abs(p.stop.distance_pct) if p.stop and p.stop.distance_pct is not None else 9e9,
    ))
    return out


@router.get("/{strategy_id}", response_model=SavedStrategyResponse)
def get_saved_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedStrategyResponse:
    row = saved_strategy_service.get_strategy(db, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    # Public strategies are readable by anyone authenticated; private only by owner.
    if not row.is_public and row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return SavedStrategyResponse.model_validate(row)


@router.delete("/{strategy_id}", status_code=204, response_class=Response)
def delete_saved_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    deleted = saved_strategy_service.delete_strategy(db, current_user.id, strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return Response(status_code=204)


# ── PRD-19: Mark-as-Executed retention metric loop ──────────────────────────


class MarkAsExecutedRequest(BaseModel):
    """User-attested action log. Optional free-text note bounded to 560
    chars per PRD §4 (matches the email-embed preview limit)."""
    user_note: Optional[str] = None


class MarkAsExecutedResponse(BaseModel):
    ok: bool
    latency_seconds: int  # signal_event.created_at → executed_at
    signal_event_id: str
    executed_at: datetime
    # True if a row already existed for (user, signal_event) — idempotent.
    # The endpoint never errors on repeat clicks; it just returns the
    # existing row. Lets the frontend optimistic-UI button stay idempotent
    # without race-condition worry.
    idempotent: bool


@router.post(
    "/{strategy_id}/mark-executed",
    response_model=MarkAsExecutedResponse,
)
def mark_strategy_executed(
    strategy_id: str,
    payload: MarkAsExecutedRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarkAsExecutedResponse:
    """Log that the current user acted on the latest signal for this
    strategy. Idempotent — second click on the same notification returns
    the existing row.

    The retention metric Sprint A is trying to measure
    (HANDOFF §7): time from `signal_event.created_at` to `executed_at`.
    PostHog captures it as `notification_executed` with `latency_seconds`.

    Compliance note: this is a user attestation, not a Livermore claim
    of trade placement (PRD §"Compliance" — Mark-as-Executed event is
    user-attested only).

    Failures:
      - 404 if the strategy doesn't exist OR isn't owned by the caller
        (the message is intentionally the same to avoid leaking strategy
        existence to non-owners)
      - 404 if no SignalEvent exists for this strategy yet (nothing to
        mark — the user hasn't received a notification at all)
    """
    from uuid import uuid4
    from sqlalchemy import select, desc
    from app.models.mark_as_executed_event import MarkAsExecutedEvent
    from app.models.saved_strategy import SavedStrategy
    from app.models.signal_event import SignalEvent

    # Snapshot scalars (trap #17 — DB-bound ORM instances expire across
    # commits; reading user_id / current_user.id again after the
    # MarkAsExecutedEvent commit below could trigger DetachedInstanceError
    # in some configurations).
    user_id: str = current_user.id

    # 1. Resolve strategy + verify ownership. Public strategies don't count;
    # you can only mark-executed on something you saved.
    strategy = db.get(SavedStrategy, strategy_id)
    if strategy is None or strategy.user_id != user_id:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    # 2. Find the latest SignalEvent for this strategy. If none, there's
    # nothing to act on — return 404 so the frontend can degrade gracefully.
    latest_event = db.execute(
        select(SignalEvent)
        .where(SignalEvent.saved_strategy_id == strategy_id)
        .order_by(desc(SignalEvent.created_at))
        .limit(1)
    ).scalar_one_or_none()
    if latest_event is None:
        raise HTTPException(
            status_code=404,
            detail="No signal event to mark as executed for this strategy.",
        )

    # 3. Idempotency check — has the user already marked THIS specific
    # signal event as executed? The UNIQUE index on
    # (user_id, signal_event_id) backs this query.
    existing = db.execute(
        select(MarkAsExecutedEvent).where(
            MarkAsExecutedEvent.user_id == user_id,
            MarkAsExecutedEvent.signal_event_id == latest_event.id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Idempotent — return the existing row's data. No write, no
        # PostHog re-capture (avoids inflating the retention metric with
        # duplicate clicks).
        latency = int((existing.executed_at - latest_event.created_at).total_seconds())
        return MarkAsExecutedResponse(
            ok=True,
            latency_seconds=max(0, latency),
            signal_event_id=latest_event.id,
            executed_at=existing.executed_at,
            idempotent=True,
        )

    # 4. Write the new attestation. `datetime.utcnow()` to match the
    # model default's TZ semantics (naive UTC).
    now = datetime.utcnow()
    event = MarkAsExecutedEvent(
        id=str(uuid4()),
        user_id=user_id,
        signal_event_id=latest_event.id,
        saved_strategy_id=strategy_id,
        executed_at=now,
        user_note=(payload.user_note.strip() if payload.user_note else None),
    )
    db.add(event)
    db.commit()

    latency = int((now - latest_event.created_at).total_seconds())

    # 5. PostHog event for the retention metric. PRD-19 §7 names this
    # `notification_executed` with `latency_seconds`. Best-effort — never
    # blocks the response, never raises.
    try:
        from app.services import posthog_service
        posthog_service.capture(
            user_id=user_id,
            event="notification_executed",
            properties={
                "latency_seconds": max(0, latency),
                "saved_strategy_id": strategy_id,
                "signal_event_id": latest_event.id,
                "has_user_note": bool(payload.user_note),
            },
        )
    except Exception:
        # PostHog being down / misconfigured / module absent must never
        # break the user action. The DB row is the source of truth for
        # the metric; PostHog is convenience for the dashboard view.
        pass

    return MarkAsExecutedResponse(
        ok=True,
        latency_seconds=max(0, latency),
        signal_event_id=latest_event.id,
        executed_at=now,
        idempotent=False,
    )


# ── PRD-16c-3c: Live dashboard endpoints ────────────────────────────────────
#
# Three GETs feed the strategy-detail "active execution" dashboard:
#
#   /{strategy_id}/universe-state — one row per universe ticker with the
#                                   latest price + price source (intraday
#                                   bar for active strategies; future:
#                                   live quote)
#   /{strategy_id}/positions      — open + recently-closed PositionState
#                                   rows with distance-to-tier indicators
#   /{strategy_id}/trade-log      — flattened paginated event log across
#                                   all positions for the strategy
#
# Owner-only. Public strategies don't expose this surface — positions
# belong to the owner who's actively running the strategy. Anonymous +
# non-owner authed callers get 404 (same shape as `get_saved_strategy`).


class UniverseSymbolState(BaseModel):
    symbol: str
    latest_price: Optional[float] = None
    latest_at: Optional[datetime] = None
    # Source so the UI can distinguish "live" (intraday cache, within
    # last hour) from "stale" (no recent bar — strategy not actively
    # monitored, or AV returned no bar today).
    source: str  # 'intraday' | 'no_data'


class UniverseStateResponse(BaseModel):
    strategy_id: str
    bar_resolution: str
    universe: list[UniverseSymbolState]
    generated_at: datetime


class PositionView(BaseModel):
    """One row in the dashboard's positions grid. Includes the
    distance-to-tier ratios that the UI renders as bars."""
    id: str
    symbol: str
    entered_at: datetime
    entry_price: float
    shares_initial: float
    shares_remaining: float
    is_open: bool
    closed_at: Optional[datetime] = None
    final_pnl: Optional[float] = None
    latest_price: Optional[float] = None
    pct_change_from_entry: Optional[float] = None
    trade_log: list[dict]


class PositionsResponse(BaseModel):
    strategy_id: str
    positions: list[PositionView]
    open_count: int
    closed_count: int


class TradeEvent(BaseModel):
    """One row in the chronological trade-log table."""
    position_id: str
    symbol: str
    event: str  # entry | stop_hit | tp1_hit | tp2_hit | ...
    timestamp: datetime
    price: Optional[float] = None
    shares: Optional[float] = None
    shares_sold: Optional[float] = None
    tier_label: Optional[str] = None


class TradeLogResponse(BaseModel):
    strategy_id: str
    events: list[TradeEvent]
    total: int
    # Pagination cursor — events are sorted newest-first; next page is
    # `?before=<timestamp>` for the next 100. Simpler than offset-based
    # for an append-only event stream.
    next_before: Optional[datetime] = None


# ── intraday live chart (price trend + tier lines + trigger markers) ────────


class IntradayBarPoint(BaseModel):
    t: datetime
    close: float


class IntradayChartTier(BaseModel):
    """A horizontal level the chart draws: entry_price * (1 + trigger_pct)."""
    label: str
    trigger_pct: float
    price_level: Optional[float] = None


class IntradayChartEvent(BaseModel):
    """A point marker on the chart — entry or a fired exit tier."""
    t: datetime
    price: Optional[float] = None
    event: str
    tier_label: Optional[str] = None


class IntradayChartSeries(BaseModel):
    position_id: str
    symbol: str
    is_open: bool
    entry_at: Optional[datetime] = None
    entry_price: Optional[float] = None
    bars: list[IntradayBarPoint]
    tiers: list[IntradayChartTier]
    events: list[IntradayChartEvent]


class IntradayChartResponse(BaseModel):
    strategy_id: str
    bar_resolution: str
    generated_at: datetime
    series: list[IntradayChartSeries]


# US market timezone. Intraday bars are stored as naive US/Eastern
# wall-clock (the AV wrapper parses AV's ET strings naive — see
# alpha_vantage.py), while trade-log/entry timestamps are naive UTC
# (datetime.utcnow()). The chart must put both on ONE basis or the
# trigger markers land hours off the price line — we normalize everything
# to ET-aware here so the frontend can render an ET axis directly.
_ET = ZoneInfo("America/New_York")


def _bar_time_to_et(naive_et: datetime) -> datetime:
    """A stored bar_time is naive ET wall-clock — attach ET, don't shift."""
    return naive_et.replace(tzinfo=_ET)


def _utc_to_et(dt: Optional[datetime]) -> Optional[datetime]:
    """An event/entry timestamp is naive (or aware) UTC — convert to ET."""
    if dt is None:
        return None
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return aware.astimezone(_ET)


def _resolve_owned_strategy(
    db: Session, strategy_id: str, current_user: User
):
    """Common owner-only resolver. Returns the SavedStrategy row or
    raises 404 (404 not 403 — don't leak existence)."""
    from app.models.saved_strategy import SavedStrategy
    row = db.get(SavedStrategy, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return row


@router.get(
    "/{strategy_id}/universe-state",
    response_model=UniverseStateResponse,
)
async def get_universe_state(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UniverseStateResponse:
    """Latest price per universe ticker for the active-execution dashboard.

    For intraday strategies (`bar_resolution != 'daily'`), reads from the
    `intraday_bars` cache via `IntradayBarService`. For daily strategies
    OR when no intraday bar is cached, returns `latest_price=None` with
    `source='no_data'`. Daily strategies' "current price" comes from
    elsewhere (the existing Market Pulse / live_quote_service path) and
    isn't this endpoint's concern.
    """
    from app.services.intraday_bar_service import IntradayBarService

    strategy = _resolve_owned_strategy(db, strategy_id, current_user)
    sj_dict = strategy.strategy_json or {}
    universe = sj_dict.get("universe") or sj_dict.get("inherited_universe") or []
    bar_resolution = sj_dict.get("bar_resolution", "daily")

    rows: list[UniverseSymbolState] = []
    if bar_resolution == "daily" or not universe:
        # Daily strategies: this endpoint returns the symbols with no
        # intraday price. Frontend's dashboard renders these as "EOD only."
        for sym in universe:
            rows.append(UniverseSymbolState(
                symbol=sym, latest_price=None, latest_at=None,
                source="no_data",
            ))
        return UniverseStateResponse(
            strategy_id=strategy_id,
            bar_resolution=bar_resolution,
            universe=rows,
            generated_at=datetime.utcnow(),
        )

    from app.services.intraday_bar_service import et_now_naive

    bar_svc = IntradayBarService()
    # Read from cache only — never fetch on the GET path. The monitor cron
    # keeps the cache fresh. A cold cache is reported truthfully
    # (source='no_data') rather than gating the UI on a network roundtrip.
    # Window in ET to match the naive-ET bar_time (a UTC window skews ~4-5h
    # and would report fresh bars as "no recent bar").
    end = et_now_naive()
    start = end - timedelta(hours=6)
    for sym in universe:
        cached = bar_svc._read_cached(db, sym.upper(), bar_resolution, start, end)
        if cached:
            last = cached[-1]
            rows.append(UniverseSymbolState(
                symbol=sym,
                latest_price=float(last.close),
                latest_at=last.bar_time,
                source="intraday",
            ))
        else:
            rows.append(UniverseSymbolState(
                symbol=sym, latest_price=None, latest_at=None,
                source="no_data",
            ))
    return UniverseStateResponse(
        strategy_id=strategy_id,
        bar_resolution=bar_resolution,
        universe=rows,
        generated_at=datetime.utcnow(),
    )


@router.get(
    "/{strategy_id}/positions",
    response_model=PositionsResponse,
)
def get_strategy_positions(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PositionsResponse:
    """Open + recently-closed positions for the active-execution
    dashboard. Includes `latest_price` + `pct_change_from_entry` so the
    UI can render distance-to-tier bars without a second request."""
    from sqlalchemy import select, desc
    from app.models.position_state import PositionState

    _ = _resolve_owned_strategy(db, strategy_id, current_user)

    rows = db.execute(
        select(PositionState)
        .where(PositionState.saved_strategy_id == strategy_id)
        .order_by(desc(PositionState.is_open), desc(PositionState.updated_at))
    ).scalars().all()

    # Latest price per symbol: intraday cache first, daily close after.
    #
    # This used to read ONLY `IntradayBar`. A daily strategy has no intraday
    # bars, so every daily position came back with `latest_price=None` and
    # `pct_change_from_entry=None`, and the dashboard's distance-to-tier bars
    # had nothing to render — on the only configuration the product supports.
    # Same shape as the daily gates #331/#337/#340 removed: the code was
    # correct when active execution meant intraday, and nobody revisited it.
    sym_to_price = _latest_prices(db, {pos.symbol for pos in rows}) if rows else {}

    positions: list[PositionView] = []
    open_count = 0
    closed_count = 0
    for pos in rows:
        latest = sym_to_price.get(pos.symbol)
        latest_price = latest[0] if latest else None
        pct_change: Optional[float] = None
        if latest_price is not None and pos.entry_price:
            pct_change = (latest_price - pos.entry_price) / pos.entry_price
        positions.append(PositionView(
            id=pos.id,
            symbol=pos.symbol,
            entered_at=pos.entered_at,
            entry_price=pos.entry_price,
            shares_initial=pos.shares_initial,
            shares_remaining=pos.shares_remaining,
            is_open=pos.is_open,
            closed_at=pos.closed_at,
            final_pnl=pos.final_pnl,
            latest_price=latest_price,
            pct_change_from_entry=pct_change,
            trade_log=list(pos.trade_log or []),
        ))
        if pos.is_open:
            open_count += 1
        else:
            closed_count += 1

    return PositionsResponse(
        strategy_id=strategy_id,
        positions=positions,
        open_count=open_count,
        closed_count=closed_count,
    )


@router.get(
    "/{strategy_id}/trade-log",
    response_model=TradeLogResponse,
)
def get_strategy_trade_log(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 100,
    before: Optional[datetime] = None,
) -> TradeLogResponse:
    """Chronological trade events flattened across every PositionState
    row for this strategy. Newest first; paginated via `?before=<iso8601>`.
    `total` is the unfiltered count so the UI can show "247 events."""
    from sqlalchemy import select
    from app.models.position_state import PositionState

    _ = _resolve_owned_strategy(db, strategy_id, current_user)
    # Cap limit to keep payload bounded.
    limit = max(1, min(limit, 500))

    rows = db.execute(
        select(PositionState)
        .where(PositionState.saved_strategy_id == strategy_id)
    ).scalars().all()

    flat: list[TradeEvent] = []
    for pos in rows:
        for event in (pos.trade_log or []):
            ts_raw = event.get("timestamp")
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw)
            except (TypeError, ValueError):
                continue
            flat.append(TradeEvent(
                position_id=pos.id,
                symbol=pos.symbol,
                event=event.get("event") or "unknown",
                timestamp=ts,
                price=event.get("price"),
                shares=event.get("shares"),
                shares_sold=event.get("shares_sold"),
                tier_label=event.get("tier_label"),
            ))
    flat.sort(key=lambda e: e.timestamp, reverse=True)
    total = len(flat)
    if before is not None:
        flat = [e for e in flat if e.timestamp < before]
    page = flat[:limit]
    next_before = page[-1].timestamp if len(flat) > limit else None
    return TradeLogResponse(
        strategy_id=strategy_id,
        events=page,
        total=total,
        next_before=next_before,
    )


@router.get(
    "/{strategy_id}/intraday-chart",
    response_model=IntradayChartResponse,
)
def get_intraday_chart(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    lookback_hours: int = 48,
) -> IntradayChartResponse:
    """Per-open-position intraday price series + exit-tier price levels +
    fired-trigger markers, for the dashboard's live chart.

    Reads bars from the `intraday_bars` cache ONLY (the monitor cron keeps
    it fresh) — never fetches from AlphaVantage on this GET path, so it
    can't hold a DB connection across a network await (trap #13) and a
    cold cache is reported truthfully as an empty `bars` list rather than
    blocking the UI. Daily strategies return an empty `series`.
    """
    from sqlalchemy import select, desc
    from app.models.position_state import PositionState
    from app.services.intraday_bar_service import IntradayBarService

    strategy = _resolve_owned_strategy(db, strategy_id, current_user)
    sj_dict = strategy.strategy_json or {}
    bar_resolution = sj_dict.get("bar_resolution", "daily")
    exit_ladder = (sj_dict.get("risk_management") or {}).get("exit_ladder") or []

    generated = datetime.utcnow()
    series: list[IntradayChartSeries] = []

    if bar_resolution != "daily":
        bar_svc = IntradayBarService()
        # Clamp the window: ≥1h, ≤7 days of cached intraday bars.
        hours = max(1, min(lookback_hours, 168))
        end = generated
        start = end - timedelta(hours=hours)

        rows = db.execute(
            select(PositionState)
            .where(
                PositionState.saved_strategy_id == strategy_id,
                PositionState.is_open == True,  # noqa: E712
            )
            .order_by(desc(PositionState.updated_at))
        ).scalars().all()

        for pos in rows:
            cached = bar_svc._read_cached(
                db, pos.symbol.upper(), bar_resolution, start, end,
            )
            bars = [
                IntradayBarPoint(t=_bar_time_to_et(b.bar_time), close=float(b.close))
                for b in cached
            ]

            tiers: list[IntradayChartTier] = []
            for tier in exit_ladder:
                trigger_pct = tier.get("trigger_pct")
                if trigger_pct is None:
                    continue
                price_level = (
                    pos.entry_price * (1 + trigger_pct)
                    if pos.entry_price
                    else None
                )
                tiers.append(IntradayChartTier(
                    label=tier.get("label") or f"{trigger_pct * 100:.0f}%",
                    trigger_pct=trigger_pct,
                    price_level=price_level,
                ))

            events: list[IntradayChartEvent] = []
            for ev in (pos.trade_log or []):
                ts_raw = ev.get("timestamp")
                if not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except (TypeError, ValueError):
                    continue
                events.append(IntradayChartEvent(
                    t=_utc_to_et(ts),
                    price=ev.get("price"),
                    event=ev.get("event") or "unknown",
                    tier_label=ev.get("tier_label"),
                ))

            series.append(IntradayChartSeries(
                position_id=pos.id,
                symbol=pos.symbol,
                is_open=pos.is_open,
                entry_at=_utc_to_et(pos.entered_at),
                entry_price=pos.entry_price,
                bars=bars,
                tiers=tiers,
                events=events,
            ))

    return IntradayChartResponse(
        strategy_id=strategy_id,
        bar_resolution=bar_resolution,
        generated_at=generated,
        series=series,
    )


# ── PRD-28 §2.2: attach an exit ladder to a saved strategy ──────────────────
#
# ONE OF THE PRODUCT'S TWO SIGN-OFF POINTS, and the reason this is its own
# endpoint rather than a field on some larger update.
#
# Founder decision, 2026-08-21: saving a strategy and placing an order both
# require explicit user sign-off, and neither may rely on a developer
# remembering to render a confirmation dialog.
#
# Order placement already had that property structurally: `place_order` takes
# only a trade id produced by a preview, so an order can only ever be one the
# user saw priced (see `snaptrade.py`). This endpoint gives the same property
# to the other half.
#
# THE RULE: the ladder arrives ONLY as an explicit payload. There is no
# server-side path that applies a default, derives one from ATR, or copies one
# from a template. Because the server never invents a ladder, the ladder that
# lands on a strategy is always one the client sent — and the client can only
# send what it rendered. The confirmation is a consequence of the API's shape
# rather than a promise about the UI.
#
# `tests/test_exit_ladder_signoff_guard.py` asserts no other code path writes
# `risk_management.exit_ladder` onto an existing SavedStrategy.


class AttachExitLadderRequest(BaseModel):
    """The ladder, in full, every time.

    Deliberately has no "use the default" flag and no partial/patch form. A
    request that omits `exit_ladder` is a 422, not a signal to apply
    something sensible — "sensible" chosen by the server is exactly the stop
    a user will not believe when it fires.
    """
    exit_ladder: list  # validated below by RiskManagement, the real validator


@router.post("/{strategy_id}/exit-ladder", response_model=SavedStrategyResponse)
def attach_exit_ladder(
    strategy_id: str,
    payload: AttachExitLadderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedStrategyResponse:
    """Set the exit ladder on a strategy the user owns.

    Replaces any existing ladder wholesale — the client renders the current
    one, the user edits it, and what comes back is the whole intended state.
    A merge would mean the saved ladder is something neither side displayed.

    400 rather than 422 on a bad ladder: the tiers came from a form the user
    just filled in, and the validator's messages ("must include at least one
    stop tier") are written to be read by a person.
    """
    from app.schemas.strategy import RiskManagement

    strategy = _resolve_owned_strategy(db, strategy_id, current_user)

    if not payload.exit_ladder:
        raise HTTPException(
            status_code=400,
            detail=(
                "An exit ladder needs at least one tier. To remove tracking, "
                "delete the position rather than emptying the ladder."
            ),
        )

    # Validate through the SAME model the backtester and the monitor read, so
    # a ladder that saves is a ladder both of them can act on. Doing the
    # checks by hand here is how the two drift apart.
    try:
        validated = RiskManagement(exit_ladder=payload.exit_ladder)
    except Exception as exc:  # pydantic ValidationError
        raise HTTPException(status_code=400, detail=_first_ladder_error(exc)) from exc

    tiers = [t.model_dump(exclude_none=True) for t in (validated.exit_ladder or [])]

    # REASSIGN, never mutate in place. `strategy_json` is a plain JSON column
    # with no MutableDict wrapper, so SQLAlchemy's change detection compares
    # object identity — mutating the nested dict leaves the row unflagged and
    # the commit silently writes nothing. Pinned by
    # `test_attaching_a_ladder_actually_persists`.
    sj = dict(strategy.strategy_json or {})
    risk = dict(sj.get("risk_management") or {})
    risk["exit_ladder"] = tiers
    sj["risk_management"] = risk
    strategy.strategy_json = sj

    db.commit()
    db.refresh(strategy)
    return SavedStrategyResponse.model_validate(strategy)


def _first_ladder_error(exc: Exception) -> str:
    """Pull the human sentence out of a pydantic ValidationError.

    The validators in `RiskManagement` raise prose written for a user ("must
    include at least one stop tier (trigger_pct < 0 with action='sell_all')").
    Pydantic wraps that in several lines of type and location noise, and
    handing the whole envelope to a form field turns a usable message into
    something that looks like a crash.
    """
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            first = errors()[0]
            msg = str(first.get("msg", "")).strip()
            # "Value error, <the real message>" — drop pydantic's prefix.
            for prefix in ("Value error, ", "Assertion failed, "):
                if msg.startswith(prefix):
                    msg = msg[len(prefix):]
            if msg:
                return msg
        except Exception:  # noqa: BLE001 — never let error handling raise
            pass
    return "That exit ladder isn't valid."


# ── active-execution-v2 PR2: declare a real held position ───────────────────


class DeclarePositionRequest(BaseModel):
    """User declares a position they actually hold, to be tracked against
    the strategy's exit ladder. The numbers are the user's REAL fill —
    Livermore never simulates ownership."""
    symbol: str
    shares: float
    entry_price: float          # the user's actual average cost basis
    entered_at: Optional[datetime] = None  # defaults to now (UTC)


@router.post(
    "/{strategy_id}/positions",
    response_model=PositionView,
    status_code=201,
)
def declare_position(
    strategy_id: str,
    payload: DeclarePositionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PositionView:
    """Declare a real position the user holds, tracked against the
    strategy's exit ladder. Owner-only.

    Guards:
      - 404 if the strategy doesn't exist or isn't owned by the caller.
      - 400 if the strategy isn't set up for active execution
        (`bar_resolution == 'daily'` OR no `exit_ladder`) — there's
        nothing to monitor the position against.
      - 400 on non-positive shares / entry_price.
      - 409 if an OPEN position already exists for this (strategy, symbol)
        — one open position per symbol per strategy; close it first.

    The created PositionState carries the user's real numbers. The
    intraday monitor (PR1) detects exit-ladder triggers and notifies;
    the user confirms the actual sale (PR3) — Livermore never mutates
    the position itself.
    """
    from uuid import uuid4
    from sqlalchemy import select
    from app.models.position_state import PositionState

    strategy = _resolve_owned_strategy(db, strategy_id, current_user)

    # Active-execution eligibility: a tracked position needs an exit ladder
    # to be monitored against. Bar resolution NO LONGER gates this.
    #
    # Daily strategies were rejected here until 2026-08-18, which excluded
    # the majority case and the only coherent one: entry signals come from
    # the daily snapshot and the backtester runs on daily bars (it degrades
    # any intraday choice), so a daily strategy is the one configuration
    # where the backtest and the live monitor measure the same thing.
    # `app/jobs/daily_position_jobs.py` monitors these after the close.
    sj = strategy.strategy_json or {}
    has_ladder = bool(
        (sj.get("risk_management") or {}).get("exit_ladder")
    )
    if not has_ladder:
        raise HTTPException(
            status_code=400,
            detail=(
                "This strategy has no exit ladder, so there is nothing to "
                "monitor a position against. Add a stop (and any targets) "
                "to the strategy before declaring a tracked position."
            ),
        )

    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required.")
    if payload.shares <= 0:
        raise HTTPException(status_code=400, detail="Shares must be positive.")
    if payload.entry_price <= 0:
        raise HTTPException(
            status_code=400, detail="Entry price must be positive."
        )

    # One open position per (strategy, symbol).
    existing = db.execute(
        select(PositionState)
        .where(PositionState.saved_strategy_id == strategy_id)
        .where(PositionState.symbol == symbol)
        .where(PositionState.is_open == True)  # noqa: E712
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"An open position for {symbol} already exists on this "
                "strategy. Close it before declaring a new one."
            ),
        )

    entered_at = payload.entered_at or datetime.utcnow()
    pos = PositionState(
        id=str(uuid4()),
        saved_strategy_id=strategy_id,
        symbol=symbol,
        entered_at=entered_at,
        entry_price=payload.entry_price,
        shares_initial=payload.shares,
        shares_remaining=payload.shares,
        is_open=True,
        trade_log=[{
            "event": "entry",
            "status": "declared",   # user-declared (vs signal_confirmed)
            "timestamp": entered_at.isoformat(),
            "price": payload.entry_price,
            "shares": payload.shares,
        }],
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)

    return _position_to_view(pos)


def _position_to_view(pos, *, latest_price=None, pct_change=None) -> PositionView:
    """Build a PositionView from a PositionState row."""
    return PositionView(
        id=pos.id,
        symbol=pos.symbol,
        entered_at=pos.entered_at,
        entry_price=pos.entry_price,
        shares_initial=pos.shares_initial,
        shares_remaining=pos.shares_remaining,
        is_open=pos.is_open,
        closed_at=pos.closed_at,
        final_pnl=pos.final_pnl,
        latest_price=latest_price,
        pct_change_from_entry=pct_change,
        trade_log=list(pos.trade_log or []),
    )


# ── active-execution-v2 PR3: confirm an exit (decrement on user fill) ────────


class ConfirmExitRequest(BaseModel):
    """The user confirms they executed a pending exit tier in their own
    brokerage. `shares_sold` + `fill_price` are the user's REAL fill —
    Livermore decrements the tracked position to match, it never sells."""
    trigger_type: str            # the pending tier to confirm: 'stop_hit' | 'tp1_hit' | ...
    shares_sold: float
    fill_price: Optional[float] = None   # actual fill; defaults to the tier's recorded price


_CLOSE_EPSILON = 1e-6


@router.post(
    "/{strategy_id}/positions/{position_id}/confirm-exit",
    response_model=PositionView,
)
def confirm_position_exit(
    strategy_id: str,
    position_id: str,
    payload: ConfirmExitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PositionView:
    """Confirm that the user executed a pending exit tier (recorded by the
    intraday monitor cron). Owner-only. This is the ONLY path that mutates
    `shares_remaining` / closes a position — the cron only detects +
    notifies; the user's confirmation is what moves the numbers, so the
    tracked position reflects the user's ACTUAL brokerage activity.

    Effect:
      - Flips the matching `pending_confirmation` trade_log event to
        `executed`, recording the user's fill (shares + price + time).
      - Decrements `shares_remaining` by `shares_sold`.
      - When `shares_remaining` reaches ~0, closes the position
        (`is_open=False`, `closed_at`, `final_pnl` from the realized
        gains on the executed sells).

    Failures:
      - 404 if strategy/position missing or not owned by the caller.
      - 400 if no pending event matches `trigger_type`.
      - 400 if `shares_sold <= 0` or exceeds `shares_remaining`.
    """
    from sqlalchemy import select
    from app.models.position_state import PositionState

    _ = _resolve_owned_strategy(db, strategy_id, current_user)

    pos = db.execute(
        select(PositionState)
        .where(PositionState.id == position_id)
        .where(PositionState.saved_strategy_id == strategy_id)
    ).scalar_one_or_none()
    if pos is None:
        raise HTTPException(status_code=404, detail="Position not found.")

    if payload.shares_sold <= 0:
        raise HTTPException(status_code=400, detail="shares_sold must be positive.")
    if payload.shares_sold > pos.shares_remaining + _CLOSE_EPSILON:
        raise HTTPException(
            status_code=400,
            detail=(
                f"shares_sold ({payload.shares_sold}) exceeds shares "
                f"remaining ({pos.shares_remaining})."
            ),
        )

    # Find the matching pending event (most recent wins if duplicated).
    log = list(pos.trade_log or [])
    pending_idx = None
    for i in range(len(log) - 1, -1, -1):
        ev = log[i]
        if (
            ev.get("event") == payload.trigger_type
            and ev.get("status") == "pending_confirmation"
        ):
            pending_idx = i
            break
    if pending_idx is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No pending '{payload.trigger_type}' exit to confirm on "
                "this position."
            ),
        )

    now = datetime.utcnow()
    fill_price = (
        payload.fill_price
        if payload.fill_price is not None
        else log[pending_idx].get("price")
    )
    # Flip pending → executed with the user's real fill.
    log[pending_idx] = {
        **log[pending_idx],
        "status": "executed",
        "executed_shares": payload.shares_sold,
        "fill_price": fill_price,
        "executed_at": now.isoformat(),
    }
    pos.trade_log = log

    # Decrement + maybe close.
    pos.shares_remaining = max(0.0, pos.shares_remaining - payload.shares_sold)
    if pos.shares_remaining <= _CLOSE_EPSILON:
        pos.shares_remaining = 0.0
        pos.is_open = False
        pos.closed_at = now
        # Realized P&L = sum over executed sells of
        # (fill_price - entry_price) * executed_shares.
        realized = 0.0
        for ev in pos.trade_log:
            if ev.get("status") == "executed":
                fp = ev.get("fill_price")
                sh = ev.get("executed_shares")
                if fp is not None and sh is not None:
                    realized += (float(fp) - pos.entry_price) * float(sh)
        pos.final_pnl = realized

    db.commit()
    db.refresh(pos)
    return _position_to_view(pos)


# ── active-execution: "I'm holding" — the OTHER way to resolve an exit ──────


class HoldExitRequest(BaseModel):
    """The user saw the exit signal and consciously kept the position."""
    trigger_type: str
    user_note: Optional[str] = None


@router.post(
    "/{strategy_id}/positions/{position_id}/hold",
    response_model=PositionView,
)
def hold_position_through_exit(
    strategy_id: str,
    position_id: str,
    payload: HoldExitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PositionView:
    """Resolve a pending exit as "I looked, and I'm keeping it". Owner-only.

    WHY THIS EXISTS. Until now a fired tier had exactly one resolution:
    confirm that you sold. A user who saw the signal and decided to hold —
    a completely ordinary decision, and one this product must not treat as
    non-compliance — had no way to say so. Their only options were to leave
    the exit pending forever or dismiss the notice, and dismissing loses the
    fact that it fired. So the honest answer was unrecordable, and
    `unresolved-exits` would have nagged them about a decision they had
    already made.

    It is also the difference between a research tool and an instruction
    system. Livermore reports that a rule the user set was met; what they do
    next is theirs. "Holding" is not a failure state.

    Effect: flips the matching `pending_confirmation` event to `held`.
    Deliberately does NOT touch `shares_remaining`, `is_open` or
    `final_pnl` — nothing was sold, so nothing moves.

    The tier stays disarmed. It fired, the user decided; re-notifying about
    the same rung would be nagging, and the exit ladder's contract is that
    each tier fires at most once per entry.

    Failures:
      - 404 if strategy/position missing or not owned by the caller
      - 400 if no pending event matches `trigger_type`
    """
    from sqlalchemy import select
    from app.models.position_state import PositionState

    _ = _resolve_owned_strategy(db, strategy_id, current_user)

    pos = db.execute(
        select(PositionState)
        .where(PositionState.id == position_id)
        .where(PositionState.saved_strategy_id == strategy_id)
    ).scalar_one_or_none()
    if pos is None:
        raise HTTPException(status_code=404, detail="Position not found.")

    log = list(pos.trade_log or [])
    pending_idx = None
    for i in range(len(log) - 1, -1, -1):
        ev = log[i]
        if (
            ev.get("event") == payload.trigger_type
            and ev.get("status") == "pending_confirmation"
        ):
            pending_idx = i
            break
    if pending_idx is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No pending '{payload.trigger_type}' exit to resolve on "
                f"{pos.symbol}."
            ),
        )

    ev = dict(log[pending_idx])
    ev["status"] = "held"
    ev["held_at"] = datetime.utcnow().isoformat()
    if payload.user_note:
        ev["user_note"] = payload.user_note
    log[pending_idx] = ev
    pos.trade_log = log

    db.commit()
    db.refresh(pos)
    return _position_to_view(pos)
