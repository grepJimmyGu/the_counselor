from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class ClarificationState(str, Enum):
    ready = "ready"                        # strategy_json populated, no issues
    needs_parameters = "needs_parameters"  # supported type, missing quantifiable fields
    not_supported = "not_supported"        # concept outside engine scope (PRD-05)


StrategyType = Literal[
    # ── Original 6 (engine-backed) ───────────────────────────────────────────
    "moving_average_filter",
    "moving_average_crossover",
    "momentum_rotation",
    "rsi_mean_reversion",
    "breakout",
    "static_allocation",
    # ── Extended template types (schema only — backtester support pending) ───
    "cross_sectional_momentum",
    "time_series_momentum",
    "short_term_reversal",
    "pairs_trading",
    "sector_rotation",
    "dual_momentum",
    "low_volatility",
    "bollinger_mean_reversion",
]

# The 6 types that the backtester engine currently handles
ENGINE_SUPPORTED_TYPES = frozenset({
    "moving_average_filter",
    "moving_average_crossover",
    "momentum_rotation",
    "rsi_mean_reversion",
    "breakout",
    "static_allocation",
})

RebalanceFrequency = Literal["daily", "weekly", "monthly", "quarterly"]


class StrategyRule(BaseModel):
    # ── Original fields (preserved unchanged) ────────────────────────────────
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

    # ── Extended fields for new strategy templates ────────────────────────────
    signal_source: Optional[Literal[
        "price", "return", "vol", "sentiment_score", "f_score",
        "buyback_yield", "value_composite", "quality_composite",
        "earnings_surprise", "estimate_revision", "insider_net_buy",
    ]] = None
    rank_direction: Optional[Literal["top", "bottom"]] = None
    zscore_entry: Optional[float] = None
    zscore_exit: Optional[float] = None
    zscore_stop: Optional[float] = None
    pair_symbol: Optional[str] = None
    hedge_ratio: Optional[float] = None
    target_vol_annual: Optional[float] = None
    formation_period_days: Optional[int] = None
    skip_period_days: Optional[int] = None
    num_std: Optional[float] = None
    top_pct: Optional[float] = None


class PositionSizing(BaseModel):
    method: Literal["equal_weight", "fixed_weight", "vol_target", "signal_weighted"]
    max_positions: Optional[int] = None
    weights: Optional[dict[str, float]] = None
    # New fields for vol_target and signal_weighted methods
    target_vol_annual: Optional[float] = None
    signal_power: Optional[float] = None


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
        # fixed_weight requires weights (unchanged behavior)
        if self.position_sizing.method == "fixed_weight":
            if not self.position_sizing.weights:
                raise ValueError("fixed_weight position sizing requires weights")
        # static_allocation weight-sum check (unchanged behavior)
        if self.strategy_type == "static_allocation":
            weights = self.position_sizing.weights or {}
            if not weights:
                raise ValueError("static_allocation requires explicit weights")
            total_weight = sum(weights.values())
            if not 0.99 <= total_weight <= 1.01:
                raise ValueError("static allocation weights must sum to 1.0")
        # vol_target and signal_weighted do NOT require weights
        return self


class StrategyChatRequest(BaseModel):
    user_message: str = Field(..., min_length=3)
    previous_strategy_json: Optional[StrategyJSON] = None
    previous_backtest_id: Optional[str] = None
    locale: str = "en"


class StrategyChatResponse(BaseModel):
    assistant_message: str
    strategy_json: Optional[StrategyJSON]
    validation_status: Literal["valid", "needs_clarification", "invalid"]
    missing_fields: list[str]
    clarification_questions: list[str]
    # PRD-04: typed clarification state so frontend can branch correctly
    clarification_state: ClarificationState = ClarificationState.ready
    # Set when parser approximated an intent — shown to user for transparency
    approximation_note: Optional[str] = None
    # PRD-05 (stubbed): populated when clarification_state == not_supported
    unsupported_reason: Optional[str] = None
    suggested_reformulation: Optional[str] = None


class StrategyExtractedField(BaseModel):
    field: str
    value: str
    status: Literal["explicit", "inferred", "missing"]


class StrategyMarkdownParseRequest(BaseModel):
    markdown_content: str = Field(..., min_length=20)
    document_name: Optional[str] = None
    previous_strategy_json: Optional[StrategyJSON] = None
    locale: str = "en"


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
