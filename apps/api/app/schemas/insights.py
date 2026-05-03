from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategyJSON


class ExplainRequest(BaseModel):
    strategy_json: StrategyJSON
    backtest_result: BacktestResult
    locale: str = "en"


class ExplanationResponse(BaseModel):
    strategy_summary: str
    performance_explanation: str
    strengths: list[str]
    weaknesses: list[str]
    market_regime_notes: list[str]
    suggested_iterations: list[str]
    disclaimer: str


class SandboxReviewRequest(BaseModel):
    strategy_json: StrategyJSON
    backtest_result: BacktestResult
    prior_iterations: Optional[list[str]] = None
    iteration_count: int = 1  # how many times the user has iterated on this strategy
    locale: str = "en"


class SandboxReviewResponse(BaseModel):
    # Core verdict
    review_verdict: Literal["promising", "mixed", "skeptical", "untrusted"]
    trust_score: int  # 0–100
    confidence_level: Literal["low", "medium", "high"]
    # Risk levels
    overfitting_risk: Literal["low", "medium", "high"]
    overfitting_risk_explanation: str
    # Concerns (evidence-based, not promotional)
    benchmark_concerns: list[str]
    regime_dependence_concerns: list[str]
    parameter_sensitivity_concerns: list[str]
    transaction_cost_concerns: list[str]
    sample_size_concerns: list[str]
    data_quality_concerns: list[str]
    # Balanced assessment
    main_reasons_to_trust: list[str]
    main_reasons_to_distrust: list[str]
    # Next steps
    required_next_tests: list[str]
    suggested_next_experiments: list[str]
    final_warning: str
