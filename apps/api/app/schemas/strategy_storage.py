from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StrategySaveRequest(BaseModel):
    backtest_id: str
    name: str = Field(..., min_length=1, max_length=80)
    is_public: bool = True


class StrategySaveResponse(BaseModel):
    slug: str
    url: str
    is_public: bool


class VisibilityUpdateRequest(BaseModel):
    is_public: bool


class SavedStrategyResponse(BaseModel):
    slug: str
    name: str
    saved_at: datetime
    is_public: bool = True
    strategy_json: dict
    metrics: dict
    equity_curve: list[dict]
    benchmark_curve: list[dict]
    drawdown_curve: list[dict]
    trade_log: list[dict]
    warnings: list[str]


class LivePerformanceResponse(BaseModel):
    slug: str
    published_at: date
    total_return: Optional[float] = None       # 0.042 = +4.2%
    total_return_pct: Optional[float] = None   # 4.2 (display value)
    days_tracked: int = 0
    current_signal: Optional[str] = None
    last_price_date: Optional[date] = None
    equity_curve: list[dict] = []
    error: Optional[str] = None
    computed_at: Optional[datetime] = None


class PublicStrategyItem(BaseModel):
    slug: str
    name: str
    saved_at: datetime
    upvote_count: int = 0
    live: Optional[LivePerformanceResponse] = None
