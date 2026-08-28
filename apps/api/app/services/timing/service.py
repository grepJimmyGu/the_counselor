"""Driving the Timing Engine over one user's record.

The one place in 43b that touches a database. Everything under it is pure over
a `BarSeries`, which is what lets the whole engine be tested against a
hand-written book — and what keeps the split frame consistent, since the series
is built once per symbol and shared by markouts, excursions and the snapshot.

Reads are bounded by the symbols the user actually traded, never the universe
(HANDOFF §6F): a few dozen names, one query each, plus two market series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.services.mirror.reconstruction import TradeEpisode, build_episodes
from app.services.timing.analytics import EpisodeAnalytics, analyse_episode
from app.services.timing.bars import BarSeries, load_series
from app.services.timing.report import TimingReport, build_report
from app.services.timing.snapshot import MARKET_SYMBOLS, WARMUP_DAYS

__all__ = ["TimingAnalysis", "analyse_record"]

# Headroom past the last exit so a 20-trading-day markout has bars to read.
_HORIZON_HEADROOM_DAYS = 45


@dataclass
class TimingAnalysis:
    report: TimingReport = field(default_factory=TimingReport)
    episodes: List[EpisodeAnalytics] = field(default_factory=list)
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    symbols_measured: int = 0
    # (symbol, reason) — carried through from the episode builder plus any
    # symbol whose bars we simply do not hold.
    excluded: List[Tuple[str, str]] = field(default_factory=list)


def _symbol_windows(
    episodes: Sequence[TradeEpisode], window_end: date,
) -> Dict[str, Tuple[date, date]]:
    out: Dict[str, Tuple[date, date]] = {}
    for ep in episodes:
        last = ep.closed_on or window_end
        start = ep.opened_on - timedelta(days=WARMUP_DAYS)
        end = last + timedelta(days=_HORIZON_HEADROOM_DAYS)
        if ep.symbol in out:
            prev_start, prev_end = out[ep.symbol]
            out[ep.symbol] = (min(prev_start, start), max(prev_end, end))
        else:
            out[ep.symbol] = (start, end)
    return out


def analyse_record(
    db: Session,
    transactions: Sequence[Dict[str, Any]],
    *,
    positions: Optional[Sequence[Any]] = None,
    window_end: Optional[date] = None,
    with_state: bool = True,
) -> TimingAnalysis:
    """Episodes → per-fill markouts, per-position excursions, both labels.

    `transactions` are the ledger's split-resolved rows (43a §3.2), so the
    cash-equivalent and off-market exclusions have already been applied by
    `build_episodes` — §3.4's asset filtering is that shared classifier, never
    a second one here.
    """
    out = TimingAnalysis()
    episodes, excluded = build_episodes(transactions, positions=positions)
    out.excluded = list(excluded)
    if not episodes:
        out.report = build_report([])
        return out

    window_end = window_end or max(
        (ep.closed_on or ep.opened_on) for ep in episodes
    )
    out.window_start = min(ep.opened_on for ep in episodes)
    out.window_end = window_end

    windows = _symbol_windows(episodes, window_end)
    span_start = min(s for s, _ in windows.values())
    span_end = max(e for _, e in windows.values())

    # Market context: two series for the whole record, not per symbol. VIX
    # coverage is unverified (§3.5) — absent, it degrades that one feature and
    # the rest of the snapshot still computes.
    benchmark = volatility = None
    if with_state:
        benchmark = _safe_series(db, MARKET_SYMBOLS["benchmark"], span_start, span_end)
        volatility = _safe_series(db, MARKET_SYMBOLS["volatility"], span_start, span_end)

    cache: Dict[str, Optional[BarSeries]] = {}
    for ep in episodes:
        series = cache.get(ep.symbol)
        if ep.symbol not in cache:
            start, end = windows[ep.symbol]
            series = _safe_series(db, ep.symbol, start, end)
            cache[ep.symbol] = series
        if series is None or not len(series):
            out.excluded.append((ep.symbol, "no_price_history"))
            continue
        out.episodes.append(analyse_episode(
            ep, series,
            benchmark=benchmark, volatility=volatility,
            with_state=with_state,
        ))

    out.symbols_measured = len({a.episode.symbol for a in out.episodes})
    out.excluded = sorted(set(out.excluded))
    out.report = build_report(out.episodes)
    out.report.coverage.episodes_total = len(episodes)
    return out


def _safe_series(
    db: Session, symbol: str, start: date, end: date,
) -> Optional[BarSeries]:
    """A symbol we hold no bars for is a named exclusion, not a failed run."""
    try:
        series = load_series(db, symbol, start, end)
    except Exception:  # noqa: BLE001
        return None
    return series if len(series) else None
