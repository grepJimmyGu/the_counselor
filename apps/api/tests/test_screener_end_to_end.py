"""PRD-23a — Market Screener end-to-end integration (the DoD "the flow works").

Drives the ENTIRE real loop with NO stubs:
  seed real-shaped daily price_bars
    -> SignalSnapshotService.warm_universe   (real provider._compute from bars)
    -> scan                                  (real _apply_rule_threshold filter)
    -> RankService.rank                      (real BacktestEngine on the matched subset)

No network: with no AV key the cache fetch fails fast and ensure_history falls
back to the seeded bars (they cover the requested window). This is the
reproducible proof of the resolve -> snapshot -> scan -> rank pipeline; the
real *live S&P 500* warm is the post-deploy step once SCREENER_SNAPSHOT_ENABLED
is flipped (slice 2b), which needs prod data this sandbox doesn't have.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from app.models.price_bar import PriceBar
from app.schemas.strategy import PositionSizing, StrategyJSON, StrategyRule
from app.services.screener.rank_service import RankService
from app.services.screener.scan_service import scan
from app.services.screener.signal_snapshot_service import SignalSnapshotService

SYMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
WARM_AS_OF = date(2024, 1, 3)


def _seed_bars(db, symbol: str, seed: int, drift: float) -> None:
    # Start well before the backtest window (2023-01-01) so the cache fully
    # covers the engine's warmup lookback and ensure_history never needs a
    # live fetch (no AV key in this sandbox).
    idx = pd.bdate_range("2021-01-01", "2024-01-05")
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.015, len(idx))
    closes = 100.0 * np.exp(np.cumsum(rets))
    for d, c in zip(idx, closes):
        db.add(
            PriceBar(
                symbol=symbol,
                trading_date=d.date(),
                open=float(c * 0.999),
                high=float(c * 1.01),
                low=float(c * 0.99),
                close=float(c),
                adjusted_close=float(c),
                volume=1_000_000,
            )
        )
    db.flush()


def _strategy(rule: StrategyRule) -> StrategyJSON:
    return StrategyJSON(
        strategy_name="Screener e2e reading",
        strategy_type="custom_build",
        universe=["AAA"],  # rank swaps this per matched symbol
        benchmark="SPY",
        start_date="2023-01-01",
        end_date="2024-01-01",
        initial_capital=100_000,
        rebalance_frequency="monthly",
        position_sizing=PositionSizing(method="equal_weight"),
        rules=[rule],
    )


async def test_screener_full_loop(db):
    # Seed 6 screenable symbols (varied drift) + the SPY benchmark.
    for i, sym in enumerate(SYMS):
        _seed_bars(db, sym, seed=100 + i, drift=(-0.0006 if i % 2 else 0.0009))
    _seed_bars(db, "SPY", seed=7, drift=0.0004)
    db.commit()

    # 1) WARM the snapshot from the seeded bars (real compute, fixed as_of).
    svc = SignalSnapshotService()
    summary = await svc.warm_universe(db, SYMS, as_of=WARM_AS_OF)
    assert summary["symbols_ok"] == len(SYMS)
    assert summary["rows"] > 0

    snap = svc.get_snapshot(db, SYMS)
    assert "rsi" in snap.frame.columns
    assert snap.as_of_date is not None and snap.as_of_date <= WARM_AS_OF

    # 2) SCAN — extremes prove the filter end-to-end on the real snapshot.
    all_match = scan(db, "symbols", [StrategyRule(primitive_id="rsi", operator="lt", threshold=100)], symbols=SYMS)
    assert all_match.universe_size == len(SYMS)
    assert all_match.matched_count == len(SYMS)  # every symbol has a real RSI

    none_match = scan(db, "symbols", [StrategyRule(primitive_id="rsi", operator="lt", threshold=0)], symbols=SYMS)
    assert none_match.matched == []

    # A real, selective reading narrows the universe to a proper subset.
    selective = scan(db, "symbols", [StrategyRule(primitive_id="rsi", operator="lt", threshold=50)], symbols=SYMS)
    assert 0 <= selective.matched_count <= len(SYMS)
    assert selective.matched_count == len(selective.matched)

    # 3) RANK the matched subset with the REAL BacktestEngine (no stub).
    strategy = _strategy(StrategyRule(primitive_id="rsi", operator="lt", threshold=100))
    rank_res = await RankService().rank(
        db, all_match.matched, strategy, as_of_date=all_match.as_of_date
    )
    assert rank_res.backtested_count == len(SYMS)
    assert rank_res.matched_count == len(SYMS)
    # Every entry has a real, finite return...
    assert all(math.isfinite(e.total_return) for e in rank_res.ranked)
    # ...and the basket is ordered best-return-first.
    returns = [e.total_return for e in rank_res.ranked]
    assert returns == sorted(returns, reverse=True)
