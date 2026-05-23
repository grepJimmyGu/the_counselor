"""Regression tests for `_build_top_assets` — Market Pulse Top Movers
candidate pool.

**2026-05-23 redesign:** the US universe is now `SP500_TICKERS` — the
full S&P 500 constituent list. The previous region-and-market_cap
heuristic is gone. All region / suffix / ETF exclusions are now
*implicit* (the SPX universe contains no CN listings, no ETFs, no
foreign ADRs).

Tests below cover:
  * The SP500 universe filter is the only thing that matters now
  * Symbols outside SP500 — even with healthy price_bars + market_cap —
    don't appear in the pool
  * Tests inject `universe_override={...fake symbols...}` to express
    pool semantics (gainers/losers, ordering) without depending on a
    specific SPX member surviving the next index reconstitution
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


def test_us_top_assets_filters_to_sp500_universe(db):
    """Symbols outside `SP500_TICKERS` must not appear in US Top Movers
    even with healthy price_bars + market_cap. NVDA (SPX member) passes;
    a fictional non-SPX name with the same shape does not."""
    _insert_symbol_with_bars(db, "NVDA", "NVIDIA", region="US", market_cap=3_000_000_000_000)
    _insert_symbol_with_bars(db, "NONSPX1", "Random Co", region="US", market_cap=200_000_000_000)

    assets = _build_top_assets("US", db, limit=600)
    syms = {a.symbol for a in assets}
    assert "NVDA" in syms
    assert "NONSPX1" not in syms, "Non-SP500 symbol leaked into Top Movers"


def test_us_top_assets_excludes_cn_a_share_implicitly_via_sp500(db):
    """The 2026-05-22 `510300.SH` production bug: a CN A-share with NULL
    region snuck into the US Top Movers. With the SP500 filter, this is
    impossible — `.SH` symbols can never be in the SPX universe.

    Verified by inserting the exact production-bug symbol shape and
    asserting it's absent from the result. No region check needed."""
    _insert_symbol_with_bars(db, "AAPL", "Apple Inc.", region="US", market_cap=3_000_000_000_000)
    _insert_symbol_with_bars(db, "510300.SH", "Huatai PineBridge", region=None, market_cap=10_000_000_000)

    assets = _build_top_assets("US", db, limit=600)
    syms = {a.symbol for a in assets}
    assert "AAPL" in syms
    assert "510300.SH" not in syms, "510300.SH leaked despite SP500 filter — regression!"


def test_us_top_assets_excludes_etf_implicitly_via_sp500(db):
    """SPY / QQQ / sector ETFs aren't constituents of their underlying
    indices — the SP500 filter excludes them naturally."""
    _insert_symbol_with_bars(db, "SPY", "SPDR S&P 500", region="US", market_cap=500_000_000_000)
    _insert_symbol_with_bars(db, "GOOGL", "Alphabet", region="US", market_cap=2_000_000_000_000)

    assets = _build_top_assets("US", db, limit=600)
    syms = {a.symbol for a in assets}
    assert "GOOGL" in syms
    assert "SPY" not in syms


def test_us_top_assets_pool_size_reflects_full_sp500(db):
    """Pool returns up to ~500 names, not a heuristic top-10 / top-50.
    Insert 60 SPX members + verify they all flow through."""
    from app.data.sp500_tickers import SP500_TICKERS
    sample = list(SP500_TICKERS)[:60]
    for i, sym in enumerate(sample):
        _insert_symbol_with_bars(db, sym, sym, region="US", market_cap=(60 - i) * 100_000_000_000)

    assets = _build_top_assets("US", db)
    assert len(assets) == 60, (
        f"Pool size {len(assets)} — expected all 60 SPX members. "
        "The old market_cap-LIMIT-50 cap should be gone."
    )


def _insert_symbol_with_directional_bars(
    db, symbol: str, market_cap: float, trend: str
) -> None:
    """Insert a symbol with bars that produce a clear positive / negative
    perf_1d. `trend` ∈ {"up", "down"} controls last-day movement."""
    db.add(SymbolCache(
        symbol=symbol, name=symbol, region="US",
        market_cap=market_cap, market_cap_category="large", is_active=True,
    ))
    today = date.today()
    # 25 days of flat ~100 then a directional jump on the last day.
    for i in range(24):
        d = today - timedelta(days=25 - i)
        db.add(PriceBar(
            symbol=symbol, trading_date=d,
            open=100.0, high=100.5, low=99.5, close=100.0, adjusted_close=100.0,
            volume=1_000_000, dividend_amount=0.0, split_coefficient=1.0,
            source="test", fetched_at=datetime.utcnow(),
        ))
    # Last bar: ±5% move
    last_close = 105.0 if trend == "up" else 95.0
    db.add(PriceBar(
        symbol=symbol, trading_date=today - timedelta(days=1),
        open=100.0, high=max(last_close, 100.5), low=min(last_close, 99.5),
        close=last_close, adjusted_close=last_close,
        volume=1_000_000, dividend_amount=0.0, split_coefficient=1.0,
        source="test", fetched_at=datetime.utcnow(),
    ))
    db.commit()


