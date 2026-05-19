"""Tests for GET /api/billing/pricing."""
from __future__ import annotations

from unittest.mock import patch

from app.services.stripe_service import AMOUNTS, DISPLAY_PRICES


def test_pricing_returns_four_options() -> None:
    from app.api.routes.billing import get_pricing

    with patch("app.api.routes.billing.stripe_service.get_price_map", return_value={
        ("strategist", "monthly"): "price_strat_mo",
        ("strategist", "annual"):  "price_strat_yr",
        ("quant",       "monthly"): "price_quant_mo",
        ("quant",       "annual"):  "price_quant_yr",
    }):
        result = get_pricing()

    assert result.trial_days == 14
    assert len(result.options) == 4
    tiers = {(o.tier, o.billing_cycle) for o in result.options}
    assert ("strategist", "monthly") in tiers
    assert ("strategist", "annual")  in tiers
    assert ("quant",       "monthly") in tiers
    assert ("quant",       "annual")  in tiers


def test_pricing_amounts_match_spec() -> None:
    assert AMOUNTS[("strategist", "monthly")] == 2400
    assert AMOUNTS[("strategist", "annual")]  == 22800
    assert AMOUNTS[("quant",       "monthly")] == 7900
    assert AMOUNTS[("quant",       "annual")]  == 70800


def test_display_prices_present() -> None:
    for key in [
        ("strategist", "monthly"),
        ("strategist", "annual"),
        ("quant",       "monthly"),
        ("quant",       "annual"),
    ]:
        assert key in DISPLAY_PRICES
        assert "$" in DISPLAY_PRICES[key]
