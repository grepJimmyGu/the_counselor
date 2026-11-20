"""What the agent looks for. Pure functions: plain data in, findings out.

Each check states a fact and the rule that made it worth saying. None of them
reads the network or the database, so every one is tested without either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class Finding:
    kind: str                 # price_move | concentration | filing | exits_waiting
    severity: str             # watch | info | good
    title: str
    body: str
    dedupe_key: str
    symbol: Optional[str] = None
    facts: Dict[str, Any] = field(default_factory=dict)
    # {"type": "open_company", "symbol": ...}
    # {"type": "review_order", "symbol": ..., "side": "sell", "units": ...}
    # {"type": "open_actions"}
    action: Optional[Dict[str, Any]] = None


@dataclass
class Holding:
    symbol: str
    units: float
    price: float

    @property
    def value(self) -> float:
        return self.units * self.price


def _money(amount: float) -> str:
    return "${:,.0f}".format(amount) if abs(amount) >= 1000 else "${:,.2f}".format(amount)


def price_moves(
    quotes: Dict[str, Dict[str, float]],
    threshold_pct: float,
    holdings: Iterable[Holding],
    today: date,
) -> List[Finding]:
    """A watched or held symbol that moved at least `threshold_pct` today.

    `quotes` maps a symbol to {"price", "change_percent"}.
    """
    held = {h.symbol: h for h in holdings}
    found = []
    for symbol in sorted(quotes):
        quote = quotes[symbol]
        change = quote.get("change_percent")
        price = quote.get("price")
        if change is None or price is None or abs(change) < threshold_pct:
            continue
        direction = "up" if change > 0 else "down"
        holding = held.get(symbol)
        if holding is not None:
            context = "You hold {:g} shares, worth {} at this price.".format(holding.units, _money(holding.units * price))
        else:
            context = "It is on your watchlist."
        found.append(Finding(
            kind="price_move",
            # A fall in something owned is the case worth a second look.
            severity="watch" if (holding is not None and change < 0) else "info",
            symbol=symbol,
            title="{} is {} {:.1f}% today".format(symbol, direction, abs(change)),
            body="{} is at {}. {} Your alert is set at a {:g}% move in a day.".format(
                symbol, _money(price), context, threshold_pct),
            facts={"price": price, "change_percent": change, "threshold_pct": threshold_pct,
                   "held_units": holding.units if holding else None},
            action={"type": "open_company", "symbol": symbol},
            # One a day per direction: a stock that keeps falling is not news every half hour.
            dedupe_key="price_move:{}:{}:{}".format(symbol, today.isoformat(), direction),
        ))
    return found


def concentration(holdings: Iterable[Holding], max_position_pct: float, today: date) -> List[Finding]:
    """A holding that is more of the portfolio than the user's own limit.

    The size of the sale that would bring it back to the limit is arithmetic:
    selling x from a holding worth v in a portfolio worth t leaves
    (v - x) / (t - x), which equals the limit L when x = (v - L t) / (1 - L).
    """
    rows = [h for h in holdings if h.units > 0 and h.price > 0]
    total = sum(h.value for h in rows)
    limit = max_position_pct / 100.0
    if total <= 0 or not 0 < limit < 1:
        return []
    iso_year, iso_week, _ = today.isocalendar()
    found = []
    for holding in sorted(rows, key=lambda h: h.value, reverse=True):
        weight = holding.value / total
        if weight <= limit:
            continue
        excess = (holding.value - limit * total) / (1 - limit)
        units = int(excess // holding.price)
        action: Optional[Dict[str, Any]] = None
        if units >= 1:
            action = {"type": "review_order", "symbol": holding.symbol, "side": "sell", "units": units}
        found.append(Finding(
            kind="concentration",
            severity="watch",
            symbol=holding.symbol,
            title="{} is {:.0f}% of your holdings, over your {:g}% limit".format(
                holding.symbol, weight * 100, max_position_pct),
            body="{} is worth {} of {} held. Selling about {} ({} shares at {}) would bring it to {:g}%.".format(
                holding.symbol, _money(holding.value), _money(total), _money(excess),
                units, _money(holding.price), max_position_pct),
            facts={"weight_pct": round(weight * 100, 2), "limit_pct": max_position_pct,
                   "value": round(holding.value, 2), "portfolio_value": round(total, 2),
                   "excess_value": round(excess, 2), "units_to_limit": units},
            action=action,
            # Once a week while it stays over. Daily would be nagging.
            dedupe_key="concentration:{}:{}-W{:02d}".format(holding.symbol, iso_year, iso_week),
        ))
    return found


def filing(symbol: str, period: str, watch_titles: List[str], details: List[str]) -> List[Finding]:
    """The latest quarterly filing has findings marked "watch"."""
    if not watch_titles:
        return []
    count = len(watch_titles)
    return [Finding(
        kind="filing",
        severity="watch",
        symbol=symbol,
        title="{}'s {} filing has {} to check".format(
            symbol, period, "1 thing" if count == 1 else "{} things".format(count)),
        body=" ".join(details),
        facts={"period": period, "findings": watch_titles},
        action={"type": "open_company", "symbol": symbol},
        # Once per filing.
        dedupe_key="filing:{}:{}".format(symbol, period),
    )]


def exits_waiting(exits: List[Dict[str, Any]], today: date) -> List[Finding]:
    """Exits a strategy signalled that the user has not yet decided on."""
    if not exits:
        return []
    symbols = sorted({e.get("symbol") or "" for e in exits} - {""})
    count = len(exits)
    return [Finding(
        kind="exits_waiting",
        severity="watch",
        title="{} waiting on your decision".format("1 exit is" if count == 1 else "{} exits are".format(count)),
        body="Your strategies signalled an exit on {}. Each stays open until you sell or choose to hold.".format(
            ", ".join(symbols) if symbols else "a position"),
        facts={"count": count, "symbols": symbols},
        action={"type": "open_actions"},
        # Said again only when the set of waiting exits changes.
        dedupe_key="exits:{}:{}".format(today.isoformat(), "-".join(symbols) or str(count)),
    )]
