"""What a person's own trading record says about how they trade.

Pure arithmetic over a transaction log. No prediction, no scoring, no
"trading personality" — every number here is something the user did, counted
back to them.

WHY THIS EXISTS. People do not know their own trading. They remember the
winners and the last loss, and almost nobody knows their own average holding
period, their win rate, or the ratio between what they make when right and
lose when wrong. That ratio decides whether a method survives, and it is
invisible without doing this sum.

THE ONE FINDING WORTH BUILDING FOR. The disposition effect — selling winners
early and holding losers — is the best-documented pattern in retail trading,
and a transaction log measures it directly: compare the average holding
period of profitable round-trips against unprofitable ones. If losers are
held meaningfully longer, that is the effect, in the user's own numbers.
It is not a claim about the future; it is a description of the past.

WHAT THIS DELIBERATELY DOES NOT COMPUTE
  - Total account return. Meaningless without deposits and withdrawals,
    which we never see. The broker's own figure is passed through instead.
  - Unrealised P/L. The broker reports `open_pnl` per position; recomputing
    it from a truncated log would be a worse number with our name on it.
  - Anything predictive. "You should trade less" is advice; "your median
    hold is 4 days" is a fact.

MATCHING IS FIFO, PER ACCOUNT, PER SYMBOL. Never across accounts: the same
ticker held at two brokers is two positions, and crossing them would invent
round-trips that never happened.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "RoundTrip",
    "SymbolSummary",
    "TradingBehavior",
    "summarize",
]


def _parse_date(value: Any) -> Optional[date]:
    """Broker dates arrive as ISO strings, sometimes with a time or a zone."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


@dataclass
class _Lot:
    """An open parcel of shares, waiting to be sold."""

    units: float
    price: float
    when: Optional[date]
    fee_per_unit: float


@dataclass(frozen=True)
class RoundTrip:
    """One complete decision: bought, later sold.

    `holding_days` is None when either leg has no usable date — a real
    condition with some brokers, and one that must not silently count as a
    same-day trade.
    """

    symbol: str
    account_id: str
    units: float
    buy_price: float
    sell_price: float
    buy_date: Optional[date]
    sell_date: Optional[date]
    holding_days: Optional[int]
    pnl: float
    pnl_pct: Optional[float]

    @property
    def is_win(self) -> bool:
        return self.pnl > 0


@dataclass
class SymbolSummary:
    symbol: str
    trades: int = 0            # completed round-trips
    buys: int = 0
    sells: int = 0
    units_bought: float = 0.0
    gross_bought: float = 0.0  # dollars committed, for "where the money went"
    realised_pnl: float = 0.0
    wins: int = 0
    holding_days: List[int] = field(default_factory=list)

    @property
    def avg_holding_days(self) -> Optional[float]:
        return (sum(self.holding_days) / len(self.holding_days)
                if self.holding_days else None)

    @property
    def win_rate(self) -> Optional[float]:
        return (self.wins / self.trades) if self.trades else None


@dataclass
class TradingBehavior:
    """The summary a user reads. Every field is a count of what they did."""

    # scope
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    total_buys: int = 0
    total_sells: int = 0
    symbols_traded: int = 0

    # completed decisions
    round_trips: int = 0
    realised_pnl: float = 0.0
    fees_paid: float = 0.0
    wins: int = 0
    losses: int = 0
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None       # positive magnitude
    largest_win: Optional[float] = None
    largest_loss: Optional[float] = None

    # holding periods — where the disposition effect shows up
    avg_holding_days: Optional[float] = None
    median_holding_days: Optional[float] = None
    avg_holding_days_winners: Optional[float] = None
    avg_holding_days_losers: Optional[float] = None

    # concentration
    top_symbols_by_trades: List[SymbolSummary] = field(default_factory=list)
    top_symbols_by_pnl: List[SymbolSummary] = field(default_factory=list)
    worst_symbols_by_pnl: List[SymbolSummary] = field(default_factory=list)

    # honesty about the window
    unmatched_sells: int = 0
    unmatched_sell_symbols: List[str] = field(default_factory=list)
    open_lots: int = 0

    @property
    def win_rate(self) -> Optional[float]:
        return (self.wins / self.round_trips) if self.round_trips else None

    @property
    def win_loss_ratio(self) -> Optional[float]:
        """How much is made when right, over how much is lost when wrong.

        The number that decides whether a method survives, and the one almost
        nobody knows about themselves. A 70% win rate with losers three times
        the size of winners loses money.
        """
        if not self.avg_win or not self.avg_loss:
            return None
        return self.avg_win / self.avg_loss

    @property
    def holds_losers_longer(self) -> Optional[bool]:
        """The disposition effect, as a yes or no.

        None when either side has no completed trades — a two-trade history
        cannot support the claim, and asserting it anyway would be the kind
        of confident nonsense this module exists to avoid.
        """
        w, l = self.avg_holding_days_winners, self.avg_holding_days_losers
        if w is None or l is None:
            return None
        return l > w


