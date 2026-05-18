"""
Integration tests for news_sentiment_momentum and insider_buying templates.

Setup
-----
- 5 synthetic symbols (SYM1–SYM5), 2 years of daily prices.
- Signals injected via patched _fetch_signal_matrix.
- _load_prices and _check_microcap patched (no live DB/FMP calls).

Assertions per template
-----------------------
(a) engine.run() returns a valid BacktestResult with finite total_return.
(b) trade_log is non-empty.
(c) Total weight <= 1.0 at every date (weight invariant).
(d) news_sentiment_momentum: high-sentiment symbols dominate trades.
(e) insider_buying: high-net-buy symbols dominate trades.
(f) news_sentiment_momentum: mixed-evidence warning present in result.
(g) validate_strategy: warning fires for news_sentiment_momentum.
(h) Schema: new types accepted by StrategyJSON without validation error.
(i) Registry: SentimentSignalProvider and InsiderSignalProvider still in registry.
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
from app.services.strategy_validator import validate_strategy

# ── Synthetic data ────────────────────────────────────────────────────────────

SYMS  = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
START = date(2021, 1, 4)
END   = date(2022, 12, 30)
N     = 504


def _make_close_df(seed: int = 21) -> pd.DataFrame:
    dates = pd.date_range(START.isoformat(), periods=N, freq="B")
    data  = {}
    for i, sym in enumerate(SYMS):
        rng = np.random.default_rng(seed + i * 9)
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


def _base_strategy(**ov) -> StrategyJSON:
    base = dict(
        strategy_name="Alt Signal Test",
        strategy_type="news_sentiment_momentum",
        universe=SYMS,
        benchmark=SYMS[0],
        start_date=START,
        end_date=END,
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=[StrategyRule(top_pct=0.4)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    base.update(ov)
    return StrategyJSON(**base)


# ── Signal factories ──────────────────────────────────────────────────────────

def _sentiment_dense(symbol: str, rank: int, close_idx: pd.DatetimeIndex) -> pd.Series:
    """
    Daily-dense sentiment score (as SentimentSignalProvider would return after
    rolling 30-day mean). rank 0 = highest (SYM1=80), rank 4 = lowest (SYM5=40).
    """
    value = 80.0 - rank * 10.0
    return pd.Series([value] * len(close_idx), index=close_idx, name="sentiment_score")


def _insider_sparse(symbol: str, rank: int, close_idx: pd.DatetimeIndex) -> pd.Series:
    """
    Weekly sparse insider net-buy $ (positive = buying).
    rank 0 = highest ($2M/week), rank 4 = lowest ($0 or negative).
    """
    weekly_idx = pd.date_range(close_idx[0], close_idx[-1], freq="W-FRI")
    value = 2_000_000.0 - rank * 600_000.0   # SYM1=2M, SYM5=-400K
    return pd.Series([value] * len(weekly_idx), index=weekly_idx, name="insider_net_buy")


def _build_precomputed(close_idx: pd.DatetimeIndex, signal_name: str,
                        factory, ffill_limit=None):
    cols = {}
    for i, sym in enumerate(SYMS):
        sparse = factory(sym, i, close_idx)
        combined = sparse.index.union(close_idx)
        cols[sym] = sparse.reindex(combined).ffill(limit=ffill_limit).reindex(close_idx)
    return {signal_name: pd.DataFrame(cols, index=close_idx)}


async def _run(strategy: StrategyJSON, close_df: pd.DataFrame, signal_name: str,
               factory, ffill_limit=None):
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
    prebuilt = _build_precomputed(close_matrix.index, signal_name, factory, ffill_limit)

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

    return result, engine


# ── news_sentiment_momentum ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sentiment_momentum_valid_result():
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="news_sentiment_momentum",
                               rules=[StrategyRule(top_pct=0.4)])
    result, _ = await _run(strategy, close_df, "sentiment_score", _sentiment_dense)
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_sentiment_momentum_non_empty_trade_log():
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="news_sentiment_momentum",
                               rules=[StrategyRule(top_pct=0.4)])
    result, _ = await _run(strategy, close_df, "sentiment_score", _sentiment_dense)
    assert len(result.trade_log) > 0


@pytest.mark.asyncio
async def test_sentiment_momentum_weight_invariant():
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="news_sentiment_momentum",
                               rules=[StrategyRule(top_pct=0.4)])
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(strategy.start_date)]
    precomputed = _build_precomputed(close_matrix.index, "sentiment_score",
                                      _sentiment_dense)
    weights = engine._generate_weights(strategy, close_matrix, {}, precomputed)
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()


@pytest.mark.asyncio
async def test_sentiment_momentum_high_sentiment_symbols_selected():
    """SYM1 (80) and SYM2 (70) always have the top sentiment — they dominate trades."""
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="news_sentiment_momentum",
                               rules=[StrategyRule(top_pct=0.4)])
    result, _ = await _run(strategy, close_df, "sentiment_score", _sentiment_dense)
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Low-sentiment symbols in trades: {trade_syms - {'SYM1', 'SYM2'}}"
    )


@pytest.mark.asyncio
async def test_sentiment_momentum_mixed_evidence_warning_in_result():
    """BacktestResult.warnings must contain the mixed-evidence note."""
    close_df = _make_close_df()
    strategy = _base_strategy(strategy_type="news_sentiment_momentum",
                               rules=[StrategyRule(top_pct=0.4)])
    result, _ = await _run(strategy, close_df, "sentiment_score", _sentiment_dense)
    assert any("mixed" in w.lower() or "sentiment" in w.lower()
               for w in result.warnings), (
        f"Expected mixed-evidence warning, got: {result.warnings}"
    )


# ── insider_buying ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insider_buying_valid_result():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="insider_buying",
        rebalance_frequency="weekly",
        rules=[StrategyRule(top_n=2)],
    )
    result, _ = await _run(strategy, close_df, "insider_net_buy",
                            lambda sym, rank, idx: _insider_sparse(sym, rank, idx))
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_insider_buying_non_empty_trade_log():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="insider_buying",
        rebalance_frequency="weekly",
        rules=[StrategyRule(top_n=2)],
    )
    result, _ = await _run(strategy, close_df, "insider_net_buy",
                            lambda sym, rank, idx: _insider_sparse(sym, rank, idx))
    assert len(result.trade_log) > 0


@pytest.mark.asyncio
async def test_insider_buying_weight_invariant():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="insider_buying",
        rebalance_frequency="weekly",
        rules=[StrategyRule(top_n=2)],
    )
    engine = BacktestEngine()
    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(strategy.start_date)]
    precomputed = _build_precomputed(
        close_matrix.index, "insider_net_buy",
        lambda sym, rank, idx: _insider_sparse(sym, rank, idx),
    )
    weights = engine._generate_weights(strategy, close_matrix, {}, precomputed)
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()


@pytest.mark.asyncio
async def test_insider_buying_top_buyers_selected():
    """SYM1 ($2M) and SYM2 ($1.4M) have highest net buys — they dominate."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="insider_buying",
        rebalance_frequency="weekly",
        rules=[StrategyRule(top_n=2)],
    )
    result, _ = await _run(strategy, close_df, "insider_net_buy",
                            lambda sym, rank, idx: _insider_sparse(sym, rank, idx))
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Low-buying symbols in trades: {trade_syms - {'SYM1', 'SYM2'}}"
    )


