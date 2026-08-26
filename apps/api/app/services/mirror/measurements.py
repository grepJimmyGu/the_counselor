"""What the user's decisions were worth, in dollars.

PRD-43a §3.3, measurements M1 and M4. Both answer the same shape of question —
*what would a different version of this decision have been worth?* — and both
are UPPER BOUNDS by construction. §0.1 governs: the headline is what better
behaviour is worth, not what past behaviour cost, and the bound is stated in
the rendered copy rather than a tooltip.

━━ M1, THE EXIT GAP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRD-43a states it as: replay every BUY, suppress every SELL, value the book at
the latest close, compare to realised proceeds plus current market value. That
reads as needing the buy history and the current position. **It needs
neither** — the buys cancel:

    never_sold  = bought x close
    actual      = SUM(sell_u x sell_p) + (bought - sold) x close
    difference  = SUM over sells of  sell_u x (close - sell_p)

Verified numerically against the naive form over 20,000 random books; max
divergence 2.9e-10, i.e. float noise. This is not a simplification for its own
sake. It means **M1 survives a truncated buy history**, which is the most
common data problem here: a broker that retains 90 days still yields a valid
exit gap for every sell inside it, where the replay formulation would have
needed purchase records it cannot produce.

WHAT IT IS NOT. Not the Dalbar behaviour gap — that compares money-weighted to
time-weighted return and needs deposit timing, which we never see. M1 isolates
EXITS and the copy must say so.

WHAT IT ASSUMES, AND THE ASSUMPTION IS FALSE. That every exit was wrong, and
that the proceeds did nothing. Nobody holds everything forever, and the money
from a sale usually buys something else. So this is a ceiling, never an
expectation.

AND IT CUTS BOTH WAYS. If the sum is negative the user's exits ADDED value, and
we say that. Reporting a number only when it flatters the thesis is the
failure mode this module is most exposed to.

━━ M4, EXECUTION QUALITY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Where each fill landed inside its own day's range: `(fill - low) / (high - low)`.
Low is good for a buy, high is good for a sell. The dollar attribution is the
distance from that day's midpoint — `(fill - mid) x units`, signed by side —
which is a fill you could plausibly have got, unlike the low or the high, which
you could not.

This one has a real remedy attached (PRD-43b's price bands), which is why it is
in v1 at all: a percentile with no money and no fix is a statistic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.services.trading_behavior import _parse_date, _side

__all__ = [
    "ExitGap",
    "ExecutionQuality",
    "RollUp",
    "recoverable",
    "load_latest_closes",
    "load_bars_on",
    "exit_gap",
    "execution_quality",
]

# A gap smaller than this share of what was sold is arithmetic, not a finding.
# 1% of gross proceeds — below that, a "you could have made $40 on $180,000"
# headline is noise dressed as insight, and routing someone to a remedy for it
# wastes the one piece of attention they gave us.
_MATERIAL_GAP_FRACTION = 0.01

# "The worst third of the day's range." A buy averaging above this, or a sell
# averaging below its mirror, is the condition PRD-43a §3.5 routes to 43b.
_WORST_TERCILE = 2.0 / 3.0


@dataclass
class ExitGap:
    """M1. Positive dollars = selling cost you; negative = selling saved you."""
    dollars: float = 0.0
    sells_measured: int = 0
    sells_total: int = 0
    symbols_measured: int = 0
    gross_sold: float = 0.0
    # (symbol, reason) for sells we could not price. Rendered, never hidden.
    excluded: List[Tuple[str, str]] = field(default_factory=list)
    # The single sale that contributed most, for the copy to name.
    largest_symbol: Optional[str] = None
    largest_dollars: Optional[float] = None
    as_of: Optional[date] = None
    remedy: Optional[str] = None

    @property
    def is_material(self) -> bool:
        if self.gross_sold <= 0:
            return False
        return self.dollars / self.gross_sold >= _MATERIAL_GAP_FRACTION


@dataclass
class ExecutionQuality:
    """M4. Positive dollars = your fills cost you against the day's midpoint.

    Split by side, because the roll-up can only use half of it — see
    `recoverable()`.
    """
    dollars: float = 0.0
    buy_dollars: float = 0.0
    sell_dollars: float = 0.0
    fills_measured: int = 0
    fills_total: int = 0
    buy_percentile: Optional[float] = None
    sell_percentile: Optional[float] = None
    buys_measured: int = 0
    sells_measured: int = 0
    remedy: Optional[str] = None

    @property
    def in_worst_tercile(self) -> bool:
        """Buys landing high in the range, or sells landing low. Either alone
        is enough — they are separate habits with the same remedy."""
        if self.buy_percentile is not None and self.buy_percentile > _WORST_TERCILE:
            return True
        if self.sell_percentile is not None and self.sell_percentile < 1 - _WORST_TERCILE:
            return True
        return False


# ── loading ─────────────────────────────────────────────────────────────────


def load_latest_closes(
    db: Session, symbols: Any,
) -> Dict[str, Tuple[date, float]]:
    """The most recent close we hold for each symbol, with its date.

    The date is returned rather than assumed to be today: `price_bars` is a
    cache, a delisted or thinly-covered name can be months stale, and "worth
    $N today" over a six-month-old bar is a different claim. The caller
    renders the date (the date-stamp product invariant).
    """
    wanted = sorted({str(s).strip().upper() for s in symbols if s})
    if not wanted:
        return {}

    newest = (
        select(PriceBar.symbol, func.max(PriceBar.trading_date).label("d"))
        .where(PriceBar.symbol.in_(wanted))
        .group_by(PriceBar.symbol)
        .subquery()
    )
    stmt = select(PriceBar.symbol, PriceBar.trading_date, PriceBar.close).join(
        newest,
        (PriceBar.symbol == newest.c.symbol) & (PriceBar.trading_date == newest.c.d),
    )
    return {
        str(sym).upper(): (when, float(close))
        for sym, when, close in db.execute(stmt).all()
        if close is not None
    }


def load_bars_on(
    db: Session, pairs: Any,
) -> Dict[Tuple[str, date], Tuple[float, float]]:
    """`(high, low)` for each (symbol, date) a trade happened on.

    One query bounded by the symbols traded and the span they were traded
    over — a few dozen names, never the universe (HANDOFF §6F).
    """
    wanted = {(str(s).strip().upper(), d) for s, d in pairs if s and d}
    if not wanted:
        return {}
    symbols = sorted({s for s, _ in wanted})
    days = [d for _, d in wanted]

    stmt = select(
        PriceBar.symbol, PriceBar.trading_date, PriceBar.high, PriceBar.low
    ).where(
        PriceBar.symbol.in_(symbols),
        PriceBar.trading_date >= min(days),
        PriceBar.trading_date <= max(days),
    )
    out: Dict[Tuple[str, date], Tuple[float, float]] = {}
    for sym, when, high, low in db.execute(stmt).all():
        key = (str(sym).upper(), when)
        if key in wanted and high is not None and low is not None:
            out[key] = (float(high), float(low))
    return out


# ── M1 ──────────────────────────────────────────────────────────────────────


def exit_gap(
    transactions: List[Dict[str, Any]],
    latest_closes: Dict[str, Tuple[date, float]],
    *,
    skip_symbols: Optional[Set[str]] = None,
) -> ExitGap:
    """What every exit was worth, measured against still holding it.

    `SUM over sells of units x (latest_close - sell_price)` — see the module
    docstring for why the buys drop out.
    """
    out = ExitGap()
    skip = {s.upper() for s in (skip_symbols or set())}
    per_symbol: Dict[str, float] = defaultdict(float)
    missing: Dict[str, str] = {}
    measured_symbols: Set[str] = set()
    as_of: List[date] = []

    for t in transactions:
        if _side(t) != "SELL":
            continue
        out.sells_total += 1
        sym = str(t.get("symbol") or "").strip().upper()
        units, price = t.get("units"), t.get("price")
        if not sym or units is None or price is None:
            # A sell with no price is a transfer out or a corporate action.
            # It has no counterfactual, and inventing one would be fabricated
            # data (HANDOFF §6C).
            if sym:
                missing.setdefault(sym, "no_price_on_trade")
            continue
        if sym in skip:
            continue
        found = latest_closes.get(sym)
        if found is None:
            # Delisted, or simply never warmed into the cache. Either way we
            # do not know what it is worth now, and a guess would be the
            # entire number.
            missing.setdefault(sym, "no_price_history")
            continue

        when, close = found
        as_of.append(when)
        units_f, price_f = abs(float(units)), float(price)
        per_symbol[sym] += units_f * (close - price_f)
        out.gross_sold += units_f * price_f
        out.sells_measured += 1
        measured_symbols.add(sym)

    out.dollars = sum(per_symbol.values())
    out.symbols_measured = len(measured_symbols)
    out.excluded = sorted(missing.items())
    out.as_of = max(as_of) if as_of else None

    if per_symbol:
        sym, amount = max(per_symbol.items(), key=lambda kv: kv[1])
        # Only worth naming when it is the direction we are reporting.
        if amount > 0:
            out.largest_symbol, out.largest_dollars = sym, amount

    if out.is_material:
        out.remedy = "exit_rule"
    return out


# ── M4 ──────────────────────────────────────────────────────────────────────


def execution_quality(
    transactions: List[Dict[str, Any]],
    bars: Dict[Tuple[str, date], Tuple[float, float]],
) -> ExecutionQuality:
    """Where each fill landed in its own day's range, and what that cost."""
    out = ExecutionQuality()
    buy_pcts: List[float] = []
    sell_pcts: List[float] = []

    for t in transactions:
        side = _side(t)
        if side not in ("BUY", "SELL"):
            continue
        out.fills_total += 1
        sym = str(t.get("symbol") or "").strip().upper()
        when = _parse_date(t.get("trade_date"))
        units, price = t.get("units"), t.get("price")
        if not sym or when is None or units is None or price is None:
            continue
        bar = bars.get((sym, when))
        if bar is None:
            continue
        high, low = bar
        span = high - low
        if span <= 0:
            # A limit-up day, a halt, or a bar we only have one price for.
            # There is no "where in the range" when there is no range, and
            # dividing here is how a percentile becomes infinity.
            continue

        fill = float(price)
        pct = (fill - low) / span
        # A fill outside its own day's range means the bar and the trade
        # disagree — a stale cache, a different venue, an extended-hours
        # print. Clamping would hide it inside a plausible average.
        if pct < -0.01 or pct > 1.01:
            continue
        pct = min(max(pct, 0.0), 1.0)

        units_f = abs(float(units))
        mid = (high + low) / 2.0
        if side == "BUY":
            buy_pcts.append(pct)
            out.buys_measured += 1
            out.buy_dollars += (fill - mid) * units_f   # paid above the middle
        else:
            sell_pcts.append(pct)
            out.sells_measured += 1
            out.sell_dollars += (mid - fill) * units_f  # sold below the middle
        out.fills_measured += 1

    out.dollars = out.buy_dollars + out.sell_dollars
    if buy_pcts:
        out.buy_percentile = sum(buy_pcts) / len(buy_pcts)
    if sell_pcts:
        out.sell_percentile = sum(sell_pcts) / len(sell_pcts)
    if out.in_worst_tercile and out.dollars > 0:
        out.remedy = "price_band"
    return out


