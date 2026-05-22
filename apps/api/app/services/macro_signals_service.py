"""Macro Pulse signal builder — Phase 1c.

Produces the 4-row payload consumed by `MacroPulseTable.tsx`:
  Growth (ISM Services PMI)
  Inflation (Core CPI proxy via headline CPI)
  Rates (10Y Treasury yield)
  Stress (HY OAS)

Real data via Alpha Vantage where available:
  - Rates / 10Y: AV TREASURY_YIELD (maturity=10year, monthly) — real
  - Inflation / CPI: AV CPI (headline; Core CPI requires FRED) — real,
    approximate

Mock with documented "pending FRED key" status:
  - Growth / ISM Services PMI — AV doesn't expose PMI; needs FRED
    (`NMFCI` or `BACTSAMFRBNY`) or ISM direct
  - Stress / HY OAS — AV doesn't expose ICE BofA OAS; needs FRED
    (`BAMLH0A0HYM2`)

The frontend already renders fine against the mock; this service just
swaps the real signals in. Mock signals retain the "Mock data" caveat
in their `explanation` field so users see what's real vs not.

Cache: 24h. CPI + Treasury yields update daily at most; intraday hits
just reuse the cache.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.services.alpha_vantage import AlphaVantageClient, AlphaVantageError

_log = logging.getLogger("livermore.macro_signals")

# ── Output shape ─────────────────────────────────────────────────────────────


@dataclass
class MacroSignal:
    """Matches the `MacroSignal` interface in `MacroPulseTable.tsx`."""
    category: str             # "Growth" | "Inflation" | "Rates" | "Stress"
    latestLabel: str          # "10Y Yield: 4.30%"
    trendDirection: str       # "up" | "down" | "flat"
    trendLabel: str           # "Rising" | "Cooling" | "Stable"
    takeaway: str             # plain-English read
    explanation: str          # tooltip definition
    series1M: list[float]
    series1Y: list[float]
    series3Y: list[float]
    source: str               # "alpha_vantage" | "mock_pending_fred"


# ── Cache ────────────────────────────────────────────────────────────────────

_CACHE: Optional[tuple[datetime, list[MacroSignal]]] = None
_CACHE_TTL = timedelta(hours=24)


# ── Mock data (Growth + Stress where AV has no source) ──────────────────────

_MOCK_GROWTH = MacroSignal(
    category="Growth",
    latestLabel="ISM Services PMI: 52.0",
    trendDirection="up",
    trendLabel="Improving",
    takeaway="Economy still expanding",
    explanation=(
        "ISM Services PMI — monthly diffusion index of services sector "
        "activity. >50 = expansion, <50 = contraction. Mock data pending "
        "FRED API key for the real series (NMFCI)."
    ),
    series1M=[51.4, 51.7, 51.9, 52.1, 52.0, 52.0, 52.2, 52.0],
    series1Y=[
        50.8, 51.0, 51.2, 51.5, 51.6, 51.8, 51.7, 51.9, 52.0, 52.0, 52.1, 52.0,
    ],
    series3Y=[
        53.1, 52.5, 51.8, 50.9, 49.5, 48.2, 47.5, 48.0, 49.0, 50.1, 51.0, 52.0,
    ],
    source="mock_pending_fred",
)


_MOCK_STRESS = MacroSignal(
    category="Stress",
    latestLabel="HY Spread: 3.4%",
    trendDirection="flat",
    trendLabel="Stable",
    takeaway="Credit risk contained",
    explanation=(
        "ICE BofA US High-Yield Option-Adjusted Spread — extra yield "
        "investors demand to hold junk bonds vs Treasuries. Below 4% = "
        "risk-on; 4-6% = stretched; above 7% = credit stress. Mock data "
        "pending FRED API key for the real series (BAMLH0A0HYM2)."
    ),
    series1M=[3.35, 3.40, 3.42, 3.38, 3.40, 3.41, 3.40, 3.40],
    series1Y=[
        3.85, 3.75, 3.65, 3.55, 3.50, 3.45, 3.40, 3.38, 3.40, 3.42, 3.40, 3.40,
    ],
    series3Y=[
        4.50, 4.30, 4.10, 3.90, 3.80, 3.85, 4.00, 3.90, 3.75, 3.60, 3.50, 3.40,
    ],
    source="mock_pending_fred",
)


# ── Real-data builders ──────────────────────────────────────────────────────


def _trend_from_series(series: list[float], threshold: float = 0.0) -> tuple[str, str]:
    """Compare last value to median of prior values; return
    (direction, label). Threshold is the relative-change band counted as
    'flat'. Direction maps to MacroPulseTable's expected enum."""
    if len(series) < 2:
        return "flat", "Stable"
    latest = series[-1]
    prior = statistics.median(series[:-1])
    if prior == 0:
        return "flat", "Stable"
    delta = (latest - prior) / abs(prior)
    if abs(delta) < threshold:
        return "flat", "Stable"
    return ("up", "Rising") if delta > 0 else ("down", "Cooling")


