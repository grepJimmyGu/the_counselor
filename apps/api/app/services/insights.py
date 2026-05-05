from __future__ import annotations

from app.core.config import get_settings
from app.schemas.backtest import BacktestResult
from app.schemas.insights import ExplanationResponse, SandboxReviewResponse
from app.schemas.strategy import StrategyJSON
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway
from app.services.strategy_parser import COMMODITY_TICKERS, _is_commodity_universe

_EXPLANATION_SYSTEM_PROMPT = (
    "You are the strategy explainer for a quantitative research app. "
    "Your job is to give a thorough, honest, and educational analysis — not cheerleading. "
    "Use only the strategy JSON and backtest result provided. Do not invent data. "
    "\n\n"
    "Cover all of the following in your response:\n"
    "- strategy_summary: what the strategy does and what the backtest tested\n"
    "- performance_explanation: how the numbers look in context — total return, "
    "Sharpe, drawdown, win rate, and how they compare to the benchmark\n"
    "- strengths: genuine evidence-based positives from the data (2–4 items)\n"
    "- weaknesses: honest limitations including sample size, concentration risk, "
    "regime dependency, and execution assumptions (2–4 items)\n"
    "- market_regime_notes: specific market conditions that would help or hurt this "
    "strategy — e.g. trending vs choppy, high vs low volatility, rate environment (2–3 items)\n"
    "- suggested_iterations: concrete next tests the researcher should run — different "
    "parameter values, date windows, universes, or cost assumptions (3–4 items)\n"
    "- disclaimer: a clear, specific sentence on backtest limitations — data-snooping risk, "
    "execution slippage in real markets, and that past performance does not predict future results\n"
    "\n"
    "If the universe contains commodity ETFs (GLD, SLV, USO, UNG, DBA, DBC, etc.), "
    "flag that ETF prices exclude roll yield and contango/backwardation — "
    "the backtest reflects ETF price return only, which may understate or overstate real commodity exposure. "
    "Return a JSON object with exactly these keys: "
    "strategy_summary (str), performance_explanation (str), "
    "strengths (list[str]), weaknesses (list[str]), "
    "market_regime_notes (list[str]), suggested_iterations (list[str]), "
    "disclaimer (str)."
)

_REVIEW_SYSTEM_PROMPT = (
    "You are the independent sandbox reviewer for a quantitative research app. "
    "You are skeptical, evidence-based, and completely independent from the strategy builder. "
    "You must never be promotional or assume positive returns imply a durable edge. "
    "Your job is to protect the user from overconfidence, not to validate their work. "
    "If the universe contains commodity ETFs (GLD, SLV, USO, UNG, DBA, DBC, etc.), "
    "flag that: (1) ETF price returns exclude roll yield and contango/backwardation costs "
    "which can materially drag real commodity exposure; (2) commodity strategies are highly "
    "regime-dependent — supply shocks, geopolitical events, and dollar cycles dominate; "
    "(3) correlations between commodities and traditional benchmarks like SPY are unstable. "
    "Return a JSON object with exactly these keys: "
    "review_verdict (one of: promising, mixed, skeptical, untrusted), "
    "trust_score (int 0-100, where 50 is neutral), "
    "confidence_level (one of: low, medium, high — reflecting how much data supports any conclusion), "
    "overfitting_risk (one of: low, medium, high), "
    "overfitting_risk_explanation (str — specific reasons, not generic warnings), "
    "benchmark_concerns (list[str]), "
    "regime_dependence_concerns (list[str]), "
    "parameter_sensitivity_concerns (list[str]), "
    "transaction_cost_concerns (list[str]), "
    "sample_size_concerns (list[str]), "
    "data_quality_concerns (list[str]), "
    "main_reasons_to_trust (list[str] — genuine evidence, not wishful thinking), "
    "main_reasons_to_distrust (list[str] — specific, not generic), "
    "required_next_tests (list[str] — concrete and actionable), "
    "suggested_next_experiments (list[str] — specific parameter or universe changes), "
    "final_warning (str — one honest sentence about the biggest risk)."
)


def _explanation_user_prompt(strategy: StrategyJSON, result: BacktestResult) -> str:
    return (
        f"Strategy JSON:\n{strategy.model_dump_json(indent=2)}\n\n"
        f"Backtest result:\n{result.model_dump_json(indent=2)}\n\n"
        "Explain the result and suggest the next research iterations."
    )


def _review_user_prompt(
    strategy: StrategyJSON, result: BacktestResult, iteration_count: int
) -> str:
    iteration_note = (
        f"\nIMPORTANT: The user has run {iteration_count} iteration(s) of this strategy. "
        "If iteration_count > 3, explicitly warn about selection bias — they may be "
        "cherry-picking the best-performing version from multiple trials."
        if iteration_count > 1
        else ""
    )
    return (
        f"Strategy JSON:\n{strategy.model_dump_json(indent=2)}\n\n"
        f"Backtest result:\n{result.model_dump_json(indent=2)}\n\n"
        f"Iteration count: {iteration_count}{iteration_note}\n\n"
        "Critique the result as an independent, skeptical reviewer."
    )


