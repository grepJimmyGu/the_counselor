from __future__ import annotations

from datetime import date
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


StrategyType = Literal[
    "moving_average_filter",
    "moving_average_crossover",
    "momentum_rotation",
    "rsi_mean_reversion",
    "breakout",
    "static_allocation",
]
RebalanceFrequency = Literal["daily", "weekly", "monthly", "quarterly"]


class StrategyRule(BaseModel):
    indicator: Optional[str] = None
    lookback_days: Optional[int] = None
    threshold: Optional[float] = None
    operator: Optional[
        Literal["gt", "gte", "lt", "lte", "crosses_above", "crosses_below"]
    ] = None
    source: Optional[
        Literal["close", "adjusted_close", "return", "moving_average", "rsi", "high"]
    ] = None
    value: Optional[Union[float, str]] = None
    fast_window: Optional[int] = None
    slow_window: Optional[int] = None
    entry_window: Optional[int] = None
    exit_window: Optional[int] = None
    top_n: Optional[int] = None
    ranking_measure: Optional[Literal["total_return"]] = None
    ranking_lookback_days: Optional[int] = None


class PositionSizing(BaseModel):
    method: Literal["equal_weight", "fixed_weight"]
    max_positions: Optional[int] = None
    weights: Optional[dict[str, float]] = None


class RiskManagement(BaseModel):
    max_drawdown_stop: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None


class CashManagement(BaseModel):
    hold_cash_when_no_signal: bool = True
    cash_yield_bps: Optional[float] = 0.0


class StrategyJSON(BaseModel):
    strategy_name: str = Field(..., min_length=3, max_length=200)
    strategy_type: StrategyType
    universe: list[str] = Field(..., min_length=1)
    benchmark: str = Field(..., min_length=1)
    start_date: date
    end_date: date
    initial_capital: float = Field(..., gt=0)
    rebalance_frequency: RebalanceFrequency
    transaction_cost_bps: float = Field(0.0, ge=0)
    slippage_bps: float = Field(0.0, ge=0)
    rules: list[StrategyRule] = Field(default_factory=list)
    position_sizing: PositionSizing
    risk_management: RiskManagement = Field(default_factory=RiskManagement)
    cash_management: CashManagement = Field(default_factory=CashManagement)

    @field_validator("universe", mode="before")
    @classmethod
    def normalize_universe(cls, value: list[str]) -> list[str]:
        return [item.upper().strip() for item in value]

    @field_validator("benchmark")
    @classmethod
    def normalize_benchmark(cls, value: str) -> str:
        return value.upper().strip()

    @model_validator(mode="after")
    def validate_dates(self) -> "StrategyJSON":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.position_sizing.method == "fixed_weight":
            if not self.position_sizing.weights:
                raise ValueError("fixed_weight position sizing requires weights")
        if self.strategy_type == "static_allocation":
            weights = self.position_sizing.weights or {}
            if not weights:
                raise ValueError("static_allocation requires explicit weights")
            total_weight = sum(weights.values())
            if not 0.99 <= total_weight <= 1.01:
                raise ValueError("static allocation weights must sum to 1.0")
        return self


class StrategyChatRequest(BaseModel):
    user_message: str = Field(..., min_length=3)
    previous_strategy_json: Optional[StrategyJSON] = None
    previous_backtest_id: Optional[str] = None


class StrategyChatResponse(BaseModel):
    assistant_message: str
    strategy_json: Optional[StrategyJSON]
    validation_status: Literal["valid", "needs_clarification", "invalid"]
    missing_fields: list[str]
    clarification_questions: list[str]


class StrategyExtractedField(BaseModel):
    field: str
    value: str
    status: Literal["explicit", "inferred", "missing"]


class StrategyMarkdownParseRequest(BaseModel):
    markdown_content: str = Field(..., min_length=20)
    document_name: Optional[str] = None
    previous_strategy_json: Optional[StrategyJSON] = None


class StrategyMarkdownParseResponse(BaseModel):
    assistant_message: str
    strategy_json: Optional[StrategyJSON]
    validation_status: Literal["valid", "needs_clarification", "invalid"]
    extracted_fields: list[StrategyExtractedField]
    ambiguities: list[str]
    assumption_log: list[str]
    missing_fields: list[str]
    clarification_questions: list[str]
    source_summary: str