def _median(values: List[int]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _side(activity: Dict[str, Any]) -> Optional[str]:
    raw = (activity.get("type") or "").strip().upper()
    if raw in {"BUY", "BUY_TO_OPEN", "BUY_TO_COVER"}:
        return "BUY"
    if raw in {"SELL", "SELL_TO_CLOSE", "SELL_SHORT"}:
        return "SELL"
    return None


def _num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        out = float(value)
        return out if out == out else None   # NaN
    except (TypeError, ValueError):
        return None


def summarize(
    activities: List[Dict[str, Any]], *, top_n: int = 5,
) -> TradingBehavior:
    """Turn a transaction log into a description of how someone trades.

    `activities` are dicts as `snaptrade_service.list_activities` produces
    them (or plain dicts in tests). Anything that is not a buy or a sell —
    dividends, fees, transfers — is ignored: they are not decisions.
    """
    out = TradingBehavior()

    trades: List[Tuple[date, Dict[str, Any], str]] = []
    undated: List[Tuple[Dict[str, Any], str]] = []
    for a in activities or []:
        side = _side(a)
        if side is None:
            continue
        when = _parse_date(a.get("trade_date"))
        if when is None:
            undated.append((a, side))
        else:
            trades.append((when, a, side))

    # Oldest first — FIFO only means anything in chronological order.
    trades.sort(key=lambda t: t[0])

    # UNDATED TRADES GO FIRST, and the alternative is worse.
    #
    # A trade with no date cannot be ordered, so either end is arbitrary. But
    # putting them last means a dated sell runs before an undated buy that we
    # DID see — the lot isn't open yet, the sale is reported as "opened before
    # your history window", and both the P/L and the honesty note are wrong.
    #
    # First is the reading that loses least: we know the basis, we just don't
    # know when. The round trip is counted with `holding_days = None`, which
    # says exactly that.
    ordered = [(a, side) for a, side in undated] + [
        (a, side) for _, a, side in trades
    ]
    if not ordered:
        return out

    dates = [d for d, _, _ in trades]
    if dates:
        out.window_start, out.window_end = dates[0], dates[-1]

    lots: Dict[Tuple[str, str], List[_Lot]] = defaultdict(list)
    by_symbol: Dict[str, SymbolSummary] = {}
    round_trips: List[RoundTrip] = []
    unmatched: List[str] = []

    for a, side in ordered:
        symbol = (a.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        account_id = str(a.get("account_id") or "")
        units = abs(_num(a.get("units")) or 0.0)
        price = _num(a.get("price"))
        fee = abs(_num(a.get("fee")) or 0.0)
        when = _parse_date(a.get("trade_date"))

        # A trade with no price cannot produce a P/L. Counted, never matched:
        # inventing a basis is how a dashboard starts lying.
        summary = by_symbol.setdefault(symbol, SymbolSummary(symbol=symbol))
        out.fees_paid += fee

        if side == "BUY":
            summary.buys += 1
            summary.units_bought += units
            if price is not None:
                summary.gross_bought += units * price
                if units > 0:
                    lots[(account_id, symbol)].append(_Lot(
                        units=units, price=price, when=when,
                        fee_per_unit=(fee / units) if units else 0.0,
                    ))
            continue

        # SELL — match against the oldest open lots in the SAME account.
        summary.sells += 1
        if price is None or units <= 0:
            continue
        queue = lots[(account_id, symbol)]
        remaining = units
        sell_fee_per_unit = (fee / units) if units else 0.0
        matched_any = False

        while remaining > 1e-9 and queue:
            lot = queue[0]
            take = min(remaining, lot.units)
            gross = (price - lot.price) * take
            costs = (lot.fee_per_unit + sell_fee_per_unit) * take
            pnl = gross - costs
            basis = lot.price * take
            days = (
                (when - lot.when).days
                if (when is not None and lot.when is not None) else None
            )
            round_trips.append(RoundTrip(
                symbol=symbol, account_id=account_id, units=take,
                buy_price=lot.price, sell_price=price,
                buy_date=lot.when, sell_date=when, holding_days=days,
                pnl=pnl, pnl_pct=(pnl / basis) if basis else None,
            ))
            lot.units -= take
            remaining -= take
            matched_any = True
            if lot.units <= 1e-9:
                queue.pop(0)

        if remaining > 1e-9:
            # Sold more than we saw bought. Almost always a position opened
            # before the history window — NOT an error, and not something to
            # invent a cost basis for. Counted and named so the numbers below
            # can be read for what they are.
            out.unmatched_sells += 1
            if symbol not in unmatched:
                unmatched.append(symbol)
        del matched_any  # kept for readability above; nothing downstream uses it

    # ── roll up ─────────────────────────────────────────────────────────────
    out.total_buys = sum(s.buys for s in by_symbol.values())
    out.total_sells = sum(s.sells for s in by_symbol.values())
    out.symbols_traded = len(by_symbol)
    out.unmatched_sell_symbols = unmatched
    out.open_lots = sum(1 for q in lots.values() for _ in q)

    for rt in round_trips:
        s = by_symbol[rt.symbol]
        s.trades += 1
        s.realised_pnl += rt.pnl
        if rt.is_win:
            s.wins += 1
        if rt.holding_days is not None:
            s.holding_days.append(rt.holding_days)

    out.round_trips = len(round_trips)
    out.realised_pnl = sum(rt.pnl for rt in round_trips)

    wins = [rt for rt in round_trips if rt.is_win]
    losses = [rt for rt in round_trips if not rt.is_win]
    out.wins, out.losses = len(wins), len(losses)
    if wins:
        out.avg_win = sum(rt.pnl for rt in wins) / len(wins)
        out.largest_win = max(rt.pnl for rt in wins)
    if losses:
        out.avg_loss = abs(sum(rt.pnl for rt in losses) / len(losses))
        out.largest_loss = min(rt.pnl for rt in losses)

    held = [rt.holding_days for rt in round_trips if rt.holding_days is not None]
    if held:
        out.avg_holding_days = sum(held) / len(held)
        out.median_holding_days = _median(held)
    held_w = [rt.holding_days for rt in wins if rt.holding_days is not None]
    held_l = [rt.holding_days for rt in losses if rt.holding_days is not None]
    if held_w:
        out.avg_holding_days_winners = sum(held_w) / len(held_w)
    if held_l:
        out.avg_holding_days_losers = sum(held_l) / len(held_l)

    ranked = list(by_symbol.values())
    out.top_symbols_by_trades = sorted(
        ranked, key=lambda s: (s.buys + s.sells), reverse=True,
    )[:top_n]
    with_pnl = [s for s in ranked if s.trades]
    out.top_symbols_by_pnl = sorted(
        with_pnl, key=lambda s: s.realised_pnl, reverse=True,
    )[:top_n]
    out.worst_symbols_by_pnl = sorted(
        with_pnl, key=lambda s: s.realised_pnl,
    )[:top_n]

    return out
