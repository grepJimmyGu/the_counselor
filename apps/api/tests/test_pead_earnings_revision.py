"""
Integration tests for pead_drift and earnings_revision strategy templates.

Setup
-----
- 5 synthetic symbols (SYM1–SYM5) with 2 years of daily price data.
- Signals are injected via patched _fetch_signal_matrix so no live FMP calls.
- _load_prices is patched to return synthetic price frames.

Assertions per strategy
-----------------------
(a) engine.run() returns a valid BacktestResult with finite total_return.
(b) trade_log is non-empty.
(c) Total weight <= 1.0 at every date (weight invariant).
(d) pead_drift: only high-SUE symbols appear in trades.
(e) pead_drift microcap warning fires when avg market cap < $300M.
(f) pead_drift no microcap warning when avg market cap >= $300M.
(g) earnings_revision: only high-revision symbols appear in trades.
(h) holding_window_days: StrategyRule field parses and is accessible.
(i) estimate_revision_3m: registered in signal provider registry.
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

SYMS   = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
N_DAYS = 504
START  = date(2021, 1, 4)
END    = date(2022, 12, 30)
LAG    = 45    # report_date_lag in days


def _make_close_df(seed: int = 13) -> pd.DataFrame:
    dates = pd.date_range(START.isoformat(), periods=N_DAYS, freq="B")
    data = {}
    for i, sym in enumerate(SYMS):
        rng = np.random.default_rng(seed + i * 7)
        data[sym] = 100.0 * np.cumprod(1 + rng.normal(3e-4, 0.015, N_DAYS))
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
        strategy_name="Event Test",
        strategy_type="pead_drift",
        universe=SYMS,
        benchmark=SYMS[0],
        start_date=START,
        end_date=END,
        initial_capital=100_000,
        rebalance_frequency="weekly",
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=[],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    base.update(ov)
    return StrategyJSON(**base)


# ── Signal factories ──────────────────────────────────────────────────────────

def _sue_sparse(symbol: str, start: date, end: date, rank: int) -> pd.Series:
    """
    Quarterly SUE dated at period_end + LAG.
    rank 0 (SYM1) = highest SUE (2.0), rank 4 (SYM5) = lowest (-1.0).
    """
    period_ends = pd.date_range(
        (start - timedelta(days=2 * 365)).isoformat(),
        end.isoformat(),
        freq="QE",
    )
    disc = period_ends + pd.Timedelta(days=LAG)
    values = [2.0 - rank * 0.75] * len(disc)   # SYM1=2.0, SYM2=1.25, SYM3=0.5, …
    return pd.Series(values, index=disc, name="earnings_surprise")


def _rev_sparse(symbol: str, start: date, end: date, rank: int) -> pd.Series:
    period_ends = pd.date_range(
        (start - timedelta(days=2 * 365)).isoformat(),
        end.isoformat(),
        freq="QE",
    )
    disc = period_ends + pd.Timedelta(days=LAG)
    values = [0.30 - rank * 0.08] * len(disc)   # SYM1=0.30, SYM5=-0.02
    return pd.Series(values, index=disc, name="estimate_revision_3m")


# ── Engine run helpers ────────────────────────────────────────────────────────

def _build_signal_matrix(close_idx, signal_factory, holding_window=None):
    """Build a precomputed_signals dict using the given factory."""
    cols = {}
    for i, sym in enumerate(SYMS):
        sparse = signal_factory(sym, i)
        combined = sparse.index.union(close_idx)
        cols[sym] = sparse.reindex(combined).ffill(limit=holding_window).reindex(close_idx)
    signal_name = next(iter(cols.values())).name if cols else "signal"
    # Get name from the first series
    first_sparse = signal_factory(SYMS[0], 0)
    return {first_sparse.name: pd.DataFrame(cols, index=close_idx)}


async def _run(strategy: StrategyJSON, close_df: pd.DataFrame,
               signal_factory=None, holding_window=None):
    engine = BacktestEngine()
    db = MagicMock()
    load_return = _price_frames(close_df)

    # Build precomputed signals from factory if provided
    if signal_factory is not None:
        close_matrix, _ = engine._build_price_matrix(
            {sym: pd.DataFrame(
                {"adjusted_close": close_df[sym].values,
                 "high": (close_df[sym] * 1.01).values},
                index=close_df.index,
            ) for sym in close_df.columns}
        )
        close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(strategy.start_date)]
        prebuilt_signals = _build_signal_matrix(
            close_matrix.index, signal_factory, holding_window
        )
    else:
        prebuilt_signals = None

    async def _fake_fetch(providers, universe, db, close_index, sig_start, sig_end,
                          ffill_limit=None):
        if prebuilt_signals is not None:
            return prebuilt_signals
        return {}

    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)), \
         patch.object(engine, "_fetch_signal_matrix",
                      new=AsyncMock(side_effect=_fake_fetch)), \
         patch.object(engine, "_check_microcap", new=AsyncMock(return_value=[])):
        result = await engine.run(db, strategy)

    return result, engine


async def _run_with_microcap_check(strategy, close_df, signal_factory,
                                    mock_caps: dict):
    """Run with real _check_microcap against a mock DB."""
    engine = BacktestEngine()
    db = MagicMock()
    load_return = _price_frames(close_df)

    close_matrix, _ = engine._build_price_matrix(
        {sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        ) for sym in close_df.columns}
    )
    close_matrix = close_matrix[close_matrix.index >= pd.Timestamp(strategy.start_date)]
    prebuilt_signals = _build_signal_matrix(close_matrix.index, signal_factory)

    # Mock DB execute to return market caps
    rows = [(mock_caps.get(sym, None),) for sym in strategy.universe]
    db.execute.return_value.fetchall.return_value = rows

    async def _fake_fetch(providers, universe, _db, close_index, sig_start, sig_end,
                          ffill_limit=None):
        return prebuilt_signals

    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)), \
         patch.object(engine, "_fetch_signal_matrix",
                      new=AsyncMock(side_effect=_fake_fetch)):
        result = await engine.run(db, strategy)

    return result


# ── pead_drift tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pead_drift_valid_result():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.4, holding_window_days=60)],
    )
    result, _ = await _run(
        strategy, close_df,
        signal_factory=lambda sym, rank: _sue_sparse(sym, START, END, rank),
    )
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_pead_drift_non_empty_trade_log():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.4, holding_window_days=60)],
    )
    result, _ = await _run(
        strategy, close_df,
        signal_factory=lambda sym, rank: _sue_sparse(sym, START, END, rank),
    )
    assert len(result.trade_log) > 0


@pytest.mark.asyncio
async def test_pead_drift_weight_invariant():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.4, holding_window_days=60)],
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
    precomputed = _build_signal_matrix(
        close_matrix.index,
        lambda sym, rank: _sue_sparse(sym, START, END, rank),
        holding_window=60,
    )
    weights = engine._generate_weights(strategy, close_matrix, {}, precomputed)
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()


@pytest.mark.asyncio
async def test_pead_drift_high_sue_symbols_selected():
    """SYM1 (SUE=2.0) and SYM2 (SUE=1.25) are always top-decile."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.4, holding_window_days=60)],
    )
    result, _ = await _run(
        strategy, close_df,
        signal_factory=lambda sym, rank: _sue_sparse(sym, START, END, rank),
    )
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Low-SUE symbols in trade log: {trade_syms - {'SYM1', 'SYM2'}}"
    )


