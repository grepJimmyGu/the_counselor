from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute_drawdown(equity_curve: pd.Series) -> pd.Series:
    running_max = equity_curve.cummax()
    return equity_curve / running_max - 1.0


def compute_metrics(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    trade_returns: list[float],
    holding_periods: list[int],
    turnover_series: pd.Series,
    time_in_market_series: pd.Series,
) -> dict[str, float]:
    portfolio_returns = portfolio_returns.fillna(0.0)
    benchmark_returns = benchmark_returns.reindex(portfolio_returns.index).fillna(0.0)

    equity_curve = (1.0 + portfolio_returns).cumprod()
    benchmark_curve = (1.0 + benchmark_returns).cumprod()
    total_return = equity_curve.iloc[-1] - 1.0
    benchmark_total_return = benchmark_curve.iloc[-1] - 1.0

    annualized_return = equity_curve.iloc[-1] ** (252 / max(len(equity_curve), 1)) - 1.0
    annualized_volatility = portfolio_returns.std(ddof=0) * math.sqrt(252)
    downside = portfolio_returns.clip(upper=0)
    sortino_denominator = downside.std(ddof=0) * math.sqrt(252)
    sharpe_ratio = annualized_return / annualized_volatility if annualized_volatility else 0.0
    sortino_ratio = annualized_return / sortino_denominator if sortino_denominator else 0.0

    drawdown = compute_drawdown(equity_curve)
    max_drawdown = float(drawdown.min())
    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown else 0.0

    covariance = np.cov(portfolio_returns, benchmark_returns)
    beta = covariance[0][1] / covariance[1][1] if covariance[1][1] else 0.0
    alpha = annualized_return - beta * (benchmark_returns.mean() * 252)

    number_of_trades = len(trade_returns)
    win_rate = sum(1 for trade in trade_returns if trade > 0) / number_of_trades if number_of_trades else 0.0
    average_trade_return = float(np.mean(trade_returns)) if trade_returns else 0.0
    best_trade = float(np.max(trade_returns)) if trade_returns else 0.0
    worst_trade = float(np.min(trade_returns)) if trade_returns else 0.0
    average_holding_period = float(np.mean(holding_periods)) if holding_periods else 0.0

    return {
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "annualized_volatility": float(annualized_volatility),
        "sharpe_ratio": float(sharpe_ratio),
        "sortino_ratio": float(sortino_ratio),
        "max_drawdown": float(max_drawdown),
        "calmar_ratio": float(calmar_ratio),
        "win_rate": float(win_rate),
        "number_of_trades": number_of_trades,
        "average_trade_return": float(average_trade_return),
        "best_trade": float(best_trade),
        "worst_trade": float(worst_trade),
        "average_holding_period": float(average_holding_period),
        "benchmark_total_return": float(benchmark_total_return),
        "excess_return_vs_benchmark": float(total_return - benchmark_total_return),
        "alpha_vs_benchmark": float(alpha),
        "beta_vs_benchmark": float(beta),
        "turnover": float(turnover_series.mean()),
        "time_in_market": float(time_in_market_series.mean()),
    }

