"""Assembling one episode's analytics — §3.3, and the anchoring rule of §3.2.1.

The type layout carries the leakage boundary, and it is not cosmetic:

- **`FillAnalytics` is one decision moment.** Markouts and the technical state
  live here, because each fill has its own price and its own date.
- **`EpisodeAnalytics` is the position.** Excursions live here, because "how
  far under water did this go" has one answer for the whole position.
- `setup_type` sits on the fill (decision-time); `timing_outcome` sits on the
  episode (it needs the position's whole future). Anything reaching for a
  `timing_outcome` while building a rule is reaching across that boundary, and
  the layout makes the reach visible.

**The anchoring rule.** An episode built from `BUY 100 (Jan 5) / BUY 50 (Feb
20) / SELL 150 (Mar 3)` has one weighted-average cost and *three decision
moments*. Anchoring a timing markout to the weighted-average price at the
first fill's date measures a position the user never held: on Jan 5 they held
100 shares at the Jan 5 price, not 150 at a blend that did not exist until
February. So markouts are per fill event, and the weighted average is used
only for P/L and excursions — where it is correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.services.mirror.reconstruction import TradeEpisode
from app.services.timing.bars import BarSeries
from app.services.timing.classify import setup_type, timing_outcome
from app.services.timing.excursion import Excursion, excursion
from app.services.timing.markout import FillMarkouts, fill_markouts
from app.services.timing.snapshot import TechnicalSnapshot, snapshot_at
from app.services.trading_behavior import _num, _parse_date

__all__ = [
    "FillAnalytics", "EpisodeAnalytics", "analyse_episode",
    "OPENING_ENTRY", "ADD_ON", "PARTIAL_EXIT", "FINAL_EXIT",
]

OPENING_ENTRY = "opening_entry"
ADD_ON = "add_on"
PARTIAL_EXIT = "partial_exit"
FINAL_EXIT = "final_exit"


@dataclass
class FillAnalytics:
    """One decision moment."""

    fill_date: date
    fill_price: float
    units: float
    role: str
    markouts: Dict[int, Optional[float]] = field(default_factory=dict)
    unavailable: Dict[int, str] = field(default_factory=dict)
    state: TechnicalSnapshot = field(default_factory=TechnicalSnapshot)
    setup_type: Optional[str] = None

    @property
    def is_entry(self) -> bool:
        return self.role in (OPENING_ENTRY, ADD_ON)


@dataclass
class EpisodeAnalytics:
    """Properties of the position."""

    episode: TradeEpisode
    fills: List[FillAnalytics] = field(default_factory=list)
    mae: Optional[float] = None
    mfe: Optional[float] = None
    mae_date: Optional[date] = None
    mfe_date: Optional[date] = None
    profit_capture: Optional[float] = None
    excursion_precision: Optional[str] = None
    timing_outcome: Optional[str] = None
    excluded_reason: Optional[str] = None

    @property
    def opening_entry(self) -> Optional[FillAnalytics]:
        """The decision that started the position.

        Per-episode aggregates use this rather than an add-on: averaging in is
        a different behaviour from opening, and reporting them as one
        population mixes two decisions.
        """
        for f in self.fills:
            if f.role == OPENING_ENTRY:
                return f
        return None

    @property
    def final_exit(self) -> Optional[FillAnalytics]:
        for f in reversed(self.fills):
            if f.role == FINAL_EXIT:
                return f
        return None

    @property
    def entries(self) -> List[FillAnalytics]:
        return [f for f in self.fills if f.is_entry]

    @property
    def exits(self) -> List[FillAnalytics]:
        return [f for f in self.fills if not f.is_entry]


def _rows(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in raw:
        when = _parse_date(r.get("trade_date"))
        price = _num(r.get("price"))
        units = _num(r.get("units"))
        if when is None or price is None:
            continue
        out.append({"when": when, "price": price, "units": abs(units or 0.0)})
    out.sort(key=lambda r: r["when"])
    return out


def analyse_episode(
    episode: TradeEpisode,
    series: BarSeries,
    *,
    benchmark: Optional[BarSeries] = None,
    volatility: Optional[BarSeries] = None,
    sector: Optional[BarSeries] = None,
    with_state: bool = True,
) -> EpisodeAnalytics:
    """Markouts per fill, excursions per position, and the two labels."""
    out = EpisodeAnalytics(episode=episode)

    entries = _rows(episode.entries)
    exits = _rows(episode.exits)
    closed = episode.closed_on is not None

    def build(row, role, side) -> FillAnalytics:
        # Anchored to THIS fill's own price and date — never to the episode's
        # weighted average, and never to the first fill's date (§3.2.1).
        m: FillMarkouts = fill_markouts(
            series, row["when"], row["price"], side=side)
        fa = FillAnalytics(
            fill_date=row["when"], fill_price=row["price"], units=row["units"],
            role=role, markouts=m.markouts, unavailable=m.unavailable,
        )
        if with_state:
            fa.state = snapshot_at(
                series, row["when"], benchmark=benchmark,
                volatility=volatility, sector=sector,
            )
            # Decision-time information only. `setup_type` reads the snapshot
            # and cannot see `fa.markouts` — see classify.py.
            fa.setup_type = setup_type(fa.state)
        return fa

    for i, row in enumerate(entries):
        out.fills.append(build(row, OPENING_ENTRY if i == 0 else ADD_ON, "entry"))
    for i, row in enumerate(exits):
        last = closed and i == len(exits) - 1
        out.fills.append(build(row, FINAL_EXIT if last else PARTIAL_EXIT, "exit"))

    ex: Excursion = excursion(series, episode)
    out.mae, out.mfe = ex.mae, ex.mfe
    out.mae_date, out.mfe_date = ex.mae_date, ex.mfe_date
    out.profit_capture = ex.profit_capture
    out.excursion_precision = ex.precision
    out.excluded_reason = ex.excluded_reason

    opening = out.opening_entry
    final = out.final_exit
    out.timing_outcome = timing_outcome(
        entry_markouts=opening.markouts if opening else None,
        exit_markouts=final.markouts if final else None,
        mae=out.mae, mfe=out.mfe,
        realised_return=episode.realised_return,
        entry_setup=opening.setup_type if opening else None,
    )
    return out
