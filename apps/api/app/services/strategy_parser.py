from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from app.schemas.strategy import (
    CashManagement,
    PositionSizing,
    RiskManagement,
    StrategyChatResponse,
    StrategyJSON,
    StrategyRule,
)


DEFAULT_BENCHMARK = "SPY"
SYMBOL_PATTERN = re.compile(r"\b[A-Z]{1,5}\b")
RESERVED_TOKENS = {
    "A",
    "AN",
    "AND",
    "ABOVE",
    "AT",
    "AVERAGE",
    "BASED",
    "BELOW",
    "BUY",
    "DAY",
    "DAYS",
    "EVERY",
    "FROM",
    "HOLD",
    "IS",
    "ITS",
    "LOW",
    "MONTH",
    "MONTHS",
    "MOVING",
    "OF",
    "ON",
    "OR",
    "PRICE",
    "RETURN",
    "SELL",
    "STOCK",
    "STOCKS",
    "THE",
    "THEN",
    "TOP",
    "WHEN",
}


def _extract_symbols(message: str) -> list[str]:
    matches = SYMBOL_PATTERN.findall(message.upper())
    filtered = [
        token for token in matches if token not in RESERVED_TOKENS and len(token) >= 2
    ]
    return list(dict.fromkeys(filtered))


def _base_strategy(
    strategy_name: str,
    strategy_type: str,
    universe: list[str],
    rebalance_frequency: str,
    rules: list[StrategyRule],
    position_sizing: PositionSizing,
) -> StrategyJSON:
    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    return StrategyJSON(
        strategy_name=strategy_name,
        strategy_type=strategy_type,
        universe=universe,
        benchmark=DEFAULT_BENCHMARK,
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=rules,
        position_sizing=position_sizing,
        risk_management=RiskManagement(),
        cash_management=CashManagement(hold_cash_when_no_signal=True),
    )