# ── PR-2 / PR-8: candidate pool shape ──────────────────────────────────────
#
# These tests use `universe_override` to inject a small fake set in place
# of `SP500_TICKERS`, so the assertions about gainers/losers/pool-size
# stay stable even as the real SPX index reconstitutes over time.


_FAKE_UNIVERSE = {"GAIN1", "GAIN2", "LOSS1", "LOSS2", "BIG", "SMALL", "IPO1"} | {
    f"SYM{i:02d}" for i in range(15)
}


def test_pool_contains_both_gainers_and_losers(db):
    """**The PR-2 production bug:** prior behavior returned the top-10 by
    CMF — a CMF-biased pool. The frontend's 'Top losers' sort then ordered
    only gainers and produced the 'least gainer' visual (AMD +3.99% as
    'top loser'). PR-2 widens the pool to draw from the full SP500
    universe WITHOUT pre-sorting, so client-side 'losers' has actual
    losers to rank."""
    _insert_symbol_with_directional_bars(db, "GAIN1", 500_000_000_000, "up")
    _insert_symbol_with_directional_bars(db, "GAIN2", 400_000_000_000, "up")
    _insert_symbol_with_directional_bars(db, "LOSS1", 600_000_000_000, "down")
    _insert_symbol_with_directional_bars(db, "LOSS2", 300_000_000_000, "down")

    assets = _build_top_assets("US", db, universe_override=_FAKE_UNIVERSE)
    gainers = [a for a in assets if (a.perf_1d or 0) > 0]
    losers = [a for a in assets if (a.perf_1d or 0) < 0]

    assert len(gainers) >= 2
    assert len(losers) >= 2, (
        "Pool contains no losers — the 'Top losers' sort will surface "
        f"least-gainers. Pool: {[(a.symbol, a.perf_1d) for a in assets]}"
    )


def test_pool_ordered_by_market_cap_not_cmf(db):
    """The returned list must NOT be pre-sorted by CMF descending —
    that's what caused the gainer-bias. Order is market_cap desc so the
    frontend can re-sort freely."""
    _insert_symbol_with_directional_bars(db, "BIG", 3_000_000_000_000, "down")  # huge cap, loser
    _insert_symbol_with_directional_bars(db, "SMALL", 100_000_000_000, "up")    # smaller, gainer

    assets = _build_top_assets("US", db, universe_override=_FAKE_UNIVERSE)
    assert assets[0].symbol == "BIG"


def test_pool_default_limit_is_wider_than_display_count(db):
    """`_build_top_assets` should return all SPX members the DB has bars
    for — frontend's `.slice(0, 10)` handles the visible cards."""
    for i in range(15):
        _insert_symbol_with_directional_bars(
            db, f"SYM{i:02d}", market_cap=(15 - i) * 100_000_000_000,
            trend="up" if i % 2 == 0 else "down",
        )
    assets = _build_top_assets("US", db, universe_override=_FAKE_UNIVERSE)
    assert len(assets) >= 15, (
        f"Pool size {len(assets)} — expected all 15 inserted members"
    )


def test_pool_includes_short_history_assets(db):
    """Stocks with <20 days of history (CMF cannot be computed) should
    still appear in the pool with `cmf_20=None`. Old behavior dropped
    them entirely."""
    db.add(SymbolCache(
        symbol="IPO1", name="Recent IPO", region="US",
        market_cap=50_000_000_000, market_cap_category="large", is_active=True,
    ))
    today = date.today()
    for i in range(5):
        d = today - timedelta(days=5 - i)
        db.add(PriceBar(
            symbol="IPO1", trading_date=d,
            open=100.0, high=101.0, low=99.0, close=100.0, adjusted_close=100.0,
            volume=1_000_000, dividend_amount=0.0, split_coefficient=1.0,
            source="test", fetched_at=datetime.utcnow(),
        ))
    db.commit()

    assets = _build_top_assets("US", db, universe_override=_FAKE_UNIVERSE)
    ipo = next((a for a in assets if a.symbol == "IPO1"), None)
    assert ipo is not None, f"Short-history asset dropped — pool: {[a.symbol for a in assets]}"
    assert ipo.cmf_20 is None
