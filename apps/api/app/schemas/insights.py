from typing import Optional

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
    locale: str = "en"


class SandboxReviewResponse(BaseModel):
    review_verdict: str
    trust_score: int
    overfitting_risk: str
    benchmark_concerns: list[str]
    regime_dependence: list[str]
    parameter_sensitivity_concerns: list[str]
    transaction_cost_concerns: list[str]
    sample_size_concerns: list[str]
    robustness_tests: list[str]
    suggested_next_tests: list[str]
    final_warning: str
