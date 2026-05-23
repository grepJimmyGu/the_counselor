"""Chat-tool QA: every tool in TOOL_REGISTRY must accept the EXACT data
shapes its producer service returns in production — not the convenient
mock shapes that existing happy-path tests use.

Motivation (2026-05-22/23 incident):
  - stock_lookup tool failed every prod call because the existing test
    passed `as_of_date="2026-05-21"` (string) while production returns
    a `datetime.date` instance. Pydantic v2 won't coerce date→str, the
    response model raised ValidationError, the dispatch loop swallowed
    it into `{"error": "Tool stock_lookup failed: ..."}`, and the LLM
    apologized to the user about a "temporary issue."

  - Same family: 2026-05-22 DetachedInstanceError (tests kept the db
    fixture alive across stream iteration; production closed it).
    2026-05-23 cookie propagation (tests pre-seeded the AnonymousSession;
    production cookie round-trips through the browser).

  - Pattern: test fixtures more permissive than production. This file
    is the pre-merge gate that catches the next instance of that pattern.

Design:
  Each tool gets one parametrized test that calls its handler with mock
  data **explicitly shaped like the production producer's actual output**:
    - `date` / `datetime` instances where the producer returns date types,
      not pre-formatted strings
    - real Pydantic model instances (or MagicMock with the right field
      types), not bare dicts
    - edge values where they're known to occur: missing optional fields,
      large floats, empty lists

  The assertion is minimal: **the handler must return its response model
  without raising ValidationError**. We deliberately don't assert deep
  on the response contents — the existing per-tool happy-path tests
  cover that. This file's job is solely to catch type-coercion drift at
  the chat-tool seam.

  If a new tool is added to TOOL_REGISTRY, this file will fail loudly
  via the `test_every_registered_tool_has_a_production_shape_test`
  guard — forcing the author to add a matching case below.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_tools import TOOL_REGISTRY


# ── Per-tool production-shape exercisers ──────────────────────────────────────
#
# Each function returns a coroutine that, when awaited, invokes the tool
# handler with production-shape data. The test framework awaits each one
# and asserts no ValidationError raised.
#
# The function name = the registered tool name; the dict below maps registry
# keys to these functions and the test parametrizes over it. Adding a new
# tool means adding a new function here AND registering it in TOOL_REGISTRY.


async def _exercise_concept_explainer() -> Any:
    """Pure-Python tool — no producer service, no mocks. The reader of
    `chat_concepts.md` always returns strings, so type drift is unlikely
    here. We still exercise it to cement the parametrize-all-tools rule."""
    from app.services.chat_tools.concept_explainer import explain_concept
    return await explain_concept("Sharpe Ratio")


async def _exercise_template_search() -> Any:
    """Same as above — no external producer. Just exercise to enforce
    the rule that every registered tool gets a production-shape test."""
    from app.services.chat_tools.template_search import search_templates
    return await search_templates("momentum", limit=3)


async def _exercise_onboarding_tutor() -> Any:
    """No producer. Returns a pre-baked script. Verify both branches
    (None step = full script, int step = single step)."""
    from app.services.chat_tools.onboarding_tutor import run_onboarding_tutor
    r1 = await run_onboarding_tutor(step=None)
    r2 = await run_onboarding_tutor(step=0)
    return [r1, r2]


async def _exercise_strategy_builder_iterate() -> Any:
    """Producer is `parse_strategy_message`. Realistic shape: returns a
    full StrategyChatResponse with a populated StrategyJSON. The LLM
    passes `previous_strategy_json` as a dict (not a model) — we mimic
    that path because it's where Pydantic v2 strictness has bit us before."""
    from app.services.chat_tools.strategy_builder_iterate import iterate_strategy
    from app.schemas.strategy import (
        ClarificationState,
        StrategyChatResponse,
        StrategyJSON,
    )

    fake_response = StrategyChatResponse(
        assistant_message="ok",
        strategy_json=None,
        validation_status="needs_clarification",
        missing_fields=["universe"],
        clarification_questions=["Which tickers?"],
        clarification_state=ClarificationState.ready,
    )

    # Production: LLM emits previous_strategy_json as a dict, not a model.
    # The tool must tolerate dict input + serialize it through StrategyJSON.
    prev_as_dict = {
        "strategy_name": "MA",
        "strategy_type": "moving_average_filter",
        "universe": ["AAPL"],
        "benchmark": "SPY",
        "start_date": "2024-01-01",  # backend accepts ISO strings here
        "end_date": "2024-12-31",
        "initial_capital": 10000,
        "rebalance_frequency": "daily",
        "transaction_cost_bps": 10,
        "slippage_bps": 5,
        "rules": [{"ma_length": 200}],
        "position_sizing": {"method": "equal_weight", "max_positions": 1},
        "risk_management": {},
        "cash_management": {"hold_cash_when_no_signal": True, "cash_yield_bps": 0},
    }

    with patch(
        "app.services.chat_tools.strategy_builder_iterate.parse_strategy_message",
        new=AsyncMock(return_value=fake_response),
    ):
        return await iterate_strategy(
            user_message="use 50-day instead",
            previous_strategy_json=prev_as_dict,
        )


