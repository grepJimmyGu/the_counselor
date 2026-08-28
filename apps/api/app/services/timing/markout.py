"""Forward returns from each decision moment — §3.1.

A markout asks: after you acted, what did the stock do? At +1/3/5/10/20
**trading days**, off the bar index, never the calendar — SnapTrade gives a
`trade_date` with no timestamp, so a horizon is an offset in the series and
nothing finer is knowable.

Two sign conventions and one aggregation rule carry most of the meaning:

**Exit markouts are negated.** A stock that rises after you sell is a *bad*
exit. §6 calls this "the one everyone gets backwards", and it is the whole
meaning of the number rather than a presentation detail.

**Aggregate as medians with quartiles, and always report N.** One 400%
outlier should not define a profile. And a profile whose quartiles straddle
zero at every horizon is *noise* — the first real account produced exactly
that, and rendering a diagnosis from its medians alone was the v1 script's
worst defect. `MarkoutProfile.has_consistent_pattern` exists so the surface
can say "no consistent timing pattern in your entries", which is itself a
useful finding, rather than inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.timing.bars import BarSeries

__all__ = [
    "MARKOUT_HORIZONS", "FillMarkouts", "HorizonStat", "MarkoutProfile",
    "fill_markouts", "aggregate_markouts",
]

MARKOUT_HORIZONS: Tuple[int, ...] = (1, 3, 5, 10, 20)


@dataclass
class FillMarkouts:
    """One decision moment's forward returns."""

    anchor_date: Optional[date] = None
    markouts: Dict[int, Optional[float]] = field(default_factory=dict)
    unavailable: Dict[int, str] = field(default_factory=dict)
    side: str = "entry"


@dataclass
class HorizonStat:
    horizon: int
    n: int = 0
    median: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None

    @property
    def straddles_zero(self) -> bool:
        """True when the interquartile range contains zero — i.e. the sign of
        the median is not supported by the bulk of the distribution."""
        if self.q1 is None or self.q3 is None:
            return True
        return self.q1 <= 0.0 <= self.q3


@dataclass
class MarkoutProfile:
    horizons: List[HorizonStat] = field(default_factory=list)
    excluded_beyond_window: int = 0

    @property
    def has_consistent_pattern(self) -> bool:
        """False when every horizon's quartiles straddle zero.

        The surface renders that as "no consistent timing pattern", never as a
        diagnosis read out of the medians.
        """
        return any(not h.straddles_zero for h in self.horizons if h.n)


def fill_markouts(
    series: BarSeries,
    fill_date: date,
    fill_price: float,
    *,
    side: str = "entry",
    horizons: Sequence[int] = MARKOUT_HORIZONS,
) -> FillMarkouts:
    """Forward returns from one fill, in the series' split frame.

    `fill_price` is restated into that frame before anything is divided by it
    — a 20-day markout spanning a 10:1 split on a raw fill price reports −90%
    and lands in the aggregate as a timing catastrophe that never happened.
    """
    out = FillMarkouts(side=side)
    i = series.pos_on_or_after(fill_date)
    if i is None:
        for h in horizons:
            out.markouts[h] = None
            out.unavailable[h] = "no_bars"
        return out

    out.anchor_date = series.dates[i]
    anchored = series.restate(fill_price, out.anchor_date)
    if not anchored or anchored != anchored:                 # zero or NaN
        for h in horizons:
            out.markouts[h] = None
            out.unavailable[h] = "no_fill_price"
        return out

    sign = -1.0 if side == "exit" else 1.0
    for h in horizons:
        j = i + h
        if j >= len(series):
            # Never truncated to the last available bar: that quietly turns a
            # 20-day markout into a 6-day one and files it in the 20-day row.
            out.markouts[h] = None
            out.unavailable[h] = "beyond_window"
            continue
        close = series.close(j)
        if close != close:
            out.markouts[h] = None
            out.unavailable[h] = "no_bar_close"
            continue
        out.markouts[h] = sign * (close - anchored) / anchored
    return out


def _quartiles(values: List[float]) -> Tuple[float, float]:
    """Q1/Q3 by the median-of-halves rule. Hand-rolled because the dependency
    floor is pandas + numpy and this needs neither (HANDOFF §6J)."""
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return ordered[0], ordered[0]
    half = n // 2
    lower = ordered[:half]
    upper = ordered[half + 1:] if n % 2 else ordered[half:]
    return median(lower or ordered), median(upper or ordered)


def aggregate_markouts(
    rows: Sequence[FillMarkouts],
    horizons: Sequence[int] = MARKOUT_HORIZONS,
) -> MarkoutProfile:
    """Medians and quartiles per horizon, each carrying its own N.

    N is per horizon rather than per profile because they genuinely differ:
    a fill six days before the window ends contributes to 1/3/5 and not to
    10/20, and reporting one N across the table would overstate the long
    horizons exactly where the sample thins out.
    """
    prof = MarkoutProfile()
    for h in horizons:
        vals = [
            r.markouts[h] for r in rows
            if r.markouts.get(h) is not None
        ]
        stat = HorizonStat(horizon=h, n=len(vals))
        if vals:
            stat.median = median(vals)
            stat.q1, stat.q3 = _quartiles(vals)
        prof.horizons.append(stat)
    prof.excluded_beyond_window = sum(
        1 for r in rows for h in horizons
        if r.unavailable.get(h) == "beyond_window"
    )
    return prof
