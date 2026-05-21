from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.strategy import StrategyJSON


class CurvePoint(BaseModel):
    date: date
    value: float


class TradeLogItem(BaseModel):
    symbol: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    return_pct: float
    holding_period_days: int


class AnnualReturnItem(BaseModel):
    year: int
    return_pct: float


class MonthlyReturnItem(BaseModel):
    year: int
    month: int
    return_pct: float


class BacktestMetrics(BaseModel):
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    number_of_trades: int
    average_trade_return: float
    best_trade: float
    worst_trade: float
    average_holding_period: float
    benchmark_total_return: float
    excess_return_vs_benchmark: float
    alpha_vs_benchmark: float
    beta_vs_benchmark: float
    turnover: float
    time_in_market: float
    # Extended trade diagnostics
    profit_factor: Optional[float] = None
    avg_winner: Optional[float] = None
    avg_loser: Optional[float] = None
    median_trade_return: Optional[float] = None
    longest_winning_streak: Optional[int] = None
    longest_losing_streak: Optional[int] = None
    # Buy-and-hold comparison
    buy_and_hold_return: Optional[float] = None
    buy_and_hold_annualized_return: Optional[float] = None


class BacktestRunRequest(BaseModel):
    strategy_json: StrategyJSON
    # Stage 3: set to the template_id (a string) when running a pre-built template.
    # Custom/chat-built strategies leave this null. The gating dep skips universe
    # + history caps when template_id is present (templates are unlimited).
    template_id: Optional[str] = None


class BacktestResult(BaseModel):
    backtest_id: str
    strategy_json: StrategyJSON
    metrics: BacktestMetrics
    equity_curve: list[CurvePoint]
    benchmark_curve: list[CurvePoint]
    buy_and_hold_curve: list[CurvePoint] = []
    drawdown_curve: list[CurvePoint]
    trade_log: list[TradeLogItem]
    annual_returns: list[AnnualReturnItem]
    monthly_returns: list[MonthlyReturnItem]
    warnings: list[str]
    created_at: Optional[datetime] = None
