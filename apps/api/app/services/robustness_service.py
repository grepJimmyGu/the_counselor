from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.robustness import (
    BenchmarkComparisonRow,
    ParameterSensitivityRow,
    PeerTickerRow,
    RobustnessResults,
    SubperiodRow,
    TransactionCostRow,
)
from app.schemas.strategy import StrategyJSON
from app.services.backtester.engine import BacktestEngine

_engine = BacktestEngine()

# Default parameter grids per strategy type
_DEFAULT_GRIDS: dict[str, dict[str, list[Any]]] = {
    "moving_average_filter": {"lookback_days": [50, 100, 150, 200, 250, 300]},
    "moving_average_crossover": {
        "fast_window": [20, 30, 50, 75],
        "slow_window": [100, 150, 200, 250],
    },
    "rsi_mean_reversion": {
        "buy_threshold": [20, 25, 30, 35],
        "sell_threshold": [55, 60, 65, 70],
    },
    "breakout": {"entry_window": [20, 40, 60, 80, 100]},
    "momentum_rotation": {"ranking_lookback_days": [63, 126, 189, 252]},
}

_COST_LEVELS = [0, 5, 10, 25, 50]

_BENCHMARK_PEERS = [
    ("SPY", "S&P 500"),
    ("QQQ", "Nasdaq 100"),
    ("IWM", "Russell 2000"),
]


