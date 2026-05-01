from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.price_bar import PriceBar
from app.schemas.market_data import PriceBarResponse, SymbolSearchItem
from app.services.alpha_vantage import AlphaVantageClient
from app.services.price_data_service import PriceDataService
from app.services.symbol_service import SymbolService


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

    async def search_symbols(self, db: Session, query: str) -> list[SymbolSearchItem]:
        return await self._symbol_svc.search(db, query)

    async def get_cached_bars(self, db: Session, symbol: str, end_date: date) -> list[PriceBarResponse]:
        await self._price_data.cache_svc.ensure_history(db, symbol.upper(), end_date)
        rows = db.execute(
            select(PriceBar)
            .where(PriceBar.symbol == symbol.upper())
            .order_by(PriceBar.trading_date.asc())
        ).scalars().all()
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
