"""PRD-23a slice 5 — rank service.

Backtest the matched subset and rank by return. Verifies ordering, the
top-K cap with cheap-proxy pre-order, the (symbol, rule_hash, as_of_date)
cache, rule_hash stability, and that failed backtests are skipped — all with
a stub backtest_fn (no real prices needed).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.schemas.strategy import PositionSizing, StrategyJSON, StrategyRule
from app.services.screener.rank_service import (
    RankedEntry,
    RankService,
    rule_hash,
)

AS_OF = date(2026, 6, 15)


def _strategy(rules=None) -> StrategyJSON:
    return StrategyJSON(
        strategy_name="Screener reading",
        strategy_type="custom_build",
        universe=["SPY"],
        benchmark="SPY",
        start_date="2023-01-01",
        end_date="2024-01-01",
        initial_capital=100_000,
        rebalance_frequency="monthly",
        position_sizing=PositionSizing(method="equal_weight"),
        rules=rules or [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)],
    )


def _stub(returns, calls=None):
    async def fn(db, symbol, sj):
        if calls is not None:
            calls.append(symbol)
        r = returns.get(symbol)
        return None if r is None else RankedEntry(symbol=symbol, total_return=r)

    return fn


async def test_ranks_by_total_return_desc():
    svc = RankService()
    res = await svc.rank(
        None,
        ["AAPL", "MSFT", "TSLA"],
        _strategy(),
        as_of_date=AS_OF,
        backtest_fn=_stub({"AAPL": 0.10, "MSFT": 0.30, "TSLA": 0.20}),
    )
    assert [e.symbol for e in res.ranked] == ["MSFT", "TSLA", "AAPL"]
    assert res.backtested_count == 3
    assert res.matched_count == 3
    assert res.dropped_count == 0


async def test_top_k_cap_uses_proxy_preorder():
    svc = RankService()
    calls = []
    matched = ["A", "B", "C", "D", "E"]
    proxy = {"A": 1, "B": 5, "C": 4, "D": 2, "E": 3}  # top-2 by proxy: B, C
    res = await svc.rank(
        None,
        matched,
        _strategy(),
        as_of_date=AS_OF,
        top_k=2,
        proxy_scores=proxy,
        backtest_fn=_stub({s: 0.1 for s in matched}, calls),
    )
    assert set(calls) == {"B", "C"}  # only the top-2 proxy names backtested
    assert res.dropped_count == 3
    assert res.backtested_count == 2


async def test_cache_skips_second_backtest():
    svc = RankService()
    calls = []
    fn = _stub({"AAPL": 0.1, "MSFT": 0.2}, calls)
    await svc.rank(None, ["AAPL", "MSFT"], _strategy(), as_of_date=AS_OF, backtest_fn=fn)
    assert len(calls) == 2
    # Same reading + same snapshot day → all cache hits, no new backtests.
    await svc.rank(None, ["AAPL", "MSFT"], _strategy(), as_of_date=AS_OF, backtest_fn=fn)
    assert len(calls) == 2


async def test_cache_invalidates_on_new_as_of():
    svc = RankService()
    calls = []
    fn = _stub({"AAPL": 0.1}, calls)
    await svc.rank(None, ["AAPL"], _strategy(), as_of_date=AS_OF, backtest_fn=fn)
    await svc.rank(None, ["AAPL"], _strategy(), as_of_date=date(2026, 6, 16), backtest_fn=fn)
    assert len(calls) == 2  # new snapshot day → re-backtest


async def test_failed_backtest_is_skipped():
    svc = RankService()
    res = await svc.rank(
        None,
        ["AAPL", "MSFT"],
        _strategy(),
        as_of_date=AS_OF,
        backtest_fn=_stub({"AAPL": 0.1, "MSFT": None}),  # MSFT fails
    )
    assert [e.symbol for e in res.ranked] == ["AAPL"]
    assert res.backtested_count == 1


def test_rule_hash_stable_and_universe_independent():
    s1 = _strategy()
    s2 = _strategy()
    assert rule_hash(s1) == rule_hash(s2)
    # Universe change doesn't change the reading hash.
    s3 = s1.model_copy(update={"universe": ["AAPL"]})
    assert rule_hash(s3) == rule_hash(s1)
    # Rule change does.
    s4 = _strategy(rules=[StrategyRule(primitive_id="rsi", operator="lt", threshold=40)])
    assert rule_hash(s4) != rule_hash(s1)