async def _build_rates_signal(av: AlphaVantageClient) -> MacroSignal:
    """Real 10Y Treasury yield via AV. Monthly data, last 3 yrs."""
    data = await av.fetch_treasury_yield(maturity="10year", interval="monthly")
    # data is chronological after fetch_treasury_yield()'s reverse() —
    # each entry is { "date": "YYYY-MM-DD", "value": "4.30" }.
    series_3y_full = [
        float(d["value"]) for d in data if d.get("value") not in (None, ".")
    ]
    series3Y = series_3y_full[-36:] if len(series_3y_full) >= 36 else series_3y_full
    series1Y = series_3y_full[-12:] if len(series_3y_full) >= 12 else series_3y_full
    # Monthly cadence — 1M sparkline gets the last point repeated as a flat
    # line of 8 samples so the visual doesn't collapse to a single dot.
    last = series_3y_full[-1] if series_3y_full else 4.0
    series1M = [last] * 8

    direction, label = _trend_from_series(series1Y, threshold=0.005)
    if direction == "up":
        takeaway = "Headwind for growth stocks"
    elif direction == "down":
        takeaway = "Tailwind for duration-sensitive sectors"
    else:
        takeaway = "Rates holding range"

    return MacroSignal(
        category="Rates",
        latestLabel=f"10Y Yield: {last:.2f}%",
        trendDirection=direction,
        trendLabel=label,
        takeaway=takeaway,
        explanation=(
            "10-year US Treasury yield — the global risk-free rate "
            "benchmark. Discount rate for long-duration equity cash flows. "
            "Rising = pressure on growth multiples; falling = relief rally "
            "for duration-sensitive sectors (tech, REITs, utilities). "
            "Source: Alpha Vantage TREASURY_YIELD (monthly)."
        ),
        series1M=series1M,
        series1Y=series1Y,
        series3Y=series3Y,
        source="alpha_vantage",
    )


async def _build_inflation_signal(av: AlphaVantageClient) -> MacroSignal:
    """Real CPI via AV. Note: this is HEADLINE CPI; Core CPI (the Fed's
    preferred gauge) requires FRED. Approximation called out in the
    `explanation`."""
    data = await av.fetch_cpi(interval="monthly")
    # CPI is reported as an INDEX (not a YoY %). Compute YoY% over the
    # series to get the headline-CPI rate-of-change figure the user
    # expects to see ("3.4%" not "320.5").
    index_series = [
        float(d["value"]) for d in data if d.get("value") not in (None, ".")
    ]
    yoy_series: list[float] = []
    for i in range(12, len(index_series)):
        prior = index_series[i - 12]
        if prior > 0:
            yoy_series.append((index_series[i] - prior) / prior * 100.0)

    series3Y = yoy_series[-36:] if len(yoy_series) >= 36 else yoy_series
    series1Y = yoy_series[-12:] if len(yoy_series) >= 12 else yoy_series
    last = yoy_series[-1] if yoy_series else 3.4
    series1M = [last] * 8  # monthly cadence

    direction, label = _trend_from_series(series1Y, threshold=0.02)
    if direction == "down":
        takeaway = "Supports future rate cuts"
        label = "Cooling"
    elif direction == "up":
        takeaway = "Could delay rate cuts"
    else:
        takeaway = "Inflation steady"

    return MacroSignal(
        category="Inflation",
        latestLabel=f"CPI YoY: {last:.1f}%",
        trendDirection=direction,
        trendLabel=label,
        takeaway=takeaway,
        explanation=(
            "Year-over-year headline CPI. Approximation of Core CPI (the "
            "Fed's preferred gauge — ex food and energy). Above 3% = "
            "restrictive policy stance; trending lower = cuts on the table. "
            "Source: Alpha Vantage CPI (monthly); FRED CORESTICKM158SFRBATL "
            "for true Core CPI pending."
        ),
        series1M=series1M,
        series1Y=series1Y,
        series3Y=series3Y,
        source="alpha_vantage",
    )


