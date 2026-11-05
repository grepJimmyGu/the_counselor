"""Regression: symbols.country is VARCHAR(8); yfinance writes country NAMES.

Symptom (2026-11-05, prod): company page for BBY rendered "Unable to load
company data" with ``psycopg.errors.StringDataRightTruncation: value too long
for type character varying(8)`` on ``UPDATE symbols SET ... country='United States'``.

Root cause: ``SymbolCache.country`` is ``String(8)`` (ISO codes, which FMP
returns). When FMP is unconfigured or rate-limited, ``_fetch_profile`` falls
back to yfinance, whose ``info["country"]`` is the full name. ``_upsert_symbol``
wrote it unguarded. SQLite ignores VARCHAR length, so the local suite could
never see it; Postgres enforces it.

Two fixes, each pinned below:
  1. ``normalize_country`` canonicalises to alpha-2 at both boundaries.
  2. The cache upsert can no longer take the page down — a failing write logs
     and the fetched profile is still returned.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.data.countries import COUNTRY_MAX_LEN, normalize_country
from app.models.symbol import SymbolCache
from app.schemas.fundamental import CompanyProfile
from app.services.fundamental_service import FundamentalService


# ── 1. the normaliser ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("United States", "US"),          # yfinance spelling — the production value
    ("united states", "US"),
    ("US", "US"),                      # FMP spelling passes through
    ("us", "US"),
    ("United Kingdom", "GB"),
    ("Cayman Islands", "KY"),
    ("  Canada ", "CA"),
    (None, None),
    ("", None),
    ("N/A", None),                     # placeholder vocabulary from sectors.py
])
def test_normalize_country_maps_names_to_codes(raw, expected):
    assert normalize_country(raw) == expected


def test_normalize_country_never_exceeds_column_width():
    # The whole point: nothing this function returns can trip VARCHAR(8).
    for raw in ("United States", "United States of America", "Bosnia and Herzegovina",
                "Some Country Nobody Aliased Yet", "US", "XX"):
        out = normalize_country(raw)
        assert out is None or len(out) <= COUNTRY_MAX_LEN, (raw, out)


def test_normalize_country_drops_long_unknown_instead_of_truncating():
    # "United " would be a fabricated country. Exclude-and-state, never estimate.
    assert normalize_country("Some Country Nobody Aliased Yet") is None


def test_column_width_constant_matches_model():
    assert SymbolCache.__table__.c.country.type.length == COUNTRY_MAX_LEN


# ── 2. the write path ─────────────────────────────────────────────────────────

def _profile(country: str) -> CompanyProfile:
    return CompanyProfile(symbol="BBY", name="Best Buy Co., Inc.", sector="Consumer Cyclical",
                          industry="Specialty Retail", exchange="NYQ", country=country,
                          description="x", data_source="yfinance")


def test_upsert_writes_the_code_not_the_name():
    svc = FundamentalService()
    db = MagicMock()
    existing = SymbolCache(symbol="BBY", name="Best Buy")
    db.get.return_value = existing

    svc._upsert_symbol(db, _profile("United States"))

    assert existing.country == "US"
    assert len(existing.country) <= COUNTRY_MAX_LEN
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_failed_cache_write_does_not_fail_the_page():
    svc = FundamentalService()
    db = MagicMock()
    db.scalar.return_value = None                    # no cached row -> fetch path
    fetched = _profile("United States")

    with patch.object(svc, "_fetch_profile", AsyncMock(return_value=fetched)), \
         patch.object(svc, "_upsert_symbol", side_effect=RuntimeError("StringDataRightTruncation")):
        profile = await svc.get_profile(db, "BBY")

    # The read survives the write failing, and the session is left clean.
    assert profile.symbol == "BBY"
    db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_profile_canonicalises_country_at_the_boundary():
    # Fresh fetch and later cache hit must agree (same rule the sector field follows).
    svc = FundamentalService()
    with patch.object(svc._fmp, "get_profile", AsyncMock(return_value=_profile("United States"))):
        profile = await svc._fetch_profile("BBY")
    assert profile.country == "US"
