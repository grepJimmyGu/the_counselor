import pandas as pd

from app.services.backtester.metrics import compute_drawdown, compute_metrics


def test_compute_drawdown_reaches_expected_minimum():
    equity = pd.Series([100.0, 110.0, 90.0, 120.0])
    drawdown = compute_drawdown(equity)
    assert round(drawdown.min(), 4) == -0.1818


def test_compute_metrics_returns_expected_fields():
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

    assert metrics["number_of_trades"] == 3
    assert metrics["best_trade"] == 0.05
    assert metrics["worst_trade"] == -0.02
    assert "sharpe_ratio" in metrics
