"""Livermore 3-dimensional stock score — Python port.

A faithful port of the **stock** half of
`apps/web/src/lib/evaluation/scoring.ts`, which powers the score gauges on the
stock detail page. The server-rendered daily share card needs the same three
numbers, and it cannot call TypeScript.

**THE TWO IMPLEMENTATIONS ARE PINNED TO ONE FIXTURE.**
`apps/api/tests/fixtures/evaluation_scoring_cases.json` holds input→expected
cases read by BOTH `tests/test_evaluation_scoring.py` and
`apps/web/src/lib/evaluation/__tests__/scoring-contract.test.ts`. Change either
side's arithmetic and that side's test goes red. Without it, the drift is
silent and the failure mode is a shared card claiming "Valuation 78" linking to
a page that says 71 — the product contradicting itself in front of a reader who
clicked through precisely to check.

Only the STOCK scorers are ported. The commodity half of `scoring.ts` has no
server-side consumer; porting it would be ~190 lines of untested duplication.

Faithful means faithful: `_score_roe` scores a *negative* ROE well because it
takes an absolute value, which is almost certainly a bug — but it is the
behaviour the stock page ships today, and silently "fixing" it here would make
the two implementations disagree, which is the one thing this file exists to
prevent. See the PR for the separate report.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ── JS-compatible rounding ──────────────────────────────────────────────────
# `clamp` in scoring.ts uses Math.round, which rounds half AWAY from zero for
# positives: Math.round(2.5) === 3. Python's built-in round() is banker's
# rounding: round(2.5) == 2. Using it here would make the two implementations
# disagree on every score whose total lands on a .5 boundary — a rare,
# data-dependent, nearly-unfindable divergence. floor(x + 0.5) matches JS for
# the non-negative range these scores live in.


def _js_round(v: float) -> int:
    return int(math.floor(v + 0.5))


def _clamp(v: float) -> int:
    return max(0, min(100, _js_round(v)))


# ── health ──────────────────────────────────────────────────────────────────


def _score_revenue_growth(v: Optional[float]) -> float:
    if v is None:
        return 50
    if v > 0.20:
        return 95
    if v > 0.10:
        return 80
    if v > 0.05:
        return 65
    if v > 0.00:
        return 50
    if v > -0.05:
        return 30
    return 10


def _score_margin(gross_margin: Optional[float], op_margin: Optional[float]) -> float:
    s = 0.0
    w = 0
    if gross_margin is not None:
        s += 90 if gross_margin > 0.5 else 70 if gross_margin > 0.35 else 50 if gross_margin > 0.2 else 25
        w += 1
    if op_margin is not None:
        s += 90 if op_margin > 0.2 else 70 if op_margin > 0.1 else 45 if op_margin > 0 else 15
        w += 1
    return s / w if w > 0 else 50


def _score_fcf(fcf_margin: Optional[float], fcf_conversion: Optional[float]) -> float:
    s = 0.0
    w = 0
    if fcf_margin is not None:
        s += (
            95 if fcf_margin > 0.25
            else 80 if fcf_margin > 0.15
            else 60 if fcf_margin > 0.05
            else 40 if fcf_margin > 0
            else 15
        )
        w += 1
    if fcf_conversion is not None:
        s += 95 if fcf_conversion > 1.0 else 80 if fcf_conversion > 0.8 else 55 if fcf_conversion > 0.5 else 25
        w += 1
    return s / w if w > 0 else 50


def _score_roe(roe: Optional[float]) -> float:
    if roe is None:
        return 50
    # Ported verbatim, abs() included. A -35% ROE takes abs() to 0.35 and
    # scores 90 — see the module docstring; do not "fix" this in isolation.
    r = min(abs(roe), 0.5)
    if r > 0.30:
        return 90
    if r > 0.20:
        return 75
    if r > 0.10:
        return 60
    if r > 0.00:
        return 40
    return 20


def _score_balance_sheet(
    net_debt: Optional[float], current_ratio: Optional[float], debt_equity: Optional[float]
) -> float:
    s = 0.0
    w = 0
    if net_debt is not None and net_debt < 0:
        s += 95  # net cash
        w += 1
    elif net_debt is not None:
        s += 75 if net_debt < 5e9 else 60 if net_debt < 20e9 else 45 if net_debt < 50e9 else 30
        w += 1
    if current_ratio is not None:
        s += (
            90 if current_ratio > 2
            else 75 if current_ratio > 1.5
            else 55 if current_ratio > 1
            else 35 if current_ratio > 0.75
            else 15
        )
        w += 1
    if debt_equity is not None:
        s += (
            90 if debt_equity < 0.3
            else 70 if debt_equity < 0.75
            else 50 if debt_equity < 1.5
            else 30 if debt_equity < 3
            else 10
        )
        w += 1
    return s / w if w > 0 else 50


# ── valuation ───────────────────────────────────────────────────────────────


def _score_fcf_yield(v: Optional[float]) -> float:
    if v is None:
        return 50
    if v > 0.08:
        return 95
    if v > 0.05:
        return 80
    if v > 0.03:
        return 60
    if v > 0.01:
        return 40
    return 20


def _score_ev_ebitda(v: Optional[float]) -> float:
    if v is None:
        return 50
    if v < 8:
        return 90
    if v < 12:
        return 75
    if v < 18:
        return 55
    if v < 25:
        return 38
    if v < 35:
        return 25
    return 12


def _score_pe(v: Optional[float]) -> float:
    if v is None:
        return 50
    if v < 12:
        return 90
    if v < 18:
        return 75
    if v < 25:
        return 58
    if v < 35:
        return 40
    if v < 50:
        return 25
    return 10


def _score_peg(v: Optional[float]) -> float:
    if v is None:
        return 50
    if v < 0.8:
        return 90
    if v < 1.2:
        return 75
    if v < 2.0:
        return 55
    if v < 3.0:
        return 35
    return 15


# ── trend ───────────────────────────────────────────────────────────────────


def _score_momentum(perf3m: Optional[float], perf12m: Optional[float]) -> float:
    # Mirrors the TS exactly, including the `s = s * 1.5` placement: with both
    # present the result is (s3m*1.5 + s12m) / 2.5 — the intended weighted
    # average, just written in an order that reads like a bug and isn't.
    s = 0.0
    w = 0.0
    if perf3m is not None:
        s += 90 if perf3m > 0.15 else 72 if perf3m > 0.05 else 55 if perf3m > 0 else 38 if perf3m > -0.1 else 18
        w += 1.5
        s = s * 1.5
    if perf12m is not None:
        s += 88 if perf12m > 0.25 else 70 if perf12m > 0.10 else 52 if perf12m > 0 else 33 if perf12m > -0.2 else 14
        w += 1
    return s / w if w > 0 else 50


def _score_ma_position(
    price: Optional[float], ma50: Optional[float], ma200: Optional[float]
) -> float:
    if price is None:
        return 50
    s = 0.0
    w = 0
    if ma50 is not None:
        pct = price / ma50 - 1
        s += 80 if pct > 0.05 else 62 if pct > 0 else 42 if pct > -0.05 else 22
        w += 1
    if ma200 is not None:
        pct = price / ma200 - 1
        s += 85 if pct > 0.10 else 65 if pct > 0 else 38 if pct > -0.10 else 18
        w += 1
    return s / w if w > 0 else 50


def _score_relative_strength(rs3m: Optional[float]) -> float:
    if rs3m is None:
        return 50
    if rs3m > 0.10:
        return 88
    if rs3m > 0.03:
        return 72
    if rs3m > -0.03:
        return 52
    if rs3m > -0.10:
        return 34
    return 16


# ── public API ──────────────────────────────────────────────────────────────


@dataclass
class StockMetrics:
    """The subset of `StockMetricsInput` the three scorers actually read."""

    revenue_yoy: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    fcf_margin: Optional[float] = None
    fcf_conversion: Optional[float] = None
    roe: Optional[float] = None
    net_debt: Optional[float] = None
    current_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    fcf_yield: Optional[float] = None
    ev_ebitda: Optional[float] = None
    pe_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    price: Optional[float] = None
    perf3m: Optional[float] = None
    perf12m: Optional[float] = None
    ma50: Optional[float] = None
    ma200: Optional[float] = None
    rs_vs_sector: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "StockMetrics":
        """Accepts the camelCase keys the fixture and the TS side use."""
        alias = {
            "revenueYoy": "revenue_yoy",
            "grossMargin": "gross_margin",
            "operatingMargin": "operating_margin",
            "fcfMargin": "fcf_margin",
            "fcfConversion": "fcf_conversion",
            "netDebt": "net_debt",
            "currentRatio": "current_ratio",
            "debtToEquity": "debt_to_equity",
            "fcfYield": "fcf_yield",
            "evEbitda": "ev_ebitda",
            "peRatio": "pe_ratio",
            "pegRatio": "peg_ratio",
            "rsVsSector": "rs_vs_sector",
        }
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {}
        for k, v in d.items():
            key = alias.get(k, k)
            if key in known:
                kwargs[key] = v
        return cls(**kwargs)


def health_score(m: StockMetrics) -> int:
    return _clamp(
        _score_revenue_growth(m.revenue_yoy) * 0.20
        + _score_margin(m.gross_margin, m.operating_margin) * 0.20
        + _score_fcf(m.fcf_margin, m.fcf_conversion) * 0.20
        + _score_roe(m.roe) * 0.20
        + _score_balance_sheet(m.net_debt, m.current_ratio, m.debt_to_equity) * 0.20
    )


def valuation_score(m: StockMetrics) -> int:
    return _clamp(
        _score_fcf_yield(m.fcf_yield) * 0.28
        + _score_ev_ebitda(m.ev_ebitda) * 0.27
        + _score_pe(m.pe_ratio) * 0.22
        + _score_peg(m.peg_ratio) * 0.17
        + 50 * 0.06  # DCF placeholder: neutral
    )


def trend_score(m: StockMetrics) -> int:
    has_any = (
        m.perf3m is not None
        or m.perf12m is not None
        or m.ma50 is not None
        or m.ma200 is not None
    )
    if not has_any:
        return 50  # neutral placeholder when no price data
    return _clamp(
        _score_momentum(m.perf3m, m.perf12m) * 0.35
        + _score_ma_position(m.price, m.ma50, m.ma200) * 0.30
        + _score_relative_strength(m.rs_vs_sector) * 0.20
        + 50 * 0.15  # volume + EPS revision — neutral placeholder
    )


def final_score(health: int, valuation: int, trend: int) -> int:
    return _clamp(health * 0.40 + valuation * 0.30 + trend * 0.30)


def final_label(score: int) -> str:
    if score >= 80:
        return "Attractive"
    if score >= 60:
        return "Moderately Positive"
    if score >= 40:
        return "Neutral"
    if score >= 20:
        return "Caution"
    return "High Risk / Avoid"


@dataclass
class ThreeDimensionalScore:
    health: int
    valuation: int
    trend: int
    final: int
    label: str


def score_stock(m: StockMetrics) -> ThreeDimensionalScore:
    h = health_score(m)
    v = valuation_score(m)
    t = trend_score(m)
    f = final_score(h, v, t)
    return ThreeDimensionalScore(health=h, valuation=v, trend=t, final=f, label=final_label(f))
