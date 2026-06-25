"""Tests for the Russell 3000 GICS sector map (app/data/russell3000_sectors.py)
— the canonical taxonomy the Sector screen + the frontend picker must share for
the verbatim `SymbolCache.sector` match to line up (R3000 sector normalization)."""
from __future__ import annotations

from app.data.russell3000_sectors import RUSSELL3000_SECTORS
from app.data.russell3000_tickers import RUSSELL3000_TICKERS

# The 11 canonical GICS sectors. MUST stay in sync with the frontend
# universe-selector `SECTORS` list — the sector tier matches the label verbatim.
CANONICAL_GICS = {
    "Information Technology",
    "Financials",
    "Health Care",
    "Consumer Discretionary",
    "Communication Services",
    "Industrials",
    "Consumer Staples",
    "Energy",
    "Materials",
    "Real Estate",
    "Utilities",
}


def test_every_russell3000_ticker_has_a_sector():
    assert set(RUSSELL3000_SECTORS) == set(RUSSELL3000_TICKERS)
    assert all(RUSSELL3000_SECTORS.values())  # no empty / null labels


def test_only_canonical_gics_labels():
    used = set(RUSSELL3000_SECTORS.values())
    assert used <= CANONICAL_GICS, f"non-canonical labels: {used - CANONICAL_GICS}"
    assert used == CANONICAL_GICS  # the broad market spans all 11 sectors


def test_no_abbreviated_communication_label():
    # iShares abbreviates to "Communication"; we canonicalise to the full GICS
    # "Communication Services" so it matches the picker + the existing DB rows.
    assert "Communication" not in set(RUSSELL3000_SECTORS.values())


def test_spot_check_known_sectors():
    assert RUSSELL3000_SECTORS["AAPL"] == "Information Technology"
    assert RUSSELL3000_SECTORS["JPM"] == "Financials"
    assert RUSSELL3000_SECTORS["XOM"] == "Energy"
    assert RUSSELL3000_SECTORS["BRK.B"] == "Financials"
