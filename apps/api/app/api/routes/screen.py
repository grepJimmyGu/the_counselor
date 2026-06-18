"""Market Screener — scan/count endpoints (PRD-23a §3.5-3.6).

`POST /api/screen/scan`  — a composed reading + a universe -> matched basket
                           + per-symbol satisfied readings.
`POST /api/screen/count` — the same filter, count only (the live funnel).

Both are pure reads over the pre-warmed `signal_snapshot` — no backtest (the
rank step is PRD-23a slice 5). `allow_anonymous=True` so the mode is
explorable pre-sign-in (trap #18); the expensive rank-by-backtest is the
sign-in-gated step.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from app.api.entitlement_errors import upgrade_error
from app.data.sp500_tickers import SP500_TICKERS
from app.db.session import get_db
from app.models.saved_strategy import SavedStrategy
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.symbol import SymbolCache
from app.schemas.screener_scan import (
    RankedSymbol,
    SavedScreenDetail,
    SavedScreenSummary,
    SavedScreensListResponse,
    ScreenBasketEntry,
    ScreenCountResponse,
    ScreenRankRequest,
    ScreenRankResponse,
    ScreenSaveRequest,
    ScreenSaveResponse,
    ScreenScanRequest,
    ScreenScanResponse,
)
from app.schemas.strategy import StrategyRule
from app.services.saved_strategy_service import SaveStrategyRequest, save_strategy
from app.services.screener.rank_service import rank_service
from app.services.screener.saved_screen_service import (
    current_basket,
    is_screen,
    list_user_screens,
    rescan_and_diff,
    screen_history,
    screen_strategy_json,
)
from app.services.screener.scan_service import scan
from app.services.screener.signal_snapshot_service import SignalSnapshotService

logger = logging.getLogger("livermore.screener.api")

router = APIRouter(prefix="/api/screen", tags=["screener"])

# Snapshot columns used (in order of preference) as the cheap-proxy pre-order
# for the rank top-K cap, so a loose rule keeps the highest-momentum names
# rather than an alphabetical slice.
_PROXY_PRIMITIVES = ("time_series_momentum", "roc", "mom", "rank_return_6m")


def _momentum_proxy(db: Session, symbols: List[str]):
    """{symbol -> momentum score} from the snapshot's first available momentum
    column, for the rank top-K pre-order. None if the snapshot has no such
    column for these symbols (rank then falls back to scan order)."""
    if not symbols:
        return None
    frame = SignalSnapshotService().get_snapshot(db, symbols).frame
    for col in _PROXY_PRIMITIVES:
        if col in frame.columns:
            return {
                str(sym): float(val)
                for sym, val in frame[col].items()
                if val == val  # drop NaN
            }
    return None


def _db_sector_membership(db: Session):
    """sector_<key> membership from SymbolCache.sector, intersected with the
    S&P 500 standard (expand-only + snapshot coverage). v1 matches the sector
    string the client sends; sector-label normalization is a follow-up."""

    def lookup(key: str) -> List[str]:
        rows = (
            db.execute(
                select(SymbolCache.symbol).where(
                    func.lower(SymbolCache.sector) == key.lower()
                )
            )
            .scalars()
            .all()
        )
        return [s for s in rows if s in SP500_TICKERS]

    return lookup


@router.post("/scan", response_model=ScreenScanResponse)
async def screen_scan(
    payload: ScreenScanRequest,
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=True, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> ScreenScanResponse:
    result = scan(
        db,
        payload.universe_id,
        payload.rules,
        symbols=payload.symbols,
        sector_membership=_db_sector_membership(db),
    )
    return ScreenScanResponse(
        matched=result.matched,
        readings=result.readings,
        as_of_date=result.as_of_date,
        universe_size=result.universe_size,
        matched_count=result.matched_count,
        unsupported_primitives=result.unsupported_primitives,
        default_param_primitives=result.default_param_primitives,
    )


@router.post("/count", response_model=ScreenCountResponse)
async def screen_count(
    payload: ScreenScanRequest,
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=True, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> ScreenCountResponse:
    result = scan(
        db,
        payload.universe_id,
        payload.rules,
        symbols=payload.symbols,
        sector_membership=_db_sector_membership(db),
    )
    return ScreenCountResponse(
        matched_count=result.matched_count,
        universe_size=result.universe_size,
        as_of_date=result.as_of_date,
        unsupported_primitives=result.unsupported_primitives,
        default_param_primitives=result.default_param_primitives,
    )


@router.post("/rank", response_model=ScreenRankResponse)
async def screen_rank(
    payload: ScreenRankRequest,
    auth: tuple = Depends(
        # The expensive step — backtests the matched subset. Sign-in-gated
        # (§3.6); the scan/count above stay anonymous-explorable.
        require_entitlement(needs_run_quota=False, allow_anonymous=False, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> ScreenRankResponse:
    result = scan(
        db,
        payload.universe_id,
        payload.rules,
        symbols=payload.symbols,
        sector_membership=_db_sector_membership(db),
    )
    # NOTE (backlog — trap #13 / quota): rank backtests the matched subset
    # sequentially while holding this request `db`; on a cold-cache symbol each
    # run can await an AV fetch with the conn checked out. Bounded today by
    # sign-in gating + top_k<=200 + the warm-cache short-circuit, but a
    # fresh-SessionLocal-per-backtest + a per-tier run quota are tracked in
    # PROJECT_BACKLOG before this is heavily trafficked.
    rank_result = await rank_service.rank(
        db,
        result.matched,
        payload.strategy,
        as_of_date=result.as_of_date,
        top_k=payload.top_k,
        proxy_scores=_momentum_proxy(db, result.matched),
    )
    return ScreenRankResponse(
        ranked=[
            RankedSymbol(
                symbol=e.symbol,
                total_return=e.total_return,
                annualized_return=e.annualized_return,
                sharpe_ratio=e.sharpe_ratio,
                readings=result.readings.get(e.symbol, []),
            )
            for e in rank_result.ranked
        ],
        as_of_date=rank_result.as_of_date,
        matched_count=rank_result.matched_count,
        backtested_count=rank_result.backtested_count,
        dropped_count=rank_result.dropped_count,
        universe_size=result.universe_size,
        unsupported_primitives=result.unsupported_primitives,
        default_param_primitives=result.default_param_primitives,
    )


@router.post("/save", response_model=ScreenSaveResponse)
async def screen_save(
    payload: ScreenSaveRequest,
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=False, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> ScreenSaveResponse:
    """Persist a standing screen + start tracking it (PRD-23c §3.1).

    The screen is a `SavedStrategy` (kind="screen"); a `SignalAlertSubscription`
    wires it into the `monitor_saved_screens` cron, which notifies on each NEW
    basket entrant. Tier-gated Strategist+ (standing-screen tracking is a paid
    feature). The initial basket is seeded SILENTLY here so the first cron tick
    doesn't fire a "new entrant" alert for every current match.
    """
    user, ent = auth
    # Snapshot ORM-bound scalars before any commit expires them (trap #17).
    user_id: str = user.id
    tier: str = ent.tier

    if tier not in ("strategist", "quant"):
        raise upgrade_error(
            "screen_tracking_locked",
            current_tier=tier,
            current_value=tier,
            limit_value="strategist",
        )
    # Intraday screening is Quant-only — the universe-wide intraday warm is the
    # top-tier perk (PRD-23c PR3).
    if payload.bar_resolution == "intraday" and tier != "quant":
        raise upgrade_error(
            "screen_tracking_locked",
            current_tier=tier,
            current_value="intraday",
            limit_value="quant",
            required_tier_override="quant",
        )

    sj = screen_strategy_json(payload.universe_id, payload.rules, payload.bar_resolution)
    # save_strategy enforces the per-tier saved-strategy cap + commits.
    saved = save_strategy(
        db,
        user,
        SaveStrategyRequest(title=payload.title, strategy_json=sj, is_public=False),
    )
    saved_id: str = saved.id

    # Subscribe so the cron tracks it + dispatches new-entrant alerts.
    db.add(
        SignalAlertSubscription(
            user_id=user_id, saved_strategy_id=saved_id, email_enabled=True
        )
    )
    db.commit()

    # Seed the initial basket (writes members; no dispatch happens here).
    diff = rescan_and_diff(db, db.get(SavedStrategy, saved_id))
    return ScreenSaveResponse(
        saved_strategy_id=saved_id,
        basket=diff.basket,
        as_of_date=diff.as_of_date,
        universe_size=diff.universe_size,
    )


@router.get("/saved", response_model=SavedScreensListResponse)
async def list_saved_screens(
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=False, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> SavedScreensListResponse:
    """The signed-in user's tracked screens (PRD-23c §3.3)."""
    user, _ = auth
    summaries = [
        SavedScreenSummary(
            saved_strategy_id=s.id,
            title=s.title,
            universe_id=(s.strategy_json or {}).get("universe_id", ""),
            basket_size=len(current_basket(db, s.id)),
            created_at=s.created_at.isoformat() if s.created_at else None,
        )
        for s in list_user_screens(db, user.id)
    ]
    return SavedScreensListResponse(screens=summaries)


