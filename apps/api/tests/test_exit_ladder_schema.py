"""PRD-16c-2 — ExitTier + RiskManagement.exit_ladder schema validators."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.strategy import ExitTier, RiskManagement


# ── ExitTier — fraction + action validators ─────────────────────────────────


def test_sell_all_tier_without_fraction_ok() -> None:
    tier = ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")
    assert tier.fraction is None
    assert tier.action == "sell_all"


def test_sell_all_tier_with_fraction_rejected() -> None:
    with pytest.raises(ValidationError, match="must not set `fraction`"):
        ExitTier(trigger_pct=-0.10, action="sell_all", fraction=0.5)


def test_sell_fraction_tier_requires_fraction() -> None:
    with pytest.raises(ValidationError, match="requires `fraction`"):
        ExitTier(trigger_pct=+0.15, action="sell_fraction")


def test_sell_fraction_zero_rejected() -> None:
    with pytest.raises(ValidationError, match="0 < f < 1"):
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.0)


def test_sell_fraction_one_rejected() -> None:
    with pytest.raises(ValidationError, match="0 < f < 1"):
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=1.0)


def test_sell_fraction_valid_range() -> None:
    tier = ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1")
    assert tier.fraction == 0.33


# ── RiskManagement.exit_ladder — top-level ladder validator ─────────────────


def test_no_exit_ladder_preserves_existing_behavior() -> None:
    rm = RiskManagement(stop_loss_pct=0.10, take_profit_pct=0.20)
    assert rm.exit_ladder is None


def test_empty_exit_ladder_rejected() -> None:
    with pytest.raises(ValidationError, match="must contain at least 1 tier"):
        RiskManagement(exit_ladder=[])


def test_exit_ladder_without_stop_rejected() -> None:
    """Multi-tier ladders without a hard stop are dangerous — the validator
    enforces at least one negative-trigger sell_all tier."""
    with pytest.raises(ValidationError, match="must include at least one stop tier"):
        RiskManagement(exit_ladder=[
            ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
            ExitTier(trigger_pct=+0.30, action="sell_all", label="TP2"),
        ])


def test_exit_ladder_must_be_ordered_ascending() -> None:
    with pytest.raises(ValidationError, match="ordered ascending by `trigger_pct`"):
        RiskManagement(exit_ladder=[
            ExitTier(trigger_pct=+0.30, action="sell_all", label="TP2"),
            ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ])


def test_canonical_spacex_ladder_accepted() -> None:
    """The SpaceX-style 3-tier exit from the PRD spec — Stop / TP1 / TP2."""
    rm = RiskManagement(exit_ladder=[
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
        ExitTier(trigger_pct=+0.30, action="sell_all", label="TP2"),
    ])
    assert len(rm.exit_ladder) == 3
    assert [t.label for t in rm.exit_ladder] == ["Stop", "TP1", "TP2"]


def test_stop_only_ladder_accepted() -> None:
    """The minimal valid ladder: a single stop tier (no take-profits)."""
    rm = RiskManagement(exit_ladder=[
        ExitTier(trigger_pct=-0.08, action="sell_all", label="Stop"),
    ])
    assert len(rm.exit_ladder) == 1
