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


class PublicStrategyItem(BaseModel):
    slug: str
    name: str
    saved_at: datetime
    upvote_count: int = 0
