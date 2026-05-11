from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.symbol import SymbolCache
from app.schemas.screener import (
    ScreenerFilters,
    ScreenerFiltersResponse,
    ScreenerResponse,
    ScreenerResult,
)

_VALID_SORT_COLUMNS = {
    "symbol", "name", "sector", "market_cap", "pe_ratio", "dividend_yield", "beta",
}
_CAP_CATEGORIES = ["mega", "large", "mid", "small", "micro"]


class ScreenerService:
    def get_filters(self, db: Session) -> ScreenerFiltersResponse:
        def _distinct(col):
            rows = db.execute(
                select(col).where(col.isnot(None)).distinct().order_by(col)
            ).scalars().all()
            return [r for r in rows if r and r.strip()]

        total = db.scalar(select(func.count()).select_from(SymbolCache)) or 0
        return ScreenerFiltersResponse(
            sectors=_distinct(SymbolCache.sector),
            industries=_distinct(SymbolCache.industry),
            countries=_distinct(SymbolCache.country),
            exchanges=_distinct(SymbolCache.exchange),
            market_cap_categories=_CAP_CATEGORIES,
            total_symbols=total,
        )

    def screen(self, db: Session, filters: ScreenerFilters) -> ScreenerResponse:
        q = select(SymbolCache).where(SymbolCache.is_active.is_(True))

        if filters.sector:
            q = q.where(SymbolCache.sector == filters.sector)
        if filters.industry:
            q = q.where(SymbolCache.industry == filters.industry)
        if filters.country:
            q = q.where(SymbolCache.country == filters.country)
        if filters.exchange:
            q = q.where(SymbolCache.exchange == filters.exchange)
        if filters.market_cap_category:
            q = q.where(SymbolCache.market_cap_category == filters.market_cap_category)
        if filters.min_market_cap is not None:
            q = q.where(SymbolCache.market_cap >= filters.min_market_cap)
        if filters.max_market_cap is not None:
            q = q.where(SymbolCache.market_cap <= filters.max_market_cap)
        if filters.min_pe is not None:
            q = q.where(SymbolCache.pe_ratio >= filters.min_pe)
        if filters.max_pe is not None:
            q = q.where(SymbolCache.pe_ratio <= filters.max_pe)
        if filters.min_dividend_yield is not None:
            q = q.where(SymbolCache.dividend_yield >= filters.min_dividend_yield)

        # Count total before pagination
        count_q = select(func.count()).select_from(q.subquery())
        total = db.scalar(count_q) or 0

        # Sort
        sort_col_name = filters.sort_by if filters.sort_by in _VALID_SORT_COLUMNS else "market_cap"
        sort_col = getattr(SymbolCache, sort_col_name, SymbolCache.market_cap)
        if filters.sort_order == "asc":
            q = q.order_by(sort_col.asc().nulls_last())
        else:
            q = q.order_by(sort_col.desc().nulls_last())

        q = q.offset(filters.offset).limit(filters.limit)
        rows = db.execute(q).scalars().all()

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
            offset=filters.offset,
            limit=filters.limit,
            filters_applied={k: v for k, v in filters.model_dump().items() if v is not None},
        )
