"""Canonical GICS sector taxonomy + the one normalization choke point.

`symbols.sector` is written by three independent paths, each using a different
upstream vocabulary, and until this module none of them normalized on write:

  * `app/scripts/seed_symbols.py` — FinanceDatabase, bulk seed, GICS spellings
  * `app/services/fundamental_service.py` — FMP (yfinance fallback) profile,
    FMP spellings, fired on *every* company-page view
  * `app/main.py` `_TOP_US_STOCKS` — hand-written FMP spellings, fresh-DB seed

So the same sector accumulated two spellings ("Health Care" from the seed,
"Healthcare" from FMP), and `ScreenerService.screen()` — which matches with
exact `==` — silently returned only the half the user happened to pick. The FMP
path made it progressively worse: every company page a user opened rewrote that
row's sector into the FMP vocabulary, quietly removing it from the sector screen.

The 11 canonical labels are GICS and match the frontend pickers **verbatim**
(`apps/web/src/app/stocks/_page-inner.tsx` `GICS_SECTORS` and
`apps/web/src/lib/flows/bricks/universe-selector.tsx` `SECTORS`). The sector
universe tier resolves by exact label match, so those lists and this set must
stay in sync — `tests/test_russell3000_sectors.py` guards the contract.

Every writer to `symbols.sector` must go through `normalize_sector()`.
"""
from __future__ import annotations

from typing import Dict, Optional

# The 11 canonical GICS sectors.
CANONICAL_SECTORS = frozenset({
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
})

# Placeholder junk that upstream providers hand us in place of a real sector.
# "nan" is the big one: pandas gives `float('nan')` for a missing cell, and
# `bool(float('nan')) is True`, so the `str(x or "") or None` idiom in
# seed_symbols.py stringified it into the literal label "nan" on 518 prod rows.
_JUNK_VALUES = frozenset({
    "nan", "none", "null", "n/a", "na", "-", "--", "unknown", "undefined",
})

# Non-canonical spelling (lowercased) -> canonical label. Identity entries for
# the 11 canonical labels are added below so lookups are uniformly caseless.
_ALIASES: Dict[str, str] = {c.lower(): c for c in CANONICAL_SECTORS}
_ALIASES.update({
    # FMP / yfinance vocabulary — the live contamination source.
    "basic materials": "Materials",
    "consumer cyclical": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "financial services": "Financials",
    "healthcare": "Health Care",
    "technology": "Information Technology",
    # Narrower industry-ish labels that arrive in the sector field.
    "banking": "Financials",
    "insurance": "Financials",
    # iShares abbreviates the GICS label; keep the full form (see
    # tests/test_russell3000_sectors.py::test_no_abbreviated_communication_label).
    "communication": "Communication Services",
    "telecommunications": "Communication Services",
    "telecommunication services": "Communication Services",
})


def normalize_sector(raw: Optional[object]) -> Optional[str]:
    """Map any upstream sector spelling to its canonical GICS label.

    Returns ``None`` for missing, blank, or placeholder values so the column
    stays NULL rather than carrying a junk label into the screener's filter list.

    Unrecognised labels pass through stripped-but-unchanged: a genuinely new
    sector should surface for triage, not be silently discarded.
    """
    if raw is None:
        return None
    # str() also absorbs the float('nan') pandas hands us for an empty cell —
    # the exact value that produced the "nan" sector rows in production.
    text = str(raw).strip()
    if not text or text.lower() in _JUNK_VALUES:
        return None
    return _ALIASES.get(text.lower(), text)
