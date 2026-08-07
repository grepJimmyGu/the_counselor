"""A derived P/E outside a plausible band must be discarded, not stored.

The regression: `/key-metrics-ttm` no longer returns `peRatioTTM`, so we derive
it as `1 / earningsYieldTTM`. FMP returns that yield as a fraction for most
symbols but occasionally as a percent — and `1/100` silently produces a P/E of
0.01. Observed live during the 2026-08-07 Russell 3000 backfill: ARW 0.01,
AMPH 0.01, CART 0.02, AKAM 0.04 (Akamai's real P/E is ~30).

Why it matters more than a cosmetic wrong number: a "cheapest first" value
screen sorts ascending on P/E, so every one of these fabricated values lands at
the TOP of the results. The user sees Akamai presented as the cheapest stock in
the market.

We reject rather than rescale, because the upstream unit is ambiguous
per-symbol — any correction would be a guess. None renders as "—" and drops the
name from value screens, which is honest. A confident 0.04 is not.
"""
from __future__ import annotations

import pytest

from app.services.fmp_client import _derive_pe, _normalise_key_metrics


@pytest.mark.parametrize(
    "earnings_yield,expected",
    [
        (0.0333, 30.03),   # a normal name — AKAM's real shape
        (0.05, 20.0),
        (0.5, 2.0),        # 50% earnings yield: extreme but real (deep value)
        (1.0, 1.0),        # exactly at the floor — kept
    ],
)
def test_plausible_yields_derive_a_pe(earnings_yield, expected) -> None:
    assert _derive_pe(earnings_yield) == pytest.approx(expected, rel=1e-3)


@pytest.mark.parametrize(
    "earnings_yield,why",
    [
        (100.0, "the ARW / AMPH case — percent-form yield inverts to 0.01"),
        (25.0, "the AKAM case — inverts to 0.04"),
        (50.0, "inverts to 0.02"),
        (0.0009, "inverts to a P/E of 1111 — beyond any real multiple"),
    ],
)
def test_implausible_yields_are_discarded(earnings_yield, why) -> None:
    assert _derive_pe(earnings_yield) is None, why


@pytest.mark.parametrize("bad", [None, 0, -0.02, "n/a", ""])
def test_missing_or_negative_earnings_yield_is_none(bad) -> None:
    # Negative earnings have no meaningful P/E — must not become a negative
    # multiple that sorts below every profitable company on a cheapest-first
    # screen.
    assert _derive_pe(bad) is None


def test_normalise_uses_the_guard() -> None:
    """The guard has to sit on the path the client actually calls."""
    out = _normalise_key_metrics({"earningsYieldTTM": 100.0})
    assert out["peRatioTTM"] is None

    out = _normalise_key_metrics({"earningsYieldTTM": 0.04})
    assert out["peRatioTTM"] == pytest.approx(25.0)


def test_an_explicit_upstream_pe_is_left_alone() -> None:
    """When FMP does return peRatioTTM we pass it through untouched — the
    derivation (and its guard) only applies to the fallback path."""
    out = _normalise_key_metrics({"peRatioTTM": 0.04, "earningsYieldTTM": 25.0})
    assert out["peRatioTTM"] == 0.04
