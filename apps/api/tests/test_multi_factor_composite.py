"""
End-to-end integration tests for multi_factor_composite strategy.

Verifies:
(a) Valid BacktestResult with finite total_return.
(b) Non-empty trade_log.
(c) Weight invariant: sum <= 1.0 at every date.
(d) Symbol selection: top-composite symbols dominate trades.
(e) factor_weights StrategyRule field parses correctly.
(f) All four named factors can be built individually via _build_factor_score_matrix.
(g) Empty factor_weights → holds cash (no trades or all-zero weights).
(h) Schema roundtrip: multi_factor_composite accepted by StrategyJSON.
(i) Provider routing: value_composite and quality_f_score factors trigger
    the right FundamentalSignalProvider instances.

Signal setup:
- Fundamental signals (value_composite, quality_f_score) injected via
  patched _fetch_signal_matrix.
- Price-derived signals (momentum_12_1, low_volatility) computed directly
  from synthetic prices — no mock needed.
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

SYMS  = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
START = date(2021, 1, 4)
END   = date(2022, 12, 30)
N     = 504
LAG   = 45


def _make_close_df(seed: int = 31) -> pd.DataFrame:
    dates = pd.date_range(START.isoformat(), periods=N, freq="B")
    data  = {}
    for i, sym in enumerate(SYMS):
        rng = np.random.default_rng(seed + i * 13)
        data[sym] = 100.0 * np.cumprod(1 + rng.normal(3e-4, 0.015, N))
    return pd.DataFrame(data, index=dates)


def _price_frames(close_df: pd.DataFrame):
    uf = {
        sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        )
        for sym in close_df.columns
    }
    bench = pd.DataFrame(
        {"adjusted_close": close_df[SYMS[0]].values,
         "high": (close_df[SYMS[0]] * 1.01).values},
        index=close_df.index,
    )
    return uf, bench


# ── Default equal-weight 4-factor strategy ───────────────────────────────────

def _strategy(**ov) -> StrategyJSON:
    base = dict(
        strategy_name="Multi-Factor Test",
        strategy_type="multi_factor_composite",
        universe=SYMS,
        benchmark=SYMS[0],
        start_date=START,
        end_date=END,
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=10,
        slippage_bps=10,
        rules=[StrategyRule(
            factor_weights={
                "value_composite": 0.25,
                "momentum_12_1":   0.25,
                "quality_f_score": 0.25,
                "low_volatility":  0.25,
            },
            top_pct=0.4,
        )],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    base.update(ov)
    return StrategyJSON(**base)


# ── Fundamental signal factories ─────────────────────────────────────────────

def _fundamental_sparse(signal_name: str, symbol: str, rank: int,
                         start: date, end: date) -> pd.Series:
    """
    Quarterly sparse fundamental signal.
    rank 0 (SYM1) = best; rank 4 (SYM5) = worst.
    """
    period_ends = pd.date_range(
        (start - timedelta(days=2 * 365)).isoformat(),
        end.isoformat(),
        freq="QE",
    )
    disc = period_ends + pd.Timedelta(days=LAG)
    values_map = {
        "fcf_yield":       [0.10 - rank * 0.015] * len(disc),
        "book_to_market":  [0.80 - rank * 0.10]  * len(disc),
        "ebitda_ev":       [0.15 - rank * 0.02]  * len(disc),
        "f_score":         [9.0  - rank]          * len(disc),
    }
    vals = values_map.get(signal_name, [0.5 - rank * 0.1] * len(disc))
    return pd.Series(vals, index=disc, name=signal_name)


def _build_precomputed(close_idx: pd.DatetimeIndex,
                        signals: list[str]) -> dict[str, pd.DataFrame]:
    result = {}
    for sn in signals:
        cols = {}
        for i, sym in enumerate(SYMS):
            sparse = _fundamental_sparse(sn, sym, i, START, END)
            combined = sparse.index.union(close_idx)
            cols[sym] = sparse.reindex(combined).ffill().reindex(close_idx)
        result[sn] = pd.DataFrame(cols, index=close_idx)
    return result


# ── Run helper ────────────────────────────────────────────────────────────────

async def _run(strategy: StrategyJSON, close_df: pd.DataFrame,
               fundamental_signals: list[str] | None = None):
    engine = BacktestEngine()
    db = MagicMock()

    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(strategy.start_date)]

    prebuilt = {}
    if fundamental_signals:
        prebuilt = _build_precomputed(close_matrix.index, fundamental_signals)

    async def _fake_fetch(providers, universe, _db, close_index, sig_start, sig_end,
                          ffill_limit=None):
        return prebuilt

    with patch.object(engine, "_load_prices",
                      new=AsyncMock(return_value=_price_frames(close_df))), \
         patch.object(engine, "_fetch_signal_matrix",
                      new=AsyncMock(side_effect=_fake_fetch)), \
         patch.object(engine, "_check_microcap",
                      new=AsyncMock(return_value=[])):
        result = await engine.run(db, strategy)

    return result, engine, close_matrix


# ── (a-d) End-to-end backtest ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multi_factor_valid_result():
    close_df = _make_close_df()
    result, _, _ = await _run(
        _strategy(),
        close_df,
        fundamental_signals=["fcf_yield", "book_to_market", "ebitda_ev", "f_score"],
    )
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_multi_factor_non_empty_trade_log():
    close_df = _make_close_df()
    result, _, _ = await _run(
        _strategy(),
        close_df,
        fundamental_signals=["fcf_yield", "book_to_market", "ebitda_ev", "f_score"],
    )
    assert len(result.trade_log) > 0, "Expected non-empty trade_log"


@pytest.mark.asyncio
async def test_multi_factor_weight_invariant():
    close_df = _make_close_df()
    result, engine, close_matrix = await _run(
        _strategy(),
        close_df,
        fundamental_signals=["fcf_yield", "book_to_market", "ebitda_ev", "f_score"],
    )
    precomputed = _build_precomputed(
        close_matrix.index,
        ["fcf_yield", "book_to_market", "ebitda_ev", "f_score"],
    )
    weights = engine._generate_weights(_strategy(), close_matrix, {}, precomputed)
    exposure = weights.sum(axis=1)
    assert (exposure <= 1.0 + 1e-9).all(), f"Max exposure = {exposure.max():.6f}"


@pytest.mark.asyncio
async def test_multi_factor_top_symbols_selected():
    """With only fundamental factors (fully mocked), SYM1+SYM2 always dominate."""
    close_df = _make_close_df()
    # Use only fundamental factors so rankings are fully deterministic from mock data
    fundamental_only_strategy = _strategy(rules=[StrategyRule(
        factor_weights={"value_composite": 0.5, "quality_f_score": 0.5},
        top_pct=0.4,
    )])
    result, _, _ = await _run(
        fundamental_only_strategy,
        close_df,
        fundamental_signals=["fcf_yield", "book_to_market", "ebitda_ev", "f_score"],
    )
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Unexpected symbols in trades: {trade_syms - {'SYM1', 'SYM2'}}"
    )
    # Ensure the worst-ranked symbol never appears
    assert "SYM5" not in trade_syms


# ── (e) factor_weights field parsing ─────────────────────────────────────────

def test_factor_weights_field_parses():
    rule = StrategyRule(factor_weights={"value_composite": 0.5, "momentum_12_1": 0.5},
                        top_pct=0.2)
    assert rule.factor_weights == {"value_composite": 0.5, "momentum_12_1": 0.5}
    assert rule.top_pct == 0.2


def test_factor_weights_default_none():
    assert StrategyRule().factor_weights is None


# ── (f) Individual factor score matrices ─────────────────────────────────────

def test_build_factor_momentum_12_1():
    close_df = _make_close_df()
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(START)]
    mat = engine._build_factor_score_matrix("momentum_12_1", close_matrix, {})
    assert isinstance(mat, pd.DataFrame)
    assert mat.shape == close_matrix.shape
    # First 252+21 rows should be NaN (warmup)
    assert mat.iloc[:252].isna().all().all()


def test_build_factor_low_volatility():
    close_df = _make_close_df()
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(START)]
    mat = engine._build_factor_score_matrix("low_volatility", close_matrix, {})
    assert isinstance(mat, pd.DataFrame)
    assert mat.shape == close_matrix.shape
    # Negated vol: all non-NaN values should be <= 0
    assert (mat.dropna() <= 0).all().all()


def test_build_factor_value_composite():
    close_df = _make_close_df()
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(START)]
    precomputed = _build_precomputed(
        close_matrix.index, ["fcf_yield", "book_to_market", "ebitda_ev"]
    )
    mat = engine._build_factor_score_matrix("value_composite", close_matrix, precomputed)
    assert isinstance(mat, pd.DataFrame)
    # SYM1 should consistently have the highest composite z-score
    valid_rows = mat.dropna(how="all")
    if not valid_rows.empty:
        assert (valid_rows.idxmax(axis=1) == "SYM1").mean() > 0.8


def test_build_factor_quality_f_score():
    close_df = _make_close_df()
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(START)]
    precomputed = _build_precomputed(close_matrix.index, ["f_score"])
    mat = engine._build_factor_score_matrix("quality_f_score", close_matrix, precomputed)
    assert isinstance(mat, pd.DataFrame)
    assert mat.shape == close_matrix.shape


def test_build_factor_unknown_name_returns_nan():
    close_df = _make_close_df()
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(START)]
    mat = engine._build_factor_score_matrix("nonexistent_factor", close_matrix, {})
    assert isinstance(mat, pd.DataFrame)
    assert mat.isna().all().all()


# ── (g) Empty factor_weights → holds cash ────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_factor_weights_holds_cash():
    close_df = _make_close_df()
    strat = _strategy(rules=[StrategyRule(factor_weights={}, top_pct=0.4)])
    result, _, _ = await _run(strat, close_df)
    # All-cash: no active trades (only open position at end is none)
    assert len(result.trade_log) == 0


# ── (h) Schema roundtrip ──────────────────────────────────────────────────────

def test_multi_factor_schema_roundtrip():
    s = _strategy()
    assert s.strategy_type == "multi_factor_composite"
    assert s.rules[0].factor_weights == {
        "value_composite": 0.25,
        "momentum_12_1":   0.25,
        "quality_f_score": 0.25,
        "low_volatility":  0.25,
    }
    assert s.rules[0].top_pct == 0.4


# ── (i) Provider routing ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_routing_value_and_quality():
    """value_composite + quality_f_score factors request the right FMP providers."""
    from app.services.backtester.signal_provider import FundamentalSignalProvider

    close_df = _make_close_df()
    strat = _strategy(rules=[StrategyRule(
        factor_weights={"value_composite": 0.5, "quality_f_score": 0.5},
        top_pct=0.4,
    )])

    engine = BacktestEngine()
    captured_providers = []

    async def _capture_fetch(providers, universe, _db, close_index, sig_start, sig_end,
                              ffill_limit=None):
        captured_providers.extend(providers)
        return {}

    with patch.object(engine, "_load_prices",
                      new=AsyncMock(return_value=_price_frames(close_df))), \
         patch.object(engine, "_fetch_signal_matrix",
                      new=AsyncMock(side_effect=_capture_fetch)), \
         patch.object(engine, "_check_microcap",
                      new=AsyncMock(return_value=[])):
        await engine.run(MagicMock(), strat)

    provider_names = [p.name for p in captured_providers]
    # value_composite needs fcf_yield, book_to_market, ebitda_ev
    assert "fcf_yield"       in provider_names
    assert "book_to_market"  in provider_names
    assert "ebitda_ev"       in provider_names
    # quality_f_score needs f_score
    assert "f_score"         in provider_names
    # No duplicates
    assert len(provider_names) == len(set(provider_names))


@pytest.mark.asyncio
async def test_provider_routing_price_only_factors():
    """momentum_12_1 and low_volatility need no providers."""
    close_df = _make_close_df()
    strat = _strategy(rules=[StrategyRule(
        factor_weights={"momentum_12_1": 0.5, "low_volatility": 0.5},
        top_pct=0.4,
    )])

    engine = BacktestEngine()
    captured_providers = []

    async def _capture_fetch(providers, universe, _db, close_index, sig_start, sig_end,
                              ffill_limit=None):
        captured_providers.extend(providers)
        return {}

    with patch.object(engine, "_load_prices",
                      new=AsyncMock(return_value=_price_frames(close_df))), \
         patch.object(engine, "_fetch_signal_matrix",
                      new=AsyncMock(side_effect=_capture_fetch)), \
         patch.object(engine, "_check_microcap",
                      new=AsyncMock(return_value=[])):
        await engine.run(MagicMock(), strat)

    # No providers needed for price-based factors
    assert len(captured_providers) == 0
