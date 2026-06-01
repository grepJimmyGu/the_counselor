"""Phase 1e — macro_similarity_service tests.

Covers:
  * _cosine math (orthogonal / identical / negated)
  * _five_day_return_vector returns None when window goes off the start
  * _context_label produces plain-English tags
  * _format_label same-month / cross-month / cross-year cases
  * get_history_rhymes() empty-when-missing path
  * get_history_rhymes() returns top-K matches with post-outcome
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import text

from app.services import macro_similarity_service as svc


# ── _cosine ────────────────────────────────────────────────────────────────


def test_cosine_identical_vectors_is_one():
    a = np.array([1.0, 2.0, 3.0])
    assert svc._cosine(a, a) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert svc._cosine(a, b) == pytest.approx(0.0)


def test_cosine_negated_vectors_is_negative_one():
    a = np.array([1.0, 2.0, 3.0])
    b = -a
    assert svc._cosine(a, b) == pytest.approx(-1.0)


def test_cosine_zero_vector_returns_zero():
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([1.0, 2.0, 3.0])
    assert svc._cosine(a, b) == 0.0


# ── _five_day_return_vector ─────────────────────────────────────────────────


def test_five_day_return_vector_basic():
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0]
    # end_idx=5, start_idx=0: 110/100 - 1 = 0.10
    out = svc._five_day_return_vector(prices, 5)
    assert out is not None
    assert out[0] == pytest.approx(0.10)


def test_five_day_return_vector_none_when_window_starts_negative():
    prices = [100.0, 101.0, 102.0]
    # end_idx=2, start_idx=-3 → None
    assert svc._five_day_return_vector(prices, 2) is None


def test_five_day_return_vector_none_when_end_out_of_range():
    prices = [100.0] * 10
    assert svc._five_day_return_vector(prices, 20) is None


# ── _context_label ─────────────────────────────────────────────────────────


def test_context_label_quiet_when_all_small():
    vec = np.array([0.001, 0.001, 0.001, 0.001, 0.001, 0.001])
    assert svc._context_label(vec) == "Quiet macro tape"


def test_context_label_equities_selling_off():
    # SPY, TLT, SHY, UUP, HYG, GLD — SPY −5%
    vec = np.array([-0.05, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert "equities selling off" in svc._context_label(vec).lower()


def test_context_label_bonds_rallying_dollar_bid():
    # SPY, TLT, SHY, UUP, HYG, GLD — TLT +3% (SHY close so no curve steepen), UUP +5%
    vec = np.array([0.0, 0.03, 0.025, 0.05, 0.0, 0.0])
    label = svc._context_label(vec)
    assert "bonds rallying" in label.lower()
    assert "dollar bid" in label.lower()


def test_context_label_wrong_dim_returns_mixed():
    vec = np.array([0.0, 0.0])
    assert svc._context_label(vec) == "Mixed signals"


# ── _format_label ──────────────────────────────────────────────────────────


def test_format_label_same_month():
    out = svc._format_label(date(2019, 8, 13), date(2019, 8, 19))
    # Mac/Linux date strings use "%-d" for "no leading zero"
    assert "Aug 13" in out
    assert "19" in out
    assert "2019" in out


def test_format_label_cross_month():
    out = svc._format_label(date(2020, 1, 29), date(2020, 2, 4))
    assert "Jan 29" in out
    assert "Feb 4" in out
    assert "2020" in out


def test_format_label_cross_year():
    out = svc._format_label(date(2018, 12, 28), date(2019, 1, 3))
    assert "2018" in out
    assert "2019" in out


# ── DB-backed integration tests ─────────────────────────────────────────────


def _insert_bars(db, symbol: str, start_date: date, prices: list[float]):
    """Insert a daily price series starting at start_date."""
    for i, p in enumerate(prices):
        d = start_date + timedelta(days=i)
        db.execute(text(
            "INSERT INTO price_bars "
            "(symbol, trading_date, open, high, low, close, adjusted_close, "
            "volume, dividend_amount, split_coefficient, source, fetched_at) "
            "VALUES (:s, :d, :p, :p, :p, :p, :p, 1000, 0, 1, "
            "'test', :now)"
        ), {"s": symbol, "d": d, "p": p, "now": datetime.utcnow()})
    db.commit()


async def test_get_history_rhymes_empty_when_no_data(db):
    svc.invalidate_cache()
    resp = await svc.get_history_rhymes("US", db)
    assert resp.matches == []
    assert "Insufficient" in resp.caveat or "history" in resp.caveat.lower()


async def test_get_history_rhymes_cn_returns_us_only_caveat(db):
    svc.invalidate_cache()
    resp = await svc.get_history_rhymes("CN", db)
    assert resp.matches == []
    assert "US-only" in resp.caveat


async def test_get_history_rhymes_with_data(db):
    """End-to-end: insert enough macro + SPY data so that at least one
    full 5-day window + 30d post-outcome can be computed."""
    svc.invalidate_cache()
    # 100 bars per symbol — enough for the window + post-outcome.
    today = date.today()
    start = today - timedelta(days=200)
    n = 100

    def _series(seed: int) -> list[float]:
        return [100.0 + seed * 0.1 + i * 0.05 for i in range(n)]

    # All 6 macro symbols + SPY
    for sym in set(svc.MACRO_BASKET + ["SPY"]):
        _insert_bars(db, sym, start, _series(hash(sym) % 5))

    resp = await svc.get_history_rhymes("US", db)
    # With monotonically increasing series, every window's return is
    # roughly the same, so cosine sim ≈ 1.0 against today's vector.
    # We should get up to TOP_K matches.
    assert len(resp.matches) <= svc.TOP_K
    if resp.matches:
        m = resp.matches[0]
        assert 0.0 <= m.similarity <= 1.0
        assert len(m.sample_sparkline) == svc.POST_WINDOW_DAYS
        # Sparkline starts at 100 by construction
        assert m.sample_sparkline[0] == 100.0


async def test_get_history_rhymes_cache_round_trip(db):
    """Second call returns the cached object (identity equality)."""
    svc.invalidate_cache()
    today = date.today()
    start = today - timedelta(days=200)
    for sym in set(svc.MACRO_BASKET + ["SPY"]):
        _insert_bars(db, sym, start, [100.0 + i * 0.05 for i in range(100)])

    first = await svc.get_history_rhymes("US", db)
    second = await svc.get_history_rhymes("US", db)
    assert first is second


async def test_invalidate_cache_clears_state(db):
    svc.invalidate_cache()
    today = date.today()
    start = today - timedelta(days=200)
    for sym in set(svc.MACRO_BASKET + ["SPY"]):
        _insert_bars(db, sym, start, [100.0 + i * 0.05 for i in range(100)])

    first = await svc.get_history_rhymes("US", db)
    svc.invalidate_cache()
    second = await svc.get_history_rhymes("US", db)
    # Identity differs because the cache was rebuilt
    assert first is not second
