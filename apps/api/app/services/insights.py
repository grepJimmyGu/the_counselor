from __future__ import annotations

import json

from app.core.config import get_settings
from app.schemas.backtest import BacktestResult
from app.schemas.insights import ExplanationResponse, SandboxReviewResponse
from app.schemas.strategy import StrategyJSON
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway


def _explanation_system_prompt() -> str:
    return (
        "You are the friendly strategy explainer for a quantitative research app. "
        "Explain the backtest clearly without giving trading advice. "
        "Use the provided strategy JSON and backtest result only. "
        "Return JSON only matching this schema:\n"
        f"{json.dumps(ExplanationResponse.model_json_schema(), indent=2)}"
    )


def _review_system_prompt() -> str:
    return (
        "You are the independent sandbox reviewer for a quantitative research app. "
        "Be skeptical, benchmark-aware, and explicit about overfitting and robustness risk. "
        "Do not assume positive returns imply trustworthiness. "
        "Return JSON only matching this schema:\n"
        f"{json.dumps(SandboxReviewResponse.model_json_schema(), indent=2)}"
    )


def _build_explanation_user_prompt(
    strategy: StrategyJSON, backtest_result: BacktestResult
) -> str:
    return (
        f"Strategy JSON:\n{strategy.model_dump_json(indent=2)}\n\n"
        f"Backtest result:\n{backtest_result.model_dump_json(indent=2)}\n\n"
        "Explain the result and suggest the next research iterations."
    )


def _build_review_user_prompt(
    strategy: StrategyJSON, backtest_result: BacktestResult
) -> str:
    return (
        f"Strategy JSON:\n{strategy.model_dump_json(indent=2)}\n\n"
        f"Backtest result:\n{backtest_result.model_dump_json(indent=2)}\n\n"
        "Critique the result as an independent reviewer."
    )


def build_explanation_fallback(
    strategy: StrategyJSON, backtest_result: BacktestResult
) -> ExplanationResponse:
    metrics = backtest_result.metrics
    strengths = []
    weaknesses = []
    if metrics.excess_return_vs_benchmark > 0:
        strengths.append("The strategy outperformed its benchmark over the tested period.")
    if metrics.max_drawdown > -0.2:
        strengths.append("Peak-to-trough drawdown stayed relatively contained for an equity strategy.")
    if metrics.sharpe_ratio < 0.7:
        weaknesses.append("Risk-adjusted returns are still modest.")
    if metrics.number_of_trades < 10:
        weaknesses.append("The trade sample is small, so the result may be noisy.")

    return ExplanationResponse(
        strategy_summary=f"{strategy.strategy_name} is a {strategy.strategy_type.replace('_', ' ')} strategy over {', '.join(strategy.universe)} versus {strategy.benchmark}.",
        performance_explanation=(
            f"The backtest returned {metrics.total_return:.1%} total return with {metrics.max_drawdown:.1%} max drawdown "
            f"and a Sharpe ratio of {metrics.sharpe_ratio:.2f}."
        ),
        strengths=strengths or ["The rules are deterministic and easy to reason about."],
        weaknesses=weaknesses or ["The result still needs broader robustness testing before it deserves much trust."],
        market_regime_notes=[
            "Trend-following strategies often shine in persistent uptrends and lag in choppy sideways markets.",
            "Mean-reversion strategies can deteriorate quickly when volatility regimes shift."
            if strategy.strategy_type == "rsi_mean_reversion"
            else "A single backtest window cannot guarantee regime robustness."
        ],
        suggested_iterations=[
            "Try a different but related benchmark and compare excess return stability.",
            "Expand the universe or shift the date window to see whether the edge persists.",
            "Stress test transaction costs and parameter changes before trusting the headline return.",
        ],
        disclaimer="This is educational research output, not trading advice or a live execution system.",
    )


