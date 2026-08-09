"""The Python half of the 3-dimensional score contract.

`evaluation_scoring.py` is a port of `apps/web/src/lib/evaluation/scoring.ts`,
which drives the score gauges on the stock detail page. The server-rendered
share card needs the same three numbers and cannot call TypeScript.

Two implementations of one score drift silently. The failure mode is a shared
card claiming "Valuation 78" linking to a page that says 71 — the product
contradicting itself in front of a reader who clicked through precisely to
check. So both sides read THIS fixture, which was generated from the
TypeScript implementation (the incumbent). Its mirror is
`apps/web/src/lib/evaluation/__tests__/scoring-contract.test.ts`; change either
side's arithmetic and that side's test goes red.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.evaluation_scoring import (
    StockMetrics,
    _clamp,
    _js_round,
    score_stock,
)

FIXTURE = Path(__file__).parent / "fixtures" / "evaluation_scoring_cases.json"
CASES = json.loads(FIXTURE.read_text())["cases"]


def _ids():
    return [c["name"] for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=_ids())
def test_matches_the_typescript_implementation(case):
    got = score_stock(StockMetrics.from_dict(case["input"]))
    exp = case["expected"]
    assert got.health == exp["health"], f"health drifted on {case['name']}"
    assert got.valuation == exp["valuation"], f"valuation drifted on {case['name']}"
    assert got.trend == exp["trend"], f"trend drifted on {case['name']}"
    assert got.final == exp["final"], f"final drifted on {case['name']}"
    assert got.label == exp["label"]


def test_fixture_is_not_empty():
    """A fixture that silently emptied would make every case above vacuous —
    the parametrize would collect zero tests and the suite would pass."""
    assert len(CASES) >= 10


def test_rounds_like_javascript_not_like_python():
    """`clamp` in scoring.ts uses Math.round: half rounds AWAY from zero.
    Python's round() is banker's rounding — round(2.5) == 2, round(3.5) == 4.

    Using the builtin would make the two sides disagree only on totals landing
    exactly on .5: rare, data-dependent, and nearly unfindable in production.
    """
    assert _js_round(2.5) == 3
    assert _js_round(3.5) == 4
    assert _js_round(0.5) == 1
    assert round(2.5) == 2  # the trap this avoids
    assert _clamp(74.5) == 75


def test_clamps_to_the_visible_range():
    assert _clamp(-10) == 0
    assert _clamp(140) == 100


def test_unknown_input_keys_are_ignored_not_fatal():
    """The fixture carries the full camelCase `StockMetricsInput`, most of
    which the scorers never read. A stricter constructor would break the
    contract test the first time the TS type gained a field."""
    m = StockMetrics.from_dict({"peRatio": 11, "ticker": "MSFT", "companyName": "x", "sector": "Tech"})
    assert m.pe_ratio == 11


def test_no_price_data_returns_neutral_trend_not_zero():
    """A stock we have no price history for scores 50 (unknown), not 0 (bad).
    Zero would rank it below a genuinely collapsing name."""
    assert score_stock(StockMetrics()).trend == 50
