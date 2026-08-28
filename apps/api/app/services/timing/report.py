"""Aggregates over a whole record — §3.1's profile, §3.6.3's breakdown, §3.7's leak.

Three rules shape everything here, and each exists because breaking it
produced a wrong finding on a real account:

**Every aggregate carries its N.** 126 closed trades split three ways is
16-trade cells. Low-N rows render with their sample size and never auto-promote
to a recommended rule.

**Opening entries and add-ons are separate populations.** Averaging in is a
different decision from opening a position; the entry-timing profile is mostly
a statement about openings, and mixing them describes neither.

**The leak ranking is deterministic and priced in dollars.** Not "the model
thought this was most important" — the largest dollar gap, computed the same
way every time, so two runs on the same record name the same leak.

⚠ The dollar figures here attribute the SAME money 43a's roll-up prices at a
coarser grain. They are a breakdown of it, never an addition to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Dict, List, Optional, Sequence

from app.services.timing.analytics import (
    ADD_ON, EpisodeAnalytics, FINAL_EXIT, OPENING_ENTRY, PARTIAL_EXIT,
)
from app.services.timing.markout import (
    MARKOUT_HORIZONS, FillMarkouts, MarkoutProfile, aggregate_markouts,
)

__all__ = [
    "SetupRow", "ExcursionSummary", "Leak", "TimingCoverage", "TimingReport",
    "build_report",
]

# A gap smaller than this is not worth naming as a leak.
_MIN_LEAK_DOLLARS = 1.0


@dataclass
class SetupRow:
    """One decision-time category, with its consequences measured.

    This is `setup_type` CONDITIONING the outcome measures — legitimate, and
    the engine's most valuable output. What would be illegitimate is a category
    defined by its own consequences, which is what a single merged label gives.
    """

    setup: Optional[str]                    # None == matched no category
    n: int = 0
    wins: int = 0
    median_return: Optional[float] = None
    median_mae: Optional[float] = None
    median_capture: Optional[float] = None

    @property
    def win_rate(self) -> Optional[float]:
        return (self.wins / self.n) if self.n else None

    @property
    def label(self) -> str:
        return self.setup or "unclassified"


@dataclass
class ExcursionSummary:
    """Winner vs loser drawdown — the paired statistic that teaches the most.

    If winning trades routinely dip 4% before working, the user learns what
    normal looks like for their own method, which is the input to a stop that
    does not shake them out of their own winners.

    ⚠ `same_day_excluded` must be rendered wherever this is. Same-day episodes
    have no excursion at all, and a reader who does not know they were dropped
    will read the gap as covering the whole record.
    """

    winner_mae: Optional[float] = None
    winner_n: int = 0
    loser_mae: Optional[float] = None
    loser_n: int = 0
    median_capture: Optional[float] = None
    capture_n: int = 0
    same_day_excluded: int = 0
    approximate_boundary: int = 0


@dataclass
class Leak:
    key: str
    n: int
    dollars: float
    detail: str = ""


@dataclass
class TimingCoverage:
    episodes_total: int = 0
    episodes_measured: int = 0
    excluded: Dict[str, int] = field(default_factory=dict)
    unclassified_entries: int = 0
    classified_entries: int = 0

    @property
    def unclassified_share(self) -> Optional[float]:
        total = self.unclassified_entries + self.classified_entries
        return (self.unclassified_entries / total) if total else None


@dataclass
class TimingReport:
    opening_entry_profile: MarkoutProfile = field(default_factory=MarkoutProfile)
    add_on_profile: MarkoutProfile = field(default_factory=MarkoutProfile)
    final_exit_profile: MarkoutProfile = field(default_factory=MarkoutProfile)
    partial_exit_profile: MarkoutProfile = field(default_factory=MarkoutProfile)
    excursions: ExcursionSummary = field(default_factory=ExcursionSummary)
    setups: List[SetupRow] = field(default_factory=list)
    outcomes: Dict[str, int] = field(default_factory=dict)
    leaks: List[Leak] = field(default_factory=list)
    coverage: TimingCoverage = field(default_factory=TimingCoverage)

    @property
    def biggest_leak(self) -> Optional[Leak]:
        return self.leaks[0] if self.leaks else None

    @property
    def second_leak(self) -> Optional[Leak]:
        return self.leaks[1] if len(self.leaks) > 1 else None


def _profile(rows: Sequence[EpisodeAnalytics], role: str) -> MarkoutProfile:
    marks = [
        FillMarkouts(anchor_date=f.fill_date, markouts=f.markouts,
                     unavailable=f.unavailable)
        for a in rows for f in a.fills if f.role == role
    ]
    return aggregate_markouts(marks)


def _median_or_none(values: List[float]) -> Optional[float]:
    return median(values) if values else None


def _after_exit(a: EpisodeAnalytics, horizon: int = 5) -> Optional[float]:
    """What the stock did after the final exit, undoing the engine's negation."""
    final = a.final_exit
    if final is None:
        return None
    v = final.markouts.get(horizon)
    return None if v is None else -v


