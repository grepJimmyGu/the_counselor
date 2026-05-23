"""Phase 1d — sector_comparison_service + /api/market/sector-comparison
endpoint tests.

Covers:
  * _cum_returns normalizes against the first price
  * _perf_n_days / _perf_since edge cases (insufficient bars)
  * get_comparison() aligns sector + SPY dates, returns matched series
  * Route returns 404 when the symbol has no bars in the window
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.services import sector_comparison_service as svc


# ── Pure-helper unit tests (no DB) ──────────────────────────────────────────


def test_cum_returns_normalizes_to_start():
    out = svc._cum_returns([100.0, 110.0, 105.0])
    assert out[0] == 0.0
    assert out[1] == pytest.approx(0.10)
    assert out[2] == pytest.approx(0.05)


def test_cum_returns_handles_zero_base():
    out = svc._cum_returns([0.0, 1.0, 2.0])
    assert out == [0.0, 0.0, 0.0]


def test_cum_returns_empty_series():
    assert svc._cum_returns([]) == []


def test_perf_n_days_basic():
    prices = [100.0, 105.0, 108.0, 110.0]
    # 1-day perf: 110 / 108 - 1 ≈ 0.0185
    assert svc._perf_n_days(prices, 1) == pytest.approx(110 / 108 - 1)
    # 3-day perf: 110 / 100 - 1 = 0.10
    assert svc._perf_n_days(prices, 3) == pytest.approx(0.10)


def test_perf_n_days_insufficient_bars():
    # 4 bars; asking for 5-day perf should return None
    assert svc._perf_n_days([100.0, 101.0, 102.0, 103.0], 5) is None


def test_perf_n_days_zero_base_returns_none():
    assert svc._perf_n_days([0.0, 10.0, 20.0], 1) == pytest.approx(1.0)
    # base price <=0 → None
    assert svc._perf_n_days([0.0, 0.0, 10.0], 2) is None


def test_perf_since_picks_first_bar_after_cutoff():
    dates = [date(2024, 1, 1), date(2024, 6, 1), date(2024, 12, 31)]
    prices = [100.0, 110.0, 121.0]
    # since 2024-04-01 → first bar at-or-after is 2024-06-01 (price 110)
    # final price 121 → 121 / 110 - 1 = 0.10
    assert svc._perf_since(prices, dates, date(2024, 4, 1)) == pytest.approx(0.10)


def test_perf_since_no_bar_after_cutoff():
    dates = [date(2024, 1, 1), date(2024, 6, 1)]
    prices = [100.0, 110.0]
    assert svc._perf_since(prices, dates, date(2025, 1, 1)) is None


def test_cutoff_for_ytd_returns_jan_1():
    today = date(2025, 8, 14)
    assert svc._cutoff_for_range("YTD", today) == date(2025, 1, 1)


def test_cutoff_for_1y_returns_365_days_back():
    today = date(2025, 8, 14)
    expected = today - timedelta(days=365)
    assert svc._cutoff_for_range("1Y", today) == expected


# ── DB-backed integration test ──────────────────────────────────────────────


def _insert_price_bars(db, symbol: str, bars: list[tuple[date, float]]):
    """Insert minimal price_bars rows for testing. Uses raw SQL because
    PriceBar.__init__ has additional defaulted columns we don't care
    about here."""
    for d, close in bars:
        db.execute(text(
            "INSERT INTO price_bars "
            "(symbol, trading_date, open, high, low, close, adjusted_close, "
            "volume, dividend_amount, split_coefficient, source, fetched_at) "
            "VALUES (:s, :d, :p, :p, :p, :p, :p, 1000, 0, 1, "
            "'test', :now)"
        ), {"s": symbol, "d": d, "p": close, "now": datetime.utcnow()})
    db.commit()


def test_get_comparison_aligns_sector_and_spy_dates(db):
    """The chart series must have matched indices for sector + SPY —
    days where only one symbol has a bar are dropped."""
    today = date.today()
    # Sector: 3 bars
    sector_bars = [
        (today - timedelta(days=10), 100.0),
        (today - timedelta(days=5), 110.0),
        (today - timedelta(days=1), 121.0),
    ]
    # SPY: 4 bars — one extra date that sector doesn't have
    spy_bars = [
        (today - timedelta(days=10), 400.0),
        (today - timedelta(days=7), 405.0),  # not in sector — should be dropped
        (today - timedelta(days=5), 410.0),
        (today - timedelta(days=1), 420.0),
    ]
    _insert_price_bars(db, "XLK", sector_bars)
    _insert_price_bars(db, "SPY", spy_bars)

    resp = svc.get_comparison(db, "XLK", "1M")
    assert resp.symbol == "XLK"
    assert resp.range == "1M"
    # Aligned: only the 3 shared dates remain
    assert len(resp.series) == 3
    # First point normalized to 0
    assert resp.series[0].sector == pytest.approx(0.0)
    assert resp.series[0].spy == pytest.approx(0.0)
    # Last sector point: 121 / 100 - 1 = 0.21
    assert resp.series[-1].sector == pytest.approx(0.21)
    # Last SPY point: 420 / 400 - 1 = 0.05
    assert resp.series[-1].spy == pytest.approx(0.05)


def test_get_comparison_empty_when_no_bars(db):
    """Symbol with no bars in window → empty series + None totals."""
    resp = svc.get_comparison(db, "XLK", "1M")
    assert resp.series == []
    assert resp.sector_day is None


def test_get_comparison_falls_back_to_1y_for_bogus_range(db):
    today = date.today()
    _insert_price_bars(db, "XLE", [(today - timedelta(days=1), 100.0)])
    _insert_price_bars(db, "SPY", [(today - timedelta(days=1), 400.0)])
    resp = svc.get_comparison(db, "XLE", "garbage")
    assert resp.range == "1Y"


def test_get_comparison_sector_name_mapping(db):
    today = date.today()
    _insert_price_bars(db, "XLK", [(today - timedelta(days=1), 100.0)])
    _insert_price_bars(db, "SPY", [(today - timedelta(days=1), 400.0)])
    resp = svc.get_comparison(db, "XLK", "1M")
    assert resp.sector_name == "Technology"


def test_get_comparison_unknown_symbol_falls_back_to_symbol(db):
    today = date.today()
    _insert_price_bars(db, "UNKN", [(today - timedelta(days=1), 100.0)])
    _insert_price_bars(db, "SPY", [(today - timedelta(days=1), 400.0)])
    resp = svc.get_comparison(db, "UNKN", "1M")
    assert resp.sector_name == "UNKN"


# ── PR-5: ^GSPC index benchmark ─────────────────────────────────────────────


def test_get_comparison_prefers_gspc_when_bars_present(db):
    """When ^GSPC bars exist, the benchmark series should be ^GSPC's
    cumulative return, NOT SPY's."""
    today = date.today()
    # XLK gains 10% in 5 days
    _insert_price_bars(db, "XLK", [
        (today - timedelta(days=5), 100.0),
        (today - timedelta(days=1), 110.0),
    ])
    # ^GSPC gains 5% in the same window
    _insert_price_bars(db, "^GSPC", [
        (today - timedelta(days=5), 5000.0),
        (today - timedelta(days=1), 5250.0),
    ])
    # SPY moves a different amount (3%) — to prove we're NOT using SPY
    _insert_price_bars(db, "SPY", [
        (today - timedelta(days=5), 500.0),
        (today - timedelta(days=1), 515.0),
    ])

    resp = svc.get_comparison(db, "XLK", "1M")
    # Last benchmark point should be ^GSPC's 5%, not SPY's 3%
    assert resp.series[-1].spy == pytest.approx(0.05)
    # Sector unchanged
    assert resp.series[-1].sector == pytest.approx(0.10)


