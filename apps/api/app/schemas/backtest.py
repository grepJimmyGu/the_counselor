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
    # Which methodology produced these numbers. `None` means the result
    # predates versioning — see BACKTEST_ENGINE_VERSION in the engine for
    # what changed. Deliberately NOT defaulted to the current version:
    # stored payloads without the key would then claim to be current, which
    # is the one thing this field exists to prevent.
    engine_version: Optional[str] = None
    # Today's target allocation — the last row of the engine's weights matrix.
    # {"NVDA": 1.0} means the strategy says hold NVDA right now; {"NVDA": 0.0}
    # means be in cash.
    #
    # Every "what does my strategy say today" surface has been INFERRING this
    # from `trade_log`, because the matrix never left the engine. The signal
    # cron's single-asset branch reads the last CLOSED trade and calls you
    # long if it had duration and non-zero P&L — so a strategy that went to
    # cash two months ago still reports LONG. This field is the real answer.
    #
    # None for results computed before this field existed, and for an empty
    # frame. An all-zero row is a meaningful answer (fully in cash) and is
    # returned as-is rather than collapsed to None.
    current_weights: Optional[dict[str, float]] = None
