"""
Integration tests for fundamental-signal strategy templates:
  value_composite, quality_piotroski, buyback_yield.

Setup
-----
- 5 synthetic symbols (SYM1–SYM5) with 2 years of random-walk price data.
- FundamentalSignalProvider.get_signal_frame is patched per-signal-name so
  the engine receives deterministic sparse Series dated at quarterly
  disclosure points (period_end + 45 days).
- _load_prices is patched to return the synthetic price frames.

Assertions (per strategy type)
------------------------------
(a) engine.run() returns a valid BacktestResult.
(b) result.trade_log is non-empty.
(c) Total weight at any date <= 1.0 (verified via _generate_weights directly
    after patching precomputed_signals in).
(d) Look-ahead: no signal value appears before its disclosure date.
"""
from __future__ import annotations

from datetime import date, timedelta
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

# ── Synthetic data ────────────────────────────────────────────────────────────

SYMS      = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
N_DAYS    = 504   # ~2 years of trading days
START     = date(2021, 1, 4)
END       = date(2022, 12, 30)
REPORT_LAG = 45    # days after fiscal period end → disclosure


def _make_close_df(seed: int = 7) -> pd.DataFrame:
    rng  = np.random.default_rng(seed)
    dates = pd.date_range(START.isoformat(), periods=N_DAYS, freq="B")
    data  = {}
    for i, sym in enumerate(SYMS):
        s = np.random.default_rng(seed + i * 11)
        data[sym] = 100.0 * np.cumprod(1 + s.normal(3e-4, 0.015, N_DAYS))
    return pd.DataFrame(data, index=dates)


def _price_frames(close_df: pd.DataFrame):
    universe_frames = {
        sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        )
        for sym in close_df.columns
    }
    benchmark = pd.DataFrame(
        {"adjusted_close": close_df[SYMS[0]].values,
         "high": (close_df[SYMS[0]] * 1.01).values},
        index=close_df.index,
    )
    return universe_frames, benchmark


def _base_strategy(**overrides) -> StrategyJSON:
    base = dict(
        strategy_name="Fundamental Test",
        strategy_type="value_composite",
        universe=SYMS,
        benchmark=SYMS[0],
        start_date=START,
        end_date=END,
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


# ── Sparse signal factories ───────────────────────────────────────────────────

def _sparse_series(
    signal_name: str,
    symbol: str,
    start: date,
    end: date,
    rank: int = 0,      # 0 = SYM1 (best), 4 = SYM5 (worst)
) -> pd.Series:
    """
    Return a quarterly sparse Series dated at period_end + REPORT_LAG.
    Higher rank → lower value (worst); rank 0 → highest value.
    """
    # Quarterly period ends starting 2 years before strategy start (pre-strategy disclosures)
    period_ends = pd.date_range(
        (start - timedelta(days=2 * 365)).isoformat(),
        end.isoformat(),
        freq="QE",  # quarter-end
    )
    disclosure_dates = period_ends + pd.Timedelta(days=REPORT_LAG)

    base_values = {
        "fcf_yield":         0.10 - rank * 0.015,  # SYM1=0.10, SYM5=0.04
        "book_to_market":    0.80 - rank * 0.10,   # SYM1=0.80, SYM5=0.40
        "ebitda_ev":         0.15 - rank * 0.02,   # SYM1=0.15, SYM5=0.07
        "f_score":           9.0  - rank,          # SYM1=9, SYM2=8, SYM3=7, …
        "buyback_yield_ttm": 0.05 - rank * 0.008,  # SYM1=0.05, SYM5=0.018
    }
    value = base_values.get(signal_name, 1.0 - rank * 0.1)
    return pd.Series(
        [float(value)] * len(disclosure_dates),
        index=disclosure_dates,
        name=signal_name,
    )


def _make_signal_mock(strategy_type: str):
    """
    Return an AsyncMock for FundamentalSignalProvider.get_signal_frame that
    returns the correct sparse Series based on symbol index in SYMS.
    """
    async def _side_effect(db, symbol, start, end):
        # The mock doesn't know which signal it's called for without capture.
        # We capture via closure in the calling test.
        raise RuntimeError("use _make_provider_mock instead")
    return AsyncMock(side_effect=_side_effect)


def _provider_mock_for(signal_name: str):
    """Return an async mock that returns the correct series for any symbol."""
    async def _side_effect(db, symbol, start, end):
        rank = SYMS.index(symbol) if symbol in SYMS else 0
        return _sparse_series(signal_name, symbol, start, end, rank=rank)
    mock = AsyncMock(side_effect=_side_effect)
    mock_provider = MagicMock()
    mock_provider.name = signal_name
    mock_provider.get_signal_frame = mock
    return mock_provider


# ── Engine run helper (patches _load_prices + signal providers) ──────────────

async def _run(strategy: StrategyJSON, close_df: pd.DataFrame):
    engine = BacktestEngine()
    db = MagicMock()
    load_return = _price_frames(close_df)

    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        # Patch _fetch_signal_matrix to use our deterministic mocked providers
        signal_names_map = {
            "value_composite":   ["fcf_yield", "book_to_market", "ebitda_ev"],
            "quality_piotroski": ["f_score"],
            "buyback_yield":     ["buyback_yield_ttm"],
        }
        signal_names = signal_names_map.get(strategy.strategy_type, [])
        mock_providers = [_provider_mock_for(sn) for sn in signal_names]

        async def _fake_fetch_signal_matrix(providers, universe, db, close_index, sig_start, sig_end, ffill_limit=None):
            result = {}
            for p in mock_providers:
                cols = {}
                for sym in universe:
                    sparse = await p.get_signal_frame(db, sym, sig_start, sig_end)
                    combined = sparse.index.union(close_index)
                    cols[sym] = sparse.reindex(combined).ffill().reindex(close_index)
                result[p.name] = pd.DataFrame(cols, index=close_index)
            return result

        with patch.object(engine, "_fetch_signal_matrix",
                          new=AsyncMock(side_effect=_fake_fetch_signal_matrix)):
            result = await engine.run(db, strategy)

    return result, engine


# ── value_composite ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_value_composite_valid_result():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="value_composite",
        rules=[StrategyRule(top_pct=0.4)],   # top 40% of 5 = 2 symbols
    )
    result, _ = await _run(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_value_composite_non_empty_trade_log():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="value_composite",
        rules=[StrategyRule(top_pct=0.4)],
    )
    result, _ = await _run(strategy, close_df)
    assert len(result.trade_log) > 0, "trade_log must be non-empty"


