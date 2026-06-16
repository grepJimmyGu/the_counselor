"""Market Screener — universe resolver (PRD-23a §3.1).

Turns a `universe_id` into the concrete list of symbols a composed reading
will be screened over.

THE UNIFIED-MODE CONTRACT (HANDOFF §0): a single symbol is just a universe
of size 1. The `symbols` tier is the narrowest universe — it is what
"Build from scratch" becomes. Broader tiers (`sp500`, `sector_<key>`) are
the screener proper.

Tiers
-----
- "symbols"      -> the caller's entered symbol(s)   (client-supplied)
- "watchlist"    -> the user's watchlist symbols     (client-supplied¹)
- "portfolio"    -> the user's uploaded holdings     (client-supplied¹)
- "sp500"        -> SP500_TICKERS (the expand-only standard)
- "sector_<key>" -> the sector basket               (via `sector_membership`)

¹ watchlist/portfolio have no persistent backend universe yet (the
  `user_watchlists` table is Phase 3); v1 receives their symbols from the
  flow context, exactly like entered symbols. The tier label is still
  preserved end-to-end — it drives the "why this universe" UI and the
  dual-execution routing below.

PURITY: this module holds no DB session and no entitlement logic (that
gates at the endpoint, PRD-23a §3.6). The `sector_<key>` tier takes an
*injected* `sector_membership` callable so the function stays unit-testable;
the route layer supplies a DB-backed implementation (SymbolCache.sector).

Dual execution (PRD-23a §3.1)
-----------------------------
`is_standing_universe(universe_id)` tells the caller which path to take:
- standing (sp500 / sector) -> pre-warmed snapshot scan -> rank the matches
- non-standing (symbols / watchlist / portfolio) -> direct backtest, no snapshot
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence

from app.data.sp500_tickers import SP500_TICKERS

# The S&P 500 tier must never quietly shrink (CLAUDE.md "expand only" +
# PRD-23a §6 / risk table). The live set is ~525; this floor catches a
# catastrophic contraction while tolerating quarterly reconstitution churn.
SP500_FLOOR = 490

SECTOR_PREFIX = "sector_"

# sector_key (e.g. "XLK" or "Technology") -> the symbols in that sector.
SectorMembershipFn = Callable[[str], Sequence[str]]

# Tiers whose membership the caller supplies as a symbol list (v1).
_CLIENT_SUPPLIED = frozenset({"symbols", "watchlist", "portfolio"})


def normalize_symbols(symbols: Optional[Sequence[str]]) -> List[str]:
    """Uppercase, trim, drop blanks, dedupe — order-preserving.

    A single entered symbol and a pasted list both flow through here so the
    rest of the pipeline never sees casing/whitespace/dupe noise.
    """
    seen = set()
    out: List[str] = []
    for raw in symbols or []:
        sym = (raw or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def is_standing_universe(universe_id: str) -> bool:
    """True for pre-warmed universes (snapshot scan path); False for the
    client-supplied baskets that take the direct-backtest path.

    This is the switch behind the unified mode's dual execution: entered
    symbols / watchlist / portfolio are small, user-specific, and not in the
    standing snapshot, so they backtest directly; `sp500` / `sector_*` ride
    the daily snapshot so a scan is a sub-300ms in-memory filter.
    """
    return universe_id == "sp500" or universe_id.startswith(SECTOR_PREFIX)


def resolve_universe(
    universe_id: str,
    *,
    symbols: Optional[Sequence[str]] = None,
    sector_membership: Optional[SectorMembershipFn] = None,
) -> List[str]:
    """Resolve a `universe_id` to its concrete, normalized symbol list.

    Args:
        universe_id: one of "symbols" | "watchlist" | "portfolio" | "sp500"
            | "sector_<key>".
        symbols: the caller-supplied list, used by the client-supplied tiers.
        sector_membership: `sector_key -> symbols` lookup, required by the
            `sector_<key>` tier. The route binds this to a DB query; tests
            inject a stub.

    Raises:
        ValueError: unknown `universe_id`, or a `sector_` id with no key.
    """
    if universe_id == "sp500":
        return sorted(SP500_TICKERS)

    if universe_id in _CLIENT_SUPPLIED:
        return normalize_symbols(symbols)

    if universe_id.startswith(SECTOR_PREFIX):
        key = universe_id[len(SECTOR_PREFIX):]
        if not key:
            raise ValueError(
                "sector universe_id is missing a sector key (e.g. 'sector_XLK')"
            )
        members = sector_membership(key) if sector_membership is not None else []
        return normalize_symbols(members)

    raise ValueError(f"Unknown universe_id: {universe_id!r}")
