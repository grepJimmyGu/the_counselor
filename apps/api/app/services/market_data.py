from __future__ import annotations

import time
from datetime import date
from typing import Dict, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.concurrency import SingleFlight
from app.core.config import get_settings
from app.models.price_bar import PriceBar
from app.schemas.market_data import PriceBarResponse, SymbolSearchItem
from app.services.alpha_vantage import AlphaVantageClient
from app.services.price_data_service import PriceDataService
from app.services.symbol_service import SymbolService

# A forced refresh downloads a symbol's whole daily history and writes
# thousands of rows. It used to run inside every request that found the
# symbol more than three days behind, with nothing shared: on 2026-11-20 six
# simultaneous watchlist loads with four such symbols took 39 s in production
# and held the health check up for 3 s, each request repeating the same four
# downloads. Now one refresh per symbol is shared by everyone waiting on it,
# and a symbol is not tried again for ten minutes. The second part matters on
# the first trading day after a long weekend, when every symbol is "more than
# three days behind" all day and no refresh can change that until the close.
_DISPLAY_REFRESH_EVERY_SECONDS = 600.0
_display_refresh_attempts: Dict[str, float] = {}
_display_refreshes = SingleFlight()


def _now() -> float:
    return time.monotonic()


class MarketDataService:
    """
    Thin facade kept for backward compatibility with the backtest engine and existing routes.
    New code should call PriceDataService and SymbolService directly.
    """

    def __init__(self) -> None:
        self.client = AlphaVantageClient()
        self.settings = get_settings()
        self._price_data = PriceDataService()
        self._symbol_svc = SymbolService(self.client)

    def _is_stale(self, latest_date: Optional[date], requested_end_date: date) -> bool:
        return self._price_data.cache_svc.is_stale(latest_date, requested_end_date)

    async def ensure_daily_history(self, db: Session, symbol: str, end_date: date) -> None:
        await self._price_data.cache_svc.ensure_history(db, symbol.upper(), end_date)

    async def ensure_display_fresh(self, db: Session, symbol: str) -> None:
        """Force a refresh when the cached bar is more than 2 business days behind today.
        Used by the homepage market overview where display freshness matters more than
        avoiding extra API calls. Falls back gracefully if the fetch fails."""
        sym = symbol.upper()
        cache_svc = self._price_data.cache_svc
        latest = cache_svc.get_latest_date(db, sym)
        today = date.today()
        # Allow up to 3 calendar days stale (covers Mon showing Fri close).
        # More than 3 days stale means we've missed at least one trading day.
        if latest is not None and (today - latest).days <= 3:
            return

        key = ("display", sym)
        if not _display_refreshes.is_running(key):
            last = _display_refresh_attempts.get(sym)
            if last is not None and _now() - last < _DISPLAY_REFRESH_EVERY_SECONDS:
                return  # tried recently; serve what is cached
            _display_refresh_attempts[sym] = _now()

        # The shared refresh outlives the request that started it, so it
        # writes through its own session on the caller's engine.
        bind = db.get_bind()

        async def refresh() -> None:
            own = sessionmaker(bind=bind, autoflush=False, autocommit=False, future=True)()
            try:
                await cache_svc.ensure_history(own, sym, today, force=True)
            finally:
                own.close()

        try:
            await _display_refreshes.run(key, refresh)
        except Exception:
            pass  # Serve cached data if refresh fails

    async def get_price_frame(
        self,
        db: Session,
        symbol: str,
        start_date: date,
        end_date: date,
        lookback_days: int = 0,
    ) -> pd.DataFrame:
        return await self._price_data.get_price_frame(
            db, symbol, start_date, end_date, lookback_days=lookback_days
        )

    async def ensure_last_close(self, db: Session, symbol: str) -> None:
        """Bring `symbol` up to the last completed close; never raises."""
        await self._price_data.ensure_last_close(db, symbol)

    async def search_symbols(self, db: Session, query: str) -> list[SymbolSearchItem]:
        return await self._symbol_svc.search(db, query)

    async def get_cached_bars(
        self, db: Session, symbol: str, end_date: date, start_date: Optional[date] = None,
    ) -> list[PriceBarResponse]:
        """Daily bars for a symbol, oldest first; from `start_date` on when
        one is given. A long-listed stock has 27 years of them (1.2 MB of
        JSON), and a phone chart reads five."""
        await self._price_data.cache_svc.ensure_history(db, symbol.upper(), end_date)
        # A chart someone is looking at ends on the last completed close.
        await self._price_data.ensure_last_close(db, symbol)
        query = select(PriceBar).where(PriceBar.symbol == symbol.upper())
        if start_date is not None:
            query = query.where(PriceBar.trading_date >= start_date)
        rows = db.execute(query.order_by(PriceBar.trading_date.asc())).scalars().all()
        return [
            PriceBarResponse(
                symbol=row.symbol,
                trading_date=row.trading_date,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                adjusted_close=row.adjusted_close,
                volume=row.volume,
                dividend_amount=row.dividend_amount,
                split_coefficient=row.split_coefficient,
            )
            for row in rows
        ]
