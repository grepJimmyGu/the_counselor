"""PRD-13b — PortfolioDiagnosisService unit tests.

Mocks PriceDataService + FundamentalService so no DB / network calls
happen. Asserts the diagnosis payload shape and the recommendation
ranking logic.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from app.schemas.fundamental import CompanyProfile, KeyMetrics
from app.schemas.portfolio import Holding
from app.services.portfolio_diagnosis_service import PortfolioDiagnosisService


def _profile(symbol: str, **kwargs) -> CompanyProfile:
    return CompanyProfile(
        symbol=symbol,
        name=symbol,
        sector=kwargs.get("sector", "Technology"),
        beta=kwargs.get("beta", 1.0),
        market_cap=kwargs.get("market_cap", 1e11),
        pe_ratio=kwargs.get("pe_ratio", 25.0),
    )


def _metrics(symbol: str, **kwargs) -> KeyMetrics:
    return KeyMetrics(
        symbol=symbol,
        pe_ratio=kwargs.get("pe_ratio", 25.0),
        roe=kwargs.get("roe", 0.20),
        free_cash_flow_yield=kwargs.get("free_cash_flow_yield", 0.05),
    )


def _price_frame(symbol: str, n_days: int = 1500, drift: float = 0.0004, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=date.today(), periods=n_days, freq="B")
    rets = rng.normal(drift, 0.015, n_days)
    prices = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame({"adjusted_close": prices}, index=dates)


def _build_service(profiles_by_sym=None, metrics_by_sym=None, frames_by_sym=None):
    """Construct a PortfolioDiagnosisService with mocked composed services."""
    fundamental = MagicMock()
    profiles_by_sym = profiles_by_sym or {}
    metrics_by_sym = metrics_by_sym or {}
    fundamental.get_profile = AsyncMock(side_effect=lambda db, s: profiles_by_sym.get(s, _profile(s)))
    fundamental.get_key_metrics = AsyncMock(side_effect=lambda db, s: metrics_by_sym.get(s, _metrics(s)))

    prices = MagicMock()
    frames_by_sym = frames_by_sym or {}

    async def _gpf(db, symbol, start_date, end_date, lookback_days=0):
        return frames_by_sym.get(symbol, _price_frame(symbol))

    prices.get_price_frame = _gpf
    return PortfolioDiagnosisService(fundamental_service=fundamental, price_data_service=prices)


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnosis_shape_and_style_mix_sums_to_1():
    svc = _build_service()
    holdings = [
        Holding(ticker="AAPL", weight=0.4),
        Holding(ticker="MSFT", weight=0.4),
        Holding(ticker="JNJ", weight=0.2),  # defensive (Healthcare)
    ]
    db = MagicMock()
    diag = await svc.diagnose(db, holdings)

    assert diag.n_holdings == 3

    # Style mix should sum to 1.0 within numerical noise.
    mix = diag.style_mix
    total = (
        mix.growth + mix.value + mix.defensive + mix.commodity
        + mix.macro_sensitive + mix.unclassified_weight
    )
    assert abs(total - 1.0) < 1e-9

    # Behavior aggregate sums to ~1.0 too.
    b = diag.behavior
    assert abs((b.trending_pct + b.mean_reverting_pct + b.mixed_pct) - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_factor_exposure_filled_when_data_present():
    svc = _build_service()
    holdings = [
        Holding(ticker="A", weight=0.5),
        Holding(ticker="B", weight=0.5),
    ]
    db = MagicMock()
    diag = await svc.diagnose(db, holdings)
    # All 6 factor fields populated since profiles + metrics + prices exist.
    fe = diag.factor_exposure
    assert fe.size is not None
    assert fe.value is not None
    assert fe.momentum is not None
    assert fe.quality is not None
    assert fe.low_vol is not None
    assert fe.beta_to_spy is not None


@pytest.mark.asyncio
async def test_diagnosis_classifies_defensive_for_jnj_sector():
    # Override JNJ profile to have Healthcare sector → defensive bucket.
    profiles = {
        "JNJ": _profile("JNJ", sector="Healthcare", beta=0.6),
    }
    svc = _build_service(profiles_by_sym=profiles)
    holdings = [Holding(ticker="JNJ", weight=1.0)]
    db = MagicMock()
    diag = await svc.diagnose(db, holdings)
    assert diag.style_mix.defensive == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_recommend_overlays_returns_three_ranked():
    svc = _build_service()
    holdings = [
        Holding(ticker="A", weight=0.3),
        Holding(ticker="B", weight=0.3),
        Holding(ticker="C", weight=0.2),
        Holding(ticker="D", weight=0.2),
    ]
    db = MagicMock()
    diag = await svc.diagnose(db, holdings)
    recs = svc.recommend_overlays(diag)
    assert len(recs) == 3
    assert sorted(r.rank for r in recs) == [1, 2, 3]
    assert sorted(r.overlay for r in recs) == ["defensive", "rebalance", "rotation"]


@pytest.mark.asyncio
async def test_empty_holdings_raises():
    svc = _build_service()
    db = MagicMock()
    with pytest.raises(ValueError):
        await svc.diagnose(db, [])


@pytest.mark.asyncio
async def test_resilient_to_missing_fundamentals():
    """If FundamentalService returns None for a ticker, the diagnosis
    still produces a valid payload — unclassified bucket absorbs the
    weight."""
    fundamental = MagicMock()
    fundamental.get_profile = AsyncMock(return_value=None)
    fundamental.get_key_metrics = AsyncMock(return_value=None)
    prices = MagicMock()

    async def _gpf(db, symbol, start_date, end_date, lookback_days=0):
        return _price_frame(symbol)

    prices.get_price_frame = _gpf

    svc = PortfolioDiagnosisService(fundamental_service=fundamental, price_data_service=prices)
    holdings = [Holding(ticker="UNKNOWN", weight=1.0)]
    db = MagicMock()
    diag = await svc.diagnose(db, holdings)
    # The "UNKNOWN" ticker has no profile → unclassified.
    assert diag.style_mix.unclassified_weight == pytest.approx(1.0)