# ── Public API ──────────────────────────────────────────────────────────────


async def get_macro_signals() -> list[MacroSignal]:
    """Return the 4 macro signals. Cached 24h. Real for Rates + Inflation
    (AV); mock with explanatory note for Growth + Stress (need FRED).

    Service never raises — any AV failure falls back to the existing
    full-mock signal so the page doesn't break."""
    global _CACHE
    now = datetime.utcnow()

    if _CACHE is not None:
        cached_at, cached = _CACHE
        if (now - cached_at) < _CACHE_TTL:
            return cached

    av = AlphaVantageClient()

    # Each real-data builder is wrapped in try/except so one signal's
    # failure doesn't poison the whole payload.
    signals: list[MacroSignal] = []
    signals.append(_MOCK_GROWTH)
    try:
        signals.append(await _build_inflation_signal(av))
    except (AlphaVantageError, KeyError, ValueError) as exc:
        _log.warning("macro_signals: inflation fell back to mock: %r", exc)
        signals.append(_full_mock_inflation())
    try:
        signals.append(await _build_rates_signal(av))
    except (AlphaVantageError, KeyError, ValueError) as exc:
        _log.warning("macro_signals: rates fell back to mock: %r", exc)
        signals.append(_full_mock_rates())
    signals.append(_MOCK_STRESS)

    _CACHE = (now, signals)
    return signals


def invalidate_cache() -> None:
    global _CACHE
    _CACHE = None


# ── Full mock fallbacks (when AV fails) ─────────────────────────────────────


def _full_mock_inflation() -> MacroSignal:
    return MacroSignal(
        category="Inflation",
        latestLabel="Core CPI: 3.4%",
        trendDirection="down",
        trendLabel="Cooling",
        takeaway="Supports future rate cuts",
        explanation=(
            "Core CPI — year-over-year change in consumer prices ex-food "
            "and energy. Mock data — Alpha Vantage CPI fetch failed."
        ),
        series1M=[3.6, 3.5, 3.5, 3.5, 3.4, 3.4, 3.4, 3.4],
        series1Y=[3.8, 3.7, 3.6, 3.5, 3.5, 3.4, 3.4, 3.4, 3.4, 3.4, 3.4, 3.4],
        series3Y=[5.5, 5.2, 4.9, 4.5, 4.2, 4.0, 3.8, 3.7, 3.6, 3.5, 3.4, 3.4],
        source="mock_av_failed",
    )


def _full_mock_rates() -> MacroSignal:
    return MacroSignal(
        category="Rates",
        latestLabel="10Y Yield: 4.3%",
        trendDirection="up",
        trendLabel="Rising",
        takeaway="Headwind for growth stocks",
        explanation=(
            "10-year US Treasury yield. Mock data — Alpha Vantage "
            "TREASURY_YIELD fetch failed."
        ),
        series1M=[4.15, 4.18, 4.22, 4.25, 4.27, 4.29, 4.30, 4.30],
        series1Y=[
            4.10, 4.12, 4.15, 4.18, 4.20, 4.22, 4.24, 4.25, 4.27, 4.28, 4.30, 4.30,
        ],
        series3Y=[
            3.50, 3.65, 3.80, 3.95, 4.05, 4.10, 4.15, 4.20, 4.22, 4.25, 4.28, 4.30,
        ],
        source="mock_av_failed",
    )
