from __future__ import annotations

from app.schemas.strategy import StrategyJSON


def validate_strategy(strategy: StrategyJSON) -> list[str]:
    warnings: list[str] = []

    if len(strategy.universe) == 1 and strategy.strategy_type == "momentum_rotation":
        warnings.append("Momentum rotation is usually more meaningful with multiple symbols.")

    if strategy.start_date.year >= strategy.end_date.year:
        warnings.append("Backtest window may be too short to judge robustness.")

    if strategy.transaction_cost_bps == 0 and strategy.slippage_bps == 0:
        warnings.append("Transaction costs and slippage are both zero.")

    if strategy.strategy_type == "moving_average_crossover":
        rule = strategy.rules[0] if strategy.rules else None
        if rule and rule.fast_window and rule.slow_window and rule.fast_window >= rule.slow_window:
            warnings.append("Fast moving average should typically be shorter than slow moving average.")

    return warnings

