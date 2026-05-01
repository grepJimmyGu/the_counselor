from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.data_fetch_log import DataFetchLog
from app.models.price_bar import PriceBar
from app.schemas.market_data import DataStatusResponse
from app.services.alpha_vantage import AlphaVantageClient
from app.services.price_cache_service import PriceCacheService


class PriceDataService:
    def __init__(self) -> None:
        self.cache_svc = PriceCacheService(AlphaVantageClient())

    async def get_price_frame(
        self,
        db: Session,
        symbol: str,
        start_date: date,
        end_date: date,
        lookback_days: int = 0,
    ) -> pd.DataFrame:
        """
        Returns a DataFrame indexed by datetime, columns: open/high/low/close/adjusted_close/volume.
        Spans [start_date - lookback_days - buffer, end_date] so indicators computed on
        start_date have the full warmup window. Callers that need only [start_date, end_date]
        should slice themselves after computing any indicators.
        """
        symbol = symbol.upper()
        fetch_from = start_date - timedelta(days=lookback_days + 10)
        await self.cache_svc.ensure_history(db, symbol, fetch_from)

        rows = db.execute(
            select(PriceBar)
            .where(PriceBar.symbol == symbol)
            .where(PriceBar.trading_date >= fetch_from)
            .where(PriceBar.trading_date <= end_date)
            .order_by(PriceBar.trading_date.asc())
        ).scalars().all()

        if not rows:
            return pd.DataFrame()

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
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.set_index("date").sort_index()

    async def get_status(self, db: Session, symbol: str) -> DataStatusResponse:
        symbol = symbol.upper()
        bar_count = self.cache_svc.get_bar_count(db, symbol)
        earliest = self.cache_svc.get_earliest_date(db, symbol)
        latest = self.cache_svc.get_latest_date(db, symbol)
        stale = self.cache_svc.is_stale(latest, date.today())

        last_log = db.execute(
            select(DataFetchLog)
            .where(DataFetchLog.symbol == symbol)
            .order_by(desc(DataFetchLog.fetched_at))
            .limit(1)
        ).scalar_one_or_none()

        return DataStatusResponse(
            symbol=symbol,
            bar_count=bar_count,
            earliest_date=earliest,
            latest_date=latest,
            is_stale=stale,
            last_fetch_status=last_log.status if last_log else None,
            last_fetched_at=last_log.fetched_at if last_log else None,
        )
