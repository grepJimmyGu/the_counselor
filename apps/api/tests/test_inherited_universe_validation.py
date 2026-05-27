"""PRD-13b — StrategyJSON additive contract.

inherited_universe must be:
  * Optional / defaultable to None (existing strategy types unaffected).
  * Required + non-empty when strategy_type is a portfolio overlay.
  * Enforced per-overlay minimum holding counts.
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.strategy import (
    CashManagement,
    PositionSizing,
    PORTFOLIO_OVERLAY_TYPES,
    RiskManagement,
    StrategyJSON,
)


def _kwargs(strategy_type: str, **overrides):
    base = dict(
        strategy_name="Test Strategy",
        strategy_type=strategy_type,
        universe=["SPY"],
        benchmark="SPY",
        start_date=date(2022, 1, 3),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        rules=[],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    base.update(overrides)
    return base


def test_existing_strategy_type_works_without_inherited_universe():
    """The 22 pre-existing strategy types must continue to accept None."""
    s = StrategyJSON(**_kwargs("moving_average_filter"))
    assert s.inherited_universe is None


def test_existing_strategy_type_ignores_inherited_universe_when_set():
    """Setting inherited_universe on a non-portfolio strategy is allowed
    but produces no behavior change (engine swap only fires for
    portfolio_* types). The contract is purely additive."""
    s = StrategyJSON(**_kwargs("moving_average_filter", inherited_universe=["AAPL"]))
    assert s.inherited_universe == ["AAPL"]


def test_portfolio_defensive_overlay_requires_inherited_universe():
    with pytest.raises(ValidationError, match="inherited_universe"):
        StrategyJSON(**_kwargs("portfolio_defensive_overlay"))


def test_portfolio_rotation_overlay_requires_three_holdings():
    # 1 and 2 holdings both fail
    with pytest.raises(ValidationError, match="at least 3"):
        StrategyJSON(**_kwargs(
            "portfolio_rotation_overlay",
            inherited_universe=["A", "B"],
            universe=["A", "B"],
        ))
    # 3+ passes
    s = StrategyJSON(**_kwargs(
        "portfolio_rotation_overlay",
        inherited_universe=["A", "B", "C"],
        universe=["A", "B", "C"],
    ))
    assert s.inherited_universe == ["A", "B", "C"]


def test_portfolio_rebalance_overlay_requires_weights():
    # Needs explicit weights
    with pytest.raises(ValidationError, match="weights"):
        StrategyJSON(**_kwargs(
            "portfolio_rebalance_overlay",
            inherited_universe=["A", "B"],
            universe=["A", "B"],
            position_sizing=PositionSizing(method="equal_weight"),
        ))
    # Valid case
    s = StrategyJSON(**_kwargs(
        "portfolio_rebalance_overlay",
        inherited_universe=["A", "B"],
        universe=["A", "B"],
        position_sizing=PositionSizing(
            method="fixed_weight", weights={"A": 0.6, "B": 0.4}
        ),
    ))
    assert s.position_sizing.weights == {"A": 0.6, "B": 0.4}


def test_overlay_types_are_in_PORTFOLIO_OVERLAY_TYPES():
    assert "portfolio_defensive_overlay" in PORTFOLIO_OVERLAY_TYPES
    assert "portfolio_rotation_overlay" in PORTFOLIO_OVERLAY_TYPES
    assert "portfolio_rebalance_overlay" in PORTFOLIO_OVERLAY_TYPES