def build_sandbox_review_fallback(
    strategy: StrategyJSON, backtest_result: BacktestResult
) -> SandboxReviewResponse:
    metrics = backtest_result.metrics
    trust_score = 55
    concerns: list[str] = []
    if metrics.excess_return_vs_benchmark <= 0:
        trust_score -= 20
        concerns.append("The strategy did not beat the benchmark after the tested assumptions.")
    if metrics.number_of_trades < 12:
        trust_score -= 10
        concerns.append("The strategy has too few completed trades to estimate edge reliably.")
    if metrics.max_drawdown < -0.35:
        trust_score -= 10
        concerns.append("Max drawdown is severe relative to the claimed edge.")
    if strategy.transaction_cost_bps + strategy.slippage_bps < 5:
        trust_score -= 5
        concerns.append("Execution frictions may still be understated.")

    verdict = "mixed"
    if trust_score >= 70:
        verdict = "promising"
    elif trust_score < 40:
        verdict = "skeptical"
    elif trust_score < 25:
        verdict = "untrusted"

    return SandboxReviewResponse(
        review_verdict=verdict,
        trust_score=max(min(trust_score, 100), 0),
        overfitting_risk="Moderate. Re-running similar ideas and keeping only winners can create false confidence quickly.",
        benchmark_concerns=[
            "Check whether buy-and-hold of the traded asset or SPY already delivered most of the return.",
            "Compare against a simple moving-average or equal-weight baseline, not only the chosen benchmark.",
        ],
        regime_dependence=[
            "Test subperiods such as pre-2020, 2020-2021, and 2022-2024 separately.",
            "Confirm the result is not dominated by one exceptional rally or crash window.",
        ],
        parameter_sensitivity_concerns=[
            "Bump each core parameter up and down by 10-20% and see whether the edge survives.",
            "If a tiny change flips the result from strong to weak, the strategy is fragile.",
        ],
        transaction_cost_concerns=[
            "Increase slippage and transaction costs to stress more realistic execution.",
            "High-turnover strategies deserve harsher cost assumptions than low-turnover trend filters.",
        ],
        sample_size_concerns=concerns or ["The sample is acceptable for an MVP backtest, but not enough for production confidence."],
        robustness_tests=[
            "Walk-forward test on a later holdout period.",
            "Neighbor-parameter sensitivity sweep.",
            "Cross-symbol validation on similar tickers or sector ETFs.",
            "Cost stress test with doubled slippage assumptions.",
        ],
        suggested_next_tests=[
            "Run the same logic on adjacent symbols and compare stability.",
            "Shorten and lengthen the test window to measure regime dependence.",
            "Compare against buy-and-hold and a plain benchmark overlay.",
        ],
        final_warning="A profitable backtest is not evidence of a durable edge until it survives benchmark, regime, and sensitivity checks.",
    )


def build_explanation(
    strategy: StrategyJSON, backtest_result: BacktestResult
) -> ExplanationResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return build_explanation_fallback(strategy, backtest_result)

    settings = get_settings()
    try:
        return gateway.generate_structured(
            model=settings.llm_explainer_model or settings.llm_strategy_model,
            system_prompt=_explanation_system_prompt(),
            user_prompt=_build_explanation_user_prompt(strategy, backtest_result),
            response_model=ExplanationResponse,
            temperature=0.2,
        )
    except LLMAdapterError:
        return build_explanation_fallback(strategy, backtest_result)


def build_sandbox_review(
    strategy: StrategyJSON, backtest_result: BacktestResult
) -> SandboxReviewResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return build_sandbox_review_fallback(strategy, backtest_result)

    settings = get_settings()
    try:
        return gateway.generate_structured(
            model=settings.llm_reviewer_model or settings.llm_strategy_model,
            system_prompt=_review_system_prompt(),
            user_prompt=_build_review_user_prompt(strategy, backtest_result),
            response_model=SandboxReviewResponse,
            temperature=0.2,
        )
    except LLMAdapterError:
        return build_sandbox_review_fallback(strategy, backtest_result)