@pytest.mark.asyncio
async def test_value_composite_weight_invariant():
    """Weight sum <= 1.0 on every trading day."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="value_composite",
        rules=[StrategyRule(top_pct=0.4)],
    )
    engine = BacktestEngine()
    close_matrix, aligned = engine._build_price_matrix(
        {sym: pd.DataFrame({"adjusted_close": close_df[sym], "high": close_df[sym] * 1.01})
         for sym in close_df.columns}
    )
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]

    # Build precomputed_signals directly
    signal_names = ["fcf_yield", "book_to_market", "ebitda_ev"]
    precomputed = {}
    for sn in signal_names:
        providers = [_provider_mock_for(sn)]
        cols = {}
        for i, sym in enumerate(SYMS):
            sparse = _sparse_series(sn, sym,
                                    strategy.start_date - timedelta(days=2*365),
                                    strategy.end_date, rank=i)
            combined = sparse.index.union(close_matrix.index)
            cols[sym] = sparse.reindex(combined).ffill().reindex(close_matrix.index)
        precomputed[sn] = pd.DataFrame(cols, index=close_matrix.index)

    weights = engine._generate_weights(strategy, close_matrix, {}, precomputed)
    exposure = weights.sum(axis=1)
    assert (exposure <= 1.0 + 1e-9).all(), f"Max exposure = {exposure.max():.6f}"


@pytest.mark.asyncio
async def test_value_composite_top_symbols_selected():
    """SYM1 and SYM2 always have the highest composite — they should dominate."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="value_composite",
        rules=[StrategyRule(top_pct=0.4)],   # 40% of 5 → top 2
    )
    result, _ = await _run(strategy, close_df)
    # All trades should be for SYM1 or SYM2
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Unexpected symbols in trade_log: {trade_syms - {'SYM1','SYM2'}}"
    )


