"""Unit tests for the 4 heavier chat tools (Stage 7 / ticket #4).

Each tool wraps an existing service; the tests verify the wrap rather
than re-testing the wrapped service. Patterns:

  - LLM-touching tools (strategy_builder_iterate, backtest_explain): patch
    the underlying service to return a canned response, assert the tool
    surfaces it.
  - DB-touching tools (backtest_execute, stock_lookup, backtest_explain):
    patch the DB-needing call to avoid running a real backtest / hitting
    Alpha Vantage in unit tests. Engine + service mocks live in this file
    (no shared fixture — keeps each test's setup explicit).
  - Error paths: all 4 tools catch exceptions internally and return an
    `error` field rather than propagating; verify each error case lands
    in the response shape.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_tools.backtest_execute import (
    BacktestExecuteResponse,
    execute_backtest,
)
from app.services.chat_tools.backtest_explain import (
    BacktestExplainResponse,
    explain_backtest,
)
from app.services.chat_tools.stock_lookup import (
    StockLookupResponse,
    lookup_stock,
)
from app.services.chat_tools.strategy_builder_iterate import iterate_strategy


# ── strategy_builder_iterate ──────────────────────────────────────────────────


def _fake_chat_response(message: str = "ok"):
    """Build a minimal valid StrategyChatResponse for tests."""
    from app.schemas.strategy import ClarificationState, StrategyChatResponse

    return StrategyChatResponse(
        assistant_message=message,
        strategy_json=None,
        validation_status="needs_clarification",
        missing_fields=[],
        clarification_questions=[],
        clarification_state=ClarificationState.ready,
    )


@pytest.mark.asyncio
async def test_iterate_strategy_passes_through_parser():
    """The tool is a thin pass-through; verify the parser's return is
    surfaced and the previous-strategy argument is forwarded."""
    fake_response = _fake_chat_response()

    with patch(
        "app.services.chat_tools.strategy_builder_iterate.parse_strategy_message",
        new=AsyncMock(return_value=fake_response),
    ) as mock_parse:
        result = await iterate_strategy(
            user_message="Build a momentum strategy",
            previous_strategy_json=None,
        )

    assert result is fake_response
    mock_parse.assert_awaited_once()
    kwargs = mock_parse.await_args.kwargs
    assert kwargs["user_message"] == "Build a momentum strategy"
    assert kwargs["previous_strategy_json"] is None
    assert kwargs["locale"] == "en"


@pytest.mark.asyncio
async def test_iterate_strategy_silently_drops_invalid_previous_strategy():
    """If the LLM passes a malformed `previous_strategy_json`, we drop it
    rather than 500ing — parser starts fresh from the new user message."""
    with patch(
        "app.services.chat_tools.strategy_builder_iterate.parse_strategy_message",
        new=AsyncMock(return_value=_fake_chat_response()),
    ) as mock_parse:
        await iterate_strategy(
            user_message="moar momentum",
            previous_strategy_json={"this": "is not a valid strategy"},
        )

    # parser called with previous=None because validation failed silently
    assert mock_parse.await_args.kwargs["previous_strategy_json"] is None


# ── backtest_execute ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_backtest_invalid_strategy_returns_error():
    """Malformed strategy JSON → success=False, no engine run attempted."""
    response = await execute_backtest({"not_a_strategy": True})

    assert isinstance(response, BacktestExecuteResponse)
    assert response.success is False
    assert response.error is not None
    assert "Invalid strategy JSON" in response.error


@pytest.mark.asyncio
async def test_execute_backtest_unknown_ticker_returns_error():
    """validate_universe returns invalid tickers → tool reports them."""
    valid_strategy = {
        "strategy_name": "Test",
        "strategy_type": "moving_average_filter",
        "universe": ["XXXX"],  # not a real ticker
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

    with patch(
        "app.services.chat_tools.backtest_execute.validate_universe",
        new=AsyncMock(return_value=["XXXX"]),
    ):
        response = await execute_backtest(valid_strategy)

    assert response.success is False
    assert "XXXX" in (response.error or "")


@pytest.mark.asyncio
async def test_execute_backtest_happy_path_returns_summary():
    """When all pre-flight passes + engine returns, tool returns headline
    metrics including backtest_id (for follow-up `backtest_explain`)."""
    from app.schemas.backtest import BacktestMetrics, BacktestResult

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

    fake_metrics = BacktestMetrics(
        total_return=0.15,
        annualized_return=0.15,
        annualized_volatility=0.18,
        sharpe_ratio=0.83,
        sortino_ratio=1.1,
        max_drawdown=-0.12,
        calmar_ratio=0.6,
        win_rate=0.55,
        number_of_trades=4,
        average_trade_return=0.04,
        best_trade=0.10,
        worst_trade=-0.05,
        average_holding_period=42.0,
        benchmark_total_return=0.12,
        excess_return_vs_benchmark=0.03,
        alpha_vs_benchmark=0.01,
        beta_vs_benchmark=0.85,
        turnover=1.2,
        time_in_market=0.65,
    )
    # The tool reads `result.metrics.*` and `result.warnings`; everything else
    # on BacktestResult is irrelevant to ticket #4's wrap. Stub a MagicMock
    # rather than full-populating every list to keep the test focused.
    fake_result = MagicMock(
        backtest_id="bt_test_abc",
        metrics=fake_metrics,
        warnings=["Sample warning"],
    )

    quality_gate = MagicMock()
    quality_gate.overall_status = "pass"

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
        response = await execute_backtest(valid_strategy)

    assert response.success is True
    assert response.backtest_id == "bt_test_abc"
    assert response.strategy_name == "MA Filter"
    assert response.total_return == 0.15
    assert response.sharpe_ratio == 0.83
    assert response.max_drawdown == -0.12
    assert response.n_trades == 4  # matches BacktestMetrics.number_of_trades
    assert response.benchmark == "SPY"
    assert response.benchmark_total_return == 0.12
    assert "Sample warning" in response.warnings


@pytest.mark.asyncio
async def test_execute_backtest_engine_failure_returns_error():
    """If engine.run raises, tool catches and surfaces in `error`."""
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

    quality_gate = MagicMock()
    quality_gate.overall_status = "pass"

    quality_service_instance = MagicMock()
    quality_service_instance.check_strategy.return_value = quality_gate

    engine_instance = MagicMock()
    engine_instance.run = AsyncMock(side_effect=RuntimeError("engine broke"))

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
        response = await execute_backtest(valid_strategy)

    assert response.success is False
    assert "engine broke" in (response.error or "")


# ── stock_lookup ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lookup_stock_empty_ticker_returns_error():
    response = await lookup_stock("   ")
    assert response.success is False
    assert response.error == "Empty ticker."


@pytest.mark.asyncio
async def test_lookup_stock_unknown_ticker_returns_error():
    """When the underlying overview service raises, tool catches it."""
    service_instance = MagicMock()
    service_instance.get_overview = AsyncMock(side_effect=KeyError("no such symbol"))

    with patch(
        "app.services.chat_tools.stock_lookup.CompanyOverviewService",
        return_value=service_instance,
    ):
        response = await lookup_stock("ZZZ")

    assert response.success is False
    assert "ZZZ" in (response.error or "")


@pytest.mark.asyncio
async def test_lookup_stock_coerces_date_as_of_to_isoformat_string():
    """Regression for 2026-05-23 production bug.

    `CompanyOverviewResponse.as_of_date` is `datetime.date`, but
    `StockLookupResponse.as_of` is `Optional[str]`. Pydantic v2 is strict
    and won't auto-coerce date→str, so the entire tool call raised
    "Input should be a valid string". The exception propagated up to the
    dispatch loop's defensive `except Exception:`, which serialized as
    `{"error": "Tool stock_lookup failed: ..."}` — the LLM read that as a
    backend issue and apologized to the user. The user saw "It seems there
    is a temporary issue retrieving the health and valuation metrics for
    Apple Inc. (AAPL)" with two "Used stock_lookup" chips (LLM retried once).

    Fix: coerce `as_of_date.isoformat()` at the seam. This test forces a
    `date` instance and asserts the response field is the ISO string."""
    fake_financial = MagicMock(
        financial_validation_label="Neutral",
        valuation_risk_score=50,
        growth_summary=None, profitability_summary=None,
        cash_flow_summary=None, balance_sheet_summary=None,
        valuation_summary=None, warnings=[],
    )
    fake_business = MagicMock(one_line_summary=None)
    fake_overview = MagicMock(
        symbol="AAPL",
        sector="Technology",
        as_of_date=date(2026, 5, 23),  # the actual prod failure shape
        financial_check=fake_financial,
        business_map=fake_business,
    )
    fake_overview.name = "Apple Inc"

    service_instance = MagicMock()
    service_instance.get_overview = AsyncMock(return_value=fake_overview)

    with patch(
        "app.services.chat_tools.stock_lookup.CompanyOverviewService",
        return_value=service_instance,
    ):
        response = await lookup_stock("AAPL")

    # Before the fix this assertion never ran — the call raised.
    assert response.success is True
    # And the value must be a STRING (ISO format), not a date instance.
    assert isinstance(response.as_of, str), (
        f"as_of should be ISO string, got {type(response.as_of).__name__}"
    )
    assert response.as_of == "2026-05-23"


@pytest.mark.asyncio
async def test_lookup_stock_happy_path_returns_scorecard():
    """Successful overview → tool returns health/val/trend bundle.

    Note: `name` is a reserved MagicMock kwarg (sets the mock's debug name,
    not a `.name` attribute) — assign explicitly via attribute set.
    """
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
        as_of_date="2026-05-21",
        financial_check=fake_financial,
        business_map=fake_business,
    )
    fake_overview.name = "Apple Inc"  # cannot pass via MagicMock kwarg (reserved)

    service_instance = MagicMock()
    service_instance.get_overview = AsyncMock(return_value=fake_overview)

    with patch(
        "app.services.chat_tools.stock_lookup.CompanyOverviewService",
        return_value=service_instance,
    ):
        response = await lookup_stock("aapl")

    assert isinstance(response, StockLookupResponse)
    assert response.success is True
    assert response.ticker == "AAPL"
    assert response.health is not None
    assert response.health.score == "Moderately Positive"
    assert response.valuation is not None
    # valuation_risk_score=40 → Neutral (33 <= 40 < 66)
    assert response.valuation.score == "Neutral"
    assert response.one_line_summary == "Designs phones and laptops"


@pytest.mark.asyncio
async def test_lookup_stock_valuation_score_buckets():
    """The score-bucket heuristic: <33 = positive, 33-65 = neutral, >=66 = caution."""

    async def _run_for_risk_score(risk_score):
        fake_overview = MagicMock(
            symbol="AAPL", sector=None, as_of_date=None,
            financial_check=MagicMock(
                financial_validation_label="Neutral",
                valuation_risk_score=risk_score,
                growth_summary=None, profitability_summary=None,
                cash_flow_summary=None, balance_sheet_summary=None,
                valuation_summary=None, warnings=[],
            ),
            business_map=MagicMock(one_line_summary=None),
        )
        fake_overview.name = None  # see above re: reserved MagicMock kwarg
        service_instance = MagicMock()
        service_instance.get_overview = AsyncMock(return_value=fake_overview)
        with patch(
            "app.services.chat_tools.stock_lookup.CompanyOverviewService",
            return_value=service_instance,
        ):
            return await lookup_stock("AAPL")

    cheap = await _run_for_risk_score(10)
    assert cheap.valuation.score == "Strongly Positive"

    mid = await _run_for_risk_score(50)
    assert mid.valuation.score == "Neutral"

    expensive = await _run_for_risk_score(85)
    assert expensive.valuation.score == "Caution"


# ── backtest_explain ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_backtest_empty_id_returns_error():
    response = await explain_backtest("   ")
    assert response.success is False
    assert response.error == "Empty backtest_id."


@pytest.mark.asyncio
async def test_explain_backtest_unknown_id_returns_error():
    """No such record → tool reports it rather than raising."""
    fake_db = MagicMock()
    fake_db.get.return_value = None

    with patch(
        "app.services.chat_tools.backtest_explain.SessionLocal",
        return_value=fake_db,
    ):
        response = await explain_backtest("bt_nonexistent")

    assert response.success is False
    assert "bt_nonexistent" in (response.error or "")


@pytest.mark.asyncio
async def test_explain_backtest_legacy_record_without_strategy_payload():
    """Record exists but `result_payload` is missing strategy → tool reports."""
    legacy_record = MagicMock(result_payload={"backtest_id": "bt_x"})  # no 'strategy'
    fake_db = MagicMock()
    fake_db.get.return_value = legacy_record

    with patch(
        "app.services.chat_tools.backtest_explain.SessionLocal",
        return_value=fake_db,
    ):
        response = await explain_backtest("bt_x")

    assert response.success is False
    assert "missing the strategy" in (response.error or "")


@pytest.mark.asyncio
async def test_explain_backtest_happy_path_returns_explanation():
    """Record + strategy + valid result → explainer called → response carries it."""
    from app.schemas.insights import ExplanationResponse

    fake_explanation = ExplanationResponse(
        strategy_summary="MA filter on AAPL — hold above 200-day, cash below.",
        performance_explanation="Sharpe 0.83 vs benchmark 0.5; filter sidestepped 2022.",
        strengths=["Cut the worst drawdown"],
        weaknesses=["Lagged exit on rebounds"],
        market_regime_notes=["Worked best in 2022 sideways regime"],
        suggested_iterations=["Test 50-day MA", "Add 3% buffer below MA"],
        disclaimer="Backtest only — not financial advice.",
    )

    # The tool's two helpers (_strategy_from_record, _result_from_record)
    # do model_validate against the stored payload. Patching them lets us
    # avoid constructing a fully-populated BacktestResult dict (≥9 required
    # fields, several nested lists) — the wrap logic is what's under test,
    # not Pydantic validation of canonical schemas.
    from app.schemas.strategy import StrategyJSON

    strategy_for_test = StrategyJSON.model_validate({
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
    result_for_test = MagicMock(backtest_id="bt_abc")

    fake_record = MagicMock(result_payload={"strategy_json": "ignored — _from_record is patched"})
    fake_db = MagicMock()
    fake_db.get.return_value = fake_record

    with patch(
        "app.services.chat_tools.backtest_explain.SessionLocal",
        return_value=fake_db,
    ), patch(
        "app.services.chat_tools.backtest_explain._strategy_from_record",
        return_value=strategy_for_test,
    ), patch(
        "app.services.chat_tools.backtest_explain._result_from_record",
        return_value=result_for_test,
    ), patch(
        "app.services.chat_tools.backtest_explain.build_explanation",
        new=AsyncMock(return_value=fake_explanation),
    ):
        response = await explain_backtest("bt_abc")

    assert isinstance(response, BacktestExplainResponse)
    assert response.success is True
    assert response.backtest_id == "bt_abc"
    assert response.explanation is fake_explanation


# ── registry includes all 4 heavier tools ─────────────────────────────────────


def test_heavier_tools_registered():
    """Each of the 4 ticket #4 tools must be in TOOL_REGISTRY with a schema."""
    from app.services.chat_tools import TOOL_REGISTRY, get_openai_tool_specs

    for name in (
        "strategy_builder_iterate",
        "backtest_execute",
        "stock_lookup",
        "backtest_explain",
    ):
        assert name in TOOL_REGISTRY
        assert TOOL_REGISTRY[name]["handler"] is not None
        assert TOOL_REGISTRY[name]["parameters"]["type"] == "object"

    spec_names = {s["function"]["name"] for s in get_openai_tool_specs()}
    assert {"strategy_builder_iterate", "backtest_execute", "stock_lookup", "backtest_explain"}.issubset(spec_names)
