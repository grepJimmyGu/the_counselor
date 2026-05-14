"""
PRD-trend: Company Price Trend Service
=======================================
Computes trend metrics from price_bars (Alpha Vantage data already in DB).

Metrics computed:
  - Latest price (adjusted close)
  - 1M / 3M / 6M / 12M price performance
  - 50-day and 200-day moving averages
  - Price vs MA50 / MA200 (% above or below)
  - Volume trend (20d avg vs 65d avg)
  - 90-day price sparkline
  - SPY relative performance (if SPY bars exist)

All lookbacks use trading days (not calendar days).
No FMP or AV API calls — reads entirely from the local price_bars table.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar

logger = logging.getLogger(__name__)

# Approximate trading day counts
_1M = 22
_3M = 63
_6M = 126
_12M = 252
_50D = 50
_200D = 200
_SPARKLINE = 90
_VOL_RECENT = 20
_VOL_HIST = 65


@dataclass
class TrendData:
    symbol: str
    latest_price: Optional[float] = None
    latest_date: Optional[date] = None

    # Performance
    perf_1m: Optional[float] = None
    perf_3m: Optional[float] = None
    perf_6m: Optional[float] = None
    perf_12m: Optional[float] = None

    # Moving averages
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None
    price_vs_ma50: Optional[float] = None    # e.g. 0.08 = 8% above MA50
    price_vs_ma200: Optional[float] = None

    # Volume
    vol_trend: Optional[str] = None          # "increasing" | "stable" | "decreasing"
    avg_vol_20d: Optional[float] = None
    avg_vol_65d: Optional[float] = None

    # Relative to SPY (benchmark)
    rs_vs_spy_3m: Optional[float] = None     # excess return over SPY (3M)
    rs_vs_spy_12m: Optional[float] = None

    # Sparkline: last 90 trading days [{date, price}]
    price_series_90d: list[dict] = field(default_factory=list)

    bar_count: int = 0


def _perf(current: float, past: Optional[float]) -> Optional[float]:
    if past is None or past == 0:
        return None
    return round((current / past) - 1, 6)


def _avg(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return sum(vals) / len(vals)


class CompanyTrendService:

    def get_trend(self, symbol: str, db: Session) -> TrendData:
        """
        Read the most recent 252 price bars from DB and compute all trend metrics.
        Returns a TrendData with whatever is available (bars < 200 → MA200 = None).
        """
        sym = symbol.upper()
        result = TrendData(symbol=sym)

        # Fetch last 252 bars (trading days) in descending order
        rows = (
            db.execute(
                select(PriceBar.trading_date, PriceBar.adjusted_close, PriceBar.volume)
                .where(PriceBar.symbol == sym)
                .order_by(desc(PriceBar.trading_date))
                .limit(_12M + 5)
            ).fetchall()
        )

        if not rows:
            return result

        result.bar_count = len(rows)

        # rows[0] = most recent; rows[-1] = oldest available in this window
        prices = [float(r[1]) for r in rows]   # adj_close, newest first
        vols   = [float(r[2]) for r in rows]
        dates  = [r[0] for r in rows]

        result.latest_price = prices[0]
        result.latest_date = dates[0]

        # Performance
        def _at(n: int) -> Optional[float]:
            return prices[n] if n < len(prices) else None

        result.perf_1m  = _perf(prices[0], _at(_1M))
        result.perf_3m  = _perf(prices[0], _at(_3M))
        result.perf_6m  = _perf(prices[0], _at(_6M))
        result.perf_12m = _perf(prices[0], _at(_12M))

        # Moving averages (need at least N bars)
        if len(prices) >= _50D:
            result.ma_50 = round(_avg(prices[:_50D]), 4)
            if result.ma_50:
                result.price_vs_ma50 = round(prices[0] / result.ma_50 - 1, 6)

        if len(prices) >= _200D:
            result.ma_200 = round(_avg(prices[:_200D]), 4)
            if result.ma_200:
                result.price_vs_ma200 = round(prices[0] / result.ma_200 - 1, 6)

        # Volume trend
        if len(vols) >= _VOL_HIST:
            avg_recent = _avg(vols[:_VOL_RECENT])
            avg_hist   = _avg(vols[:_VOL_HIST])
            if avg_recent and avg_hist and avg_hist > 0:
                result.avg_vol_20d = avg_recent
                result.avg_vol_65d = avg_hist
                ratio = avg_recent / avg_hist
                result.vol_trend = "increasing" if ratio > 1.1 else "decreasing" if ratio < 0.9 else "stable"

        # Sparkline: last 90 days in chronological order
        spark = rows[:_SPARKLINE]
        result.price_series_90d = [
            {"date": r[0].isoformat(), "price": float(r[1])}
            for r in reversed(spark)
        ]

        return result

    def get_relative_strength(
        self,
        symbol_trend: TrendData,
        db: Session,
        benchmark: str = "SPY",
    ) -> TrendData:
        """
        Enrich TrendData with relative performance vs benchmark (SPY).
        Modifies result in-place and returns it.
        """
        if symbol_trend.latest_price is None:
            return symbol_trend

        bench = self.get_trend(benchmark, db)
        if bench.perf_3m is not None and symbol_trend.perf_3m is not None:
            symbol_trend.rs_vs_spy_3m = round(
                symbol_trend.perf_3m - bench.perf_3m, 6
            )
        if bench.perf_12m is not None and symbol_trend.perf_12m is not None:
            symbol_trend.rs_vs_spy_12m = round(
                symbol_trend.perf_12m - bench.perf_12m, 6
            )
        return symbol_trend