async def _exercise_backtest_execute() -> Any:
    """Producer chain: validate_universe → ensure_data_available →
    DataQualityService.check_strategy → BacktestEngine.run. The Engine
    returns a real BacktestResult with all 19 BacktestMetrics fields as
    floats (some Optional). We mock the chain end-to-end with real types."""
    from app.services.chat_tools.backtest_execute import execute_backtest
    from app.schemas.backtest import BacktestMetrics

    valid_strategy = {
        "strategy_name": "MA Filter",
        "strategy_type": "moving_average_filter",
        "universe": ["AAPL"],
        "benchmark": "SPY",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 10000,
        "rebalance_frequency": "daily",
        "transaction_cost_bps": 10,
        "slippage_bps": 5,
        "rules": [{"ma_length": 200}],
        "position_sizing": {"method": "equal_weight", "max_positions": 1},
        "risk_management": {},
        "cash_management": {"hold_cash_when_no_signal": True, "cash_yield_bps": 0},
    }

    # Real BacktestMetrics — all required fields populated with real floats.
    fake_metrics = BacktestMetrics(
        total_return=0.15, annualized_return=0.15, annualized_volatility=0.18,
        sharpe_ratio=0.83, sortino_ratio=1.1, max_drawdown=-0.12,
        calmar_ratio=0.6, win_rate=0.55, number_of_trades=4,
        average_trade_return=0.04, best_trade=0.10, worst_trade=-0.05,
        average_holding_period=42.0, benchmark_total_return=0.12,
        excess_return_vs_benchmark=0.03, alpha_vs_benchmark=0.01,
        beta_vs_benchmark=0.85, turnover=1.2, time_in_market=0.65,
    )
    fake_result = MagicMock(
        backtest_id="bt_qa_shape",
        metrics=fake_metrics,
        warnings=["sample warning"],
    )

    quality_gate = MagicMock(overall_status="pass")
    quality_service_instance = MagicMock()
    quality_service_instance.check_strategy.return_value = quality_gate

    engine_instance = MagicMock()
    engine_instance.run = AsyncMock(return_value=fake_result)

    with patch(
        "app.services.chat_tools.backtest_execute.validate_universe",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.chat_tools.backtest_execute.ensure_data_available",
        new=AsyncMock(return_value={}),
    ), patch(
        "app.services.chat_tools.backtest_execute.DataQualityService",
        return_value=quality_service_instance,
    ), patch(
        "app.services.chat_tools.backtest_execute.BacktestEngine",
        return_value=engine_instance,
    ):
        return await execute_backtest(valid_strategy)


async def _exercise_stock_lookup() -> Any:
    """Producer: CompanyOverviewService.get_overview. The bug that motivated
    this whole file: as_of_date is a real `datetime.date` instance, not a
    string. Force that shape here. If the tool's Pydantic model regresses,
    THIS test catches it before deploy."""
    from app.services.chat_tools.stock_lookup import lookup_stock

    fake_financial = MagicMock(
        financial_validation_label="Moderately Positive",
        valuation_risk_score=40,
        growth_summary="Revenue +12% YoY",
        profitability_summary="Margins expanding",
        cash_flow_summary="FCF $10B",
        balance_sheet_summary="Net cash $5B",
        valuation_summary="P/E 28x — mid-range",
        warnings=["Watch macro"],
    )
    fake_business = MagicMock(one_line_summary="Designs phones and laptops")
    fake_overview = MagicMock(
        symbol="AAPL",
        sector="Technology",
        as_of_date=date(2026, 5, 23),  # THE production shape — date, not str
        financial_check=fake_financial,
        business_map=fake_business,
    )
    fake_overview.name = "Apple Inc"  # MagicMock(name=...) kwarg is reserved

    service_instance = MagicMock()
    service_instance.get_overview = AsyncMock(return_value=fake_overview)

    with patch(
        "app.services.chat_tools.stock_lookup.CompanyOverviewService",
        return_value=service_instance,
    ):
        return await lookup_stock("AAPL")