def _units_held_on(a: EpisodeAnalytics, when: Optional[date]) -> float:
    """Open units on a given date — entries up to it, less exits up to it."""
    if when is None:
        return 0.0
    held = 0.0
    for f in a.fills:
        if f.fill_date > when:
            continue
        held += f.units if f.is_entry else -f.units
    return max(0.0, held)


def _leak_dollars(rows: Sequence[EpisodeAnalytics]) -> Dict[str, List[float]]:
    """Price each diagnosis in dollars, deterministically.

    Every figure is `units × price × the gap the label names` — so the ranking
    is a fact about the record, not a judgement about which finding reads best.
    """
    buckets: Dict[str, List[float]] = {}

    def add(key: str, amount: Optional[float]) -> None:
        if amount is None or amount <= _MIN_LEAK_DOLLARS:
            return
        buckets.setdefault(key, []).append(amount)

    for a in rows:
        label = a.timing_outcome
        if not label:
            continue
        final = a.final_exit
        opening = a.opening_entry

        if label in ("premature_exit", "panic_exit") and final is not None:
            moved = _after_exit(a)
            if moved is not None and moved > 0:
                add(label, final.units * final.fill_price * moved)

        elif label == "giveback" and a.mfe is not None:
            realised = a.episode.realised_return
            held = _units_held_on(a, a.mfe_date)
            if realised is not None and held:
                # Units held AT THE PEAK, not the episode's total. A position
                # that scaled out beforehand never had the larger exposure, and
                # pricing the giveback as though it did inflates the number the
                # leak ranking is decided by.
                add(label, held * a.episode.avg_entry_price * (a.mfe - realised))

        elif label in ("chased", "early_entry") and opening is not None:
            near = [opening.markouts[h] for h in (1, 3, 5)
                    if opening.markouts.get(h) is not None]
            if near:
                drawdown = sum(near) / len(near)
                if drawdown < 0:
                    add(label, opening.units * opening.fill_price * -drawdown)

    return buckets


def build_report(rows: Sequence[EpisodeAnalytics]) -> TimingReport:
    """Everything the WHEN section renders, from a list of analysed episodes."""
    rep = TimingReport()
    rows = list(rows)

    rep.opening_entry_profile = _profile(rows, OPENING_ENTRY)
    rep.add_on_profile = _profile(rows, ADD_ON)
    rep.final_exit_profile = _profile(rows, FINAL_EXIT)
    rep.partial_exit_profile = _profile(rows, PARTIAL_EXIT)

    # ── excursions ──────────────────────────────────────────────────────────
    ex = rep.excursions
    winners, losers, captures = [], [], []
    for a in rows:
        if a.excluded_reason == "intraday_resolution_required":
            ex.same_day_excluded += 1
            continue
        if a.excursion_precision == "approximate_boundary":
            ex.approximate_boundary += 1
        realised = a.episode.realised_return
        if a.mae is not None and realised is not None:
            (winners if realised > 0 else losers).append(a.mae)
        if a.profit_capture is not None:
            captures.append(a.profit_capture)
    ex.winner_mae, ex.winner_n = _median_or_none(winners), len(winners)
    ex.loser_mae, ex.loser_n = _median_or_none(losers), len(losers)
    ex.median_capture, ex.capture_n = _median_or_none(captures), len(captures)

    # ── setup breakdown, one row per episode via the opening entry ──────────
    grouped: Dict[Optional[str], List[EpisodeAnalytics]] = {}
    for a in rows:
        opening = a.opening_entry
        grouped.setdefault(opening.setup_type if opening else None, []).append(a)

    for setup, group in grouped.items():
        returns = [a.episode.realised_return for a in group
                   if a.episode.realised_return is not None]
        maes = [a.mae for a in group if a.mae is not None]
        caps = [a.profit_capture for a in group if a.profit_capture is not None]
        rep.setups.append(SetupRow(
            setup=setup, n=len(group),
            wins=sum(1 for r in returns if r > 0),
            median_return=_median_or_none(returns),
            median_mae=_median_or_none(maes),
            median_capture=_median_or_none(caps),
        ))
    # Named categories first, by size; the unclassified bucket last but never
    # hidden — when it carries a better win rate than every named setup, the
    # taxonomy deserves review rather than a wider `other`.
    rep.setups.sort(key=lambda r: (r.setup is None, -r.n, r.label))

    for a in rows:
        if a.timing_outcome:
            rep.outcomes[a.timing_outcome] = rep.outcomes.get(a.timing_outcome, 0) + 1

    # ── leaks, ranked by dollars ────────────────────────────────────────────
    for key, amounts in _leak_dollars(rows).items():
        rep.leaks.append(Leak(key=key, n=len(amounts), dollars=sum(amounts)))
    rep.leaks.sort(key=lambda l: (-l.dollars, l.key))

    # ── coverage ────────────────────────────────────────────────────────────
    cov = rep.coverage
    cov.episodes_total = len(rows)
    for a in rows:
        if a.excluded_reason:
            cov.excluded[a.excluded_reason] = cov.excluded.get(a.excluded_reason, 0) + 1
        else:
            cov.episodes_measured += 1
        opening = a.opening_entry
        if opening is None:
            continue
        if opening.setup_type:
            cov.classified_entries += 1
        else:
            cov.unclassified_entries += 1
    return rep
