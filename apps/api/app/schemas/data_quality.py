from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


class DataQualityReport(BaseModel):
    symbol: str
    status: Literal["ready", "warning", "blocked"]
    warnings: list[str]
    blocking_errors: list[str]
    earliest_available_date: Optional[date]
    latest_available_date: Optional[date]
    row_count: int
    missing_date_count: Optional[int]
    adjusted_close_coverage: float  # 0.0–1.0
    volume_coverage: float          # 0.0–1.0


class BacktestQualityGate(BaseModel):
    """Aggregated quality result for all tickers in a strategy."""
    overall_status: Literal["ready", "warning", "blocked"]
    reports: dict[str, DataQualityReport]
    blocking_symbols: list[str]
    warning_symbols: list[str]