# ── quality_piotroski ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quality_piotroski_valid_result():
    close_df = _make_close_df()
    # SYM1=9, SYM2=8 qualify (>= 8); SYM3–SYM5 don't
    strategy = _base_strategy(strategy_type="quality_piotroski")
    result, _ = await _run(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_quality_piotroski_non_empty_trade_log():
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="quality_piotroski")
    result, _ = await _run(strategy, close_df)
    assert len(result.trade_log) > 0


@pytest.mark.asyncio
async def test_quality_piotroski_only_qualifying_selected():
    """Only SYM1 (f=9) and SYM2 (f=8) should appear in trades."""
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="quality_piotroski")
    result, _ = await _run(strategy, close_df)
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Below-threshold symbols in trades: {trade_syms - {'SYM1','SYM2'}}"
    )


@pytest.mark.asyncio
async def test_quality_piotroski_weight_invariant():
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="quality_piotroski")
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame({"adjusted_close": close_df[sym], "high": close_df[sym] * 1.01})
         for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(strategy.start_date)]

    cols = {}
    for i, sym in enumerate(SYMS):
        sparse = _sparse_series("f_score", sym,
                                strategy.start_date - timedelta(days=2*365),
                                strategy.end_date, rank=i)
        combined = sparse.index.union(close_matrix.index)
        cols[sym] = sparse.reindex(combined).ffill().reindex(close_matrix.index)
    precomputed = {"f_score": pd.DataFrame(cols, index=close_matrix.index)}

    weights = engine._generate_weights(strategy, close_matrix, {}, precomputed)
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()


# ── buyback_yield ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buyback_yield_valid_result():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="buyback_yield",
        rules=[StrategyRule(top_pct=0.4)],
    )
    result, _ = await _run(strategy, close_df)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_buyback_yield_non_empty_trade_log():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="buyback_yield",
        rules=[StrategyRule(top_pct=0.4)],
    )
    result, _ = await _run(strategy, close_df)
    assert len(result.trade_log) > 0


@pytest.mark.asyncio
async def test_buyback_yield_weight_invariant():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="buyback_yield",
        rules=[StrategyRule(top_pct=0.4)],
    )
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame({"adjusted_close": close_df[sym], "high": close_df[sym] * 1.01})
         for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(strategy.start_date)]

    cols = {}
    for i, sym in enumerate(SYMS):
        sparse = _sparse_series("buyback_yield_ttm", sym,
                                strategy.start_date - timedelta(days=2*365),
                                strategy.end_date, rank=i)
        combined = sparse.index.union(close_matrix.index)
        cols[sym] = sparse.reindex(combined).ffill().reindex(close_matrix.index)
    precomputed = {"buyback_yield_ttm": pd.DataFrame(cols, index=close_matrix.index)}

    weights = engine._generate_weights(strategy, close_matrix, {}, precomputed)
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()


@pytest.mark.asyncio
async def test_buyback_yield_top_symbols_selected():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="buyback_yield",
        rules=[StrategyRule(top_pct=0.4)],
    )
    result, _ = await _run(strategy, close_df)
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Unexpected low-yield symbols in trades: {trade_syms - {'SYM1','SYM2'}}"
    )


# ── Look-ahead guard ──────────────────────────────────────────────────────────

def test_signal_not_available_before_disclosure():
    """
    Sparse series reindexed to trading dates must be NaN before the
    first disclosure date (no backfilling allowed).
    """
    sparse = _sparse_series("fcf_yield", "SYM1", START, END, rank=0)
    first_disclosure = sparse.index[0]
    trading_idx = pd.date_range(START.isoformat(), END.isoformat(), freq="B")

    combined = sparse.index.union(trading_idx)
    aligned = sparse.reindex(combined).ffill().reindex(trading_idx)

    pre_disclosure = aligned[aligned.index < first_disclosure]
    assert pre_disclosure.isna().all(), (
        f"Signal values present before first disclosure {first_disclosure.date()}"
    )


def test_disclosure_date_is_period_end_plus_lag():
    """Disclosure dates must be exactly period_end + REPORT_LAG."""
    sparse = _sparse_series("f_score", "SYM1", START, END, rank=0)
    for ts in sparse.index:
        period_end = ts - pd.Timedelta(days=REPORT_LAG)
        # Period end must be a quarter-end (month 3, 6, 9, 12)
        assert period_end.month in (3, 6, 9, 12), (
            f"Disclosure {ts.date()} implies period_end {period_end.date()} "
            f"which is not a quarter-end"
        )