def _locale_instruction(locale: str) -> str:
    return " Respond in Simplified Chinese (中文)." if locale == "zh" else ""


def build_explanation_fallback(
    strategy: StrategyJSON, backtest_result: BacktestResult
) -> ExplanationResponse:
    metrics = backtest_result.metrics
    is_commodity = _is_commodity_universe(strategy.universe)
    strengths = []
    weaknesses = []
    if metrics.excess_return_vs_benchmark > 0:
        strengths.append("The strategy outperformed its benchmark over the tested period.")
    if metrics.max_drawdown > -0.2:
        label = "commodity" if is_commodity else "equity"
        strengths.append(f"Peak-to-trough drawdown stayed relatively contained for a {label} strategy.")
    if metrics.sharpe_ratio < 0.7:
        weaknesses.append("Risk-adjusted returns are still modest.")
    if metrics.number_of_trades < 10:
        weaknesses.append("The trade sample is small, so the result may be noisy.")
    if is_commodity:
        weaknesses.append(
            "Commodity ETF prices exclude roll yield and contango/backwardation costs — "
            "actual commodity exposure may differ materially from this backtest."
        )

    regime_notes = (
        [
            "Commodity strategies are highly regime-dependent: supply shocks, geopolitical events, "
            "and dollar cycles can dominate price action for extended periods.",
            "Trend-following on commodity ETFs works well in persistent trending environments "
            "but can suffer in range-bound or mean-reverting markets.",
        ]
        if is_commodity
        else [
            "Trend-following strategies often shine in persistent uptrends and lag in choppy sideways markets.",
            "A single backtest window cannot guarantee regime robustness.",
        ]
    )

    return ExplanationResponse(
        strategy_summary=(
            f"{strategy.strategy_name} is a {strategy.strategy_type.replace('_', ' ')} "
            f"strategy over {', '.join(strategy.universe)} versus {strategy.benchmark}."
        ),
        performance_explanation=(
            f"The backtest returned {metrics.total_return:.1%} total return with "
            f"{metrics.max_drawdown:.1%} max drawdown and a Sharpe ratio of {metrics.sharpe_ratio:.2f}."
        ),
        strengths=strengths or ["The rules are deterministic and fully specified — no discretion or look-ahead."],
        weaknesses=weaknesses or [
            "Single backtest window — no out-of-sample validation.",
            "Transaction costs and slippage are estimates; real execution may differ materially.",
            "The result still needs parameter sensitivity and sub-period testing before it deserves trust.",
        ],
        market_regime_notes=regime_notes,
        suggested_iterations=[
            "Run the same rules on a different but overlapping date window to check consistency.",
            "Bump transaction costs to 25 bps and 50 bps — if the edge disappears, it is fragile.",
            "Test with a tighter parameter (e.g. shorter lookback) and a looser one to map sensitivity.",
            "Compare against a simple buy-and-hold of the primary ticker to see if the timing adds value.",
        ],
        disclaimer=(
            "Backtest results are hypothetical and subject to data-snooping bias, "
            "optimistic transaction cost assumptions, and look-ahead risk. "
            "Past performance does not predict future results. "
            "This is educational research output, not financial advice or a live trading system."
        ),
    )