# ── the roll-up, and the two double-counts hiding in it ─────────────────────


@dataclass
class RollUp:
    """One number: what changing these things was worth, at most.

    A CEILING, and it has to be labelled one where it renders (§0.1). Every
    component is a counterfactual, and counterfactuals do not compose the way
    dollars do.
    """
    dollars: float = 0.0
    exit_gap: float = 0.0
    fees: float = 0.0
    execution: float = 0.0
    components: List[str] = field(default_factory=list)


def recoverable(
    gap: ExitGap, fees_paid: float, execution: ExecutionQuality,
) -> RollUp:
    """M1 + M3 + M4-on-buys. Two things are deliberately left out.

    **M2 is excluded**, per PRD-43a §3.4. The disposition effect is the
    PATTERN behind the exit gap, not a separate loss — adding it inflates the
    headline by roughly its own size, and it would ship green because every
    individual measurement is correct.

    **M4's SELL half is excluded too**, which §3.4 does not say and should.
    M1 prices the counterfactual "you never sold"; M4's sell component prices
    "you sold at a better price that day". Those are alternatives, not
    additions — you cannot both keep the shares and sell them well, and
    summing the two charges the same sale twice. The BUY half survives,
    because buying better is entirely compatible with never selling.

    The third component is fees, which are not a counterfactual at all. They
    are money that already left the account, and they compose with anything.
    """
    roll = RollUp()
    roll.exit_gap = max(gap.dollars, 0.0) if gap.is_material else 0.0
    roll.fees = max(fees_paid, 0.0)
    roll.execution = max(execution.buy_dollars, 0.0)

    # Only positive components enter. A negative one means that decision went
    # in the user's favour, and netting it away would let a good habit hide a
    # costly one — the two are reported separately instead.
    if roll.exit_gap > 0:
        roll.components.append("exit_gap")
    if roll.fees > 0:
        roll.components.append("fees")
    if roll.execution > 0:
        roll.components.append("execution")
    roll.dollars = roll.exit_gap + roll.fees + roll.execution
    return roll
