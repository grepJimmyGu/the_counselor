from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal, Optional, Union

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
    # ── Fundamental signal templates (engine-backed via SignalProvider) ───────
    "value_composite",
    "quality_piotroski",
    "buyback_yield",
    "pead_drift",
    "earnings_revision",
    # Prompt-5 alternative signal strategies
    "news_sentiment_momentum",
    "insider_buying",
    # Prompt-6 composite factor strategy
    "multi_factor_composite",
    # ── Portfolio overlay strategies (PRD-13b) ───────────────────────────────
    # Each takes the user's existing holdings (inherited_universe) and applies
    # a rule on top: defensive (per-holding MA filter), rotation (rank by
    # momentum, hold top-K), rebalance (periodic re-weight to targets).
    "portfolio_defensive_overlay",
    "portfolio_rotation_overlay",
    "portfolio_rebalance_overlay",
    # ── Custom Build composer (PRD-16b) ───────────────────────────────────────
    # User composes any combination of PRD-16a catalog primitives via the
    # composer UI. Each rule references a primitive_id + threshold; rules
    # are folded left-to-right via `logic_with_prior` (AND/OR). Falls back
    # to single-rule evaluation for backwards compatibility.
    "custom_build",
    # ── Portfolio overlay expansion (PRD-13c) ──────────────────────────────────
    "portfolio_dual_momentum_overlay",
    "portfolio_defense_first_overlay",
    "portfolio_stability_tilt_overlay",
]

# Strategy types whose universe comes from the user's holdings, not the
# strategy template. The engine treats `strategy.inherited_universe` as the
# universe and ignores `strategy.universe` if both are set.
PORTFOLIO_OVERLAY_TYPES = frozenset({
    "portfolio_defensive_overlay",
    "portfolio_rotation_overlay",
    "portfolio_rebalance_overlay",
    # PRD-13c additions:
    "portfolio_dual_momentum_overlay",
    "portfolio_defense_first_overlay",
    "portfolio_stability_tilt_overlay",
})

# The types that the backtester engine currently handles
ENGINE_SUPPORTED_TYPES = frozenset({
    "moving_average_filter",
    "moving_average_crossover",
    "momentum_rotation",
    "rsi_mean_reversion",
    "breakout",
    "static_allocation",
    # Prompt-2 cross-sectional strategies
    "cross_sectional_momentum",
    "time_series_momentum",
    "short_term_reversal",
    "pairs_trading",
    "sector_rotation",
    "dual_momentum",
    "low_volatility",
    "bollinger_mean_reversion",
    # Prompt-3 fundamental signal strategies
    "value_composite",
    "quality_piotroski",
    "buyback_yield",
    # Prompt-4 event/revision strategies
    "pead_drift",
    "earnings_revision",
    # Prompt-5 alternative signal strategies
    "news_sentiment_momentum",
    "insider_buying",
    # Prompt-6 composite factor strategy
    "multi_factor_composite",
    # PRD-13b portfolio overlays
    "portfolio_defensive_overlay",
    "portfolio_rotation_overlay",
    "portfolio_rebalance_overlay",
    # PRD-13c portfolio overlay expansion
    "portfolio_dual_momentum_overlay",
    "portfolio_defense_first_overlay",
    "portfolio_stability_tilt_overlay",
})

RebalanceFrequency = Literal["daily", "weekly", "monthly", "quarterly"]


