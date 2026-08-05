"""Regression tests for the mixed sector taxonomy in `symbols.sector`.

SYMPTOM: `GET /api/screener/filters` returned 18 sector values — six alias pairs
for the same sector plus the literal string "nan" — and `ScreenerService.screen()`
matches with exact `==`, so picking one spelling silently dropped every row
stored under the other.

ROOT CAUSE: three writers populated the column in two vocabularies with no
normalization on write, and `seed_symbols.py` stringified pandas' `float('nan')`
into the label "nan" (`bool(float('nan')) is True` defeated its `or ""` guard).

See `app/data/sectors.py`.
"""
from __future__ import annotations

import pytest

from app.data.sectors import CANONICAL_SECTORS, is_placeholder, normalize_sector
from app.schemas.fundamental import CompanyProfile
from app.schemas.screener import ScreenerFilters
from app.services.fundamental_service import FundamentalService
from app.services.screener_service import ScreenerService
from app.services.value_chain_classifier import (
    get_cyclicality_implication,
    get_value_chain_role,
)

# The six spelling collisions observed in production, as (FMP label, GICS label).
ALIAS_PAIRS = [
    ("Basic Materials", "Materials"),
    ("Consumer Cyclical", "Consumer Discretionary"),
    ("Consumer Defensive", "Consumer Staples"),
    ("Financial Services", "Financials"),
    ("Healthcare", "Health Care"),
    ("Technology", "Information Technology"),
]


# ── normalize_sector ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("fmp_label,gics_label", ALIAS_PAIRS)
def test_fmp_aliases_collapse_to_gics(fmp_label, gics_label):
    assert normalize_sector(fmp_label) == gics_label
    # The canonical label is a fixed point.
    assert normalize_sector(gics_label) == gics_label


def test_canonical_labels_are_unchanged():
    for label in CANONICAL_SECTORS:
        assert normalize_sector(label) == label


def test_normalization_is_idempotent():
    for raw in [fmp for fmp, _ in ALIAS_PAIRS] + list(CANONICAL_SECTORS):
        once = normalize_sector(raw)
        assert normalize_sector(once) == once


@pytest.mark.parametrize("junk", ["nan", "NaN", "NAN", "none", "null", "N/A", "-", "", "   "])
def test_placeholder_values_become_null(junk):
    assert normalize_sector(junk) is None


def test_pandas_missing_cell_becomes_null():
    """The exact value that produced 518 'nan' rows in production.

    `bool(float('nan')) is True`, so `str(cell or "")` never short-circuits and
    stringifies the NaN into a real-looking label.
    """
    assert normalize_sector(float("nan")) is None
    assert normalize_sector(None) is None


def test_lookup_is_case_and_whitespace_insensitive():
    assert normalize_sector("  healthcare  ") == "Health Care"
    assert normalize_sector("TECHNOLOGY") == "Information Technology"


def test_unknown_label_passes_through_stripped():
    """A genuinely new sector should surface for triage, not vanish silently."""
    assert normalize_sector("  Frontier Robotics  ") == "Frontier Robotics"


def test_no_canonical_label_is_an_alias_of_another():
    """Guards against an alias entry that would merge two real sectors."""
    for label in CANONICAL_SECTORS:
        assert normalize_sector(label) == label


# ── the user-facing screener bug ──────────────────────────────────────────────

def _ingest(db, symbol: str, sector: str) -> None:
    """Write a row through the real ingest path (the FMP company-page upsert)."""
    FundamentalService()._upsert_symbol(
        db, CompanyProfile(symbol=symbol, name=f"{symbol} Inc", sector=sector)
    )


def test_screening_by_gics_label_finds_fmp_ingested_rows(db):
    """The original bug: a company ingested as "Healthcare" was invisible to a
    "Health Care" sector screen, because `screen()` matches with exact `==`."""
    _ingest(db, "LLY", "Healthcare")        # FMP vocabulary
    _ingest(db, "JNJ", "Health Care")       # GICS vocabulary

    resp = ScreenerService().screen(db, ScreenerFilters(sector="Health Care"))

    assert sorted(r.symbol for r in resp.results) == ["JNJ", "LLY"]
    assert resp.total == 2


def test_filters_expose_no_alias_pairs_and_no_nan(db):
    """`GET /api/screener/filters` must not offer two spellings of one sector,
    nor the literal 'nan'."""
    for i, (fmp_label, gics_label) in enumerate(ALIAS_PAIRS):
        _ingest(db, f"FMP{i}", fmp_label)
        _ingest(db, f"GICS{i}", gics_label)
    _ingest(db, "SPAC", "nan")              # the pandas-NaN data bug
    _ingest(db, "BLANK", "   ")

    sectors = ScreenerService().get_filters(db).sectors

    assert "nan" not in sectors
    for fmp_label, gics_label in ALIAS_PAIRS:
        assert not (fmp_label in sectors and gics_label in sectors), (
            f"both spellings present: {fmp_label!r} and {gics_label!r}"
        )
    assert set(sectors) <= CANONICAL_SECTORS, f"non-canonical: {set(sectors) - CANONICAL_SECTORS}"
    assert len(sectors) == len(set(sectors))