# ── pead_drift holding_window_days ────────────────────────────────────────────

def test_holding_window_days_field_in_strategy_rule():
    rule = StrategyRule(holding_window_days=45)
    assert rule.holding_window_days == 45


def test_holding_window_days_default_none():
    rule = StrategyRule()
    assert rule.holding_window_days is None


def test_holding_window_in_full_strategy_parses():
    s = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.2, holding_window_days=30)],
    )
    assert s.rules[0].holding_window_days == 30


# ── pead_drift microcap warnings ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pead_microcap_warning_fires():
    """Avg market cap < $300M → warning in BacktestResult.warnings."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.4, holding_window_days=60)],
    )
    # All symbols are microcaps ($100M each)
    mock_caps = {sym: 100_000_000.0 for sym in SYMS}
    result = await _run_with_microcap_check(
        strategy, close_df,
        lambda sym, rank: _sue_sparse(sym, START, END, rank),
        mock_caps=mock_caps,
    )
    assert any("microcap" in w.lower() or "$300M" in w for w in result.warnings), (
        f"Expected microcap warning, got: {result.warnings}"
    )


@pytest.mark.asyncio
async def test_pead_no_microcap_warning_largecap():
    """Avg market cap >= $300M → no microcap warning."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.4, holding_window_days=60)],
    )
    # All symbols are large-cap ($50B each)
    mock_caps = {sym: 50_000_000_000.0 for sym in SYMS}
    result = await _run_with_microcap_check(
        strategy, close_df,
        lambda sym, rank: _sue_sparse(sym, START, END, rank),
        mock_caps=mock_caps,
    )
    assert not any("microcap" in w.lower() for w in result.warnings), (
        f"Unexpected microcap warning for large-cap: {result.warnings}"
    )


