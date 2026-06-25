"""Single source of truth for the screener's STANDING universes — the
pre-warmed, snapshot-scannable index baskets (the prewarm-universe registry
from PROJECT_BACKLOG §4).

Adding an index universe is ONE edit here. It flows through:
  - the resolver (`universe_resolver.resolve_universe` / `is_standing_universe`)
  - the request validators (`schemas.screener_scan`)
  - the daily snapshot warm (`jobs.signal_snapshot_job`), which warms the
    UNION — the snapshot is keyed by symbol, so one warm serves a scan of
    every standing tier.
Keeping the new universe's `price_bars` warm is the only other step.

NOT here: the client-supplied tiers (symbols / watchlist / portfolio) and
`sector_<key>` — those resolve dynamically in `universe_resolver`.

Product invariant (CLAUDE.md "expand only, never shrink"): entries are added,
never removed without a replacement. `sp500` stays the Market Pulse Top Movers
standard; `russell3000` is purely additive.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List

from app.data.russell3000_tickers import RUSSELL3000_TICKERS
from app.data.sp500_tickers import SP500_TICKERS

STANDING_UNIVERSES: Dict[str, FrozenSet[str]] = {
    "sp500": frozenset(SP500_TICKERS),
    "russell3000": frozenset(RUSSELL3000_TICKERS),
}


def is_standing_id(universe_id: str) -> bool:
    """True if `universe_id` is a registered standing index universe."""
    return universe_id in STANDING_UNIVERSES


def standing_universe_ids() -> FrozenSet[str]:
    """The registered standing universe ids (for request validation)."""
    return frozenset(STANDING_UNIVERSES)


def standing_universe_symbols(universe_id: str) -> List[str]:
    """Sorted symbols for one standing universe. Raises KeyError if the id is
    not registered (callers gate with `is_standing_id` first)."""
    return sorted(STANDING_UNIVERSES[universe_id])


def all_standing_symbols() -> List[str]:
    """The UNION of every standing universe — what the daily snapshot warm
    covers. Because the snapshot is symbol-keyed, warming the union once serves
    a scan of any standing tier (sp500 and russell3000 overlap heavily, so the
    union is far smaller than the naive sum)."""
    union: set = set()
    for members in STANDING_UNIVERSES.values():
        union |= members
    return sorted(union)
