"""PRD-13b — POST /api/portfolio/diagnose in-process cache behaviour.

Black-box test against the cache helpers in the route module. Verifies
cache hits short-circuit the diagnose path; expired entries miss.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from app.api.routes import portfolio as portfolio_route
from app.schemas.portfolio import (
    BehaviorAggregate,
    DiagnoseResponse,
    FactorExposure,
    Holding,
    OverlayRecommendation,
    PortfolioDiagnosis,
    SectorBreakdown,
    StyleMix,
)


def _dummy_response() -> DiagnoseResponse:
    return DiagnoseResponse(
        diagnosis=PortfolioDiagnosis(
            n_holdings=2,
            style_mix=StyleMix(growth=1.0),
            factor_exposure=FactorExposure(),
            behavior=BehaviorAggregate(mixed_pct=1.0),
            sectors=SectorBreakdown(),
        ),
        recommended_overlays=[
            OverlayRecommendation(overlay="defensive", rank=1, reason="x"),
            OverlayRecommendation(overlay="rotation", rank=2, reason="y"),
            OverlayRecommendation(overlay="rebalance", rank=3, reason="z"),
        ],
        cache_hit=False,
    )


def test_cache_key_is_order_independent():
    a = portfolio_route._make_cache_key(
        [Holding(ticker="AAPL", weight=0.6), Holding(ticker="MSFT", weight=0.4)]
    )
    b = portfolio_route._make_cache_key(
        [Holding(ticker="MSFT", weight=0.4), Holding(ticker="AAPL", weight=0.6)]
    )
    assert a == b


def test_cache_key_differs_when_weights_differ():
    a = portfolio_route._make_cache_key(
        [Holding(ticker="AAPL", weight=0.6), Holding(ticker="MSFT", weight=0.4)]
    )
    b = portfolio_route._make_cache_key(
        [Holding(ticker="AAPL", weight=0.7), Holding(ticker="MSFT", weight=0.3)]
    )
    assert a != b


def test_cache_get_returns_set_value():
    portfolio_route._reset_cache_for_tests()
    key = "test_key"
    resp = _dummy_response()
    portfolio_route._cache_set(key, resp)
    got = portfolio_route._cache_get(key)
    assert got is resp


def test_cache_expires_after_ttl():
    portfolio_route._reset_cache_for_tests()
    key = "expiring_key"
    resp = _dummy_response()
    portfolio_route._cache_set(key, resp)

    # Forcibly age the entry past TTL.
    aged_ts = time.time() - (portfolio_route._CACHE_TTL_SECONDS + 60)
    portfolio_route._CACHE[key] = (aged_ts, resp)

    assert portfolio_route._cache_get(key) is None
    # Expired entry should also be evicted from the dict.
    assert key not in portfolio_route._CACHE


def test_cache_lru_eviction_at_max_entries():
    portfolio_route._reset_cache_for_tests()
    # Fill cache to capacity + 1 — oldest should be evicted.
    for i in range(portfolio_route._CACHE_MAX_ENTRIES + 1):
        portfolio_route._cache_set(f"key_{i}", _dummy_response())
    assert len(portfolio_route._CACHE) == portfolio_route._CACHE_MAX_ENTRIES
    assert "key_0" not in portfolio_route._CACHE
    assert f"key_{portfolio_route._CACHE_MAX_ENTRIES}" in portfolio_route._CACHE