# ── validate_strategy warning ─────────────────────────────────────────────────

def test_sentiment_momentum_validator_warning():
    """validate_strategy must emit the mixed-evidence warning."""
    s = _base_strategy(strategy_type="news_sentiment_momentum",
                        rules=[StrategyRule(top_pct=0.1)])
    warnings = validate_strategy(s)
    assert any("mixed" in w.lower() for w in warnings), (
        f"Expected 'mixed' in a warning, got: {warnings}"
    )


def test_insider_buying_no_extra_warning():
    """insider_buying should not trigger the sentiment warning."""
    s = _base_strategy(strategy_type="insider_buying",
                        rebalance_frequency="weekly",
                        rules=[StrategyRule(top_n=20)])
    warnings = validate_strategy(s)
    assert not any("mixed" in w.lower() for w in warnings)


# ── Schema acceptance ─────────────────────────────────────────────────────────

def test_news_sentiment_momentum_parses():
    s = _base_strategy(strategy_type="news_sentiment_momentum",
                        rules=[StrategyRule(top_pct=0.1)])
    assert s.strategy_type == "news_sentiment_momentum"


def test_insider_buying_parses():
    s = _base_strategy(strategy_type="insider_buying",
                        rebalance_frequency="weekly",
                        rules=[StrategyRule(top_n=20)])
    assert s.strategy_type == "insider_buying"


# ── Registry ──────────────────────────────────────────────────────────────────

def test_sentiment_provider_in_registry():
    from app.services.backtester.signal_provider import (
        SentimentSignalProvider,
        get_signal_provider,
    )
    p = get_signal_provider("sentiment_score")
    assert isinstance(p, SentimentSignalProvider)


def test_insider_provider_in_registry():
    from app.services.backtester.signal_provider import (
        InsiderSignalProvider,
        get_signal_provider,
    )
    p = get_signal_provider("insider_net_buy")
    assert isinstance(p, InsiderSignalProvider)
