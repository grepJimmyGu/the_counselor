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
    return [SavedStrategyResponse.model_validate(r) for r in rows]


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
    from app.models.intraday_bar import IntradayBar
    from app.models.position_state import PositionState

    _ = _resolve_owned_strategy(db, strategy_id, current_user)

    rows = db.execute(
        select(PositionState)
        .where(PositionState.saved_strategy_id == strategy_id)
        .order_by(desc(PositionState.is_open), desc(PositionState.updated_at))
    ).scalars().all()

    # Latest price per symbol — read from the intraday cache. The query
    # picks the most recent bar across all resolutions; the dashboard
    # cares about "most recent price we have," not which resolution.
    sym_to_price: dict[str, tuple[float, datetime]] = {}
    if rows:
        symbols = {pos.symbol for pos in rows}
        for sym in symbols:
            latest = db.execute(
                select(IntradayBar)
                .where(IntradayBar.symbol == sym)
                .order_by(desc(IntradayBar.bar_time))
                .limit(1)
            ).scalar_one_or_none()
            if latest:
                sym_to_price[sym] = (float(latest.close), latest.bar_time)

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

    # Active-execution eligibility: a tracked position only makes sense
    # when the strategy has an exit ladder + a non-daily resolution.
    sj = strategy.strategy_json or {}
    bar_resolution = sj.get("bar_resolution", "daily")
    has_ladder = bool(
        (sj.get("risk_management") or {}).get("exit_ladder")
    )
    if bar_resolution == "daily" or not has_ladder:
        raise HTTPException(
            status_code=400,
            detail=(
                "This strategy isn't set up for active execution. Enable "
                "Active Execution (a non-daily bar resolution + an exit "
                "ladder) on the strategy before declaring a tracked position."
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