@pytest.mark.asyncio
async def test_pead_no_microcap_warning_when_caps_missing():
    """If market cap data is absent for all symbols, no warning (fail-safe)."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="pead_drift",
        rules=[StrategyRule(top_pct=0.4, holding_window_days=60)],
    )
    mock_caps = {}   # no market cap data
    result = await _run_with_microcap_check(
        strategy, close_df,
        lambda sym, rank: _sue_sparse(sym, START, END, rank),
        mock_caps=mock_caps,
    )
    assert not any("microcap" in w.lower() for w in result.warnings)


# ── earnings_revision tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_earnings_revision_valid_result():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="earnings_revision",
        rebalance_frequency="monthly",
        rules=[StrategyRule(top_pct=0.4)],
    )
    result, _ = await _run(
        strategy, close_df,
        signal_factory=lambda sym, rank: _rev_sparse(sym, START, END, rank),
    )
    assert result.metrics is not None
    assert np.isfinite(result.metrics.total_return)


@pytest.mark.asyncio
async def test_earnings_revision_non_empty_trade_log():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="earnings_revision",
        rebalance_frequency="monthly",
        rules=[StrategyRule(top_pct=0.4)],
    )
    result, _ = await _run(
        strategy, close_df,
        signal_factory=lambda sym, rank: _rev_sparse(sym, START, END, rank),
    )
    assert len(result.trade_log) > 0


@pytest.mark.asyncio
async def test_earnings_revision_weight_invariant():
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="earnings_revision",
        rebalance_frequency="monthly",
        rules=[StrategyRule(top_pct=0.4)],
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
    precomputed = _build_signal_matrix(
        close_matrix.index,
        lambda sym, rank: _rev_sparse(sym, START, END, rank),
    )
    weights = engine._generate_weights(strategy, close_matrix, {}, precomputed)
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()


@pytest.mark.asyncio
async def test_earnings_revision_top_symbols_selected():
    """SYM1 and SYM2 have the highest revision scores → they dominate trades."""
    close_df = _make_close_df()
    strategy = _base_strategy(
        strategy_type="earnings_revision",
        rebalance_frequency="monthly",
        rules=[StrategyRule(top_pct=0.4)],
    )
    result, _ = await _run(
        strategy, close_df,
        signal_factory=lambda sym, rank: _rev_sparse(sym, START, END, rank),
    )
    trade_syms = {t.symbol for t in result.trade_log}
    assert trade_syms.issubset({"SYM1", "SYM2"}), (
        f"Low-revision symbols in trade log: {trade_syms - {'SYM1', 'SYM2'}}"
    )


# ── signal_provider registry ──────────────────────────────────────────────────

def test_estimate_revision_3m_in_registry():
    from app.services.backtester.signal_provider import (
        FundamentalSignalProvider,
        get_signal_provider,
    )
    p = get_signal_provider("estimate_revision_3m")
    assert isinstance(p, FundamentalSignalProvider)
    assert p.name == "estimate_revision_3m"


def test_estimate_revision_3m_in_fundamental_supported():
    from app.services.backtester.signal_provider import FundamentalSignalProvider
    assert "estimate_revision_3m" in FundamentalSignalProvider.SUPPORTED


# ── estimate_revision_3m provider unit test ───────────────────────────────────

@pytest.mark.asyncio
async def test_estimate_revision_3m_provider_shape():
    from app.services.backtester.signal_provider import FundamentalSignalProvider

    # Quarterly incomes with growing EPS: 8 periods
    incomes = [
        {"date": f"202{y}-{m:02d}-30", "epsDiluted": 1.0 + 0.1 * i}
        for i, (y, m) in enumerate([
            (0, 3), (0, 6), (0, 9), (0, 12),
            (1, 3), (1, 6), (1, 9), (1, 12),
        ])
    ]

    provider = FundamentalSignalProvider("estimate_revision_3m", report_date_lag=45)
    with patch.object(provider._fmp, "get_income_statement",
                      new=AsyncMock(return_value=incomes)):
        s = await provider.get_signal_frame(
            MagicMock(), "AAPL", date(2021, 1, 1), date(2022, 12, 31)
        )

    assert isinstance(s, pd.Series)
    assert s.name == "estimate_revision_3m"
    if not s.empty:
        # Positive revision expected (EPS growing)
        assert (s > 0).all(), f"Expected positive revisions, got: {s.values}"
        # Disclosure dates = period_end + 45 days
        for ts in s.index:
            period_end = ts - pd.Timedelta(days=45)
            assert period_end.month in (3, 6, 9, 12), (
                f"Unexpected period-end month: {period_end.month}"
            )
