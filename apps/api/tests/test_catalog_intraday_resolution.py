"""PRD-16c-4 — Catalog intraday resolution metadata.

Verifies the PRD-16a catalog correctly identifies which primitives
support intraday execution. This is the editorial gate: a new
primitive that should support intraday must be added to
`_INTRADAY_ELIGIBLE_IDS` in `signal_primitives.py`.
"""
from __future__ import annotations

from app.data.signal_primitives import (
    SIGNAL_PRIMITIVES,
    _INTRADAY_ELIGIBLE_IDS,
)


def _by_id(primitive_id: str):
    for p in SIGNAL_PRIMITIVES:
        if p.id == primitive_id:
            return p
    return None


def test_core_trend_primitives_support_intraday() -> None:
    """SMA, EMA, MACD — the SpaceX-style ladder's natural building
    blocks — must be intraday-eligible."""
    for pid in ("sma", "ema", "macd"):
        p = _by_id(pid)
        assert p is not None, f"primitive {pid!r} not found"
        assert "intraday" in p.resolution, f"{pid} should support intraday"


def test_rsi_and_bollinger_support_intraday() -> None:
    for pid in ("rsi", "bbands", "stoch"):
        p = _by_id(pid)
        assert p is not None
        assert "intraday" in p.resolution


def test_vwap_supports_intraday() -> None:
    """VWAP is canonical intraday; absent intraday support it's broken."""
    p = _by_id("vwap")
    assert p is not None
    assert "intraday" in p.resolution


def test_atr_supports_intraday() -> None:
    """ATR is the SpaceX-style stop-distance source."""
    p = _by_id("atr")
    assert p is not None
    assert "intraday" in p.resolution


def test_fundamental_primitives_stay_daily_only() -> None:
    """Fundamentals don't change tick-to-tick; intraday support would
    be misleading."""
    for pid in ("fcf_yield", "book_to_market", "f_score", "buyback_yield_ttm"):
        p = _by_id(pid)
        assert p is not None, f"primitive {pid!r} not found"
        assert p.resolution == ["daily"], (
            f"{pid} should NOT support intraday (fundamental data is daily-cadence)"
        )


def test_sentiment_primitives_stay_daily_only() -> None:
    for pid in ("sentiment_score", "insider_net_buy", "analyst_rating_change"):
        p = _by_id(pid)
        assert p is not None
        assert p.resolution == ["daily"]


def test_cross_sectional_primitives_stay_daily_only() -> None:
    """Ranking primitives need a fixed universe snapshot — daily only."""
    for pid in ("rank_return_6m", "rank_composite_score", "sector_rotation_rank"):
        p = _by_id(pid)
        assert p is not None
        assert p.resolution == ["daily"]


def test_daily_listed_first_in_resolution_order() -> None:
    """Frontend ETag-caches the catalog response (PRD-16a-1 — content
    hash). Stable ordering means a no-op deploy doesn't invalidate
    that cache. Daily must come first."""
    for p in SIGNAL_PRIMITIVES:
        if "intraday" in p.resolution:
            assert p.resolution[0] == "daily", (
                f"{p.id} has intraday before daily — would invalidate the "
                "frontend ETag cache on no-op deploys"
            )


def test_intraday_eligible_ids_match_actual_catalog() -> None:
    """Every id in `_INTRADAY_ELIGIBLE_IDS` must correspond to a real
    primitive in the catalog. Catches typos / removed primitives."""
    actual_ids = {p.id for p in SIGNAL_PRIMITIVES}
    for pid in _INTRADAY_ELIGIBLE_IDS:
        assert pid in actual_ids, (
            f"_INTRADAY_ELIGIBLE_IDS has {pid!r} but no such primitive in catalog"
        )


def test_intraday_count_is_within_expected_range() -> None:
    """Sanity check — ~30-50 intraday-eligible primitives is the
    expected order of magnitude. If this snaps below 20 or above 100,
    something has shifted (large catalog mutation or accidental wipe)."""
    intraday_count = sum(
        1 for p in SIGNAL_PRIMITIVES if "intraday" in p.resolution
    )
    assert 20 <= intraday_count <= 100, (
        f"intraday_count={intraday_count} outside expected 20-100 range"
    )
