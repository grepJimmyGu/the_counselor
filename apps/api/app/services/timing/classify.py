"""Two labels per episode, in two namespaces that must never merge — §3.6.

The obvious design is one label per fill drawn from whatever features are
handy. It silently mixes decision-time information with outcome information,
and the result compiles into look-ahead bias: `momentum_chase` defined as
*"RSI high AND negative 1–5D markout"* is not a setup, it is a setup plus the
answer. On a live chart the RSI is visible and the markout does not exist yet.

So:

- **`setup_type`** is computed from a `TechnicalSnapshot` and nothing else.
  Every input was on the chart at the moment of the fill. It **may** compile
  into a live Rule.
- **`timing_outcome`** is computed with full knowledge of what happened next.
  It is a diagnosis, and a diagnosis cannot be a trading condition. It
  **never** compiles.

The dependency runs one way: an outcome may read a setup (`chased` is defined
on `extended_momentum` fills), and no setup may read an outcome. That is
enforced by shape rather than by convention — `setup_type()` takes a snapshot
as its only argument, so it cannot see an outcome even by accident, and this
module imports no symbol from `markout` or `excursion`, which
`tests/test_timing_labels.py` asserts statically.

**Thresholds are module constants with stated defaults.** They are reviewable
and tunable, and they are deliberately not fitted to the user's own data —
fitting a label to the record it then describes makes it circular.
"""

from __future__ import annotations

from typing import Dict, Optional

from app.services.timing.snapshot import TechnicalSnapshot

__all__ = [
    "SETUP_TYPES", "TIMING_OUTCOMES", "setup_type", "timing_outcome",
]

SETUP_TYPES = (
    "extended_momentum", "pullback", "breakout", "oversold", "trend_continuation",
)
TIMING_OUTCOMES = (
    "early_entry", "chased", "premature_exit", "panic_exit",
    "efficient_stop", "giveback", "trend_exhaustion_exit",
)

# ── setup thresholds (decision-time) ────────────────────────────────────────
RSI_ELEVATED = 70.0
RSI_DEPRESSED = 30.0
EXTENDED_ABOVE_SMA20 = 0.10        # price this far over its 20-day mean
STRONG_5D_RUN = 0.05
PULLBACK_MAX_ABOVE_SMA20 = 0.03    # "near sma20, from above"
BREAKOUT_RANGE_PROXIMITY = -0.005  # within 0.5% of the 20-day high
BREAKOUT_RELATIVE_VOLUME = 1.5
TREND_MAX_EXTENSION = 0.10

# ── outcome thresholds (retrospective) ──────────────────────────────────────
MATERIAL_MOVE = 0.03
PREMATURE_CAPTURE = 0.5            # kept less than half of what was available
PANIC_DRAWDOWN = -0.05
GIVEBACK_MFE = 0.10
GIVEBACK_RETAINED = 0.5
EXHAUSTION_MFE = 0.10


def setup_type(state: TechnicalSnapshot) -> Optional[str]:
    """What this looked like at the moment of the fill.

    A fill matching nothing is `None`, never `"other"` — an unnamed condition
    is not a category, and a wide `other` bucket is how a taxonomy stops being
    falsifiable. Roughly 40% of a real record matches nothing; that share is
    reported in coverage with its `N` rather than absorbed.
    """
    rsi = state.get("rsi14")
    over20 = state.get("distance_from_sma20")
    over50 = state.get("distance_from_sma50")
    run5 = state.get("return_5d")
    from_high = state.get("distance_from_20d_high")
    rvol = state.get("relative_volume")
    close_over_50 = state.get("close_over_sma50")

    uptrend = close_over_50 is not None and close_over_50 > 1.0

    if (
        rsi is not None and rsi >= RSI_ELEVATED
        and over20 is not None and over20 >= EXTENDED_ABOVE_SMA20
        and run5 is not None and run5 >= STRONG_5D_RUN
    ):
        return "extended_momentum"

    if (
        from_high is not None and from_high >= BREAKOUT_RANGE_PROXIMITY
        and rvol is not None and rvol >= BREAKOUT_RELATIVE_VOLUME
    ):
        return "breakout"

    if uptrend and over20 is not None and 0.0 <= over20 <= PULLBACK_MAX_ABOVE_SMA20:
        return "pullback"

    if (
        rsi is not None and rsi <= RSI_DEPRESSED
        and over20 is not None and over20 < 0
        and over50 is not None and over50 < 0
    ):
        return "oversold"

    if (
        uptrend
        and over20 is not None and 0.0 <= over20 < TREND_MAX_EXTENSION
        and (from_high is None or from_high < BREAKOUT_RANGE_PROXIMITY)
    ):
        return "trend_continuation"

    return None


