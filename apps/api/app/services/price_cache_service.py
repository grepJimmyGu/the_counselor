from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.data_fetch_log import DataFetchLog
from app.models.price_bar import PriceBar
from app.services.alpha_vantage import AlphaVantageClient, AlphaVantageError, AlphaVantageRateLimitError


class PriceCacheService:
    def __init__(self, client: AlphaVantageClient) -> None:
        self.client = client
        self.settings = get_settings()

    def is_stale(self, latest_date: Optional[date], reference_date: date) -> bool:
        if latest_date is None:
            return True
        cutoff = date.today() - timedelta(days=self.settings.price_cache_stale_hours // 24 + 3)
        return latest_date < min(reference_date, cutoff)

    def get_latest_date(self, db: Session, symbol: str) -> Optional[date]:
        return db.scalar(
            select(PriceBar.trading_date)
            .where(PriceBar.symbol == symbol)
            .order_by(desc(PriceBar.trading_date))
            .limit(1)
        )

    def get_earliest_date(self, db: Session, symbol: str) -> Optional[date]:
        return db.scalar(
            select(PriceBar.trading_date)
            .where(PriceBar.symbol == symbol)
            .order_by(PriceBar.trading_date.asc())
            .limit(1)
        )

    def get_bar_count(self, db: Session, symbol: str) -> int:
        from sqlalchemy import func
        return db.scalar(
            select(func.count()).select_from(PriceBar).where(PriceBar.symbol == symbol)
        ) or 0

    async def ensure_history(
        self,
        db: Session,
        symbol: str,
        required_from: date,
    ) -> None:
        """
        Fetches TIME_SERIES_DAILY_ADJUSTED (full) if cache is stale relative to required_from.
        Uses INSERT OR IGNORE / ON CONFLICT DO NOTHING — never deletes existing rows.
        """
        latest = self.get_latest_date(db, symbol)
        earliest = self.get_earliest_date(db, symbol)

        # Fresh if: latest is recent AND earliest covers the required lookback
        not_stale = not self.is_stale(latest, date.today())
        has_lookback = earliest is not None and earliest <= required_from
        if not_stale and has_lookback:
            return

        start_ms = time.monotonic()
        fetch_status = "success"
        error_msg: Optional[str] = None
        bars_upserted = 0

        try:
            bars = await self.client.fetch_daily_adjusted(symbol, outputsize="full")
            bars_upserted = self._upsert_bars(db, symbol, bars)
            db.commit()
        except AlphaVantageRateLimitError as exc:
            fetch_status = "rate_limited"
            error_msg = str(exc)
            db.rollback()
            raise
        except AlphaVantageError as exc:
            fetch_status = "error"
            error_msg = str(exc)
            db.rollback()
            raise
        finally:
            duration_ms = int((time.monotonic() - start_ms) * 1000)
            self._log(db, symbol, fetch_status, bars_upserted, error_msg, duration_ms)

    def _upsert_bars(self, db: Session, symbol: str, bars: list[dict]) -> int:
        if not bars:
            return 0

        is_sqlite = db.bind.dialect.name == "sqlite"  # type: ignore[union-attr]
        fetched_at = datetime.utcnow()
        rows = [
            {
                "symbol": bar["symbol"],
                "trading_date": bar["trading_date"],
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "adjusted_close": bar["adjusted_close"],
                "volume": bar["volume"],
                "dividend_amount": bar.get("dividend_amount", 0.0),
                "split_coefficient": bar.get("split_coefficient", 1.0),
                "source": "alpha_vantage",
                "fetched_at": fetched_at,
            }
            for bar in bars
        ]

        if is_sqlite:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(PriceBar).prefix_with("OR IGNORE").values(rows)
        else:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = (
                pg_insert(PriceBar)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["symbol", "trading_date"])
            )

        result = db.execute(stmt)
        return result.rowcount if result.rowcount >= 0 else len(rows)

    def _log(
        self,
        db: Session,
        symbol: str,
        status: str,
        bars_upserted: int,
        error_message: Optional[str],
        duration_ms: int,
    ) -> None:
        try:
            db.add(
                DataFetchLog(
                    symbol=symbol,
                    fetch_type="daily_full",
                    status=status,
                    bars_upserted=bars_upserted,
                    error_message=error_message,
                    duration_ms=duration_ms,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
