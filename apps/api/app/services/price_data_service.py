from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.concurrency import SingleFlight
from app.models.data_fetch_log import DataFetchLog
from app.models.price_bar import PriceBar
from app.schemas.market_data import DataStatusResponse
from app.services.alpha_vantage import AlphaVantageClient
from app.services.price_cache_service import PriceCacheService

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# `ensure_history` only refetches a symbol once its newest bar is three to four
# days old: right for a universe of thousands, wrong for the one stock a person
# is looking at. On 2026-11-25 at 12:58 ET the newest bar for NVDA, AAPL, MSFT,
# SPY and REGN was Monday the 23rd, while the provider already had Tuesday's
# close: NVDA's chart ended at $165.05 with the stock at $145.72.
#
# A top-up asks for the provider's last 100 days, not the whole history. One is
# shared by everyone waiting on the symbol, and a symbol is not asked for again
# for ten minutes: on a market holiday, and in the minutes after a close before
# the provider has published it, no request can bring the symbol up to date.
_TOP_UP_EVERY_SECONDS = 600.0
# The provider's short answer is its last 100 trading days, about 145 on the
# calendar. A symbol further behind than this needs the whole history.
_TOP_UP_REACH_DAYS = 120
_top_up_attempts: Dict[str, float] = {}
_top_ups = SingleFlight()


def _now() -> float:
    return time.monotonic()


def last_completed_session(now: Optional[datetime] = None) -> date:
    """The most recent weekday whose 4 pm New York close has passed.

    Market holidays are not known here, so on one this names a day that has
    no bar. That costs one short request per symbol every ten minutes while
    someone is looking, and nothing else.
    """
    at = (now or datetime.now(_ET)).astimezone(_ET)
    day = at.date() if at.hour >= 16 else at.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


class PriceDataService:
    def __init__(self) -> None:
        self.cache_svc = PriceCacheService(AlphaVantageClient())

    async def ensure_last_close(self, db: Session, symbol: str) -> None:
        """Bring a symbol that already has history up to the last completed close.

        Never raises: when the provider cannot be reached, what is cached is
        served. A symbol with no bars at all is `ensure_history`'s job.
        """
        sym = symbol.upper()
        try:
            await self._top_up_if_behind(db, sym)
        except Exception as exc:  # noqa: BLE001 — serve the cached bars
            # An httpx error's text holds the request URL, and with it the key.
            logger.info("top-up of %s failed: %s", sym, type(exc).__name__)

    async def _top_up_if_behind(self, db: Session, sym: str) -> None:
        cache_svc = self.cache_svc
        latest = cache_svc.get_latest_date(db, sym)
        expected = last_completed_session()
        if latest is None or latest >= expected:
            return

        key = ("top_up", sym)
        if not _top_ups.is_running(key):
            last = _top_up_attempts.get(sym)
            if last is not None and _now() - last < _TOP_UP_EVERY_SECONDS:
                return  # asked recently; serve what is cached
            # Stamped before the request, so one that hangs still counts.
            _top_up_attempts[sym] = _now()

        outputsize = "compact" if (expected - latest).days <= _TOP_UP_REACH_DAYS else "full"
        # The shared top-up outlives the request that started it, so it
        # writes through its own session on the caller's engine.
        bind = db.get_bind()

        async def top_up() -> None:
            own = sessionmaker(bind=bind, autoflush=False, autocommit=False, future=True)()
            try:
                await cache_svc.top_up(own, sym, through=expected, outputsize=outputsize)
            finally:
                own.close()

        await _top_ups.run(key, top_up)

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
        await self.cache_svc.ensure_history(db, symbol, fetch_from, required_through=end_date)

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
