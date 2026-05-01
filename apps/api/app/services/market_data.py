from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.price_bar import PriceBar
from app.models.symbol import SymbolCache
from app.schemas.market_data import PriceBarResponse, SymbolSearchItem
from app.services.alpha_vantage import AlphaVantageClient


class MarketDataService:
    def __init__(self) -> None:
        self.client = AlphaVantageClient()
        self.settings = get_settings()

    def _is_stale(self, latest_date: Optional[date], requested_end_date: date) -> bool:
        if latest_date is None:
            return True
        freshness_cutoff = date.today() - timedelta(days=self.settings.price_cache_stale_hours // 24 + 3)
        return latest_date < min(requested_end_date, freshness_cutoff)

    async def ensure_daily_history(self, db: Session, symbol: str, end_date: date) -> None:
        latest_bar = db.scalar(
            select(PriceBar.trading_date)
            .where(PriceBar.symbol == symbol)
            .order_by(desc(PriceBar.trading_date))
            .limit(1)
        )
        if not self._is_stale(latest_bar, end_date):
            return

        bars = await self.client.fetch_daily_adjusted(symbol)
        if not bars:
            return

        db.execute(delete(PriceBar).where(PriceBar.symbol == symbol))
        fetched_at = datetime.utcnow()
        db.add_all(
            [
                PriceBar(**bar, source="alpha_vantage", fetched_at=fetched_at)
                for bar in bars
            ]
        )
        db.commit()

    async def get_price_frame(self, db: Session, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        await self.ensure_daily_history(db, symbol, end_date)
        rows = db.execute(
            select(PriceBar)
            .where(PriceBar.symbol == symbol)
            .where(PriceBar.trading_date >= start_date)
            .where(PriceBar.trading_date <= end_date)
            .order_by(PriceBar.trading_date.asc())
        ).scalars()
        frame = pd.DataFrame(
            [
                {
                    "date": row.trading_date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "adjusted_close": row.adjusted_close,
                    "volume": row.volume,
                }
                for row in rows
            ]
        )
        if frame.empty:
            return frame
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.set_index("date").sort_index()
        return frame

    async def search_symbols(self, db: Session, query: str) -> list[SymbolSearchItem]:
        local_matches = db.execute(
            select(SymbolCache)
            .where(SymbolCache.symbol.ilike(f"%{query.upper()}%") | SymbolCache.name.ilike(f"%{query}%"))
            .limit(10)
        ).scalars()
        cached = [
            SymbolSearchItem(
                symbol=item.symbol,
                name=item.name,
                region=item.region,
                currency=item.currency,
                instrument_type=item.instrument_type,
            )
            for item in local_matches
        ]
        if cached:
            return cached

        remote_matches = await self.client.search_symbols(query)
        for match in remote_matches:
            db.merge(
                SymbolCache(
                    symbol=match["symbol"],
                    name=match["name"],
                    region=match.get("region"),
                    currency=match.get("currency"),
                    instrument_type=match.get("instrument_type"),
                )
            )
        db.commit()
        return [SymbolSearchItem(**match) for match in remote_matches]

    async def get_cached_bars(self, db: Session, symbol: str, end_date: date) -> list[PriceBarResponse]:
        await self.ensure_daily_history(db, symbol, end_date)
        rows = db.execute(
            select(PriceBar).where(PriceBar.symbol == symbol).order_by(PriceBar.trading_date.asc())
        ).scalars()
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
