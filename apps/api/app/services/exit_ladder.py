"""Exit-ladder evaluation — the single source of truth.

The backtester and the live position monitor both answer the same question:
*given an entry price and a bar, which exit tiers fire, and how much do they
sell?* Until now each answered it in its own code, and the two answers
disagreed in four separate ways:

  - scale-out size: the backtester scaled by fraction-of-REMAINING
    (``w *= 1 - f``), the monitor by fraction-of-INITIAL
  - tier identity: the backtester keyed fired-tiers on the ladder index, the
    monitor mapped EVERY negative tier to the constant string ``"stop_hit"``
  - bar interval: the backtester always ran daily, the monitor intraday
  - fires per bar: the backtester could fire several tiers on one bar, the
    monitor returned after the first

The third disagreement is the expensive one — a user's backtested equity
curve was not the plan the alert told them to execute. This module exists so
that class of bug cannot recur: there is one implementation, and both
consumers import it.

WHAT IS SHARED AND WHAT IS NOT. The *rule* is shared — which tiers fire, in
what order, and what fraction of the original position each one takes. The
*unit* is not: the backtester works in portfolio weights, the monitor in
shares. So `evaluate_bar` returns `fraction_of_initial` and each consumer
converts via `shares_for()` or `weight_delta_for()`. Sharing the rule is the
point; sharing the unit would force one consumer into the other's model.

SCALE-OUT CONVENTION: fraction of the ORIGINAL position (decided 2026-08-18).
A tier that says "sell a third" always means a third of what you started
with, so the ladder is path-independent — the size of tier 3's sale does not
depend on whether tiers 1 and 2 were executed, or on whether the user
remembered to tell us they were. Fraction-of-remaining makes the recommended
quantity a function of the user's data-entry discipline, which is the one
input we know to be unreliable.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Set

# ── Trigger field ───────────────────────────────────────────────────────────
#
# THE SINGLE SWITCH. Changing this constant changes the backtester and the
# live monitor together, which is the entire reason it lives here as one
# constant rather than as a per-caller argument. A caller that passes its own
# value is reintroducing the divergence this module was written to delete.
#
#   "close"    — a tier fires when the bar's CLOSE crosses it. Quieter; an
#                intrabar breach that recovers before the close never fires.
#   "extremes" — stops test the bar's LOW, targets test the bar's HIGH. This
#                is what a stop conventionally means (a touch, not a close).
#
# Currently "close" because that is what the backtester has always done, so
# extracting this module is a behaviour-preserving refactor apart from the
# convention and tier-identity fixes it deliberately makes.
#
# NOTE for whoever flips this: the backtester builds a CLOSE matrix only
# (`_load_prices` collects `adjusted_close`). "extremes" additionally
# requires split-adjusted high/low series, which do not exist there yet.
TRIGGER_FIELD = "close"


@dataclass(frozen=True)
class Bar:
    """One bar's prices. For close-only consumers, pass close for all three."""

    high: float
    low: float
    close: float

    @classmethod
    def from_close(cls, close: float) -> "Bar":
        """A bar with no intrabar range — the backtester's current view."""
        return cls(high=close, low=close, close=close)


@dataclass(frozen=True)
class TierFire:
    """One tier that fired on one bar.

    `fraction_of_initial` is 1.0 for `sell_all` so a consumer that only cares
    about size can treat both actions uniformly; `action` remains available
    for consumers that must distinguish closing the position from trimming it.
    """

    tier_index: int
    trigger_type: str
    trigger_pct: float
    action: str
    fraction_of_initial: float
    observed_price: float
    # The ladder's own label ("Stop", "TP1"). Notifications should show what
    # the user named the rung, not a synthesised word for its direction.
    tier_label: Optional[str] = None


def trigger_type_for(tier_index: int) -> str:
    """The stable, UNIQUE identity of a tier within its ladder.

    Keyed on the ladder index, never on the tier's direction. The live
    monitor previously returned the constant `"stop_hit"` for every negative
    tier, and its fire-once guard matched on that string — so in a ladder
    like `[-5% trim, -10% sell_all, +15% target]` the −5% trim consumed the
    identity and **the −10% hard stop could never fire for the life of that
    position**. Silent, permanent, and legal to configure.
    """
    return "tier{}_hit".format(tier_index)


