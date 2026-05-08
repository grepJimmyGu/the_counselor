from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StrategySaveRequest(BaseModel):
    backtest_id: str
    name: str = Field(..., min_length=1, max_length=80)


class StrategySaveResponse(BaseModel):
    slug: str
    url: str


class SavedStrategyResponse(BaseModel):
    slug: str
    name: str
    saved_at: datetime
    strategy_json: dict
    metrics: dict
    equity_curve: list[dict]
    benchmark_curve: list[dict]
    drawdown_curve: list[dict]
    trade_log: list[dict]
    warnings: list[str]
