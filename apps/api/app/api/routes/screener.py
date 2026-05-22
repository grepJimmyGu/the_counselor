from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.entitlement_errors import upgrade_error
from app.api.deps import get_current_user_or_anonymous
from app.db.session import get_db
from app.models.user import User
from app.schemas.screener import (
    ScreenerFilters,
    ScreenerFiltersResponse,
    ScreenerResponse,
    ScreenerResult,
)
from app.services.screener_presets import (
    PRESETS,
    PresetSpec,
    all_presets,
    get_preset,
)
from app.services.screener_service import ScreenerService

router = APIRouter(prefix="/api/screener", tags=["screener"])
_service = ScreenerService()


@router.get("/filters", response_model=ScreenerFiltersResponse)
def get_screener_filters(db: Session = Depends(get_db)) -> ScreenerFiltersResponse:
    """Return all unique filter options (sectors, industries, countries, exchanges)."""
    return _service.get_filters(db)


@router.get("/results", response_model=ScreenerResponse)
def get_screener_results(
    sector: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    exchange: Optional[str] = Query(default=None),
    market_cap_category: Optional[str] = Query(default=None),
    min_market_cap: Optional[float] = Query(default=None),
    max_market_cap: Optional[float] = Query(default=None),
    min_pe: Optional[float] = Query(default=None),
    max_pe: Optional[float] = Query(default=None),
    min_dividend_yield: Optional[float] = Query(default=None),
    sort_by: str = Query(default="market_cap"),
    sort_order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ScreenerResponse:
    """Screen stocks by fundamental filters. Results come from the seeded symbols table."""
    filters = ScreenerFilters(
        sector=sector, industry=industry, country=country, exchange=exchange,
        market_cap_category=market_cap_category, min_market_cap=min_market_cap,
        max_market_cap=max_market_cap, min_pe=min_pe, max_pe=max_pe,
        min_dividend_yield=min_dividend_yield, sort_by=sort_by,
        sort_order=sort_order, limit=limit, offset=offset,
    )
    return _service.screen(db, filters)


# ── Phase 1f: preset screens ─────────────────────────────────────────────────


_TIER_ORDER = {"scout": 0, "strategist": 1, "quant": 2}


def _user_tier(user: User) -> str:
    """Return the user's tier as a string. Defaults to 'scout' for users
    in a healed orphan-Plan state (already handled by sync_user, but be
    defensive here too)."""
    if user.plan is None:
        return "scout"
    return user.plan.tier or "scout"


def _serialize_preset_meta(p: PresetSpec, total: int, sample_tickers: list[str]) -> dict:
    return {
        "slug": p.slug,
        "title": p.title,
        "description": p.description,
        "icon": p.icon,
        "tier": p.tier,
        "result_count": total,
        "sample_tickers": sample_tickers,
    }


@router.get("/presets")
def get_screener_presets_summary(db: Session = Depends(get_db)) -> dict:
    """Return metadata + real result counts + top-5 sample tickers for
    each of the 9 presets. Consumed by the Market Pulse Screener.tsx
    tile grid; no gating at the metadata level (the UI uses `tier` to
    render the lock badge; the per-preset results endpoint enforces).
    """
    out: list[dict] = []
    for p in all_presets():
        try:
            base_q = p.build_query(db)
            total = db.scalar(select(func.count()).select_from(base_q.subquery())) or 0
            top5 = db.execute(base_q.limit(5)).scalars().all()
            sample_tickers = [r.symbol for r in top5]
        except Exception:
            total = 0
            sample_tickers = []
        out.append(_serialize_preset_meta(p, total, sample_tickers))
    return {"presets": out}


@router.get("/preset/{slug}", response_model=ScreenerResponse)
def get_screener_preset_results(
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_or_anonymous),
) -> ScreenerResponse:
    """Return paginated results for a specific preset. Strategist /
    Quant presets enforce tier via a 402 envelope (consumed by the
    existing global SoftPaywall modal in the frontend)."""
    preset = get_preset(slug)
    if preset is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown preset slug: {slug}",
        )

    user_tier = _user_tier(user)
    if _TIER_ORDER[user_tier] < _TIER_ORDER[preset.tier]:
        # Anonymous detection: get_current_user_or_anonymous returns
        # the synthetic legacy-anon user (id="legacy-anon-0000") when
        # there's no valid bearer token. The 402 envelope routes those
        # users to signup instead of upgrade.
        is_anon = getattr(user, "id", None) == "legacy-anon-0000"
        raise upgrade_error(
            "screener_preset_locked",
            current_tier=user_tier,
            is_anonymous=is_anon,
            required_tier_override=preset.tier,  # type: ignore[arg-type]
            current_value=preset.title,
            limit_value=preset.tier,
        )

    base_q = preset.build_query(db)
    total = db.scalar(select(func.count()).select_from(base_q.subquery())) or 0
    rows = db.execute(base_q.offset(offset).limit(limit)).scalars().all()

    return ScreenerResponse(
        results=[
            ScreenerResult(
                symbol=r.symbol,
                name=r.name,
                sector=r.sector,
                industry=r.industry,
                exchange=r.exchange,
                country=r.country,
                market_cap=r.market_cap,
                market_cap_category=r.market_cap_category,
                pe_ratio=r.pe_ratio,
                dividend_yield=r.dividend_yield,
                beta=r.beta,
                week_52_high=r.week_52_high,
                week_52_low=r.week_52_low,
            )
            for r in rows
        ],
        total=total,
        offset=offset,
        limit=limit,
        filters_applied={"preset": slug, "tier_required": preset.tier},
    )