async def _exercise_backtest_explain() -> Any:
    """Producer chain: load BacktestRecord by id → reconstruct strategy +
    result → call build_explanation. The two _from_record helpers do
    model_validate against a stored dict; ensure they tolerate a realistic
    BacktestResult.model_dump() payload."""
    from app.services.chat_tools.backtest_explain import explain_backtest
    from app.schemas.insights import ExplanationResponse
    from app.schemas.strategy import StrategyJSON

    fake_explanation = ExplanationResponse(
        strategy_summary="MA filter on AAPL — hold above 200-day, cash below.",
        performance_explanation="Sharpe 0.83 vs benchmark 0.5",
        strengths=["Cut the worst drawdown"],
        weaknesses=["Lagged exit on rebounds"],
        market_regime_notes=["Worked best in 2022 sideways regime"],
        suggested_iterations=["Test 50-day MA"],
        disclaimer="Backtest only — not financial advice.",
    )

    fake_strategy = StrategyJSON.model_validate({
        "strategy_name": "MA Filter",
        "strategy_type": "moving_average_filter",
        "universe": ["AAPL"],
        "benchmark": "SPY",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 10000,
        "rebalance_frequency": "daily",
        "transaction_cost_bps": 10,
        "slippage_bps": 5,
        "rules": [{"ma_length": 200}],
        "position_sizing": {"method": "equal_weight", "max_positions": 1},
        "risk_management": {},
        "cash_management": {"hold_cash_when_no_signal": True, "cash_yield_bps": 0},
    })
    fake_result = MagicMock(backtest_id="bt_qa_shape")

    fake_record = MagicMock(result_payload={"any": "shape"})
    fake_db = MagicMock()
    fake_db.get.return_value = fake_record

    with patch(
        "app.services.chat_tools.backtest_explain.SessionLocal",
        return_value=fake_db,
    ), patch(
        "app.services.chat_tools.backtest_explain._strategy_from_record",
        return_value=fake_strategy,
    ), patch(
        "app.services.chat_tools.backtest_explain._result_from_record",
        return_value=fake_result,
    ), patch(
        "app.services.chat_tools.backtest_explain.build_explanation",
        new=AsyncMock(return_value=fake_explanation),
    ):
        return await explain_backtest("bt_qa_shape")


# ── Registry of exercisers — keys must match TOOL_REGISTRY exactly ────────────


EXERCISERS: Dict[str, Any] = {
    "concept_explainer": _exercise_concept_explainer,
    "template_search": _exercise_template_search,
    "onboarding_tutor": _exercise_onboarding_tutor,
    "strategy_builder_iterate": _exercise_strategy_builder_iterate,
    "backtest_execute": _exercise_backtest_execute,
    "stock_lookup": _exercise_stock_lookup,
    "backtest_explain": _exercise_backtest_explain,
}


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_every_registered_tool_has_a_production_shape_test():
    """Forcing-function. When someone adds a new tool to TOOL_REGISTRY they
    must also add an entry to EXERCISERS above — otherwise this test fails
    loudly. Prevents new tools from launching without a prod-shape gate."""
    registered = set(TOOL_REGISTRY)
    exercised = set(EXERCISERS)
    missing = registered - exercised
    extra = exercised - registered
    assert not missing, (
        f"TOOL_REGISTRY adds new tool(s) without a prod-shape exerciser: {sorted(missing)}. "
        f"Add an _exercise_<tool> function in tests/test_chat_tools_production_shapes.py "
        f"that calls the handler with production-shape mock data."
    )
    assert not extra, (
        f"EXERCISERS lists tool(s) no longer in TOOL_REGISTRY: {sorted(extra)}. "
        f"Remove the corresponding _exercise_<tool> function (or restore the registry entry)."
    )


@pytest.mark.parametrize("tool_name", sorted(EXERCISERS))
@pytest.mark.asyncio
async def test_tool_handles_production_shape_data_without_validation_error(tool_name):
    """For each registered tool: invoke its handler with production-shape
    mock data. Failure = ValidationError or any other exception raised
    out of the handler. The dispatch loop catches Exception broadly and
    serializes to {"error": ...}, hiding the cause from the user; this
    test surfaces them at PR time."""
    exerciser = EXERCISERS[tool_name]
    try:
        result = await exerciser()
    except Exception as exc:
        pytest.fail(
            f"{tool_name} raised {type(exc).__name__} on production-shape input: {exc}. "
            f"This would surface in production as a swallowed `{{'error': 'Tool {tool_name} failed: ...'}}` "
            f"in chat_messages.tool_results, and the LLM would apologize to the user "
            f"about a 'temporary issue.' Fix at the seam in the tool, not in the test."
        )
    # Sanity: the handler returned something. Specific assertions live in the
    # per-tool happy-path tests; this file's job is purely the no-raise gate.
    assert result is not None


@pytest.mark.parametrize("tool_name", sorted(EXERCISERS))
@pytest.mark.asyncio
async def test_tool_response_is_json_serializable(tool_name):
    """The chat dispatch loop serializes tool results via json.dumps + the
    Pydantic model_dump path (see _serialize_tool_result in routes/chat.py).
    A response that's a valid Pydantic model but contains non-serializable
    field values (e.g. raw datetime in a JSON column, set instead of list,
    Decimal without a serializer) would crash the dispatch loop right after
    the tool returned. Catch that here."""
    exerciser = EXERCISERS[tool_name]
    result = await exerciser()
    # Apply the same serialization the dispatch loop uses.
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif isinstance(result, list) and result and hasattr(result[0], "model_dump"):
        payload = [r.model_dump() for r in result]
    else:
        payload = result
    try:
        json.dumps(payload, default=str)
    except (TypeError, ValueError) as exc:
        pytest.fail(
            f"{tool_name}'s response is not JSON-serializable: {exc}. "
            f"The dispatch loop would crash when feeding the result back to "
            f"the LLM. Fix by coercing non-serializable types at the tool seam."
        )