def build_sandbox_review_fallback(
    strategy: StrategyJSON, backtest_result: BacktestResult, iteration_count: int = 1
) -> SandboxReviewResponse:
    metrics = backtest_result.metrics
    is_commodity = _is_commodity_universe(strategy.universe)
    trust_score = 50
    sample_concerns: list[str] = []

    if metrics.excess_return_vs_benchmark <= 0:
        trust_score -= 20
        sample_concerns.append("The strategy did not beat the benchmark after tested assumptions.")
    if metrics.number_of_trades < 12:
        trust_score -= 10
        sample_concerns.append("Too few completed trades to estimate edge reliably.")
    if metrics.max_drawdown < -0.35:
        trust_score -= 10
        sample_concerns.append("Max drawdown is severe relative to the claimed edge.")
    if strategy.transaction_cost_bps + strategy.slippage_bps < 5:
        trust_score -= 5
        sample_concerns.append("Execution frictions may still be understated.")
    if iteration_count > 3:
        trust_score -= 10
        sample_concerns.append(
            f"The user has run {iteration_count} iterations — selection bias risk is elevated."
        )

    trust_score = max(min(trust_score, 100), 0)
    verdict = (
        "promising" if trust_score >= 65
        else "untrusted" if trust_score < 25
        else "skeptical" if trust_score < 40
        else "mixed"
    )
    overfitting_risk = (
        "high" if iteration_count > 5
        else "medium" if iteration_count > 2
        else "low"
    )
    confidence_level = (
        "high" if metrics.number_of_trades >= 30
        else "medium" if metrics.number_of_trades >= 10
        else "low"
    )

    commodity_data_concerns = (
        [
            "Commodity ETF prices do not capture roll yield — strategies on USO, UNG, DBA, etc. "
            "reflect ETF price return, not spot commodity return.",
            "Contango and backwardation can create persistent ETF drag or tailwind that "
            "is unrelated to the trading signal.",
        ]
        if is_commodity
        else [
            "Verify adjusted close prices account for dividends and splits correctly.",
        ]
    )

    return SandboxReviewResponse(
        review_verdict=verdict,  # type: ignore[arg-type]
        trust_score=trust_score,
        confidence_level=confidence_level,  # type: ignore[arg-type]
        overfitting_risk=overfitting_risk,  # type: ignore[arg-type]
        overfitting_risk_explanation=(
            f"With {iteration_count} iteration(s), the risk of selecting the best-performing "
            "parameter set from a random walk is non-trivial. Run a parameter sensitivity sweep."
        ),
        benchmark_concerns=[
            "Verify buy-and-hold of the traded asset didn't already capture most of the return.",
            "Compare against a simple benchmark overlay, not only the chosen benchmark.",
        ] + (
            ["DBC is a reasonable commodity benchmark but has different sector weights "
             "than a single-commodity ETF — excess return interpretation requires care."]
            if is_commodity else []
        ),
        regime_dependence_concerns=[
            "Test subperiods separately to confirm the edge isn't concentrated in one regime.",
            "Confirm the result is not dominated by one exceptional rally or crash window.",
        ] + (
            ["Commodity prices are heavily driven by macro regimes (inflation, dollar cycles, "
             "geopolitical events) that are structural, not cyclical — regime risk is elevated."]
            if is_commodity else []
        ),
        parameter_sensitivity_concerns=[
            "Bump each core parameter ±10–20% and see whether the edge survives.",
            "If a small change flips the result, the strategy is fragile.",
        ],
        transaction_cost_concerns=[
            "Stress test with 25 and 50 bps to simulate realistic execution.",
            "High-turnover strategies deserve harsher cost assumptions.",
        ],
        sample_size_concerns=sample_concerns or ["Sample is borderline — more trades would improve confidence."],
        data_quality_concerns=commodity_data_concerns,
        main_reasons_to_trust=[
            "Rules are deterministic and fully specified — no discretion.",
        ] + (["Strategy beat its benchmark."] if metrics.excess_return_vs_benchmark > 0 else []),
        main_reasons_to_distrust=[
            "Single backtest window, no out-of-sample validation.",
        ] + (["Did not beat benchmark."] if metrics.excess_return_vs_benchmark <= 0 else []),
        required_next_tests=[
            "Walk-forward test on a holdout period not used in development.",
            "Parameter sensitivity sweep across at least 6 nearby values.",
            "Sub-period analysis: first half vs second half of backtest window.",
        ],
        suggested_next_experiments=[
            "Test on 2–3 peer tickers using identical rules.",
            "Stress test with 25 bps and 50 bps transaction costs.",
            "Compare against buy-and-hold of the same ticker.",
        ],
        final_warning="A profitable backtest is not evidence of a durable edge until it survives benchmark, regime, and sensitivity checks.",
    )


async def build_explanation(
    strategy: StrategyJSON, backtest_result: BacktestResult, locale: str = "en"
) -> ExplanationResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return build_explanation_fallback(strategy, backtest_result)

    try:
        return await gateway.generate_structured(
            model=get_settings().llm_model,
            system_prompt=_EXPLANATION_SYSTEM_PROMPT + _locale_instruction(locale),
            user_prompt=_explanation_user_prompt(strategy, backtest_result),
            response_model=ExplanationResponse,
            temperature=0.2,
        )
    except LLMAdapterError:
        return build_explanation_fallback(strategy, backtest_result)


async def build_sandbox_review(
    strategy: StrategyJSON,
    backtest_result: BacktestResult,
    locale: str = "en",
    iteration_count: int = 1,
) -> SandboxReviewResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return build_sandbox_review_fallback(strategy, backtest_result, iteration_count)

    try:
        return await gateway.generate_structured(
            model=get_settings().llm_model,
            system_prompt=_REVIEW_SYSTEM_PROMPT + _locale_instruction(locale),
            user_prompt=_review_user_prompt(strategy, backtest_result, iteration_count),
            response_model=SandboxReviewResponse,
            temperature=0.2,
        )
    except LLMAdapterError:
        return build_sandbox_review_fallback(strategy, backtest_result, iteration_count)
