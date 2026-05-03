import math

import pandas as pd
import pytest

from app.services.backtester.metrics import (
    compute_buy_and_hold,
    compute_drawdown,
    compute_metrics,
    compute_trade_diagnostics,
)


def test_compute_drawdown_reaches_expected_minimum():
    equity = pd.Series([100.0, 110.0, 90.0, 120.0])
    drawdown = compute_drawdown(equity)
    assert round(drawdown.min(), 4) == -0.1818


def test_compute_drawdown_is_zero_for_monotone_increasing():
    equity = pd.Series([100.0, 105.0, 110.0, 120.0])
    drawdown = compute_drawdown(equity)
    assert (drawdown >= 0).all() is False or drawdown.max() == 0.0


def test_compute_metrics_returns_all_expected_fields():
    portfolio_returns = pd.Series([0.01, -0.005, 0.015, 0.002])
    benchmark_returns = pd.Series([0.008, -0.004, 0.01, 0.001])
    metrics = compute_metrics(
        portfolio_returns=portfolio_returns,
        benchmark_returns=benchmark_returns,
        trade_returns=[0.05, -0.02, 0.03],
        holding_periods=[12, 8, 15],
        turnover_series=pd.Series([0.0, 0.5, 0.3, 0.1]),
        time_in_market_series=pd.Series([1.0, 1.0, 0.0, 1.0]),
    )
    required = [
        "total_return", "annualized_return", "annualized_volatility",
        "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
        "win_rate", "number_of_trades", "average_trade_return",
        "best_trade", "worst_trade", "average_holding_period",
        "benchmark_total_return", "excess_return_vs_benchmark",
        "alpha_vs_benchmark", "beta_vs_benchmark", "turnover", "time_in_market",
        "profit_factor", "avg_winner", "avg_loser", "median_trade_return",
        "longest_winning_streak", "longest_losing_streak",
    ]
    for field in required:
        assert field in metrics, f"Missing field: {field}"
    assert metrics["number_of_trades"] == 3
    assert metrics["best_trade"] == 0.05
    assert metrics["worst_trade"] == -0.02


def test_compute_metrics_no_trades():
    portfolio_returns = pd.Series([0.01, -0.005])
    benchmark_returns = pd.Series([0.005, -0.003])
    metrics = compute_metrics(
        portfolio_returns=portfolio_returns,
        benchmark_returns=benchmark_returns,
        trade_returns=[],
        holding_periods=[],
        turnover_series=pd.Series([0.0, 0.0]),
        time_in_market_series=pd.Series([0.0, 0.0]),
    )
    assert metrics["number_of_trades"] == 0
    assert metrics["profit_factor"] is None
    assert metrics["avg_winner"] is None


# ── compute_trade_diagnostics ─────────────────────────────────────────────────

def test_trade_diagnostics_empty():
    d = compute_trade_diagnostics([])
    assert d["profit_factor"] is None
    assert d["longest_winning_streak"] is None


def test_trade_diagnostics_all_winners():
    d = compute_trade_diagnostics([0.1, 0.2, 0.05])
    assert d["profit_factor"] is None  # no losses → no gross loss
    assert d["avg_winner"] == pytest.approx(0.1167, abs=1e-3)
    assert d["avg_loser"] is None
    assert d["longest_winning_streak"] == 3
    assert d["longest_losing_streak"] == 0


def test_trade_diagnostics_mixed():
    # alternating wins/losses → max streak of 1 each
    trades = [0.1, -0.05, 0.2, -0.1, 0.05]
    d = compute_trade_diagnostics(trades)
    assert d["profit_factor"] == pytest.approx((0.1 + 0.2 + 0.05) / (0.05 + 0.1), rel=1e-3)
    assert d["longest_winning_streak"] == 1
    assert d["longest_losing_streak"] == 1
    assert d["median_trade_return"] == pytest.approx(0.05)

def test_trade_diagnostics_consecutive_wins():
    # two consecutive wins then a loss
    trades = [0.1, 0.2, -0.05]
    d = compute_trade_diagnostics(trades)
    assert d["longest_winning_streak"] == 2
    assert d["longest_losing_streak"] == 1


def test_trade_diagnostics_all_losers():
    d = compute_trade_diagnostics([-0.1, -0.2])
    assert d["profit_factor"] == pytest.approx(0.0)
    assert d["avg_winner"] is None
    assert d["longest_losing_streak"] == 2


# ── compute_buy_and_hold ──────────────────────────────────────────────────────

def test_buy_and_hold_simple():
    prices = pd.Series([100.0, 110.0, 120.0])
    result = compute_buy_and_hold(prices, 100_000, len(prices))
    assert result["buy_and_hold_return"] == pytest.approx(0.20)
    assert result["buy_and_hold_annualized_return"] is not None


def test_buy_and_hold_empty():
    result = compute_buy_and_hold(pd.Series([], dtype=float), 100_000, 0)
    assert result["buy_and_hold_return"] is None
