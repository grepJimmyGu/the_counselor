from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.schemas.strategy import StrategyJSON


class RobustnessRunRequest(BaseModel):
    strategy_json: StrategyJSON
    backtest_result_id: Optional[str] = None
    tests_to_run: list[Literal[
        "parameter_sensitivity",
        "subperiod",
        "transaction_cost",
        "benchmark_comparison",
        "peer_ticker",
    ]]
    peer_tickers: list[str] = []
    parameter_grid: Optional[dict[str, list[Any]]] = None


class ParameterSensitivityRow(BaseModel):
    parameter_set: dict[str, Any]
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    trade_count: int
    verdict: Literal["better", "similar", "worse"]


class SubperiodRow(BaseModel):
    period: str
    start_date: str
    end_date: str
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    verdict: Literal["strong", "acceptable", "weak", "insufficient_data"]


class TransactionCostRow(BaseModel):
    cost_bps: int
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    turnover_impact: float
    verdict: Literal["robust", "sensitive", "breaks_down"]


class BenchmarkComparisonRow(BaseModel):
    name: str
    symbol: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    excess_return_vs_strategy: float


class PeerTickerRow(BaseModel):
    ticker: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    trade_count: int
    verdict: Literal["better", "similar", "worse", "error"]
    error: Optional[str] = None


class RobustnessResults(BaseModel):
    parameter_sensitivity: list[ParameterSensitivityRow] = []
    subperiod: list[SubperiodRow] = []
    transaction_cost: list[TransactionCostRow] = []
    benchmark_comparison: list[BenchmarkComparisonRow] = []
    peer_ticker: list[PeerTickerRow] = []
    summary: str = ""
    warnings: list[str] = []


class RobustnessJobResponse(BaseModel):
    run_id: str
    status: Literal["pending", "running", "completed", "failed"]
    results: Optional[RobustnessResults] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
