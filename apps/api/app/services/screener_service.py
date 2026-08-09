from __future__ import annotations

from typing import List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.screen_filter_vocab import sector_spellings
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

    # ── PRD-29: symbols-only lookup for the mixed search path ───────────────

    def by_symbols(self, db: Session, symbols: Sequence[str]) -> List[ScreenerResult]:
        """Fundamentals for an explicit symbol list.

        `screen()` answers "which names match these filters"; this answers
        "what are the numbers for these names". The results page needs the
        second: its symbol list comes from a technical scan, so there are no
        filters to re-run — and re-deriving them would risk returning a
        DIFFERENT set than the one on screen.

        One indexed query. Order follows the caller's list rather than the
        DB's, so the table keeps whatever ranking the user applied.
        """
        wanted = [s.upper() for s in symbols]
        if not wanted:
            return []
        rows = db.scalars(
            select(SymbolCache).where(SymbolCache.symbol.in_(wanted))
        ).all()
        by_sym = {r.symbol.upper(): r for r in rows}
        out: List[ScreenerResult] = []
        for sym in wanted:
            r = by_sym.get(sym)
            if r is None:
                continue  # unknown ticker — omitted, never a blank row
            out.append(
                ScreenerResult(
                    symbol=r.symbol,
                    name=r.name or r.symbol,
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
            )
        return out

    def matching_symbols(
        self,
        db: Session,
        filters: ScreenerFilters,
        cap: int = 1500,
    ) -> Tuple[List[str], int]:
        """Every symbol matching the fundamental filters — no display paging.

        Returns `(symbols, total_matched)`. When `total_matched > len(symbols)`
        the caller MUST tell the user the universe was capped; silently
        truncating a screen reads as "these are all the matches" when it isn't.

        Why not reuse `screen()`: its `ScreenerFilters.limit` is a *display*
        page size hard-capped at 200 (`schemas/screener.py`). Feeding that into
        a technical scan would quietly screen 200 of, say, 800 small caps.

        Sector matching uses IN over every stored spelling, not `==`. Production
        holds 17 spellings for 11 sectors (two upstream taxonomies), so equality
        on one spelling drops the companies stored under the other — see
        `app/data/screen_filter_vocab.py`.
        """
        q = select(SymbolCache.symbol).where(SymbolCache.is_active.is_(True))

        if filters.sector:
            spellings = sector_spellings(filters.sector)
            if spellings:
                q = q.where(SymbolCache.sector.in_(spellings))
            else:
                # Not a canonical key (e.g. a raw value from the /stocks
                # dropdown) — fall back to exact match rather than dropping
                # the constraint entirely.
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

        total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
        # Largest first, so a capped universe keeps the most liquid names
        # rather than an arbitrary slice.
        q = q.order_by(SymbolCache.market_cap.desc().nulls_last()).limit(cap)
        symbols = [s for s in db.execute(q).scalars().all() if s]
        return symbols, total