def _near_term(markouts: Dict[int, Optional[float]]) -> Optional[float]:
    """The 1–5 day picture as one number: the mean of whichever are present."""
    vals = [markouts[h] for h in (1, 3, 5) if markouts.get(h) is not None]
    return sum(vals) / len(vals) if vals else None


def timing_outcome(
    *,
    entry_markouts: Optional[Dict[int, Optional[float]]] = None,
    exit_markouts: Optional[Dict[int, Optional[float]]] = None,
    mae: Optional[float] = None,
    mfe: Optional[float] = None,
    realised_return: Optional[float] = None,
    entry_setup: Optional[str] = None,
) -> Optional[str]:
    """The retrospective diagnosis. Never compiles into a Rule.

    ⚠ `exit_markouts` are **already negated** — that is the engine's one
    convention (§3.1), and a stock that rose after the sale shows up here as a
    *negative* exit markout. Reading them as raw returns inverts every exit
    label, so the stock's own move is taken through `_after_exit` and nowhere
    else.
    """
    entry_markouts = entry_markouts or {}
    exit_markouts = exit_markouts or {}

    def _after_exit(horizon: int) -> Optional[float]:
        """What the STOCK did after the sale, undoing the negation."""
        v = exit_markouts.get(horizon)
        return None if v is None else -v

    near_entry = _near_term(entry_markouts)
    long_entry = entry_markouts.get(20)
    rose_after = _near_term({h: _after_exit(h) for h in (1, 3, 5)})
    rose_after_20 = _after_exit(20)

    # ── entry-side ──────────────────────────────────────────────────────────
    # `chased` reads a setup label. Outcomes may read setups; setups may never
    # read outcomes, and `setup_type()`'s signature makes the reverse impossible.
    if (
        entry_setup == "extended_momentum"
        and near_entry is not None and near_entry <= -MATERIAL_MOVE
    ):
        return "chased"

    if (
        near_entry is not None and near_entry <= -MATERIAL_MOVE
        and long_entry is not None and long_entry >= MATERIAL_MOVE
    ):
        # Right idea, wrong week — a completely different problem from a bad
        # idea, and the most useful thing this engine can tell someone.
        return "early_entry"

    # ── exit-side ───────────────────────────────────────────────────────────
    if (
        mae is not None and mae <= PANIC_DRAWDOWN
        and realised_return is not None and realised_return < 0
        and rose_after is not None and rose_after >= MATERIAL_MOVE
    ):
        return "panic_exit"

    if (
        realised_return is not None and realised_return > 0
        and mfe is not None and mfe > 0
        and realised_return / mfe < PREMATURE_CAPTURE
        and rose_after is not None and rose_after >= MATERIAL_MOVE
    ):
        return "premature_exit"

    if (
        mfe is not None and mfe >= GIVEBACK_MFE
        and realised_return is not None
        and realised_return < mfe * GIVEBACK_RETAINED
        and (rose_after is None or rose_after < MATERIAL_MOVE)
    ):
        return "giveback"

    if (
        mfe is not None and mfe >= EXHAUSTION_MFE
        and rose_after is not None and rose_after <= -MATERIAL_MOVE
    ):
        return "trend_exhaustion_exit"

    if (
        realised_return is not None and realised_return < 0
        and rose_after_20 is not None and rose_after_20 <= -MATERIAL_MOVE
    ):
        return "efficient_stop"

    return None
