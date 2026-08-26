"""The broker's transaction feed, normalized into something matchable.

PRD-43a slice 2. `trading_behavior.summarize()` does the arithmetic and stays
pure; this module does the one thing that arithmetic cannot do for itself —
make the units comparable across a stock split — and reports honestly when it
cannot.

━━ WHY A SPLIT BREAKS A TRANSACTION LOG ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Buy 10 shares at $1,000. The stock splits 10:1. Sell 100 shares at $100.

Nothing happened to the money — $10,000 in, $10,000 out — but a FIFO matcher
reading raw units sees ten shares bought and a hundred sold. It matches ten
against ten at a pre-split cost basis, reports a **90% loss that never
happened**, and files the other ninety shares as sells with no buy. Both
numbers look like findings. Neither is real.

That is not hypothetical: production `price_bars` holds 1,916 rows with a
`split_coefficient` other than 1.0, across 998 symbols, the most recent on
2026-08-21. Roughly a third of symbols with history have a split in it.

━━ WE DO NOT KNOW WHAT THE BROKER DOES, SO WE DO NOT GUESS ━━━━━━━━━━━━━━━━━━

Some brokers restate history after a split — the old buy is rewritten as 100
shares at $100 and everything already reconciles. Others report each row as it
stood on its trade date. SnapTrade normalizes across dozens of brokers and
makes no promise either way, and picking one convention would silently corrupt
every account on the other.

So this module does not choose. It runs the match **both ways** and keeps the
one that reconciles:

  - raw units leave no unmatched sells  -> the broker restated. Change nothing.
  - adjusted units leave fewer          -> the broker did not. Adjust.
  - both leave unmatched                -> we cannot tell. Say so, and exclude
                                           the symbol rather than publish a
                                           number we do not believe.

The third case is the one that matters. `unmatched_sells` already existed as
an honesty field; this gives it a reason, so "27 sells we could not match"
becomes "NVDA split 10:1 in this window and the numbers do not reconcile
either way" — which a person can act on.

━━ THE ADJUSTMENT DOES NOT MOVE THE MONEY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`units × factor` and `price ÷ factor` leave `units × price` unchanged. This is
not a P/L correction — realised dollars are the same either way. It exists so
the *lots line up*, and lots lining up is what makes every downstream number
(holding period, win rate, the disposition effect) describe real round trips.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.services.trading_behavior import _parse_date, _side

__all__ = [
    "SplitEvent",
    "SplitResolution",
    "LedgerCoverage",
    "Ledger",
    "load_splits",
    "build_ledger",
]

# Float noise is real in this column: 1.49999925000037 and 1.499999250000375
# are two stored rows for the same 3:2 split. Never compare a coefficient for
# equality — this is the band around 1.0 that counts as "no split".
_SPLIT_EPSILON = 1e-6


@dataclass
class SplitEvent:
    symbol: str
    on_date: date
    coefficient: float


@dataclass
class SplitResolution:
    """What we decided to do about one symbol's splits, and why.

    Rendered to the user when `reason == "unreconciled"`. The other two cases
    are bookkeeping — the numbers came out right and nobody needs to know how.
    """
    symbol: str
    splits: List[SplitEvent] = field(default_factory=list)
    applied: bool = False
    # "broker_restated" | "adjusted" | "unreconciled"
    reason: str = "broker_restated"
    raw_unmatched_units: float = 0.0
    adjusted_unmatched_units: float = 0.0

    @property
    def cumulative_factor(self) -> float:
        f = 1.0
        for s in self.splits:
            f *= s.coefficient
        return f


@dataclass
class LedgerCoverage:
    """What the numbers below are computed on, and what they leave out.

    Rendered verbatim. A figure computed on 47 of 61 positions is a different
    claim from one computed on all 61, and the difference belongs on the
    screen rather than in a docstring.
    """
    symbols_total: int = 0
    symbols_included: int = 0
    # (symbol, reason) — reasons are a closed set so the UI can phrase each.
    excluded: List[Tuple[str, str]] = field(default_factory=list)
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    splits_seen: int = 0
    splits_adjusted: int = 0

    @property
    def is_complete(self) -> bool:
        return not self.excluded


@dataclass
class Ledger:
    """Transactions ready to be matched, plus what had to be left out."""
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    coverage: LedgerCoverage = field(default_factory=LedgerCoverage)
    resolutions: List[SplitResolution] = field(default_factory=list)


# ── loading ─────────────────────────────────────────────────────────────────


def load_splits(
    db: Session, symbols: Iterable[str], *,
    start: Optional[date] = None, end: Optional[date] = None,
) -> Dict[str, List[SplitEvent]]:
    """Every split we have on record for these symbols, oldest first.

    The ONE database read in this module. Bounded by the symbols the user
    actually traded — a few dozen — and never by the universe.
    """
    wanted = sorted({s.strip().upper() for s in symbols if s})
    if not wanted:
        return {}

    stmt = select(
        PriceBar.symbol, PriceBar.trading_date, PriceBar.split_coefficient
    ).where(
        PriceBar.symbol.in_(wanted),
        PriceBar.split_coefficient.isnot(None),
    )
    # Dates as `date` objects, never `.isoformat()` — Postgres has no implicit
    # varchar -> date cast and SQLite silently accepts the string (trap #20).
    if start is not None:
        stmt = stmt.where(PriceBar.trading_date >= start)
    if end is not None:
        stmt = stmt.where(PriceBar.trading_date <= end)

    out: Dict[str, List[SplitEvent]] = defaultdict(list)
    for sym, when, coef in db.execute(stmt).all():
        if coef is None or abs(float(coef) - 1.0) <= _SPLIT_EPSILON:
            continue
        out[str(sym).upper()].append(
            SplitEvent(symbol=str(sym).upper(), on_date=when, coefficient=float(coef))
        )
    for events in out.values():
        events.sort(key=lambda e: e.on_date)
    return dict(out)


# ── matching, twice ─────────────────────────────────────────────────────────


def _unmatched_sell_units(rows: List[Dict[str, Any]]) -> float:
    """Sell units FIFO leaves with no buy to match, per account.

    Deliberately not `summarize()`: this counts UNITS rather than events, and
    a hundred orphaned shares from one sell is the signal a split leaves.
    Accounts never cross — the same ticker at two brokers is two positions.
    """
    by_account: Dict[str, List[Tuple[date, str, float]]] = defaultdict(list)
    for r in rows:
        side = _side(r)
        if side not in ("BUY", "SELL"):
            continue
        units = r.get("units")
        if units is None:
            continue
        when = _parse_date(r.get("trade_date")) or date.min
        by_account[str(r.get("account_id") or "")].append(
            (when, side, abs(float(units)))
        )

    orphaned = 0.0
    for rows_for_account in by_account.values():
        rows_for_account.sort(key=lambda t: t[0])
        lots: List[float] = []
        for _, side, units in rows_for_account:
            if side == "BUY":
                lots.append(units)
                continue
            remaining = units
            while remaining > 1e-9 and lots:
                take = min(remaining, lots[0])
                remaining -= take
                lots[0] -= take
                if lots[0] <= 1e-9:
                    lots.pop(0)
            orphaned += remaining
    return orphaned


def _apply_splits(
    rows: List[Dict[str, Any]], splits: List[SplitEvent],
) -> List[Dict[str, Any]]:
    """Restate every row in post-split terms.

    A trade on the split date is already at the post-split price, so only
    splits STRICTLY AFTER a trade apply to it. Units multiply, price divides,
    and `units * price` is unchanged — see the module docstring.
    """
    out: List[Dict[str, Any]] = []
    for r in rows:
        when = _parse_date(r.get("trade_date"))
        factor = 1.0
        if when is not None:
            for s in splits:
                if s.on_date > when:
                    factor *= s.coefficient
        if factor == 1.0:
            out.append(r)
            continue
        adjusted = dict(r)
        if r.get("units") is not None:
            adjusted["units"] = float(r["units"]) * factor
        if r.get("price") is not None:
            adjusted["price"] = float(r["price"]) / factor
        adjusted["_split_factor"] = factor
        out.append(adjusted)
    return out


def _resolve_symbol(
    symbol: str, rows: List[Dict[str, Any]], splits: List[SplitEvent],
) -> Tuple[List[Dict[str, Any]], SplitResolution]:
    """Match both ways; keep whichever reconciles. See the module docstring."""
    res = SplitResolution(symbol=symbol, splits=list(splits))
    if not splits:
        return rows, res

    raw_unmatched = _unmatched_sell_units(rows)
    res.raw_unmatched_units = raw_unmatched
    if raw_unmatched <= 1e-6:
        # Already reconciles. The broker restated its own history, or the
        # position simply was not held across the split. Touching the data
        # here could only make it wrong.
        res.reason = "broker_restated"
        return rows, res

    adjusted = _apply_splits(rows, splits)
    adj_unmatched = _unmatched_sell_units(adjusted)
    res.adjusted_unmatched_units = adj_unmatched

    if adj_unmatched < raw_unmatched - 1e-6:
        res.applied = True
        res.reason = "adjusted"
        return adjusted, res

    # Neither reconciles. Something else is going on — history that starts
    # mid-position, a transfer in, a broker quirk — and a split is in the
    # window, so we cannot attribute the gap. Excluded upstream, and named.
    res.reason = "unreconciled"
    return rows, res


# ── assembly ────────────────────────────────────────────────────────────────


def build_ledger(
    activities: List[Dict[str, Any]],
    splits: Optional[Dict[str, List[SplitEvent]]] = None,
) -> Ledger:
    """Normalize a broker feed into transactions that can be matched.

    Pure — the caller supplies the activities and the splits, which is what
    keeps this testable against a hand-written ledger and keeps the single
    database read at the edge.
    """
    splits = splits or {}
    ledger = Ledger()

    by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    passthrough: List[Dict[str, Any]] = []
    dates: List[date] = []

    for a in activities:
        side = _side(a)
        when = _parse_date(a.get("trade_date"))
        if when is not None:
            dates.append(when)
        if side not in ("BUY", "SELL"):
            # Dividends and fees are not decisions and never matched, but the
            # fee total is real money and `summarize()` still wants them.
            passthrough.append(a)
            continue
        sym = str(a.get("symbol") or "").strip().upper()
        by_symbol[sym].append(a)

    ledger.coverage.window_start = min(dates) if dates else None
    ledger.coverage.window_end = max(dates) if dates else None
    ledger.coverage.symbols_total = len(by_symbol)

    kept: List[Dict[str, Any]] = []
    for sym, rows in sorted(by_symbol.items()):
        sym_splits = splits.get(sym, [])
        ledger.coverage.splits_seen += len(sym_splits)
        resolved, res = _resolve_symbol(sym, rows, sym_splits)
        if sym_splits:
            ledger.resolutions.append(res)
        if res.applied:
            ledger.coverage.splits_adjusted += len(sym_splits)

        if res.reason == "unreconciled":
            # Excluded on purpose. A 10:1 split matched raw reports a 90% loss
            # that never happened, and a fabricated loss reads exactly like a
            # real finding — which is what makes it worth excluding rather
            # than flagging in a footnote.
            ledger.coverage.excluded.append((sym, "split_unreconciled"))
            continue
        ledger.coverage.symbols_included += 1
        kept.extend(resolved)

    ledger.transactions = kept + passthrough
    return ledger
