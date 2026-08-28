"""MAE / MFE and profit capture — §3.2.

These are properties of the POSITION, not of a fill: "how far under water did
this trade go" has one answer per episode. Markouts are the opposite (§3.2.1),
which is why the two live in different modules and hang off different objects.

```
MAE = (min(low)  − avg_entry) / avg_entry     # worst drawdown while held
MFE = (max(high) − avg_entry) / avg_entry     # best unrealised gain
```

**These read `high`/`low`, which are RAW in `price_bars`.** `adjusted_close`
does not help — it is the wrong column and carries dividend adjustments
besides. `BarSeries` restates the range into one split frame; a 10:1 split
mid-episode otherwise makes MAE read −90%, which is both wrong and alarming.

**A same-day round trip has no computable excursion.** Opened and closed
inside one session, we know the daily range and nothing about where inside it
the user actually was. The range is an upper bound on the possible, not a
measurement of the experienced. Inventing a −8% MAE for a position held twenty
minutes would propagate straight into the winner-vs-loser MAE gap that stop
parameters get read from — which is the number most likely to be turned into
a rule. So: `None`, with a stated reason, counted in coverage, and absent from
every aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.services.mirror.reconstruction import TradeEpisode
from app.services.timing.bars import BarSeries

__all__ = ["Excursion", "excursion"]


@dataclass
class Excursion:
    mae: Optional[float] = None
    mfe: Optional[float] = None
    # The bar each extreme occurred on. Exposed because a dollar figure built
    # on an excursion has to know how much of the position was actually on at
    # that moment — see `report._units_held_on`.
    mae_date: Optional[date] = None
    mfe_date: Optional[date] = None
    profit_capture: Optional[float] = None
    precision: Optional[str] = None          # "exact" | "approximate_boundary"
    excluded_reason: Optional[str] = None


def excursion(series: BarSeries, episode: TradeEpisode) -> Excursion:
    """Excursions over one episode's own holding window."""
    out = Excursion()

    opened = episode.opened_on
    closed = episode.closed_on or (series.dates[-1] if len(series) else None)
    if closed is None or not len(series):
        out.excluded_reason = "no_bars"
        return out

    if episode.closed_on is not None and episode.closed_on == opened:
        # See the module docstring. This is the one exclusion in 43b that is
        # about what is *knowable*, not about what is missing.
        out.excluded_reason = "intraday_resolution_required"
        return out

    start = series.pos_on_or_after(opened)
    if start is None:
        out.excluded_reason = "no_bars"
        return out
    end = start
    for i in range(start, len(series)):
        if series.dates[i] > closed:
            break
        end = i

    entry = series.restate(episode.avg_entry_price, series.dates[start])
    if not entry or entry != entry:
        out.excluded_reason = "no_entry_price"
        return out

    lows = [(series.lows[i], i) for i in range(start, end + 1)
            if series.lows[i] == series.lows[i]]
    highs = [(series.highs[i], i) for i in range(start, end + 1)
             if series.highs[i] == series.highs[i]]
    if not lows or not highs:
        out.excluded_reason = "no_bars"
        return out

    low, low_i = min(lows, key=lambda t: t[0])
    high, high_i = max(highs, key=lambda t: t[0])
    out.mae = min(0.0, (low - entry) / entry)
    out.mfe = max(0.0, (high - entry) / entry)
    out.mae_date = series.dates[low_i]
    out.mfe_date = series.dates[high_i]

    # The entry day's low and the exit day's high are only partly inside the
    # holding window — the user was not in the position for all of either bar.
    # Interior bars are exact, so an episode whose extremes both land inside
    # is exact regardless of its length.
    boundary = {start, end}
    out.precision = (
        "exact" if low_i not in boundary and high_i not in boundary
        else "approximate_boundary"
    )

    realised = episode.realised_return
    if realised is not None and realised > 0 and out.mfe > 0:
        # Winners only. Undefined for losers and for MFE <= 0 — and `None`
        # rather than 0.0, because zero is a real value meaning "captured
        # nothing" and collapsing the two puts every loser into the average.
        out.profit_capture = realised / out.mfe
    return out