def test_nan_and_blank_sectors_are_stored_as_null(db):
    _ingest(db, "SPAC", "nan")
    resp = ScreenerService().screen(db, ScreenerFilters(sector="nan"))
    assert resp.total == 0


# ── the value-chain classifier bug ────────────────────────────────────────────

def test_value_chain_role_resolves_for_canonical_labels():
    """The classifier was keyed on FMP labels while its callers read GICS rows
    out of `symbols`, so every lookup missed and returned None."""
    assert get_value_chain_role("Information Technology", "Semiconductors") == "Component Supplier"
    assert get_value_chain_role("Health Care", "Biotechnology") == "Value-Added Technology Provider"
    assert get_value_chain_role("Materials", "Chemicals") == "Raw Material Provider"
    assert get_value_chain_role("Consumer Discretionary", "Specialty Retail") == "Retailer"


def test_every_canonical_sector_has_a_fallback_role_and_cyclicality():
    for label in CANONICAL_SECTORS:
        assert get_value_chain_role(label, None) is not None, f"no fallback role for {label}"
        assert get_cyclicality_implication(label) is not None, f"no cyclicality for {label}"


@pytest.mark.parametrize("fmp_label,gics_label", ALIAS_PAIRS)
def test_classifier_still_accepts_fmp_labels(fmp_label, gics_label):
    """Callers that hand us a raw FMP profile must resolve the same as GICS."""
    assert get_value_chain_role(fmp_label, None) == get_value_chain_role(gics_label, None)
    assert get_cyclicality_implication(fmp_label) == get_cyclicality_implication(gics_label)


# ── agreement with the PRD-29 search workaround ───────────────────────────────

def test_search_vocab_spellings_agree_with_canonical_taxonomy():
    """`app/data/screen_filter_vocab.py` carries its own list of stored sector
    spellings — the PRD-29 workaround that kept the *search* path correct while
    the underlying data bug (this module) was still open. It matches with `IN`
    over a superset, so it stays correct after the backfill and is deliberately
    left in place. This test stops the two maps from drifting apart: every
    spelling filed under a canonical key must normalize to the same label.
    """
    from app.data.screen_filter_vocab import SECTOR_ALIASES

    for key, spellings in SECTOR_ALIASES.items():
        targets = {normalize_sector(s) for s in spellings}
        assert len(targets) == 1, f"{key!r} spellings disagree: {spellings} -> {targets}"
        canonical = targets.pop()
        assert canonical in CANONICAL_SECTORS, f"{key!r} -> non-canonical {canonical!r}"
        assert normalize_sector(key) == canonical, (
            f"key {key!r} normalizes to {normalize_sector(key)!r}, spellings to {canonical!r}"
        )


def test_search_vocab_covers_every_canonical_sector():
    from app.data.screen_filter_vocab import SECTOR_ALIASES

    covered = {normalize_sector(s) for sp in SECTOR_ALIASES.values() for s in sp}
    assert covered == set(CANONICAL_SECTORS), f"uncovered: {set(CANONICAL_SECTORS) - covered}"


# ── the seed-script NaN bug ───────────────────────────────────────────────────

@pytest.mark.parametrize("junk", ["nan", "NaN", "none", "null", "N/A", "", "   ", None])
def test_is_placeholder_detects_junk(junk):
    """Used by the backfill to clear the same 'nan' from `industry`/`exchange`,
    which the seed bug hit on lines adjacent to `sector`."""
    assert is_placeholder(junk) is True


@pytest.mark.parametrize("real", ["Semiconductors", "NASDAQ", "Health Care", "Banks—Diversified"])
def test_is_placeholder_passes_real_values(real):
    assert is_placeholder(real) is False


def test_is_placeholder_detects_pandas_nan():
    assert is_placeholder(float("nan")) is True


def test_seed_clean_helper_rejects_pandas_nan():
    from app.scripts.seed_symbols import _clean

    assert _clean(float("nan"), 120) is None
    assert _clean("nan", 120) is None
    assert _clean(None, 16, default="USD") == "USD"
    assert _clean(float("nan"), 16, default="USD") == "USD"
    assert _clean("  NASDAQ  ", 32) == "NASDAQ"
    assert _clean("A" * 200, 120) == "A" * 120
