"""Unit tests for the Asset Behavior Fingerprint service (Module 2, 2026-05-26).

Service-only — no DB, no live data dependency. We synthesise price series
with known properties (geometric drift, mean-reverting random walk, recent
shock) so each acceptance criterion has a deterministic oracle.

Test areas (mirroring the Module 2 spec):
  1. asset type classification (broad / sector / commodity / fallback)
  2. realized volatility calculation
  3. max drawdown calculation
  4. data quality classification
  5. current regime classification (trending / range_bound / volatile / mixed)
  6. insufficient data behavior — never crash, return clear payload
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from app.services.asset_behavior_service import (
    AssetBehaviorFingerprint,
    classify_asset_type,
    classify_current_regime,
    classify_data_quality,
    compute_asset_behavior_fingerprint,
    compute_max_drawdown,
    compute_realized_vol,
)

# ── Synthetic price-series helpers ──────────────────────────────────────────


def _date_index(n: int) -> pd.DatetimeIndex:
    """Generate `n` consecutive trading days ending today (weekends ignored —
    the service treats every row as one trading day)."""
    end = datetime.utcnow().date()
    return pd.to_datetime([end - timedelta(days=n - 1 - i) for i in range(n)])


def _trending_prices(
    n: int = 1500, mu: float = 0.0008, sigma: float = 0.01, start: float = 100.0,
    seed: int = 0,
) -> pd.Series:
    """Geometric Brownian-motion-ish: small positive drift, modest stdev.
    With mu=0.0008 (~20% annual) and sigma=0.01 the series spends most of its
    life above the 200-day MA — a textbook trending fingerprint."""
    rng = np.random.default_rng(seed)
    increments = rng.normal(mu, sigma, size=n)
    prices = start * np.exp(np.cumsum(increments))
    return pd.Series(prices, index=_date_index(n))


def _mean_reverting_prices(
    n: int = 1500, kappa: float = 0.06, theta: float = 100.0,
    sigma: float = 1.2, seed: int = 1,
) -> pd.Series:
    """Ornstein-Uhlenbeck-ish: pulls back toward `theta` so |z|>1.5 events
    revert quickly. `kappa` is the pull-back strength."""
    rng = np.random.default_rng(seed)
    prices = np.empty(n)
    prices[0] = theta
    for i in range(1, n):
        prices[i] = prices[i - 1] + kappa * (theta - prices[i - 1]) + rng.normal(0, sigma)
        # Floor at a tiny positive value so pct_change never divides by 0.
        if prices[i] <= 0:
            prices[i] = 0.01
    return pd.Series(prices, index=_date_index(n))


def _volatile_prices(n: int = 1500, sigma: float = 0.05, seed: int = 2) -> pd.Series:
    """Centred GBM with very large sigma — annualised vol will land ~80%."""
    rng = np.random.default_rng(seed)
    increments = rng.normal(0.0, sigma, size=n)
    prices = 100.0 * np.exp(np.cumsum(increments))
    return pd.Series(prices, index=_date_index(n))


# ── 1. Asset type classification ────────────────────────────────────────────


def test_classify_asset_type_broad_etf():
    for s in ("SPY", "QQQ", "VTI", "IWM", "DIA"):
        assert classify_asset_type(s) == "broad_etf"
    assert classify_asset_type("spy") == "broad_etf"  # case-insensitive


def test_classify_asset_type_sector_etf():
    for s in ("XLE", "XLF", "XLK", "XLV", "XLY", "XLP", "XLU", "XLI", "XLB", "XLRE", "XLC"):
        assert classify_asset_type(s) == "sector_etf"


def test_classify_asset_type_commodity_etf():
    for s in ("GLD", "SLV", "USO", "UNG", "DBC", "DBA", "DBB", "CPER"):
        assert classify_asset_type(s) == "commodity_etf"


def test_classify_asset_type_defaults_to_single_stock():
    for s in ("AAPL", "NVDA", "KO", "BRK.B"):
        assert classify_asset_type(s) == "single_stock"


def test_classify_asset_type_empty_or_invalid():
    assert classify_asset_type("") == "unknown"
    assert classify_asset_type(None) == "unknown"  # type: ignore[arg-type]
    assert classify_asset_type("   ") == "unknown"


# ── 2. Realized volatility ──────────────────────────────────────────────────


def test_realized_vol_returns_none_when_too_few_points():
    returns = pd.Series([0.001, 0.002, -0.001])
    assert compute_realized_vol(returns, 252) is None


def test_realized_vol_matches_analytical_value():
    """A series of daily returns with stdev=0.01 should produce annualised
    vol ≈ 0.01 * sqrt(252) ≈ 0.1587."""
    rng = np.random.default_rng(42)
    returns = pd.Series(rng.normal(0.0, 0.01, size=500))
    vol = compute_realized_vol(returns, 252)
    assert vol is not None
    expected = 0.01 * math.sqrt(252)
    # Tolerate ±15% from random-sample noise.
    assert abs(vol - expected) / expected < 0.15


def test_realized_vol_uses_only_last_periods():
    """If the tail differs from the head, vol should reflect the tail."""
    quiet = [0.0001] * 252
    noisy_tail = list(np.random.default_rng(7).normal(0.0, 0.05, size=252))
    returns = pd.Series(quiet + noisy_tail)
    tail_vol = compute_realized_vol(returns, 252)
    assert tail_vol is not None
    assert tail_vol > 0.5  # ≈ 0.05 * sqrt(252) ≈ 0.79 — far above the head's near-zero vol


# ── 3. Max drawdown ─────────────────────────────────────────────────────────


def test_max_drawdown_known_series():
    # 100 → 120 (peak) → 60 (trough). Max DD = (60-120)/120 = -0.5.
    prices = pd.Series(
        [100, 110, 120, 100, 80, 60, 70, 80, 90, 100,
         100, 110, 120, 100, 80, 60, 70, 80, 90, 100, 100],
        index=_date_index(21),
    )
    dd = compute_max_drawdown(prices)
    assert dd is not None
    assert abs(dd - (-0.5)) < 1e-9


def test_max_drawdown_no_decline_is_zero():
    prices = pd.Series([100 + i for i in range(30)], index=_date_index(30))
    dd = compute_max_drawdown(prices)
    assert dd is not None
    assert dd == 0.0


def test_max_drawdown_returns_none_for_tiny_input():
    prices = pd.Series([100, 99, 101])
    assert compute_max_drawdown(prices) is None


# ── 4. Data quality classification ──────────────────────────────────────────


def test_data_quality_insufficient_under_one_year():
    assert classify_data_quality(pd.Series([100.0] * 100)) == "insufficient"
    assert classify_data_quality(pd.Series([100.0] * 251)) == "insufficient"


def test_data_quality_limited_one_to_three_years():
    assert classify_data_quality(pd.Series([100.0] * 252)) == "limited"
    assert classify_data_quality(pd.Series([100.0] * 600)) == "limited"
    assert classify_data_quality(pd.Series([100.0] * (252 * 3 - 1))) == "limited"


def test_data_quality_good_three_years_plus():
    assert classify_data_quality(pd.Series([100.0] * (252 * 3))) == "good"
    assert classify_data_quality(pd.Series([100.0] * 2000)) == "good"


def test_data_quality_handles_empty_input():
    assert classify_data_quality(pd.Series(dtype=float)) == "insufficient"


# ── 5. Current regime classification ────────────────────────────────────────


def test_regime_volatile_when_1y_vol_is_high():
    # 1y vol of 0.5 (50% annualised) — above the 0.40 threshold.
    regime = classify_current_regime(
        trending_pct=80.0, mean_reverting_pct=10.0,
        realized_vol_1y=0.5, realized_vol_5y=0.2,
    )
    assert regime == "volatile"


def test_regime_volatile_when_1y_spikes_vs_5y():
    # 1y vol ratio > 1.5x of 5y vol triggers volatile even when absolute level is moderate.
    regime = classify_current_regime(
        trending_pct=80.0, mean_reverting_pct=10.0,
        realized_vol_1y=0.30, realized_vol_5y=0.15,
    )
    assert regime == "volatile"


def test_regime_trending_when_trending_pct_high_and_vol_modest():
    regime = classify_current_regime(
        trending_pct=75.0, mean_reverting_pct=10.0,
        realized_vol_1y=0.20, realized_vol_5y=0.20,
    )
    assert regime == "trending"


def test_regime_range_bound_when_mr_high_and_trend_low():
    regime = classify_current_regime(
        trending_pct=20.0, mean_reverting_pct=70.0,
        realized_vol_1y=0.20, realized_vol_5y=0.20,
    )
    assert regime == "range_bound"


def test_regime_mixed_when_no_signal_dominates():
    regime = classify_current_regime(
        trending_pct=50.0, mean_reverting_pct=50.0,
        realized_vol_1y=0.20, realized_vol_5y=0.20,
    )
    assert regime == "mixed"


def test_regime_mixed_when_all_metrics_null():
    """The classifier must never crash on all-None inputs (insufficient data)."""
    regime = classify_current_regime(None, None, None, None)
    assert regime == "mixed"


# ── 6. Insufficient data behavior — never crashes ──────────────────────────


def test_fingerprint_with_empty_series_returns_insufficient():
    fp = compute_asset_behavior_fingerprint("AAPL", pd.Series(dtype=float))
    assert isinstance(fp, AssetBehaviorFingerprint)
    assert fp.symbol == "AAPL"
    assert fp.asset_type == "single_stock"
    assert fp.data_quality == "insufficient"
    assert fp.current_regime == "mixed"
    assert fp.trending_pct is None
    assert fp.mean_reverting_pct is None
    assert fp.realized_vol_1y is None
    assert fp.realized_vol_5y is None
    assert fp.max_drawdown_5y is None
    assert "not enough history" in fp.strategy_implication.lower()


def test_fingerprint_with_too_few_rows_returns_insufficient():
    prices = pd.Series([100 + i for i in range(15)], index=_date_index(15))
    fp = compute_asset_behavior_fingerprint("NVDA", prices)
    assert fp.data_quality == "insufficient"
    assert fp.strategy_implication == "There is not enough history to diagnose this asset reliably."


def test_fingerprint_with_none_series_does_not_crash():
    fp = compute_asset_behavior_fingerprint("MSFT", prices=None)  # type: ignore[arg-type]
    assert fp.data_quality == "insufficient"
    assert fp.symbol == "MSFT"


def test_fingerprint_with_empty_symbol_does_not_crash():
    fp = compute_asset_behavior_fingerprint("", pd.Series(dtype=float))
    assert fp.symbol == "?"


# ── 7. End-to-end fingerprints on synthetic series (sanity / regression) ────


def test_fingerprint_trending_series_is_classified_as_trending_or_mixed():
    """A textbook upward-drifting series should NOT classify as range_bound or volatile."""
    prices = _trending_prices()
    fp = compute_asset_behavior_fingerprint("AAPL", prices)
    assert fp.data_quality == "good"
    assert fp.current_regime in ("trending", "mixed")
    # The high-mu series should spend most of its life above the MA.
    assert fp.trending_pct is not None
    assert fp.trending_pct > 40.0


def test_fingerprint_volatile_series_is_classified_as_volatile():
    prices = _volatile_prices()
    fp = compute_asset_behavior_fingerprint("XYZ", prices)
    assert fp.data_quality == "good"
    assert fp.current_regime == "volatile"
    assert fp.realized_vol_1y is not None
    assert fp.realized_vol_1y > 0.5  # ≈ 80%+ annualised


def test_fingerprint_broad_etf_symbol_classified_correctly():
    """End-to-end: SPY input must surface as broad_etf, not single_stock."""
    prices = _trending_prices(seed=99)
    fp = compute_asset_behavior_fingerprint("SPY", prices)
    assert fp.asset_type == "broad_etf"


def test_fingerprint_commodity_etf_symbol_classified_correctly():
    prices = _trending_prices(seed=100)
    fp = compute_asset_behavior_fingerprint("GLD", prices)
    assert fp.asset_type == "commodity_etf"


def test_fingerprint_max_drawdown_is_negative_or_zero():
    prices = _trending_prices()
    fp = compute_asset_behavior_fingerprint("AAPL", prices)
    assert fp.max_drawdown_5y is not None
    assert fp.max_drawdown_5y <= 0.0


def test_fingerprint_to_dict_keys_match_spec():
    fp = compute_asset_behavior_fingerprint("AAPL", _trending_prices())
    d = fp.to_dict()
    expected_keys = {
        "symbol", "asset_type", "trending_pct", "mean_reverting_pct",
        "realized_vol_1y", "realized_vol_5y", "max_drawdown_5y",
        "current_regime", "data_quality", "strategy_implication",
    }
    assert set(d.keys()) == expected_keys
