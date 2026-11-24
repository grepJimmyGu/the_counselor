from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class SymbolSearchItem(BaseModel):
    symbol: str
    name: str
    region: Optional[str] = None
    currency: Optional[str] = None
    instrument_type: Optional[str] = None
    exchange: Optional[str] = None
    timezone: Optional[str] = None
    alpha_vantage_match_score: Optional[float] = None


class SymbolDetailResponse(BaseModel):
    symbol: str
    name: str
    region: Optional[str] = None
    currency: Optional[str] = None
    instrument_type: Optional[str] = None
    exchange: Optional[str] = None
    timezone: Optional[str] = None
    alpha_vantage_match_score: Optional[float] = None
    is_active: bool
    last_seen_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None


class PriceBarResponse(BaseModel):
    symbol: str
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
    dividend_amount: float
    split_coefficient: float


class DataStatusResponse(BaseModel):
    symbol: str
    bar_count: int
    earliest_date: Optional[date] = None
    latest_date: Optional[date] = None
    is_stale: bool
    last_fetch_status: Optional[str] = None
    last_fetched_at: Optional[datetime] = None


class MarketSnapshotItem(BaseModel):
    symbol: str
    name: str
    last_price: float
    prev_close: float
    change_pct: float
    change_abs: float
    last_date: date
    sparkline: list[float]  # last 30 adjusted closes for mini chart


class WarmupRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=20)
    lookback_days: int = Field(default=252, ge=1, le=1000)


class WarmupResponse(BaseModel):
    queued: list[str]
    already_fresh: list[str]
    errors: dict[str, str]


class IntradayBarView(BaseModel):
    """One bar of a regular session: when it started (UTC) and its prices."""
    time: datetime
    open: float
    close: float


class IntradaySessionView(BaseModel):
    date: date
    bars: list[IntradayBarView]
    close: Optional[float] = Field(
        default=None,
        description="The exchange's close for a session that has ended; null for today's.",
    )


class IntradayChartView(BaseModel):
    """The company page's 1D (5-minute) and 1W (30-minute) chart."""
    symbol: str
    range: str
    interval_minutes: int
    sessions: list[IntradaySessionView]
    previous_close: Optional[float] = Field(
        default=None,
        description="The close of the session before the first one shown; changes are measured from it.",
    )
    previous_close_date: Optional[date] = None
    previous_close_source: Optional[str] = Field(
        default=None,
        description="'official' (the exchange's close) or 'last_bar' (that day's last bar, when the close isn't available).",
    )
    as_of: Optional[datetime] = Field(default=None, description="The end of the newest bar.")
