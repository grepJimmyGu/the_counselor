"""Technical state at one decision moment — §3.5.

Every value comes from a **catalog primitive** via `get_signal_provider`. The
rule in the kickoff prompt is blunt about it — *"Do NOT write an RSI"* — and
the reason is not tidiness: a second RSI in the codebase would drift from the
one the backtester runs, so a rule discovered here would be tested against a
different indicator than the one it compiles into.

The catalog's providers expose `_compute(frame) -> pd.Series`, which is the
seam this module uses, feeding it `BarSeries.frame()`. That buys two things a
second DB read could not: the snapshot sits in the **same split frame** as the
markouts and excursions measured beside it, and the whole episode set costs one
query per symbol.

**Everything in here is decision-time information.** It is what was on the
chart at the moment of the fill, and it is the only input `classify.setup_type`
is allowed to read (§3.6.1). Nothing in this module may import a markout or an
excursion — `tests/test_timing_labels.py` asserts that statically.

Unavailable features return `None` **with a reason**, never a proxy. VIX
coverage in `price_bars` is unverified; if it is absent the market group
degrades and the rest still computes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from app.services.backtester.signal_provider import get_signal_provider
from app.services.timing.bars import BarSeries

__all__ = ["TechnicalSnapshot", "snapshot_at", "MARKET_SYMBOLS"]

MARKET_SYMBOLS = {"benchmark": "SPY", "volatility": "^VIX"}

# Warmup the longest primitive needs (sma200 -> 230 calendar days of lookback).
WARMUP_DAYS = 420


@dataclass
class TechnicalSnapshot:
    on_date: Optional[date] = None
    values: Dict[str, Optional[float]] = field(default_factory=dict)
    unavailable: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> Optional[float]:
        return self.values.get(key)


def _provider_series(name: str, frame: pd.DataFrame, **params) -> Optional[pd.Series]:
    """Run one catalog primitive over our own split-adjusted frame."""
    try:
        base = get_signal_provider(name)
    except KeyError:
        return None
    provider = type(base).with_params(**params) if params else base
    try:
        return provider._compute(frame)
    except Exception:
        # A primitive that cannot compute on this window is a missing feature,
        # not a failed snapshot. The caller records the reason.
        return None


def _value_at(series: Optional[pd.Series], stamp: pd.Timestamp) -> Optional[float]:
    if series is None or series.empty:
        return None
    try:
        window = series.loc[series.index <= stamp]
    except TypeError:
        return None
    if window.empty:
        return None
    v = window.iloc[-1]
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def snapshot_at(
    series: BarSeries,
    when: date,
    *,
    benchmark: Optional[BarSeries] = None,
    volatility: Optional[BarSeries] = None,
    sector: Optional[BarSeries] = None,
) -> TechnicalSnapshot:
    """State on the last bar at or before `when`.

    `series` must carry `WARMUP_DAYS` of history before `when` for the long
    moving averages to have a value; without it they return `None` with a
    reason rather than a value computed off a short window.
    """
    snap = TechnicalSnapshot()
    i = series.pos_on_or_after(when)
    if i is None or not len(series):
        snap.unavailable["all"] = "no_bars"
        return snap
    snap.on_date = series.dates[i]
    stamp = pd.Timestamp(snap.on_date)
    frame = series.frame()
    close = series.close(i)

    def put(key: str, value: Optional[float], reason: str = "unavailable") -> None:
        if value is None:
            snap.values[key] = None
            snap.unavailable[key] = reason
        else:
            snap.values[key] = value

    # ── trend ───────────────────────────────────────────────────────────────
    smas: Dict[int, Optional[pd.Series]] = {}
    for period in (20, 50, 200):
        smas[period] = _provider_series("sma", frame, period=period)
        val = _value_at(smas[period], stamp)
        put(f"close_over_sma{period}", (close / val) if val else None,
            "insufficient_history")

    for period in (20, 50):
        s = smas[period]
        slope = None
        if s is not None:
            window = s.loc[s.index <= stamp].dropna()
            if len(window) > 5 and window.iloc[-6]:
                slope = float(window.iloc[-1] / window.iloc[-6] - 1.0)
        put(f"sma{period}_slope", slope, "insufficient_history")

    # ── momentum ────────────────────────────────────────────────────────────
    put("rsi14", _value_at(_provider_series("rsi", frame, period=14), stamp))
    put("macd", _value_at(_provider_series("macd", frame), stamp))
    put("adx14", _value_at(_provider_series("adx", frame, period=14), stamp))

    # ── volatility ──────────────────────────────────────────────────────────
    put("atr14", _value_at(_provider_series("atr", frame, period=14), stamp))
    put("natr14", _value_at(_provider_series("natr", frame, period=14), stamp))
    put("realized_vol20", _value_at(
        _provider_series("realized_vol", frame, period=20), stamp))

    # ── extension ───────────────────────────────────────────────────────────
    for back in (1, 3, 5, 20):
        j = i - back
        prior = series.close(j) if j >= 0 else None
        put(f"return_{back}d",
            ((close - prior) / prior) if prior else None, "insufficient_history")

    for period in (20, 50):
        val = _value_at(smas[period], stamp)
        put(f"distance_from_sma{period}",
            ((close - val) / val) if val else None, "insufficient_history")

    for label, back in (("20d", 20), ("52w", 252)):
        lo = max(0, i - back + 1)
        window = [h for h in series.highs[lo:i + 1] if h == h]
        peak = max(window) if window else None
        enough = (i - lo + 1) >= min(back, 20)
        put(f"distance_from_{label}_high",
            ((close - peak) / peak) if (peak and enough) else None,
            "insufficient_history")

    # ── volume ──────────────────────────────────────────────────────────────
    lo = max(0, i - 19)
    vols = [v for v in series.volumes[lo:i + 1] if v == v]
    avg = (sum(vols) / len(vols)) if vols else None
    here = series.volumes[i]
    put("relative_volume",
        (here / avg) if (avg and here == here) else None, "insufficient_history")

    # ── market context ──────────────────────────────────────────────────────
    # Never proxied. An absent benchmark degrades this group and nothing else.
    _market_context(snap, series, i, benchmark, volatility, sector, put)
    return snap


def _trailing_return(series: BarSeries, when: date, back: int) -> Optional[float]:
    i = series.pos_on_or_after(when)
    if i is None:
        return None
    j = i - back
    if j < 0:
        return None
    prior, now = series.close(j), series.close(i)
    if not prior or prior != prior or now != now:
        return None
    return (now - prior) / prior


def _market_context(snap, series, i, benchmark, volatility, sector, put) -> None:
    when = series.dates[i]
    own20 = _trailing_return(series, when, 20)

    if benchmark is None:
        for key in ("benchmark_trend20", "relative_strength_20d"):
            put(key, None, "no_benchmark_bars")
    else:
        bench20 = _trailing_return(benchmark, when, 20)
        put("benchmark_trend20", bench20, "insufficient_history")
        put("relative_strength_20d",
            (own20 - bench20) if (own20 is not None and bench20 is not None) else None,
            "insufficient_history")

    if sector is None:
        put("sector_relative_strength_20d", None, "no_sector_bars")
    else:
        sec20 = _trailing_return(sector, when, 20)
        put("sector_relative_strength_20d",
            (own20 - sec20) if (own20 is not None and sec20 is not None) else None,
            "insufficient_history")

    if volatility is None:
        # VIX coverage in `price_bars` is unverified (§3.5). Absent is a stated
        # reason, never a substituted proxy.
        put("vix", None, "no_vix_bars")
    else:
        j = volatility.pos_on_or_after(when)
        put("vix", volatility.close(j) if j is not None else None, "no_vix_bars")