class StrategyRule(BaseModel):
    # ── Original fields (preserved unchanged) ────────────────────────────────
    indicator: Optional[str] = None
    lookback_days: Optional[int] = None
    # `float` for VALUE rules (the common case, unchanged). PRD-22c widens it:
    # a `{"min","max"}` dict for DISTANCE `in_range`, a code/string for REGIME
    # `equals`. Additive — existing rules keep using a bare float.
    threshold: Optional[Union[float, dict[str, Any], str]] = None
    operator: Optional[
        Literal[
            "gt", "gte", "lt", "lte", "crosses_above", "crosses_below",
            # ── PRD-22c kind-dispatch operators (additive) ────────────────────
            "fires",        # EVENT      — primitive fires this bar (value != 0)
            "is_true",      # LEVEL      — condition holds (bool of value)
            "crosses_up",   # CROSS      — bullish cross (value == +1)
            "crosses_down", # CROSS      — bearish cross (value == -1)
            "in_range",     # DISTANCE   — value between threshold.min / .max
            "equals",       # REGIME     — value equals threshold (code/str)
            "divergence_bullish",  # DIVERGENCE — bullish pattern (value == +1)
            "divergence_bearish",  # DIVERGENCE — bearish pattern (value == -1)
        ]
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
        "safe_asset",   # dual_momentum: marks a rule as the cash-substitute allocation
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
    holding_window_days: Optional[int] = None   # PEAD: trading days to hold post-announcement
    factor_weights: Optional[dict[str, float]] = None  # multi_factor_composite: factor → weight

    # ── PRD-16b: Custom Build composer fields ─────────────────────────────────
    # Both fields are ADDITIVE — existing 22 strategy types never set them and
    # are unaffected. Only `strategy_type="custom_build"` activates the
    # multi-rule fold path that consumes these. Pitfall C (per HANDOFF §6):
    # the engine's existing branches MUST continue to produce identical
    # output for every existing template.
    primitive_id: Optional[str] = None
    """Catalog primitive ID this rule evaluates. References an entry in
    `app/data/signal_primitives.py:SIGNAL_PRIMITIVES`. Required for
    custom_build rules; ignored by other strategy types."""

    primitive_params: Optional[dict[str, Union[float, int, str]]] = None
    """Runtime parameter overrides for the primitive (e.g. {"period": 21}
    for RSI(21)). Falls back to the catalog entry's defaults if omitted."""

    logic_with_prior: Optional[Literal["AND", "OR"]] = None
    """Operator joining THIS rule to the previous rule in the parent list.
    First rule in a list has `logic_with_prior=None`. AND means both must
    be true; OR means either must be true. Evaluated left-to-right.

    For `WHEN IN` blocks the final boolean Series after fold determines
    entry; for `WHEN OUT` blocks, same for exit. Single-rule blocks (the
    existing 22 templates) ignore this — the validator below enforces it."""


class PositionSizing(BaseModel):
    method: Literal["equal_weight", "fixed_weight", "vol_target", "signal_weighted"]
    max_positions: Optional[int] = None
    weights: Optional[dict[str, float]] = None
    # New fields for vol_target and signal_weighted methods
    target_vol_annual: Optional[float] = None
    signal_power: Optional[float] = None


class ExitTier(BaseModel):
    """One tier in a multi-tier exit ladder (PRD-16c).

    Trigger is % change from entry: positive for take-profit, negative
    for stop. Action is either `sell_all` (close the whole position) or
    `sell_fraction` (partial out — `fraction` is the share of the
    current position to liquidate, e.g. 0.33 = 1/3 out).

    Each tier fires AT MOST ONCE per entry: after `TP1` partial-outs,
    the position remains open and `TP2` can still fire later. Once a
    `sell_all` tier fires, the position is closed and subsequent tiers
    do not apply until a new entry occurs.

    Tiers are evaluated in ascending order of `trigger_pct`, so the
    `Stop` tier (most negative) is checked first on each bar.
    """

    trigger_pct: float  # e.g. -0.10 = -10% stop, +0.30 = +30% TP
    action: Literal["sell_all", "sell_fraction"]
    # Required when action='sell_fraction'; must satisfy 0 < f < 1.
    fraction: Optional[float] = None
    # Plain-English label for the dashboard / trade log ("Stop", "TP1", "TP2").
    label: Optional[str] = None

    @model_validator(mode="after")
    def validate_fraction(self) -> "ExitTier":
        if self.action == "sell_fraction":
            if self.fraction is None:
                raise ValueError(
                    "ExitTier with action='sell_fraction' requires `fraction`."
                )
            if not (0.0 < self.fraction < 1.0):
                raise ValueError(
                    f"ExitTier `fraction` must satisfy 0 < f < 1 (got {self.fraction})."
                )
        # `fraction` on a sell_all tier is harmless but confusing — reject.
        if self.action == "sell_all" and self.fraction is not None:
            raise ValueError(
                "ExitTier with action='sell_all' must not set `fraction`."
            )
        return self


class RiskManagement(BaseModel):
    max_drawdown_stop: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    # PRD-16c: multi-tier exit ladder. When set, the backtest engine
    # forces position-level exits on the bars where each tier triggers
    # — supersedes the single-stop / single-TP behavior of
    # `stop_loss_pct` + `take_profit_pct` for that strategy. Existing
    # strategies that don't set `exit_ladder` are unaffected.
    #
    # Validator below enforces:
    #   - at least one stop tier (`trigger_pct < 0` with `action='sell_all'`)
    #   - tiers ordered ascending by `trigger_pct`
    #   - sell_fraction tiers carry a valid `fraction`
    exit_ladder: Optional[list[ExitTier]] = None

    @model_validator(mode="after")
    def validate_exit_ladder(self) -> "RiskManagement":
        if self.exit_ladder is None:
            return self
        if not self.exit_ladder:
            raise ValueError("`exit_ladder`, when set, must contain at least 1 tier.")
        triggers = [t.trigger_pct for t in self.exit_ladder]
        if triggers != sorted(triggers):
            raise ValueError(
                "exit_ladder tiers must be ordered ascending by `trigger_pct`."
            )
        has_stop = any(
            t.trigger_pct < 0 and t.action == "sell_all"
            for t in self.exit_ladder
        )
        if not has_stop:
            raise ValueError(
                "exit_ladder must include at least one stop tier "
                "(trigger_pct < 0 with action='sell_all')."
            )
        return self


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
    # PRD-13b: Portfolio Mode inverts the universe relationship. When the
    # user supplies holdings, `inherited_universe` carries them through and
    # the engine uses this list instead of `universe`. Optional + defaulted
    # so the 22 pre-existing strategy_types continue to ignore it.
    inherited_universe: Optional[list[str]] = None
    # PRD-16c: bar resolution for active execution. Default "daily"
    # preserves all 22 existing strategy_types' behavior. Non-daily
    # values flag the strategy for the intraday monitor cron AND tell
    # the engine which bar series to backtest against. The engine
    # currently soft-degrades non-daily backtests to daily with a
    # warning (the intraday data path through `_load_prices` is the
    # remaining gap before non-daily backtests run on the actual
    # intraday bars from `IntradayBarService`). The composer's
    # `<BarResolutionPicker>` writes this field.
    bar_resolution: Literal["daily", "5min", "15min", "30min", "60min"] = "daily"

    @field_validator("universe", mode="before")
    @classmethod
    def normalize_universe(cls, value: list[str]) -> list[str]:
        return [item.upper().strip() for item in value]

    @field_validator("inherited_universe", mode="before")
    @classmethod
    def normalize_inherited_universe(
        cls, value: Optional[list[str]]
    ) -> Optional[list[str]]:
        if value is None:
            return None
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

        # ── PRD-13b: portfolio-overlay validation ────────────────────────────
        # Portfolio overlays MUST carry an inherited_universe. Each overlay
        # has its own minimum-holding count derived from its mechanics.
        if self.strategy_type in PORTFOLIO_OVERLAY_TYPES:
            holdings = self.inherited_universe or []
            if not holdings:
                raise ValueError(
                    f"{self.strategy_type} requires inherited_universe "
                    "(the user's holdings)"
                )
            if self.strategy_type == "portfolio_defensive_overlay" and len(holdings) < 1:
                raise ValueError("portfolio_defensive_overlay needs at least 1 holding")
            if self.strategy_type == "portfolio_rotation_overlay" and len(holdings) < 3:
                raise ValueError("portfolio_rotation_overlay needs at least 3 holdings")
            if self.strategy_type == "portfolio_rebalance_overlay":
                if len(holdings) < 2:
                    raise ValueError("portfolio_rebalance_overlay needs at least 2 holdings")
                weights = self.position_sizing.weights or {}
                if not weights:
                    raise ValueError(
                        "portfolio_rebalance_overlay requires position_sizing.weights"
                    )
            # ── PRD-13c: new overlay minimums ───────────────────────────────
            if self.strategy_type == "portfolio_dual_momentum_overlay" and len(holdings) < 3:
                raise ValueError(
                    "portfolio_dual_momentum_overlay needs at least 3 holdings "
                    "(relative ranking requires multiple candidates)"
                )
            if self.strategy_type == "portfolio_defense_first_overlay" and len(holdings) < 2:
                raise ValueError(
                    "portfolio_defense_first_overlay needs at least 2 holdings "
                    "(breadth signal requires multiple data points)"
                )
            if self.strategy_type == "portfolio_stability_tilt_overlay" and len(holdings) < 2:
                raise ValueError(
                    "portfolio_stability_tilt_overlay needs at least 2 holdings "
                    "(cross-sectional vol weighting requires multiple candidates)"
                )

        # ── PRD-16b: custom_build + logic_with_prior validation ───────────────
        if self.strategy_type == "custom_build":
            if not self.rules:
                raise ValueError(
                    "custom_build requires at least one rule (a primitive + threshold)"
                )
            for i, rule in enumerate(self.rules):
                if rule.primitive_id is None:
                    raise ValueError(
                        f"custom_build rule {i} missing primitive_id "
                        "(every rule references a catalog primitive)"
                    )
        # Logic-with-prior contract — applies to ANY strategy type (not just
        # custom_build): first rule must NOT have logic_with_prior; subsequent
        # rules with logic_with_prior set are folded via the multi-rule path.
        # Existing 22 templates never set logic_with_prior so this is a no-op
        # for them.
        for i, rule in enumerate(self.rules):
            if i == 0 and rule.logic_with_prior is not None:
                raise ValueError(
                    "First rule in a block cannot have logic_with_prior "
                    "(it joins TO the previous rule, but there is none)"
                )
            if i > 0 and rule.logic_with_prior is None and self.strategy_type == "custom_build":
                # Lax for legacy strategy_types — only custom_build enforces
                # the fold contract. Other types may have legitimate
                # multi-rule blocks (e.g. rsi_mean_reversion uses buy_rule +
                # sell_rule) where rules[1:] aren't folded.
                raise ValueError(
                    f"custom_build rule {i} must have logic_with_prior set "
                    "(AND or OR) — rules in a custom block are folded"
                )
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