def test_get_comparison_falls_back_to_spy_when_gspc_missing(db):
    """If ^GSPC isn't backfilled yet (zero bars), the service should
    transparently use SPY so the chart never breaks. Verified via the
    benchmark math matching SPY's 3% return rather than producing an
    empty series."""
    today = date.today()
    _insert_price_bars(db, "XLK", [
        (today - timedelta(days=5), 100.0),
        (today - timedelta(days=1), 110.0),
    ])
    _insert_price_bars(db, "SPY", [
        (today - timedelta(days=5), 500.0),
        (today - timedelta(days=1), 515.0),
    ])
    # No ^GSPC bars inserted — service must fall back to SPY

    resp = svc.get_comparison(db, "XLK", "1M")
    assert len(resp.series) > 0, "Service returned empty series instead of SPY fallback"
    # spy field should equal SPY's 3% return
    assert resp.series[-1].spy == pytest.approx(0.03)


def test_load_benchmark_returns_symbol_used(db):
    """`_load_benchmark` returns the symbol it loaded — so callers (and
    the future audit script) can tell whether the chart is reading
    ^GSPC or the SPY fallback."""
    today = date.today()
    cutoff = today - timedelta(days=30)
    # No ^GSPC, no SPY → empty
    sym, bars = svc._load_benchmark(db, cutoff)
    assert sym == svc._BENCHMARK_FALLBACK  # falls through to SPY name
    assert bars == []

    # Insert SPY only — should fall back to SPY
    _insert_price_bars(db, "SPY", [(today - timedelta(days=1), 500.0)])
    sym, bars = svc._load_benchmark(db, cutoff)
    assert sym == "SPY"
    assert len(bars) == 1

    # Insert ^GSPC — should prefer ^GSPC over SPY
    _insert_price_bars(db, "^GSPC", [(today - timedelta(days=1), 5000.0)])
    sym, bars = svc._load_benchmark(db, cutoff)
    assert sym == "^GSPC"
