"""One split-framed bar series, read once, shared by everything in 43b.

Markouts, excursions and the technical snapshot all need the same bars in the
same split frame. Loading them three times is the Principle-1 violation the
packet bans, and — worse — three loaders means three chances to forget the
split adjustment. So there is one series object and everything reads it.

**The frame.** Every bar and every fill price is restated into the frame of
the newest bar in the window: a bar's price is divided by the product of the
split coefficients that took effect strictly after it. That is the same rule
`portfolio_ledger_service._apply_splits` applies to transactions, deliberately
so — a split's coefficient sits on the bar for the day it took effect, and a
trade made ON that day is already at the post-split price.

Splits *after* the window need no handling: they scale every bar in the window
by the same factor, which cancels in any return.

**`adjusted_close` is not a substitute.** It carries dividend adjustments too,
and `high`/`low` are raw in `price_bars` regardless — so an excursion built on
`adjusted_close` for the close and raw bars for the range would mix two frames
in one measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar

__all__ = ["BarSeries", "load_series"]

# Matches `portfolio_ledger_service._SPLIT_EPSILON`. Float noise means a
# coefficient is never compared for equality with 1.0.
_SPLIT_EPSILON = 1e-6


@dataclass
class BarSeries:
    """Ascending trading-day bars for one symbol, in a single split frame."""

    symbol: str
    dates: List[date] = field(default_factory=list)
    opens: List[float] = field(default_factory=list)
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    closes: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)
    # Cumulative split factor per bar: raw / factor == adjusted.
    factors: List[float] = field(default_factory=list)
    _index: Dict[date, int] = field(default_factory=dict, repr=False)

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def from_rows(cls, symbol: str, rows: Sequence[Dict[str, Any]]) -> "BarSeries":
        ordered = sorted(
            (r for r in rows if r.get("trading_date") is not None),
            key=lambda r: r["trading_date"],
        )
        s = cls(symbol=str(symbol).strip().upper())
        if not ordered:
            return s

        # Walk backwards accumulating the splits that took effect after each
        # bar. A bar carrying coefficient c is itself already post-split, so
        # c applies to everything strictly before it.
        factors = [1.0] * len(ordered)
        running = 1.0
        for i in range(len(ordered) - 1, -1, -1):
            factors[i] = running
            coef = ordered[i].get("split_coefficient")
            try:
                coef = float(coef) if coef is not None else 1.0
            except (TypeError, ValueError):
                coef = 1.0
            if abs(coef - 1.0) > _SPLIT_EPSILON and coef > 0:
                running *= coef

        for row, f in zip(ordered, factors):
            s._index[row["trading_date"]] = len(s.dates)
            s.dates.append(row["trading_date"])
            s.factors.append(f)
            for key, bucket in (
                ("open", s.opens), ("high", s.highs),
                ("low", s.lows), ("close", s.closes),
            ):
                v = row.get(key)
                bucket.append(float(v) / f if v is not None else float("nan"))
            vol = row.get("volume")
            s.volumes.append(float(vol) if vol is not None else float("nan"))
        return s

    # ── access ──────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.dates)

    def close(self, i: int) -> float:
        return self.closes[i]

    def pos(self, when: date) -> Optional[int]:
        """Index of this exact trading day, or None."""
        return self._index.get(when)

    def pos_on_or_after(self, when: date) -> Optional[int]:
        """Index of the first bar on or after `when`.

        A `trade_date` can land on a weekend or a holiday — a settlement quirk,
        a broker's own stamping, a corporate action. Anchoring to the next bar
        is the only honest read; there is no bar for a day the market was shut.
        """
        hit = self._index.get(when)
        if hit is not None:
            return hit
        for i, d in enumerate(self.dates):
            if d >= when:
                return i
        return None

    def factor_on(self, when: date) -> float:
        """Cumulative split factor at `when` — splits strictly after it."""
        i = self.pos_on_or_after(when)
        if i is None:
            return self.factors[-1] if self.factors else 1.0
        return self.factors[i]

    def restate(self, price: float, when: date) -> float:
        """Put a fill price into the series' frame.

        Adjusting the bars and then comparing them to a raw fill price is
        exactly as wrong as not adjusting at all — both terms of every return
        in this package have to sit in the same frame.
        """
        return float(price) / self.factor_on(when)

    def frame(self) -> pd.DataFrame:
        """Split-adjusted OHLCV for the catalog's `_compute(frame)` seam."""
        return pd.DataFrame(
            {
                "open": self.opens, "high": self.highs, "low": self.lows,
                "close": self.closes, "volume": self.volumes,
            },
            index=pd.DatetimeIndex([pd.Timestamp(d) for d in self.dates]),
        )


def load_series(
    db: Session, symbol: str, start: date, end: date,
) -> BarSeries:
    """One symbol's bars over [start, end]. One query, bounded by the window.

    Never the universe (HANDOFF §6F) — callers hold a few dozen traded names.
    """
    sym = str(symbol).strip().upper()
    stmt = (
        select(
            PriceBar.trading_date, PriceBar.open, PriceBar.high, PriceBar.low,
            PriceBar.close, PriceBar.volume, PriceBar.split_coefficient,
        )
        .where(
            PriceBar.symbol == sym,
            PriceBar.trading_date >= start,
            PriceBar.trading_date <= end,
        )
        .order_by(PriceBar.trading_date)
    )
    rows = [
        {
            "trading_date": d, "open": o, "high": h, "low": lo,
            "close": c, "volume": v, "split_coefficient": sc,
        }
        for d, o, h, lo, c, v, sc in db.execute(stmt).all()
    ]
    return BarSeries.from_rows(sym, rows)