def evaluate_bar(
    *,
    ladder: Sequence,
    entry_price: float,
    bar: Bar,
    already_fired: Optional[Set[str]] = None,
) -> List[TierFire]:
    """Return every tier that fires on this bar, in ladder order.

    Args:
        ladder: `ExitTier`-shaped objects, ordered ascending by `trigger_pct`
            (the strategy validator enforces this, so index order IS
            ascending order and the most negative stop is checked first).
        entry_price: the position's real entry price. Must be > 0.
        bar: the bar to evaluate.
        already_fired: `trigger_type` strings that have fired for THIS entry.
            Tiers fire at most once per entry; the caller owns this state
            (trade_log for the monitor, an in-loop set for the backtester).

    Returns a list because a single bar can clear several tiers — a gap that
    jumps both take-profit rungs fires both. The live monitor used to return
    after the first, so the second rung waited for the next poll; the
    backtester did not. Returning all of them makes the two agree.

    Evaluation stops at a `sell_all`: the position is closed, so tiers beyond
    it do not apply to this entry.
    """
    if not ladder or not entry_price or entry_price <= 0:
        return []

    fired_ids = already_fired or set()
    fires: List[TierFire] = []

    # In "extremes" mode an outside day can satisfy a stop AND a target on the
    # same bar. We cannot know the intrabar sequence, so the stop wins: any
    # other choice assumes the favourable leg filled first, which is exactly
    # the assumption that makes a backtest flatter than reality.
    downside_hit = False
    if TRIGGER_FIELD == "extremes":
        low_pct = (bar.low - entry_price) / entry_price
        downside_hit = any(
            t.trigger_pct < 0 and low_pct <= t.trigger_pct for t in ladder
        )

    for index, tier in enumerate(ladder):
        trigger_type = trigger_type_for(index)
        if trigger_type in fired_ids:
            continue

        is_stop = tier.trigger_pct < 0
        if downside_hit and not is_stop:
            continue

        if TRIGGER_FIELD == "extremes":
            observed = bar.low if is_stop else bar.high
        else:
            observed = bar.close
        pct = (observed - entry_price) / entry_price

        # A tier at exactly 0.0 satisfies neither test and is inert. That is
        # pre-existing behaviour, preserved deliberately rather than silently
        # changed here; a break-even stop is a real construction and wiring it
        # up is its own decision, not a side effect of this extraction.
        triggered = (is_stop and pct <= tier.trigger_pct) or (
            tier.trigger_pct > 0 and pct >= tier.trigger_pct
        )
        if not triggered:
            continue

        if tier.action == "sell_all":
            fraction = 1.0
        else:
            fraction = float(tier.fraction or 0.0)
            if fraction <= 0:
                continue

        fires.append(
            TierFire(
                tier_index=index,
                trigger_type=trigger_type,
                trigger_pct=float(tier.trigger_pct),
                action=tier.action,
                fraction_of_initial=fraction,
                observed_price=float(observed),
                tier_label=getattr(tier, "label", None),
            )
        )

        if tier.action == "sell_all":
            break

    return fires


def shares_for(
    fire: TierFire, *, shares_initial: float, shares_remaining: float
) -> float:
    """Shares this fire sells. For share-denominated consumers (the monitor).

    `sell_all` takes everything still held. A scale-out takes its fraction of
    the ORIGINAL position, capped at what remains — the cap only binds when a
    ladder's fractions sum past 1.0, which the strategy validator should
    reject rather than let this silently absorb.
    """
    if fire.action == "sell_all":
        return max(shares_remaining, 0.0)
    return max(min(shares_initial * fire.fraction_of_initial, shares_remaining), 0.0)


def weight_delta_for(fire: TierFire, *, entry_weight: float) -> float:
    """Weight this fire removes. For weight-denominated consumers (backtest).

    The subtractive form is what makes this fraction-of-initial: the old
    `w *= (1 - f)` compounded, so each successive tier took a fraction of an
    already-reduced position. Callers floor the result at zero.
    """
    if fire.action == "sell_all":
        return entry_weight
    return entry_weight * fire.fraction_of_initial
