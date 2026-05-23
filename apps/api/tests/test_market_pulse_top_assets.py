"""Regression tests for `_build_top_assets` — Market Pulse Top Movers
candidate pool.

Covers:
  * **Region leak**: Chinese A-shares (`.SH`/`.SZ`) and HK listings (`.HK`)
    must never appear in the US Top Movers grid even when their symbols
    have price bars + market_cap data. (2026-05-22 production bug — see
    [PROJECT_BACKLOG.md §4b](../../../docs/PROJECT_BACKLOG.md).)
  * **Region IS NULL is treated as US-eligible** so legacy rows whose
    `region` never backfilled still appear in the list (defensive).
  * **`.SH`/`.SZ`/`.HK` suffix exclusion** as belt-and-suspenders catches
    the orphan case where `region` IS NULL on a CN listing.
  * **ETFs still excluded** from the equities pool (unchanged behavior).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from app.models.price_bar import PriceBar
from app.models.symbol import SymbolCache
from app.services.market_pulse_service import _build_top_assets


def _insert_symbol_with_bars(
    db,
    symbol: str,
    name: str,
    region: Optional[str],
    market_cap: float,
    bar_count: int = 25,
) -> None:
    """Helper: insert a symbol + 25 days of synthetic price bars so it
    has enough history for the CMF computation (period=20)."""
    db.add(SymbolCache(
        symbol=symbol,
        name=name,
        region=region,
        market_cap=market_cap,
        market_cap_category="large",
        is_active=True,
        instrument_type=None,  # treated as non-ETF
    ))
    today = date.today()
    for i in range(bar_count):
        d = today - timedelta(days=bar_count - i)
        # `_build_top_assets` filters with `pb.trading_date >= cutoff`
        # where cutoff = today - 30 days, so all our bars qualify.
        db.add(PriceBar(
            symbol=symbol,
            trading_date=d,
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.0 + i,
            adjusted_close=100.0 + i,
            volume=1_000_000,
            dividend_amount=0.0,
            split_coefficient=1.0,
            source="test",
            fetched_at=datetime.utcnow(),
        ))
    db.commit()


def test_us_top_assets_excludes_cn_a_share_via_region(db):
    """A symbol with `region='CN'` is filtered out even with bars + market_cap."""
    _insert_symbol_with_bars(db, "NVDA", "NVIDIA", region="US", market_cap=3_000_000_000_000)
    _insert_symbol_with_bars(db, "000001.SHE", "Ping An Bank", region="CN", market_cap=200_000_000_000)

    assets = _build_top_assets("US", db, limit=10)
    syms = {a.symbol for a in assets}
    assert "NVDA" in syms
    assert "000001.SHE" not in syms


def test_us_top_assets_excludes_sh_suffix_even_with_null_region(db):
    """The exact production-bug shape: `region` IS NULL + symbol ends in
    `.SH` → must still be excluded."""
    _insert_symbol_with_bars(db, "AAPL", "Apple Inc.", region="US", market_cap=3_000_000_000_000)
    _insert_symbol_with_bars(db, "510300.SH", "Huatai PineBridge", region=None, market_cap=10_000_000_000)

    assets = _build_top_assets("US", db, limit=10)
    syms = {a.symbol for a in assets}
    assert "AAPL" in syms
    assert "510300.SH" not in syms, "510300.SH leaked into US Top Movers — region filter regression!"


def test_us_top_assets_excludes_sz_and_hk_suffix(db):
    """Belt-and-suspenders covers all three CN listing conventions."""
    _insert_symbol_with_bars(db, "MSFT", "Microsoft", region="US", market_cap=3_000_000_000_000)
    _insert_symbol_with_bars(db, "002594.SZ", "BYD", region=None, market_cap=80_000_000_000)
    _insert_symbol_with_bars(db, "0700.HK", "Tencent", region=None, market_cap=400_000_000_000)

    assets = _build_top_assets("US", db, limit=10)
    syms = {a.symbol for a in assets}
    assert "MSFT" in syms
    assert "002594.SZ" not in syms
    assert "0700.HK" not in syms


def test_us_top_assets_null_region_us_listing_is_included(db):
    """A US listing whose `region` happens to be NULL (legacy / unbackfilled)
    must still be eligible — the suffix check is what guards CN."""
    _insert_symbol_with_bars(db, "PLTR", "Palantir", region=None, market_cap=100_000_000_000)
    assets = _build_top_assets("US", db, limit=10)
    syms = {a.symbol for a in assets}
    assert "PLTR" in syms, "Legacy NULL-region US listing got over-filtered."


def test_us_top_assets_etf_still_excluded(db):
    """ETFs (instrument_type='ETF' OR in the ETF_SYMBOLS whitelist) must
    not appear in the equities pool. Sanity-check unchanged behavior."""
    # SPY is hardcoded in ETF_SYMBOLS — the query filters via NOT IN
    _insert_symbol_with_bars(db, "SPY", "SPDR S&P 500", region="US", market_cap=500_000_000_000)
    _insert_symbol_with_bars(db, "GOOGL", "Alphabet", region="US", market_cap=2_000_000_000_000)

    assets = _build_top_assets("US", db, limit=10)
    syms = {a.symbol for a in assets}
    assert "GOOGL" in syms
    assert "SPY" not in syms