class RobustnessService:

    # ------------------------------------------------------------------
    # Parameter sensitivity
    # ------------------------------------------------------------------

    async def run_parameter_sensitivity(
        self,
        db: Session,
        strategy: StrategyJSON,
        parameter_grid: dict[str, list[Any]] | None,
        baseline_sharpe: float,
    ) -> list[ParameterSensitivityRow]:
        grid = parameter_grid or _DEFAULT_GRIDS.get(strategy.strategy_type, {})
        if not grid or not strategy.rules:
            return []

        results: list[ParameterSensitivityRow] = []
        stype = strategy.strategy_type

        if stype == "moving_average_filter":
            for val in grid.get("lookback_days", []):
                row = await self._run_variant(
                    db, strategy, {"lookback_days": val}, baseline_sharpe,
                    param_label={"lookback_days": val},
                )
                if row:
                    results.append(row)

        elif stype == "moving_average_crossover":
            for fast in grid.get("fast_window", [strategy.rules[0].fast_window or 50]):
                for slow in grid.get("slow_window", [strategy.rules[0].slow_window or 200]):
                    if fast >= slow:
                        continue
                    row = await self._run_variant(
                        db, strategy, {"fast_window": fast, "slow_window": slow},
                        baseline_sharpe, param_label={"fast": fast, "slow": slow},
                    )
                    if row:
                        results.append(row)

        elif stype == "rsi_mean_reversion":
            for buy in grid.get("buy_threshold", [30]):
                for sell in grid.get("sell_threshold", [60]):
                    if buy >= sell:
                        continue
                    row = await self._run_rsi_variant(db, strategy, buy, sell, baseline_sharpe)
                    if row:
                        results.append(row)

        elif stype == "breakout":
            for val in grid.get("entry_window", []):
                row = await self._run_variant(
                    db, strategy, {"entry_window": val}, baseline_sharpe,
                    param_label={"entry_window": val},
                )
                if row:
                    results.append(row)

        elif stype == "momentum_rotation":
            for val in grid.get("ranking_lookback_days", []):
                row = await self._run_variant(
                    db, strategy, {"ranking_lookback_days": val}, baseline_sharpe,
                    param_label={"lookback_days": val},
                )
                if row:
                    results.append(row)

        return results

    # ------------------------------------------------------------------
    # Sub-period
    # ------------------------------------------------------------------

    async def run_subperiod(
        self, db: Session, strategy: StrategyJSON
    ) -> list[SubperiodRow]:
        start = strategy.start_date
        end = strategy.end_date
        mid = date(
            (start.year + end.year) // 2,
            (start.month + end.month + 1) // 2 or 1,
            1,
        )
        # Clamp mid to valid range
        if mid <= start or mid >= end:
            mid = date(start.year + (end.year - start.year) // 2, 6, 1)

        periods = [
            ("Full Period", start, end),
            ("First Half", start, mid),
            ("Second Half", mid, end),
        ]
        # Add yearly splits if range > 2 years
        if (end - start).days > 730:
            year = start.year
            while year < end.year:
                y_start = date(year, 1, 1)
                y_end = date(year, 12, 31)
                y_start = max(y_start, start)
                y_end = min(y_end, end)
                if (y_end - y_start).days > 60:
                    periods.append((str(year), y_start, y_end))
                year += 1

        rows: list[SubperiodRow] = []
        for label, s, e in periods:
            if (e - s).days < 30:
                rows.append(SubperiodRow(
                    period=label, start_date=str(s), end_date=str(e),
                    total_return=0.0, annualized_return=0.0, sharpe_ratio=0.0,
                    max_drawdown=0.0, verdict="insufficient_data",
                ))
                continue
            variant = strategy.model_copy(update={"start_date": s, "end_date": e})
            try:
                result = await _engine.run(db, variant)
                m = result.metrics
                sharpe = m.sharpe_ratio
                verdict = "strong" if sharpe > 0.8 else "acceptable" if sharpe > 0.3 else "weak"
                rows.append(SubperiodRow(
                    period=label, start_date=str(s), end_date=str(e),
                    total_return=m.total_return,
                    annualized_return=m.annualized_return,
                    sharpe_ratio=m.sharpe_ratio,
                    max_drawdown=m.max_drawdown,
                    verdict=verdict,  # type: ignore[arg-type]
                ))
            except Exception:
                rows.append(SubperiodRow(
                    period=label, start_date=str(s), end_date=str(e),
                    total_return=0.0, annualized_return=0.0, sharpe_ratio=0.0,
                    max_drawdown=0.0, verdict="insufficient_data",
                ))
        return rows

    # ------------------------------------------------------------------
    # Transaction cost sensitivity
    # ------------------------------------------------------------------

    async def run_transaction_cost(
        self, db: Session, strategy: StrategyJSON, baseline_return: float
    ) -> list[TransactionCostRow]:
        rows: list[TransactionCostRow] = []
        for cost_bps in _COST_LEVELS:
            variant = strategy.model_copy(update={
                "transaction_cost_bps": cost_bps,
                "slippage_bps": cost_bps,
            })
            try:
                result = await _engine.run(db, variant)
                m = result.metrics
                impact = baseline_return - m.total_return
                verdict = (
                    "breaks_down" if m.sharpe_ratio < 0
                    else "sensitive" if impact > 0.05
                    else "robust"
                )
                rows.append(TransactionCostRow(
                    cost_bps=cost_bps,
                    total_return=m.total_return,
                    sharpe_ratio=m.sharpe_ratio,
                    max_drawdown=m.max_drawdown,
                    turnover_impact=impact,
                    verdict=verdict,  # type: ignore[arg-type]
                ))
            except Exception:
                pass
        return rows

    # ------------------------------------------------------------------
    # Benchmark comparison
    # ------------------------------------------------------------------

    async def run_benchmark_comparison(
        self, db: Session, strategy: StrategyJSON, strategy_sharpe: float
    ) -> list[BenchmarkComparisonRow]:
        rows: list[BenchmarkComparisonRow] = []
        benchmarks = list(_BENCHMARK_PEERS)
        if strategy.benchmark not in [b[0] for b in benchmarks]:
            benchmarks.insert(0, (strategy.benchmark, strategy.benchmark))

        for symbol, name in benchmarks:
            bh_strategy = strategy.model_copy(update={
                "strategy_type": "static_allocation",
                "universe": [symbol],
                "benchmark": symbol,
                "rules": [],
                "position_sizing": type(strategy.position_sizing)(
                    method="fixed_weight", weights={symbol: 1.0}
                ),
            })
            try:
                result = await _engine.run(db, bh_strategy)
                m = result.metrics
                rows.append(BenchmarkComparisonRow(
                    name=name, symbol=symbol,
                    total_return=m.total_return,
                    sharpe_ratio=m.sharpe_ratio,
                    max_drawdown=m.max_drawdown,
                    excess_return_vs_strategy=m.total_return - strategy_sharpe,
                ))
            except Exception:
                pass
        return rows

    # ------------------------------------------------------------------
    # Peer ticker
    # ------------------------------------------------------------------

    async def run_peer_ticker(
        self, db: Session, strategy: StrategyJSON, peer_tickers: list[str]
    ) -> list[PeerTickerRow]:
        if not peer_tickers or len(strategy.universe) != 1:
            return []

        baseline_result = await _engine.run(db, strategy)
        baseline_sharpe = baseline_result.metrics.sharpe_ratio
        rows: list[PeerTickerRow] = []

        for ticker in peer_tickers:
            variant = strategy.model_copy(update={"universe": [ticker.upper()]})
            try:
                result = await _engine.run(db, variant)
                m = result.metrics
                diff = m.sharpe_ratio - baseline_sharpe
                verdict = "better" if diff > 0.2 else "similar" if diff > -0.2 else "worse"
                rows.append(PeerTickerRow(
                    ticker=ticker.upper(),
                    total_return=m.total_return, sharpe_ratio=m.sharpe_ratio,
                    max_drawdown=m.max_drawdown, trade_count=m.number_of_trades,
                    verdict=verdict,  # type: ignore[arg-type]
                ))
            except Exception as exc:
                rows.append(PeerTickerRow(
                    ticker=ticker.upper(),
                    total_return=0.0, sharpe_ratio=0.0,
                    max_drawdown=0.0, trade_count=0,
                    verdict="error", error=str(exc),
                ))
        return rows

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _run_variant(
        self,
        db: Session,
        strategy: StrategyJSON,
        rule_overrides: dict[str, Any],
        baseline_sharpe: float,
        param_label: dict[str, Any],
    ) -> ParameterSensitivityRow | None:
        if not strategy.rules:
            return None
        new_rules = [strategy.rules[0].model_copy(update=rule_overrides)]
        variant = strategy.model_copy(update={"rules": new_rules})
        try:
            result = await _engine.run(db, variant)
            m = result.metrics
            diff = m.sharpe_ratio - baseline_sharpe
            verdict = "better" if diff > 0.1 else "similar" if diff > -0.1 else "worse"
            return ParameterSensitivityRow(
                parameter_set=param_label,
                total_return=m.total_return, sharpe_ratio=m.sharpe_ratio,
                max_drawdown=m.max_drawdown, trade_count=m.number_of_trades,
                verdict=verdict,  # type: ignore[arg-type]
            )
        except Exception:
            return None

    async def _run_rsi_variant(
        self,
        db: Session,
        strategy: StrategyJSON,
        buy_threshold: float,
        sell_threshold: float,
        baseline_sharpe: float,
    ) -> ParameterSensitivityRow | None:
        if len(strategy.rules) < 2:
            return None
        new_rules = [
            strategy.rules[0].model_copy(update={"threshold": buy_threshold}),
            strategy.rules[1].model_copy(update={"threshold": sell_threshold}),
        ]
        variant = strategy.model_copy(update={"rules": new_rules})
        try:
            result = await _engine.run(db, variant)
            m = result.metrics
            diff = m.sharpe_ratio - baseline_sharpe
            verdict = "better" if diff > 0.1 else "similar" if diff > -0.1 else "worse"
            return ParameterSensitivityRow(
                parameter_set={"buy": buy_threshold, "sell": sell_threshold},
                total_return=m.total_return, sharpe_ratio=m.sharpe_ratio,
                max_drawdown=m.max_drawdown, trade_count=m.number_of_trades,
                verdict=verdict,  # type: ignore[arg-type]
            )
        except Exception:
            return None


robustness_service = RobustnessService()
