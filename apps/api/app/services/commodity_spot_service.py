"""
Commodity Spot Price Service
=============================
Fetches and stores *actual* commodity spot prices using Alpha Vantage's
dedicated commodity endpoints (function=WTI, COPPER, WHEAT, etc.).

These endpoints return the real underlying commodity price in the proper unit
($/barrel for WTI, $/ton for copper, ¢/bushel for wheat).  They are entirely
separate from the ETF proxy price bars (GLD, USO, COPX, WEAT) used for CMF
and technical analysis.

Storage:
  Monthly spot prices are stored in price_bars with synthetic symbols:
    WTI_SPOT, COPPER_SPOT, WHEAT_SPOT, NATGAS_SPOT
  Gold spot is derived from GLD price (1 GLD share ≈ 0.0930 troy oz) since
  GLD is a direct physical-gold fund and the ratio is reliable.

Each row in price_bars for a *_SPOT symbol has:
  open = high = low = close = adjusted_close = spot_price
  volume = 0

Performance lookback: since each bar represents one calendar month, the service
uses bar index lookbacks: 1=1M, 3=3M, 6=6M, 12=12M.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Approximate troy oz of gold per GLD share (2024–2026 era; decreases ~0.5%/yr
# as fees accrue — close enough for display purposes)
GLD_OZ_PER_SHARE = 0.0930

COMMODITY_META: dict[str, dict] = {
    "WTI": {
        "av_function": "WTI",
        "spot_symbol": "WTI_SPOT",
        "display_unit": "$/bbl",
        "av_unit_divisor": 1.0,       # AV already returns $/bbl
    },
    "COPPER": {
        "av_function": "COPPER",
        "spot_symbol": "COPPER_SPOT",
        "display_unit": "$/lb",
        "av_unit_divisor": 2204.62,   # AV returns $/metric ton → $/lb
    },
    "WHEAT": {
        "av_function": "WHEAT",
        "spot_symbol": "WHEAT_SPOT",
        "display_unit": "¢/bu",
        "av_unit_divisor": 1.0,       # AV already returns cents/bushel
    },
    # GOLD uses GLD-derived price — no AV function needed
    "GOLD": {
        "av_function": None,
        "spot_symbol": "GOLD_SPOT",
        "display_unit": "$/oz",
        "av_unit_divisor": 1.0,
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _upsert_spot_bar(
    conn,
    symbol: str,
    bar_date: date,
    price: float,
    is_sqlite: bool,
) -> None:
    """Insert or replace a single monthly spot bar."""
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    if is_sqlite:
        conn.execute(
            text(
                "INSERT OR REPLACE INTO price_bars "
                "(symbol, trading_date, open, high, low, close, adjusted_close, "
                "volume, dividend_amount, split_coefficient, source, fetched_at) "
                "VALUES (:sym, :dt, :p, :p, :p, :p, :p, 0, 0.0, 1.0, 'commodity_spot', :now)"
            ),
            {"sym": symbol, "dt": bar_date, "p": price, "now": now},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO price_bars "
                "(symbol, trading_date, open, high, low, close, adjusted_close, "
                "volume, dividend_amount, split_coefficient, source, fetched_at) "
                "VALUES (:sym, :dt, :p, :p, :p, :p, :p, 0, 0.0, 1.0, 'commodity_spot', :now) "
                "ON CONFLICT (symbol, trading_date) DO UPDATE SET "
                "close=EXCLUDED.close, adjusted_close=EXCLUDED.adjusted_close, "
                "fetched_at=EXCLUDED.fetched_at"
            ),
            {"sym": symbol, "dt": bar_date, "p": price, "now": now},
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@dataclass
class SpotQuote:
    commodity: str
    spot_symbol: str
    price: float
    date: date
    display_unit: str
    perf_1m: Optional[float] = None
    perf_3m: Optional[float] = None
    perf_6m: Optional[float] = None
    perf_12m: Optional[float] = None


class CommoditySpotService:
    """
    Manages commodity spot prices.
    Warmup fetches from Alpha Vantage and stores monthly bars.
    get_quote() returns latest price + month-over-month performance.
    """

    async def warmup(
        self,
        commodity: str,          # "WTI" | "COPPER" | "WHEAT"
        av_client,
        db: Session,
    ) -> bool:
        """
        Fetch monthly spot price series from AV and store in price_bars.
        Returns True on success.
        """
        meta = COMMODITY_META.get(commodity.upper())
        if not meta or not meta["av_function"]:
            return False

        try:
            bars = await av_client.fetch_commodity_spot(
                meta["av_function"], interval="monthly"
            )
        except Exception as exc:
            logger.warning(
                "Commodity spot warmup failed for %s: %s", commodity, exc
            )
            return False

        if not bars:
            return False

        divisor = meta["av_unit_divisor"]
        sym = meta["spot_symbol"]

        from app.core.config import get_settings
        is_sqlite = "sqlite" in get_settings().database_url
        from app.db.session import engine

        try:
            with engine.begin() as conn:
                for item in bars:
                    price = item["value"] / divisor
                    _upsert_spot_bar(conn, sym, item["date"], price, is_sqlite)
            logger.info(
                "Commodity spot warmup complete: %s (%s bars, latest: %s = %.4f)",
                sym,
                len(bars),
                bars[-1]["date"],
                bars[-1]["value"] / divisor,
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to store commodity spot bars for %s: %s", sym, exc
            )
            return False

    def warmup_gold_from_gld(self, db: Session) -> bool:
        """
        Derive monthly gold spot price from GLD price_bars.
        GLD tracks physical gold at ~0.0930 oz per share.
        """
        try:
            rows = db.execute(
                text(
                    "SELECT trading_date, adjusted_close FROM price_bars "
                    "WHERE symbol = 'GLD' ORDER BY trading_date ASC"
                )
            ).fetchall()
        except Exception as exc:
            logger.error("Gold spot from GLD: query failed: %s", exc)
            return False

        if not rows:
            return False

        # Compute one data point per month (use last bar of each month)
        monthly: dict[tuple[int, int], tuple[date, float]] = {}
        for bar_date, adj_close in rows:
            bd = bar_date if isinstance(bar_date, date) else date.fromisoformat(str(bar_date))
            key = (bd.year, bd.month)
            if key not in monthly or bd > monthly[key][0]:
                monthly[key] = (bd, float(adj_close))

        if not monthly:
            return False

        from app.core.config import get_settings
        is_sqlite = "sqlite" in get_settings().database_url
        from app.db.session import engine

        sym = COMMODITY_META["GOLD"]["spot_symbol"]
        try:
            with engine.begin() as conn:
                for (year, month), (bar_date, gld_price) in monthly.items():
                    gold_spot = gld_price / GLD_OZ_PER_SHARE
                    _upsert_spot_bar(conn, sym, bar_date, gold_spot, is_sqlite)
            last_date, last_gld = max(monthly.values(), key=lambda x: x[0])
            logger.info(
                "Gold spot warmup complete: %d monthly bars, latest %s = $%.2f/oz",
                len(monthly),
                last_date,
                last_gld / GLD_OZ_PER_SHARE,
            )
            return True
        except Exception as exc:
            logger.error("Failed to store gold spot bars: %s", exc)
            return False

    def get_quote(self, commodity: str, db: Session) -> Optional[SpotQuote]:
        """
        Return latest spot price + month-over-month performance for a commodity.
        Returns None if no data available.
        """
        commodity = commodity.upper()
        meta = COMMODITY_META.get(commodity)
        if not meta:
            return None

        sym = meta["spot_symbol"]
        try:
            rows = db.execute(
                text(
                    "SELECT trading_date, adjusted_close FROM price_bars "
                    "WHERE symbol = :sym ORDER BY trading_date DESC LIMIT 15"
                ),
                {"sym": sym},
            ).fetchall()
        except Exception:
            return None

        if not rows:
            return None

        prices = [float(r[1]) for r in rows]  # newest first
        dates = [r[0] for r in rows]

        latest_price = prices[0]
        latest_date = dates[0]
        if not isinstance(latest_date, date):
            latest_date = date.fromisoformat(str(latest_date))

        def _perf(n: int) -> Optional[float]:
            if len(prices) > n:
                past = prices[n]
                return round((latest_price / past) - 1, 6) if past else None
            return None

        return SpotQuote(
            commodity=commodity,
            spot_symbol=sym,
            price=latest_price,
            date=latest_date,
            display_unit=meta["display_unit"],
            perf_1m=_perf(1),
            perf_3m=_perf(3),
            perf_6m=_perf(6),
            perf_12m=_perf(12),
        )
