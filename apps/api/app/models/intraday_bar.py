"""PRD-16c-1 — Intraday OHLCV bar cache.

Different from `PriceBar` (EOD daily bars) in three ways:
  - Composite PK: `(symbol, resolution, bar_time)` — one row per minute
    per resolution per symbol; bar_time is a full DateTime.
  - Resolution is the granularity: '5min' | '15min' | '30min' | '60min'.
    1-minute bars are out of scope for v1 (Alpha Vantage rate limits).
  - No `adjusted_close` / dividends / splits — intraday bars don't carry
    those corrections. Caller resolves splits / dividends from the daily
    `price_bars` view if needed.

Population path: `IntradayBarService.get_bars` checks this table, then
fetches from Alpha Vantage to fill any gaps, writes back the result.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class IntradayBar(Base):
    __tablename__ = "intraday_bars"

    # Composite PK — one row per (symbol, resolution, bar_time). String(10)
    # symbol matches `price_bars`'s convention; String(8) resolution
    # accommodates "5min" / "60min" with headroom for future intraday
    # resolutions ("4hour" etc.).
    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    resolution: Mapped[str] = mapped_column(String(8), primary_key=True)
    bar_time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)

    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    # When this row was written. Used by the cache to refresh stale entries
    # within a trading day (e.g. the current 15-min bar still printing).
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
