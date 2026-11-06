"""Canonical country vocabulary for ``symbols.country``.

The column is ``String(8)`` and was designed for ISO-3166 alpha-2 codes, which
is what FMP returns (``"US"``). yfinance returns the *name* (``"United States"``,
13 characters). SQLite ignores VARCHAR length, so the mismatch never shows
locally; Postgres enforces it and raises ``StringDataRightTruncation`` on the
cache upsert — which took the whole company page down for any symbol that fell
through to the yfinance path (2026-11-05, BBY, "Unable to load company data").

Same shape as ``normalize_sector``: canonicalise at every boundary so a fresh
fetch and a later cache hit agree, and so the screener's exact-match country
filter sees one spelling, not two.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from app.data.sectors import is_placeholder

logger = logging.getLogger(__name__)

# Column width of SymbolCache.country. Keep in lockstep with models/symbol.py.
COUNTRY_MAX_LEN = 8

# Names as the providers actually spell them -> ISO-3166 alpha-2. Lower-cased
# on lookup. Extend when a new spelling surfaces in the warning log below.
_ALIASES: Dict[str, str] = {
    "united states": "US", "united states of america": "US", "usa": "US",
    "canada": "CA",
    "united kingdom": "GB", "great britain": "GB", "uk": "GB",
    "ireland": "IE",
    "germany": "DE", "france": "FR", "netherlands": "NL", "switzerland": "CH",
    "sweden": "SE", "denmark": "DK", "norway": "NO", "finland": "FI",
    "spain": "ES", "italy": "IT", "belgium": "BE", "luxembourg": "LU",
    "austria": "AT", "portugal": "PT", "poland": "PL",
    "china": "CN", "hong kong": "HK", "taiwan": "TW", "japan": "JP",
    "south korea": "KR", "korea": "KR", "singapore": "SG", "india": "IN",
    "australia": "AU", "new zealand": "NZ",
    "israel": "IL", "brazil": "BR", "mexico": "MX", "argentina": "AR",
    "chile": "CL", "colombia": "CO", "south africa": "ZA",
    "bermuda": "BM", "cayman islands": "KY", "bahamas": "BS",
    "jersey": "JE", "guernsey": "GG", "isle of man": "IM",
    "puerto rico": "PR", "monaco": "MC", "cyprus": "CY", "greece": "GR",
    "united arab emirates": "AE", "saudi arabia": "SA", "turkey": "TR",
    "indonesia": "ID", "malaysia": "MY", "thailand": "TH", "philippines": "PH",
    "vietnam": "VN",
}


def normalize_country(raw: Optional[object]) -> Optional[str]:
    """Map any upstream country spelling to an ISO alpha-2 code.

    Returns ``None`` for missing or placeholder values. A short unrecognised
    value (a code we have not aliased) passes through upper-cased. A long
    unrecognised value is dropped to ``None`` with a warning rather than
    truncated: ``"United "`` is a fabricated country, and the repo rule is
    exclude-and-state, never estimate.
    """
    if is_placeholder(raw):
        return None
    text = str(raw).strip()
    if not text:
        return None
    code = _ALIASES.get(text.lower())
    if code is not None:
        return code
    if len(text) <= COUNTRY_MAX_LEN:
        return text.upper()
    logger.warning(
        "normalize_country: unrecognised value %r exceeds %d chars; storing NULL. "
        "Add it to app/data/countries.py._ALIASES.", text, COUNTRY_MAX_LEN,
    )
    return None