@router.get("/saved/{saved_strategy_id}", response_model=SavedScreenDetail)
async def get_saved_screen(
    saved_strategy_id: str,
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=False, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> SavedScreenDetail:
    """A tracked screen's current basket + entrant/exit history (PRD-23c §3.3).
    Owner-gated: a non-owner (or a non-screen id) gets 404, so existence never
    leaks."""
    user, _ = auth
    saved = db.get(SavedStrategy, saved_strategy_id)
    if saved is None or saved.user_id != user.id or not is_screen(saved):
        raise HTTPException(status_code=404, detail="Saved screen not found")

    sj = saved.strategy_json or {}
    members = current_basket(db, saved.id)
    return SavedScreenDetail(
        saved_strategy_id=saved.id,
        title=saved.title,
        universe_id=sj.get("universe_id", ""),
        basket_size=len(members),
        created_at=saved.created_at.isoformat() if saved.created_at else None,
        rules=[StrategyRule.model_validate(r) for r in sj.get("rules", [])],
        basket=sorted(m.symbol for m in members),
        history=[
            ScreenBasketEntry(
                symbol=m.symbol,
                entered_date=m.entered_date,
                exited_date=m.exited_date,
                is_current=m.exited_date is None,
            )
            for m in screen_history(db, saved.id)
        ],
    )
