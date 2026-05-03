"""Tests for RobustnessService — verify output shapes without live DB/API."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.backtest import BacktestMetrics, BacktestResult
from app.schemas.robustness import (
    ParameterSensitivityRow,
    SubperiodRow,
    TransactionCostRow,
)
from app.schemas.strategy import (
    CashManagement,
    PositionSizing,
    RiskManagement,
    StrategyJSON,
    StrategyRule,
)
from app.services.robustness_service import RobustnessService


def _minimal_strategy(**overrides) -> StrategyJSON:
    base = dict(
        strategy_name="Test MA",
        strategy_type="moving_average_crossover",
        universe=["AAPL"],
        benchmark="SPY",
        start_date=date(2023, 1, 1),
        end_date=date(2024, 1, 1),
        initial_capital=100_000,
        rebalance_frequency="daily",
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=[StrategyRule(fast_window=50, slow_window=200)],
        position_sizing=PositionSizing(method="equal_weight", max_positions=1),
        risk_management=RiskManagement(),
        cash_management=CashManagement(hold_cash_when_no_signal=True),
    )
    base.update(overrides)
    return StrategyJSON(**base)


def _fake_backtest_result(total_return=0.05, sharpe=0.8, drawdown=-0.1, trades=5) -> BacktestResult:
    metrics = BacktestMetrics(
        total_return=total_return, annualized_return=total_return,
        annualized_volatility=0.15, sharpe_ratio=sharpe, sortino_ratio=0.9,
        max_drawdown=drawdown, calmar_ratio=0.5, win_rate=0.6,
        number_of_trades=trades, average_trade_return=0.01,
        best_trade=0.05, worst_trade=-0.02, average_holding_period=20,
        benchmark_total_return=0.10, excess_return_vs_benchmark=-0.05,
        alpha_vs_benchmark=0.01, beta_vs_benchmark=0.8,
        turnover=0.1, time_in_market=0.7,
    )
    return BacktestResult(
        backtest_id="test-id",
        strategy_json=_minimal_strategy(),
        metrics=metrics,
        equity_curve=[], benchmark_curve=[], buy_and_hold_curve=[],
        drawdown_curve=[], trade_log=[], annual_returns=[], monthly_returns=[],
        warnings=[],
    )


@pytest.mark.asyncio
async def test_transaction_cost_returns_correct_number_of_rows():
    svc = RobustnessService()
    strategy = _minimal_strategy()

    with patch("app.services.robustness_service._engine") as mock_engine:
        mock_engine.run = AsyncMock(return_value=_fake_backtest_result())
        rows = await svc.run_transaction_cost(MagicMock(), strategy, baseline_return=0.05)

    assert len(rows) == 5  # 0, 5, 10, 25, 50 bps
    assert all(isinstance(r, TransactionCostRow) for r in rows)
    assert rows[0].cost_bps == 0
    assert rows[-1].cost_bps == 50


@pytest.mark.asyncio
async def test_transaction_cost_verdict_breaks_down_on_negative_sharpe():
    svc = RobustnessService()
    strategy = _minimal_strategy()

    with patch("app.services.robustness_service._engine") as mock_engine:
        mock_engine.run = AsyncMock(return_value=_fake_backtest_result(sharpe=-0.1))
        rows = await svc.run_transaction_cost(MagicMock(), strategy, baseline_return=0.05)

    assert all(r.verdict == "breaks_down" for r in rows)


@pytest.mark.asyncio
async def test_subperiod_returns_at_least_three_periods():
    svc = RobustnessService()
    strategy = _minimal_strategy()

    with patch("app.services.robustness_service._engine") as mock_engine:
        mock_engine.run = AsyncMock(return_value=_fake_backtest_result())
        rows = await svc.run_subperiod(MagicMock(), strategy)

    labels = [r.period for r in rows]
    assert "Full Period" in labels
    assert "First Half" in labels
    assert "Second Half" in labels
    assert all(isinstance(r, SubperiodRow) for r in rows)


@pytest.mark.asyncio
async def test_parameter_sensitivity_ma_crossover_skips_invalid_combos():
    svc = RobustnessService()
    strategy = _minimal_strategy()

    with patch("app.services.robustness_service._engine") as mock_engine:
        mock_engine.run = AsyncMock(return_value=_fake_backtest_result())
        rows = await svc.run_parameter_sensitivity(MagicMock(), strategy, None, baseline_sharpe=0.8)

    # fast >= slow combos must be filtered out
    for row in rows:
        fast = row.parameter_set.get("fast", 0)
        slow = row.parameter_set.get("slow", 999)
        assert fast < slow, f"Invalid combo: fast={fast} slow={slow}"
    assert all(isinstance(r, ParameterSensitivityRow) for r in rows)


@pytest.mark.asyncio
async def test_peer_ticker_skips_when_multi_asset_strategy():
    svc = RobustnessService()
    strategy = _minimal_strategy(universe=["AAPL", "MSFT"])  # multi-asset

    rows = await svc.run_peer_ticker(MagicMock(), strategy, ["GOOGL", "AMZN"])
    assert rows == []  # peer test only applies to single-asset strategies


@pytest.mark.asyncio
async def test_peer_ticker_returns_error_row_on_failed_backtest():
    svc = RobustnessService()
    strategy = _minimal_strategy()

    with patch("app.services.robustness_service._engine") as mock_engine:
        mock_engine.run = AsyncMock(side_effect=[
            _fake_backtest_result(),          # baseline
            Exception("No data for FAKE"),   # peer ticker fails
        ])
        rows = await svc.run_peer_ticker(MagicMock(), strategy, ["FAKE"])

    assert len(rows) == 1
    assert rows[0].ticker == "FAKE"
    assert rows[0].verdict == "error"
    assert rows[0].error is not None
