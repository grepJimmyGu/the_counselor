"""Backtest honesty: costs are charged, and results say which methodology
produced them.

Both decided 2026-08-18. Neither was covered before — the full suite passed
unchanged when costs were switched from 0 to 5+5 bps, which means nothing
asserted on a backtest number computed with the defaults. That gap is why
the product shipped gross-of-cost results for months.
"""

from __future__ import annotations

import pytest

from app.schemas.backtest import BacktestResult
from app.schemas.strategy import StrategyJSON
from app.services.backtester.engine import BACKTEST_ENGINE_VERSION


def _strategy(**overrides) -> StrategyJSON:
    base = {
        "strategy_name": "probe",
        "strategy_type": "moving_average_filter",
        "universe": ["AAA"],
        "benchmark": "SPY",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "initial_capital": 100_000,
        "rebalance_frequency": "monthly",
        "position_sizing": {"method": "equal_weight"},
        "rules": [{"ma_window": 50}],
    }
    base.update(overrides)
    return StrategyJSON.model_validate(base)


# ── Decision C: costs on by default ─────────────────────────────────────────


def test_REGRESSION_transaction_costs_are_not_zero_by_default():
    """Both fields were `Field(0.0)`, so every backtest ran GROSS unless a
    caller set them — and nothing did. A daily strategy that turns over
    weekly can be entirely an artifact of that: at 5+5 bps, 100% weekly
    turnover costs roughly 5% a year, which is the difference between an
    edge and a rounding error.
    """
    s = _strategy()
    assert s.transaction_cost_bps > 0
    assert s.slippage_bps > 0


def test_default_cost_assumption_is_the_documented_one():
    """Pinned so a change is deliberate and visible in a diff, not a drift.
    5 + 5 bps is a floor for liquid large caps — commissions are ~0 at
    retail brokers, so the real cost is spread plus impact."""
    s = _strategy()
    assert s.transaction_cost_bps == pytest.approx(5.0)
    assert s.slippage_bps == pytest.approx(5.0)


def test_a_user_can_still_raise_costs():
    """The default is a floor, not a ceiling. Someone trading small caps
    should be able to model a worse fill."""
    s = _strategy(transaction_cost_bps=25.0, slippage_bps=40.0)
    assert s.transaction_cost_bps == pytest.approx(25.0)
    assert s.slippage_bps == pytest.approx(40.0)


def test_costs_may_be_explicitly_zeroed_but_never_silently():
    """Zero is a legitimate research choice — the objection was to it being
    the DEFAULT, where nobody chose it."""
    s = _strategy(transaction_cost_bps=0.0, slippage_bps=0.0)
    assert s.transaction_cost_bps == 0.0


# ── Decision D: methodology versioning ──────────────────────────────────────


def _result(**overrides) -> dict:
    base = {
        "backtest_id": "bt_1",
        "strategy_json": _strategy().model_dump(mode="json"),
        "metrics": {
            "total_return": 0.1, "annualized_return": 0.1,
            "annualized_volatility": 0.1, "sharpe_ratio": 1.0,
            "sortino_ratio": 1.2, "max_drawdown": -0.1, "calmar_ratio": 1.0,
            "win_rate": 0.5, "number_of_trades": 4,
            "average_trade_return": 0.02, "best_trade": 0.1,
            "worst_trade": -0.05, "average_holding_period": 12.0,
            "benchmark_total_return": 0.05,
            "excess_return_vs_benchmark": 0.05,
            "alpha_vs_benchmark": 0.01, "beta_vs_benchmark": 0.9,
            "turnover": 1.2, "time_in_market": 0.8,
        },
        "equity_curve": [], "benchmark_curve": [], "drawdown_curve": [],
        "trade_log": [], "annual_returns": [], "monthly_returns": [],
        "warnings": [],
    }
    base.update(overrides)
    return base


def test_REGRESSION_a_payload_with_no_version_does_NOT_claim_to_be_current():
    """The entire point of the field. Every result stored before
    2026-08-18 lacks the key, and results are persisted as a JSON blob
    (`BacktestRecord.result_payload = result.model_dump()`). If the field
    defaulted to the current version, every one of those old payloads would
    deserialize claiming a methodology it never ran under — which is worse
    than having no version at all, because it would look authoritative.
    """
    old = BacktestResult.model_validate(_result())
    assert old.engine_version is None


def test_a_stored_version_survives_the_round_trip():
    stamped = BacktestResult.model_validate(
        _result(engine_version=BACKTEST_ENGINE_VERSION)
    )
    assert stamped.engine_version == BACKTEST_ENGINE_VERSION
    assert stamped.model_dump(mode="json")["engine_version"] == BACKTEST_ENGINE_VERSION


def test_the_version_is_a_real_value_the_ui_can_show():
    assert isinstance(BACKTEST_ENGINE_VERSION, str)
    assert BACKTEST_ENGINE_VERSION.strip() != ""
