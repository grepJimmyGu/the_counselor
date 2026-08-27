"""PRD-43a §3.8 — the shared reconstruction both lenses read.

The timing engine (43b) and the allocation lens (43c) need two different
views of the same history, and building them separately is how they drift:

- **`TradeEpisode`** — a position's whole life, from the first buy that opened
  it to the sell that flattened it. 43b asks markouts and excursions *of a
  position*, so accumulation and scale-out must collapse into one thing with
  one weighted-average cost. This is deliberately NOT the FIFO round trip in
  `trading_behavior.summarize()`: FIFO answers "what did each lot earn",
  which is the right question for realised P/L and the wrong one for "was
  this entry early".
- **`PortfolioSnapshot`** — what was held on a given date. 43c replays sizing
  and concentration against it.

Both are derived here, once, from the split-resolved transactions
`portfolio_ledger_service.build_ledger()` produces. Nothing in this module
does I/O: the caller supplies the ledger and the broker's current positions,
which is what lets the whole thing be tested against a hand-written book.

Two design decisions are worth stating, because both were chosen against a
plausible alternative:

**Snapshots are reconstructed BACKWARDS from `/positions`, not forwards from
the first transaction.** The broker's current position list is the one thing
in this pipeline that is authoritative, so the reconstruction is anchored
there and every known delta is undone going back. Walking forwards instead
means the feed's start is treated as zero, and any position opened before the
window survives to the present as a fabrication. That is not hypothetical —
run forwards over this account's 416 activity rows on 2026-08-27 and you get
five open positions (ERO, MU, RKLB, SQQQ, SWVXX) against a broker holding no
equities whatsoever. Backwards, the same feed reconstructs cleanly, because
it starts from the fact the phantoms contradict.

**A contradiction is reported, never smoothed.** When undoing a buy would
take a holding below zero, the feed and the broker disagree, and there is no
honest number to serve for the dates before it. The walk stops at the last
date it still agreed, reports that date as `reconstructed_from`, and names
the symbol. Clamping to zero and continuing would produce a portfolio history
that looks complete and isn't — the single worst outcome for a product whose
entire claim is that it read your actual record.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.trading_behavior import _num, _parse_date, _side

__all__ = [
    "TradeEpisode",
    "PortfolioSnapshot",
    "SnapshotCoverage",
    "ReconstructionCoverage",
    "Reconstruction",
    "is_cash_equivalent",
    "build_episodes",
    "build_snapshots",
    "reconstruct",
]

_EPS = 1e-6

# Units can change without a trade. `JRNLSEC` (×10) and `TRANSFER` (×3) are
# both present in this account's live feed. A walk that ignores them produces
# a position whose size never matched reality, so the symbol is excluded and
# named — the same treatment `split_unreconciled` gets in the ledger, for the
# same reason: a fabricated number reads exactly like a real finding.
_OFF_MARKET_TYPES = frozenset({
    "JRNLSEC", "JRNL", "TRANSFER", "TRANSFER_IN", "TRANSFER_OUT",
    "STOCK_TRANSFER", "ACAT", "SPINOFF", "MERGER", "STOCK_DIVIDEND",
})

# Fallback only. The broker's own `cash_equivalent` flag (surfaced on
# `BrokerPosition` in #354) is the primary classifier and is always preferred;
# this list exists for symbols that appear in the activity feed with no
# position row left to carry a flag — a sweep fund that has been sold out.
_CASH_EQUIVALENT_SYMBOLS = frozenset({
    "SWVXX", "SNVXX", "SNSXX", "SWGXX",          # Schwab sweep
    "SPAXX", "FDRXX", "FZFXX", "SPRXX", "FDLXX",  # Fidelity
    "VMFXX", "VMMXX", "VUSXX",                    # Vanguard
    "TIMXX", "MMDA", "CASH", "USD",
})


def is_cash_equivalent(
    symbol: str, position: Optional[Any] = None,
) -> bool:
    """Is this a money-market or sweep holding rather than a position?

    A 40% zero-volatility "position" flattens every concentration and
    correlation figure 43c computes, and an episode over a sweep fund is not a
    decision anyone made.
    """
    if position is not None and getattr(position, "cash_equivalent", False):
        return True
    return str(symbol or "").strip().upper() in _CASH_EQUIVALENT_SYMBOLS


# ── the two views ───────────────────────────────────────────────────────────


@dataclass
class TradeEpisode:
    """One position, from opened to flat.

    `avg_entry_price` is the weighted average over `entries` — not the mean of
    the fill prices. Buying 100 at $10 and 50 at $20 is a $13.33 cost basis;
    the simple mean says $15 and survives every fixture built on equal-sized
    fills.
    """

    symbol: str
    account_id: str
    opened_on: date
    closed_on: Optional[date] = None
    entries: List[Dict[str, Any]] = field(default_factory=list)
    exits: List[Dict[str, Any]] = field(default_factory=list)
    units_total: float = 0.0
    units_open: float = 0.0
    avg_entry_price: float = 0.0
    avg_exit_price: Optional[float] = None
    realised_return: Optional[float] = None
    holding_days: Optional[int] = None

    @property
    def is_open(self) -> bool:
        return self.closed_on is None


@dataclass
class PortfolioSnapshot:
    """Units held at the end of `on_date`, split-adjusted, cash excluded."""

    on_date: date
    holdings: Dict[str, float] = field(default_factory=dict)
    reconstructable: bool = True


@dataclass
class SnapshotCoverage:
    reconstructed_from: Optional[date] = None
    reconstructed_to: Optional[date] = None
    excluded: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.excluded


@dataclass
class ReconstructionCoverage:
    reconstructed_from: Optional[date] = None
    reconstructed_to: Optional[date] = None
    excluded: List[Tuple[str, str]] = field(default_factory=list)
    episodes_total: int = 0
    episodes_open: int = 0
    # (symbol, units the episode walk believes are open, units the broker reports)
    position_disagreements: List[Tuple[str, float, float]] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.excluded and not self.position_disagreements


@dataclass
class Reconstruction:
    episodes: List[TradeEpisode] = field(default_factory=list)
    snapshots: List[PortfolioSnapshot] = field(default_factory=list)
    coverage: ReconstructionCoverage = field(default_factory=ReconstructionCoverage)


# ── shared preparation ──────────────────────────────────────────────────────


def _symbol_of(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def _positions_by_symbol(positions: Optional[Sequence[Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for p in positions or []:
        sym = str(getattr(p, "symbol", "") or "").strip().upper()
        if sym:
            out.setdefault(sym, p)
    return out


def _off_market_symbols(transactions: Sequence[Dict[str, Any]]) -> set:
    out = set()
    for row in transactions or []:
        raw = str(row.get("type") or "").strip().upper()
        if raw in _OFF_MARKET_TYPES:
            sym = _symbol_of(row)
            if sym:
                out.add(sym)
    return out


def _dedupe(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return sorted(set(pairs))


# ── episodes ────────────────────────────────────────────────────────────────


def build_episodes(
    transactions: Sequence[Dict[str, Any]],
    positions: Optional[Sequence[Any]] = None,
) -> Tuple[List[TradeEpisode], List[Tuple[str, str]]]:
    """Collapse a transaction stream into positions.

    Returns the episodes and the symbols that could not be turned into any,
    each with a machine-readable reason. Grouping is per account per symbol —
    the same ticker at two brokers is two positions, and merging them would
    invent one neither broker reports.
    """
    pos_by_symbol = _positions_by_symbol(positions)
    off_market = _off_market_symbols(transactions)
    excluded: List[Tuple[str, str]] = []

    groups: Dict[Tuple[str, str], List[Tuple[date, str, float, float, Dict[str, Any]]]]
    groups = defaultdict(list)
    seen_symbols = set()

    for row in transactions or []:
        sym = _symbol_of(row)
        if not sym:
            continue
        seen_symbols.add(sym)
        side = _side(row)
        if side not in ("BUY", "SELL"):
            # Dividends and fees are not decisions; off-market moves are
            # handled below by symbol, not row.
            continue
        when = _parse_date(row.get("trade_date"))
        units = _num(row.get("units"))
        price = _num(row.get("price"))
        if when is None or units is None:
            continue
        account = str(row.get("account_id") or "")
        groups[(account, sym)].append(
            (when, side, abs(units), price if price is not None else 0.0, row)
        )

    for sym in sorted(seen_symbols):
        if is_cash_equivalent(sym, pos_by_symbol.get(sym)):
            excluded.append((sym, "cash_equivalent"))
        elif sym in off_market:
            excluded.append((sym, "units_moved_off_market"))

    skip = {s for s, _ in excluded}
    episodes: List[TradeEpisode] = []

    for (account, sym), rows in groups.items():
        if sym in skip:
            continue

        # Within a date, buys settle first. A daily feed carries no intraday
        # sequence, and rows for one date arrive in arbitrary order — so a
        # same-day round trip listed sell-first would find no open position to
        # close and take the whole symbol out as an orphaned sell. You cannot
        # sell what you have not bought, and for an already-open position the
        # order changes nothing.
        rows.sort(key=lambda r: (r[0], 0 if r[1] == "BUY" else 1))
        open_ep: Optional[TradeEpisode] = None
        units_open = 0.0
        broken = False

        for when, side, units, price, row in rows:
            if side == "BUY":
                if open_ep is None:
                    open_ep = TradeEpisode(
                        symbol=sym, account_id=account, opened_on=when,
                    )
                open_ep.entries.append(row)
                open_ep.units_total += units
                units_open += units
                continue

            if open_ep is None or units > units_open + _EPS:
                # Selling shares this feed never saw bought. There is no entry
                # to anchor to, so a markout here would be measured from a
                # price the user never paid. The whole symbol goes, because
                # every unit count after this point is off by the same
                # unexplained amount.
                broken = True
                break

            open_ep.exits.append(row)
            units_open -= units
            if units_open <= _EPS:
                open_ep.closed_on = when
                episodes.append(open_ep)
                open_ep = None
                units_open = 0.0

        if broken:
            excluded.append((sym, "sell_without_open_position"))
            # Drop anything this symbol already contributed — a partial
            # history is worse than none, because it looks complete.
            episodes = [e for e in episodes if e.symbol != sym]
            continue

        if open_ep is not None:
            open_ep.units_open = units_open
            episodes.append(open_ep)

    for ep in episodes:
        ep.units_total = round(ep.units_total, 9)
        ep.avg_entry_price = _weighted_price(ep.entries) or 0.0
        ep.avg_exit_price = _weighted_price(ep.exits)
        if ep.closed_on is not None:
            ep.units_open = 0.0
            ep.holding_days = (ep.closed_on - ep.opened_on).days
            if ep.avg_entry_price > 0 and ep.avg_exit_price is not None:
                ep.realised_return = ep.avg_exit_price / ep.avg_entry_price - 1.0

    episodes.sort(key=lambda e: (e.opened_on, e.symbol, e.account_id))
    return episodes, _dedupe(excluded)


def _weighted_price(rows: List[Dict[str, Any]]) -> Optional[float]:
    """Σ(units × price) / Σ(units). The weighting is the whole point."""
    total_units = 0.0
    total_dollars = 0.0
    for r in rows:
        units = _num(r.get("units"))
        price = _num(r.get("price"))
        if units is None or price is None:
            continue
        units = abs(units)
        total_units += units
        total_dollars += units * price
    if total_units <= _EPS:
        return None
    return total_dollars / total_units


# ── snapshots ───────────────────────────────────────────────────────────────


def build_snapshots(
    transactions: Sequence[Dict[str, Any]],
    positions: Optional[Sequence[Any]] = None,
    window_end: Optional[date] = None,
    window_start: Optional[date] = None,
) -> Tuple[List[PortfolioSnapshot], SnapshotCoverage]:
    """Reconstruct daily holdings backwards from the broker's position list.

    See the module docstring for why backwards. The returned snapshots are
    ascending by date, so `snapshots[-1]` is `window_end` and is exactly what
    `/positions` reports rather than anything derived from it.

    **Callers should pass `window_end=date.today()`.** It defaults to the last
    trade date to keep this function pure and its tests deterministic, but the
    anchor is the broker's position list, which is as-of *now* — on the live
    account the last activity row is 24 days old, so taking the default would
    silently end the series 24 days short of the holdings it started from.
    """
    pos_by_symbol = _positions_by_symbol(positions)
    off_market = _off_market_symbols(transactions)
    cov = SnapshotCoverage()

    excluded: List[Tuple[str, str]] = []
    skip = set()
    for sym in set(list(pos_by_symbol) + [_symbol_of(r) for r in transactions or []]):
        if not sym:
            continue
        if is_cash_equivalent(sym, pos_by_symbol.get(sym)):
            excluded.append((sym, "cash_equivalent"))
            skip.add(sym)
        elif sym in off_market:
            excluded.append((sym, "units_moved_off_market"))
            skip.add(sym)

    # Signed deltas NETTED per (date, symbol): a buy added units that day, a
    # sell removed them. Netting is not an optimisation — a snapshot is an
    # end-of-day quantity, and a daily feed carries no intraday sequence, so
    # undoing a date's rows one at a time lets arbitrary feed ordering dip a
    # holding below zero and fabricate a contradiction out of a same-day round
    # trip that reconciles exactly.
    netted: Dict[Tuple[date, str], float] = defaultdict(float)
    trade_dates: List[date] = []
    for row in transactions or []:
        sym = _symbol_of(row)
        side = _side(row)
        if not sym or sym in skip or side not in ("BUY", "SELL"):
            continue
        when = _parse_date(row.get("trade_date"))
        units = _num(row.get("units"))
        if when is None or units is None:
            continue
        trade_dates.append(when)
        netted[(when, sym)] += abs(units) if side == "BUY" else -abs(units)

    deltas: Dict[date, List[Tuple[str, float]]] = defaultdict(list)
    for (when, sym), signed in netted.items():
        deltas[when].append((sym, signed))

    if window_end is None:
        window_end = max(trade_dates) if trade_dates else None
    if window_end is None:
        cov.excluded = _dedupe(excluded)
        return [], cov
    if window_start is None:
        window_start = min(trade_dates) if trade_dates else window_end
    if window_start > window_end:
        window_start = window_end

    # Anchor: the broker's own position list, which is the one authoritative
    # fact available. Everything else is derived by undoing known deltas.
    current: Dict[str, float] = {}
    for sym, p in pos_by_symbol.items():
        if sym in skip:
            continue
        units = _num(getattr(p, "units", None))
        if units is not None:
            current[sym] = units
    for rows in deltas.values():
        for sym, _ in rows:
            current.setdefault(sym, 0.0)

    walked: List[PortfolioSnapshot] = []
    contradicted_at = set()

    day = window_end
    while day >= window_start:
        walked.append(PortfolioSnapshot(
            on_date=day,
            holdings={s: u for s, u in current.items() if abs(u) > _EPS},
        ))
        for sym, signed in deltas.get(day, []):
            current[sym] = current.get(sym, 0.0) - signed
            if current[sym] < -_EPS:
                # Undoing this day's net buying takes the holding below zero:
                # the feed says shares were acquired that the broker's position
                # list cannot account for. Either the feed is missing the sell
                # that removed them or the shares left outside it — and neither
                # leaves an honest number to serve for this symbol.
                contradicted_at.add(sym)
        day -= timedelta(days=1)

    # A contradiction is a property of the SYMBOL, not of the book's history.
    # There is no date at which that symbol's units become trustworthy, so it
    # leaves every snapshot — but the other symbols' dates are untouched. An
    # earlier draft moved the whole book's start to the contradiction; against
    # the live account that cut a two-year book to 282 days over 300 shares of
    # one ETF that was already being excluded anyway.
    for sym in contradicted_at:
        excluded.append((sym, "units_unexplained"))
        skip.add(sym)

    snapshots = [
        PortfolioSnapshot(
            on_date=s.on_date,
            holdings={k: v for k, v in s.holdings.items() if k not in skip},
            reconstructable=True,
        )
        for s in reversed(walked)
    ]

    cov.reconstructed_from = window_start
    cov.reconstructed_to = window_end
    cov.excluded = _dedupe(excluded)
    return snapshots, cov


# ── both together ───────────────────────────────────────────────────────────


def reconstruct(
    transactions: Sequence[Dict[str, Any]],
    positions: Optional[Sequence[Any]] = None,
    window_end: Optional[date] = None,
    window_start: Optional[date] = None,
) -> Reconstruction:
    """Build both views and cross-check them against the broker.

    The cross-check is the cheapest one available and the one this account
    actually failed before it existed: an open episode's remaining units must
    appear in the broker's position list, because both are supposed to be
    describing the same book. Where they disagree, the disagreement is
    reported — never resolved by overwriting one side with the other.
    """
    episodes, ep_excluded = build_episodes(transactions, positions=positions)
    snapshots, snap_cov = build_snapshots(
        transactions,
        positions=positions,
        window_end=window_end,
        window_start=window_start,
    )

    cov = ReconstructionCoverage(
        reconstructed_from=snap_cov.reconstructed_from,
        reconstructed_to=snap_cov.reconstructed_to,
        excluded=_dedupe(list(ep_excluded) + list(snap_cov.excluded)),
        episodes_total=len(episodes),
        episodes_open=sum(1 for e in episodes if e.is_open),
    )

    pos_by_symbol = _positions_by_symbol(positions)
    open_units: Dict[str, float] = defaultdict(float)
    for ep in episodes:
        if ep.is_open:
            open_units[ep.symbol] += ep.units_open

    # Symbols excluded because the comparison itself is meaningless: a sweep
    # fund is not a position, and for the other two the episode walk's unit
    # count is knowingly wrong for a reason already named. `units_unexplained`
    # is deliberately NOT in this set — that exclusion IS a feed-vs-broker
    # disagreement, and skipping it here would report the symbol as excluded
    # while hiding how far apart the two sources actually are.
    incomparable = {
        s for s, reason in cov.excluded
        if reason in ("cash_equivalent", "units_moved_off_market",
                      "sell_without_open_position")
    }
    for sym in sorted(set(list(open_units) + list(pos_by_symbol))):
        if sym in incomparable:
            continue
        believed = open_units.get(sym, 0.0)
        p = pos_by_symbol.get(sym)
        reported = _num(getattr(p, "units", None)) if p is not None else 0.0
        reported = reported if reported is not None else 0.0
        if abs(believed - reported) > _EPS:
            cov.position_disagreements.append((sym, believed, reported))

    return Reconstruction(episodes=episodes, snapshots=snapshots, coverage=cov)