def parse_strategy_message(
    user_message: str, previous_strategy_json: Optional[StrategyJSON] = None
) -> StrategyChatResponse:
    message = user_message.strip()
    lowered = message.lower()
    symbols = _extract_symbols(message)

    if previous_strategy_json and "benchmark" in lowered and symbols:
        updated = previous_strategy_json.model_copy(deep=True)
        updated.benchmark = symbols[0]
        return StrategyChatResponse(
            assistant_message=f"Updated the benchmark to {updated.benchmark}.",
            strategy_json=updated,
            validation_status="valid",
            missing_fields=[],
            clarification_questions=[],
        )

    if not symbols:
        return StrategyChatResponse(
            assistant_message="I can draft the strategy shape, but I still need at least one ticker symbol.",
            strategy_json=None,
            validation_status="needs_clarification",
            missing_fields=["universe"],
            clarification_questions=["Which stock symbols should this strategy trade?"],
        )

    try:
        if "above" in lowered and "moving average" in lowered and "crossover" not in lowered:
            lookback = int(re.search(r"(\d+)[-\s]?day", lowered).group(1)) if re.search(r"(\d+)[-\s]?day", lowered) else 200
            strategy = _base_strategy(
                strategy_name=f"{symbols[0]} {lookback}-Day Moving Average Filter",
                strategy_type="moving_average_filter",
                universe=[symbols[0]],
                rebalance_frequency="daily",
                rules=[
                    StrategyRule(
                        indicator="moving_average",
                        lookback_days=lookback,
                        operator="gt",
                        source="adjusted_close",
                    )
                ],
                position_sizing=PositionSizing(method="equal_weight", max_positions=1),
            )
        elif "crossover" in lowered or ("50" in lowered and "200" in lowered and "moving average" in lowered):
            windows = re.findall(r"(\d+)[-\s]?day", lowered)
            fast_window = int(windows[0]) if len(windows) > 0 else 50
            slow_window = int(windows[1]) if len(windows) > 1 else 200
            strategy = _base_strategy(
                strategy_name=f"{symbols[0]} {fast_window}/{slow_window} Moving Average Crossover",
                strategy_type="moving_average_crossover",
                universe=[symbols[0]],
                rebalance_frequency="daily",
                rules=[StrategyRule(indicator="moving_average", fast_window=fast_window, slow_window=slow_window)],
                position_sizing=PositionSizing(method="equal_weight", max_positions=1),
            )
        elif "momentum" in lowered or "top" in lowered:
            top_match = re.search(r"top\s+(\d+)", lowered)
            top_n = int(top_match.group(1)) if top_match else min(3, len(symbols))
            lookback_match = re.search(r"(\d+)[-\s]?month", lowered)
            lookback_days = (int(lookback_match.group(1)) * 21) if lookback_match else 126
            strategy = _base_strategy(
                strategy_name="Momentum Rotation",
                strategy_type="momentum_rotation",
                universe=symbols,
                rebalance_frequency="monthly",
                rules=[
                    StrategyRule(top_n=top_n, ranking_measure="total_return", ranking_lookback_days=lookback_days)
                ],
                position_sizing=PositionSizing(method="equal_weight", max_positions=top_n),
            )
            strategy.cash_management.hold_cash_when_no_signal = False
        elif "rsi" in lowered:
            buy_match = re.search(r"below\s+(\d+)", lowered)
            sell_match = re.search(r"above\s+(\d+)", lowered)
            buy_level = int(buy_match.group(1)) if buy_match else 30
            sell_level = int(sell_match.group(1)) if sell_match else 60
            strategy = _base_strategy(
                strategy_name=f"{symbols[0]} RSI Mean Reversion",
                strategy_type="rsi_mean_reversion",
                universe=[symbols[0]],
                rebalance_frequency="daily",
                rules=[
                    StrategyRule(indicator="rsi", lookback_days=14, operator="lt", threshold=buy_level),
                    StrategyRule(indicator="rsi", lookback_days=14, operator="gt", threshold=sell_level),
                ],
                position_sizing=PositionSizing(method="equal_weight", max_positions=1),
            )
        elif "breakout" in lowered or ("high" in lowered and "low" in lowered):
            windows = re.findall(r"(\d+)[-\s]?day", lowered)
            entry_window = int(windows[0]) if len(windows) > 0 else 60
            exit_window = int(windows[1]) if len(windows) > 1 else 20
            strategy = _base_strategy(
                strategy_name=f"{symbols[0]} Breakout Strategy",
                strategy_type="breakout",
                universe=[symbols[0]],
                rebalance_frequency="daily",
                rules=[StrategyRule(entry_window=entry_window, exit_window=exit_window)],
                position_sizing=PositionSizing(method="equal_weight", max_positions=1),
            )
        elif "hold" in lowered or "%" in lowered or "allocation" in lowered:
            weights = {}
            for symbol in symbols:
                percent_match = re.search(rf"(\d+)%\s+{symbol.lower()}", lowered)
                if percent_match:
                    weights[symbol] = int(percent_match.group(1)) / 100
            if not weights:
                equal_weight = round(1 / len(symbols), 4)
                weights = {symbol: equal_weight for symbol in symbols}
            strategy = _base_strategy(
                strategy_name="Static Allocation",
                strategy_type="static_allocation",
                universe=list(weights.keys()),
                rebalance_frequency="monthly",
                rules=[],
                position_sizing=PositionSizing(method="fixed_weight", weights=weights),
            )
            strategy.cash_management.hold_cash_when_no_signal = False
        else:
            return StrategyChatResponse(
                assistant_message="I recognized the tickers, but I need the strategy style. Try describing a moving average, crossover, momentum, RSI, breakout, or allocation rule.",
                strategy_json=None,
                validation_status="needs_clarification",
                missing_fields=["strategy_type", "rules"],
                clarification_questions=[
                    "Which supported strategy type should I use: moving average filter, crossover, momentum rotation, RSI mean reversion, breakout, or static allocation?"
                ],
            )
    except Exception as exc:  # pragma: no cover - defensive parser fallback
        return StrategyChatResponse(
            assistant_message=f"I couldn't safely translate that into the supported schema yet: {exc}",
            strategy_json=None,
            validation_status="invalid",
            missing_fields=["strategy_json"],
            clarification_questions=[],
        )

    return StrategyChatResponse(
        assistant_message=f"I interpreted your idea as a {strategy.strategy_type.replace('_', ' ')} strategy over {', '.join(strategy.universe)}.",
        strategy_json=strategy,
        validation_status="valid",
        missing_fields=[],
        clarification_questions=[],
    )
