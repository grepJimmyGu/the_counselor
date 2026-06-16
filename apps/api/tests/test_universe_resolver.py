"""PRD-23a slice 1 — universe resolver.

The pure function that turns a `universe_id` into the concrete symbol list a
reading is screened over. Covers the five tiers, normalization, the
expand-only S&P 500 floor, and the standing-vs-direct dual-execution switch.
"""
from __future__ import annotations

import pytest

from app.data.sp500_tickers import SP500_TICKERS
from app.services.screener.universe_resolver import (
    SP500_FLOOR,
    is_standing_universe,
    normalize_symbols,
    resolve_universe,
)


# ── normalize_symbols ────────────────────────────────────────────────────────


def test_normalize_uppercases_trims_dedupes_preserving_order():
    assert normalize_symbols([" aapl ", "MSFT", "aapl", "nvda"]) == [
        "AAPL",
        "MSFT",
        "NVDA",
    ]


def test_normalize_drops_blanks_and_handles_none():
    assert normalize_symbols(None) == []
    assert normalize_symbols(["", "  ", "TSLA", None]) == ["TSLA"]


# ── sp500 tier ───────────────────────────────────────────────────────────────


def test_sp500_returns_full_sorted_set():
    result = resolve_universe("sp500")
    assert result == sorted(SP500_TICKERS)
    assert result == sorted(result)  # deterministic order for the snapshot scan


def test_sp500_respects_expand_only_floor():
    # CLAUDE.md "expand only" invariant — the standard must not quietly shrink.
    assert len(resolve_universe("sp500")) >= SP500_FLOOR


# ── client-supplied tiers (symbols / watchlist / portfolio) ──────────────────


@pytest.mark.parametrize("tier", ["symbols", "watchlist", "portfolio"])
def test_client_supplied_tiers_return_normalized_input(tier):
    assert resolve_universe(tier, symbols=["nvda", " AMD ", "nvda"]) == ["NVDA", "AMD"]


@pytest.mark.parametrize("tier", ["symbols", "watchlist", "portfolio"])
def test_client_supplied_tiers_empty_when_no_symbols(tier):
    assert resolve_universe(tier) == []


def test_symbols_tier_single_symbol_is_a_universe_of_one():
    # The unified-mode contract: "Build from scratch" is a universe of size 1.
    assert resolve_universe("symbols", symbols=["AAPL"]) == ["AAPL"]


# ── sector tier ──────────────────────────────────────────────────────────────


def test_sector_tier_uses_injected_membership_and_normalizes():
    calls = []

    def membership(key):
        calls.append(key)
        return ["aapl", "MSFT", "aapl"]  # dupes/casing the resolver must clean

    assert resolve_universe("sector_XLK", sector_membership=membership) == [
        "AAPL",
        "MSFT",
    ]
    assert calls == ["XLK"]  # the key after the prefix is passed through


def test_sector_tier_without_membership_is_empty_not_an_error():
    # No lookup wired (e.g. a pure unit context) -> empty, never fabricated.
    assert resolve_universe("sector_XLK") == []


def test_sector_tier_missing_key_raises():
    with pytest.raises(ValueError, match="sector key"):
        resolve_universe("sector_")


# ── unknown tier ─────────────────────────────────────────────────────────────


def test_unknown_universe_id_raises():
    with pytest.raises(ValueError, match="Unknown universe_id"):
        resolve_universe("nasdaq100")


# ── dual-execution switch ────────────────────────────────────────────────────


def test_standing_universes_are_sp500_and_sectors():
    assert is_standing_universe("sp500") is True
    assert is_standing_universe("sector_XLK") is True


def test_client_supplied_tiers_are_not_standing():
    assert is_standing_universe("symbols") is False
    assert is_standing_universe("watchlist") is False
    assert is_standing_universe("portfolio") is False
