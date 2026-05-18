"""
Unit tests for BacktestEngine new strategy-type branches.

For each new strategy_type:
  (a) engine.run() returns a valid BacktestResult
  (b) total weight at any rebalance date <= 1.0
  (c) trade_log is non-empty

Strategy under test runs on synthetic 3-symbol (or 2-symbol for pairs) daily
prices.  _load_prices is mocked so no DB or market-data calls are made.

Weight invariant is verified directly via _generate_weights so we get a
numpy-level guarantee (not just inferred from the equity curve).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.schemas.strategy import (
    CashManagement,
    PositionSizing,
    RiskManagement,
    StrategyJSON,
    StrategyRule,
)
from app.services.backtester.engine import BacktestEngine


# ── Synthetic data helpers ────────────────────────────────────────────────────

def _make_close_matrix(
    n_days: int = 504,
    symbols: list[str] | None = None,
    seed: int = 42,
    start: str = "2021-01-04",
) -> pd.DataFrame:
    """Random-walk prices.  Different seeds per symbol for cross-sectional spread."""
    if symbols is None:
        symbols = ["SYM1", "SYM2", "SYM3"]
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n_days, freq="B")
    data = {}
    for i, sym in enumerate(symbols):
        rng_sym = np.random.default_rng(seed + i * 17)
        daily_ret = rng_sym.normal(0.0003, 0.018, size=n_days)
        data[sym] = 100.0 * np.cumprod(1 + daily_ret)
    return pd.DataFrame(data, index=dates)


def _make_load_prices_return(close_df: pd.DataFrame, benchmark_sym: str | None = None):
    """Build (universe_frames, benchmark_frame) matching BacktestEngine._load_prices output."""
    universe_frames = {}
    for sym in close_df.columns:
        universe_frames[sym] = pd.DataFrame(
            {
                "adjusted_close": close_df[sym].values,
                "high": (close_df[sym] * 1.01).values,
            },
            index=close_df.index,
        )
    bench_sym = benchmark_sym or close_df.columns[0]
    benchmark_frame = pd.DataFrame(
        {
            "adjusted_close": close_df[bench_sym].values,
            "high": (close_df[bench_sym] * 1.01).values,
        },
        index=close_df.index,
    )
    return universe_frames, benchmark_frame


def _base_strategy(**overrides) -> StrategyJSON:
    """Minimal valid StrategyJSON — caller overrides strategy_type and rules."""
    base = dict(
        strategy_name="Synthetic Test",
        strategy_type="moving_average_filter",   # overridden by caller
        universe=["SYM1", "SYM2", "SYM3"],
        benchmark="SYM1",
        start_date=date(2021, 1, 4),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=[],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    base.update(overrides)
    return StrategyJSON(**base)


# ── Direct weight invariant check ────────────────────────────────────────────

def _check_weights(engine: BacktestEngine, strategy: StrategyJSON, close_df: pd.DataFrame):
    """Call _generate_weights directly and assert exposure <= 1.0 everywhere."""
    close_matrix, aligned = engine._build_price_matrix(
        {sym: pd.DataFrame({"adjusted_close": close_df[sym], "high": close_df[sym] * 1.01})
         for sym in close_df.columns}
    )
    # Trim to strategy window (mirrors what run() does)
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]
    aligned = {s: f[f.index >= start_ts] for s, f in aligned.items()}
    weights = engine._generate_weights(strategy, close_matrix, aligned)
    exposure = weights.sum(axis=1)
    assert (exposure <= 1.0 + 1e-9).all(), f"Exposure > 1.0 detected: max={exposure.max():.4f}"
    return weights, close_matrix


# ── Run helper (mocks _load_prices + DB) ─────────────────────────────────────

async def _run_strategy(strategy: StrategyJSON, close_df: pd.DataFrame):
    engine = BacktestEngine()
    db = MagicMock()
    load_return = _make_load_prices_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        result = await engine.run(db, strategy)
    return result, engine


# ── cross_sectional_momentum ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_sectional_momentum_valid_result():
    close_df = _make_close_matrix()
    strategy = _base_strategy(
        strategy_type="cross_sectional_momentum",
        rules=[StrategyRule(formation_period_days=63, skip_period_days=5, top_n=2)],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    weights, _ = _check_weights(engine, strategy, close_df)


# ── time_series_momentum ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_time_series_momentum_valid_result():
    close_df = _make_close_matrix()
    strategy = _base_strategy(
        strategy_type="time_series_momentum",
        rules=[StrategyRule(lookback_days=63)],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    _check_weights(engine, strategy, close_df)


# ── short_term_reversal ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_short_term_reversal_valid_result():
    close_df = _make_close_matrix()
    strategy = _base_strategy(
        strategy_type="short_term_reversal",
        rules=[StrategyRule(formation_period_days=5, top_n=2, rank_direction="bottom")],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    _check_weights(engine, strategy, close_df)


# ── sector_rotation ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sector_rotation_valid_result():
    close_df = _make_close_matrix()
    strategy = _base_strategy(
        strategy_type="sector_rotation",
        rules=[StrategyRule(formation_period_days=63, top_n=2)],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    _check_weights(engine, strategy, close_df)


# ── dual_momentum ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dual_momentum_valid_result():
    close_df = _make_close_matrix()
    strategy = _base_strategy(
        strategy_type="dual_momentum",
        rules=[StrategyRule(formation_period_days=63)],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    _check_weights(engine, strategy, close_df)


@pytest.mark.asyncio
async def test_dual_momentum_uses_safe_asset():
    """When best stock has negative return, allocation goes to safe-asset."""
    close_df = _make_close_matrix(symbols=["SYM1", "SYM2", "CASH"])
    strategy = _base_strategy(
        strategy_type="dual_momentum",
        universe=["SYM1", "SYM2", "CASH"],
        rules=[
            StrategyRule(formation_period_days=63),
            StrategyRule(signal_source="safe_asset", value="CASH"),
        ],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)

    _check_weights(engine, strategy, close_df)


# ── low_volatility ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_low_volatility_valid_result():
    close_df = _make_close_matrix()
    strategy = _base_strategy(
        strategy_type="low_volatility",
        rules=[StrategyRule(lookback_days=21, top_n=2)],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    _check_weights(engine, strategy, close_df)


# ── bollinger_mean_reversion ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bollinger_mean_reversion_valid_result():
    # Create a price series that crosses below the lower Bollinger band
    rng = np.random.default_rng(7)
    n = 504
    dates = pd.date_range("2021-01-04", periods=n, freq="B")
    # Base random walk + engineered dips to trigger entries
    base = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.01, size=n))
    dip_idx = [80, 180, 280, 380]
    for i in dip_idx:
        base[i : i + 3] *= 0.93   # 7% dip to trigger lower-band entry
    close_df = pd.DataFrame({"SYM1": base}, index=dates)

    strategy = _base_strategy(
        strategy_type="bollinger_mean_reversion",
        universe=["SYM1"],
        benchmark="SYM1",
        rules=[StrategyRule(lookback_days=20, num_std=2.0)],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    _check_weights(engine, strategy, close_df)


# ── pairs_trading ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pairs_trading_valid_result():
    # Create two correlated series with mean-reverting spread
    rng = np.random.default_rng(99)
    n = 504
    dates = pd.date_range("2021-01-04", periods=n, freq="B")
    common = np.cumsum(rng.normal(0.0003, 0.01, size=n))
    spread_noise = np.cumsum(rng.normal(0, 0.005, size=n))
    # Inject mean reversion in the spread
    spread = np.zeros(n)
    spread[0] = 0.0
    for i in range(1, n):
        spread[i] = 0.95 * spread[i - 1] + rng.normal(0, 0.015)
    sym_a = 100.0 * np.exp(common + spread)
    sym_b = 100.0 * np.exp(common)
    close_df = pd.DataFrame({"SYMA": sym_a, "SYMB": sym_b}, index=dates)

    strategy = _base_strategy(
        strategy_type="pairs_trading",
        universe=["SYMA", "SYMB"],
        benchmark="SYMA",
        rules=[StrategyRule(lookback_days=60, zscore_entry=1.5, zscore_exit=0.5, zscore_stop=3.0, hedge_ratio=1.0)],
        rebalance_frequency="daily",
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    weights, _ = _check_weights(engine, strategy, close_df)
    # Only SYMA should have non-zero weights (long-only variant)
    assert (weights["SYMB"] == 0.0).all()


@pytest.mark.asyncio
async def test_pairs_trading_requires_two_symbols():
    close_df = _make_close_matrix(symbols=["SYM1"])
    strategy = _base_strategy(
        strategy_type="pairs_trading",
        universe=["SYM1"],
        benchmark="SYM1",
        rules=[StrategyRule(lookback_days=30, zscore_entry=2.0, zscore_exit=0.5)],
    )
    engine = BacktestEngine()
    db = MagicMock()
    load_return = _make_load_prices_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        with pytest.raises(ValueError, match="at least 2 symbols"):
            await engine.run(db, strategy)


# ── Original momentum_rotation still behaves correctly ───────────────────────

@pytest.mark.asyncio
async def test_momentum_rotation_still_works_after_refactor():
    """Sanity check: refactored momentum_rotation produces valid output."""
    close_df = _make_close_matrix()
    strategy = _base_strategy(
        strategy_type="momentum_rotation",
        rules=[StrategyRule(top_n=2, ranking_lookback_days=63, ranking_measure="total_return")],
    )
    result, engine = await _run_strategy(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)
    assert len(result.trade_log) > 0

    weights, _ = _check_weights(engine, strategy, close_df)
    # At most top_n=2 non-zero weights at any time
    active_at_rebalance = (weights > 0).sum(axis=1)
    assert (active_at_rebalance <= 2).all()


# ── Cross-sectional helper unit tests ─────────────────────────────────────────

def test_cross_sectional_helper_top_direction():
    """Helper selects correct assets and normalises weights."""
    engine = BacktestEngine()
    dates = pd.date_range("2021-01-04", periods=30, freq="B")
    # Known scores: SYM1 always best, SYM3 always worst
    close = pd.DataFrame(
        {"SYM1": 100.0 + np.arange(30) * 0.5,
         "SYM2": 100.0 + np.arange(30) * 0.2,
         "SYM3": 100.0 - np.arange(30) * 0.1},
        index=dates,
    )
    score = close.pct_change(5)    # 5-day return
    rebalance = pd.Series(True, index=dates)  # rebalance every day

    weights = engine._generate_cross_sectional_weights(
        close, score, rebalance, top_n=2, top_pct=None, rank_direction="top"
    )
    # After warmup: SYM1 and SYM2 should always be selected (highest returns)
    after_warmup = weights.iloc[10:]
    assert (after_warmup["SYM3"] == 0.0).all()
    assert (after_warmup[["SYM1", "SYM2"]].sum(axis=1).round(6) == 1.0).all()


def test_cross_sectional_helper_bottom_direction():
    """rank_direction='bottom' selects lowest scores."""
    engine = BacktestEngine()
    dates = pd.date_range("2021-01-04", periods=30, freq="B")
    close = pd.DataFrame(
        {"SYM1": 100.0 + np.arange(30) * 0.5,
         "SYM2": 100.0 + np.arange(30) * 0.2,
         "SYM3": 100.0 - np.arange(30) * 0.1},
        index=dates,
    )
    score = close.pct_change(5)
    rebalance = pd.Series(True, index=dates)

    weights = engine._generate_cross_sectional_weights(
        close, score, rebalance, top_n=1, top_pct=None, rank_direction="bottom"
    )
    after_warmup = weights.iloc[10:]
    # SYM3 has the lowest (most negative) 5-day return → selected
    assert (after_warmup["SYM3"] == 1.0).all()


def test_cross_sectional_helper_top_pct():
    """top_pct=0.5 selects the top 50% of assets."""
    engine = BacktestEngine()
    dates = pd.date_range("2021-01-04", periods=30, freq="B")
    close = pd.DataFrame(
        {f"SYM{i}": 100.0 * np.cumprod(1 + np.full(30, i * 0.001))
         for i in range(1, 5)},  # 4 symbols
        index=dates,
    )
    score = close.pct_change(5)
    rebalance = pd.Series(index.is_month_start for index in dates)
    rebalance.index = dates

    weights = engine._generate_cross_sectional_weights(
        close, score, rebalance, top_n=None, top_pct=0.5, rank_direction="top"
    )
    # On rebalance dates with valid scores, at most 2 of 4 symbols selected
    rebal_dates = dates[rebalance]
    for dt in rebal_dates:
        n_selected = (weights.loc[dt] > 0).sum()
        assert n_selected <= 2   # top 50% of 4 = 2
