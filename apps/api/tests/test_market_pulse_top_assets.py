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


# ── PR-2: candidate pool width ──────────────────────────────────────────────


def test_pool_contains_both_gainers_and_losers(db):
    """**The PR-2 production bug:** prior behavior returned the top-10 by
    CMF — a CMF-biased pool. The frontend's 'Top losers' sort then ordered
    only gainers and produced the 'least gainer' visual (AMD +3.99% as
    'top loser'). PR-2 widens the pool to top-50 by market_cap WITHOUT
    pre-sorting, so client-side 'losers' has actual losers to rank."""
    # Mix of gainers + losers, all with market_cap above the threshold
    _insert_symbol_with_directional_bars(db, "GAIN1", 500_000_000_000, "up")
    _insert_symbol_with_directional_bars(db, "GAIN2", 400_000_000_000, "up")
    _insert_symbol_with_directional_bars(db, "LOSS1", 600_000_000_000, "down")
    _insert_symbol_with_directional_bars(db, "LOSS2", 300_000_000_000, "down")

    assets = _build_top_assets("US", db)
    gainers = [a for a in assets if (a.perf_1d or 0) > 0]
    losers = [a for a in assets if (a.perf_1d or 0) < 0]

    assert len(gainers) >= 2, f"Expected gainers in pool, got {gainers}"
    assert len(losers) >= 2, (
        "Pool contains no losers — the 'Top losers' sort will surface "
        "least-gainers (the 2026-05-22 bug). Pool: "
        f"{[(a.symbol, a.perf_1d) for a in assets]}"
    )


def test_pool_ordered_by_market_cap_not_cmf(db):
    """The returned list must NOT be pre-sorted by CMF descending —
    that's what caused the gainer-bias. Order should be market_cap desc
    so the frontend can re-sort freely."""
    _insert_symbol_with_directional_bars(db, "BIG", 3_000_000_000_000, "down")  # huge cap, loser
    _insert_symbol_with_directional_bars(db, "SMALL", 100_000_000_000, "up")    # smaller, gainer

    assets = _build_top_assets("US", db)
    # First card must be the higher market_cap symbol regardless of CMF/perf
    assert assets[0].symbol == "BIG"


def test_pool_default_limit_is_wider_than_display_count(db):
    """`_build_top_assets` should return more than the 10 the frontend
    eventually displays — that's the whole point of the pool widening."""
    # Insert 15 symbols so we'd exceed the old default of 10
    for i in range(15):
        _insert_symbol_with_directional_bars(
            db, f"SYM{i:02d}", market_cap=(15 - i) * 100_000_000_000,
            trend="up" if i % 2 == 0 else "down",
        )
    assets = _build_top_assets("US", db)
    assert len(assets) >= 15, (
        f"Pool size {len(assets)} — expected the wider default (~50). "
        "The frontend slice handles the visible 10."
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
    # Only 5 days of bars — well short of CMF's 20-day window
    for i in range(5):
        d = today - timedelta(days=5 - i)
        db.add(PriceBar(
            symbol="IPO1", trading_date=d,
            open=100.0, high=101.0, low=99.0, close=100.0, adjusted_close=100.0,
            volume=1_000_000, dividend_amount=0.0, split_coefficient=1.0,
            source="test", fetched_at=datetime.utcnow(),
        ))
    db.commit()

    assets = _build_top_assets("US", db)
    syms = [a.symbol for a in assets]
    ipo = next((a for a in assets if a.symbol == "IPO1"), None)
    assert ipo is not None, f"Short-history asset dropped — pool: {syms}"
    assert ipo.cmf_20 is None  # Can't compute on 5 days; that's fine
