"""A backtest over a short period, checked against arithmetic done by hand.

Jimmy, 2026-11-25: let a strategy be tested over any period from three months
up, "with precise calculation". The app only ever sent 3, 5 or 10 years, so
nothing had exercised the engine on a short period. Doing one by hand found
four things, each pinned here:

  1. The warm-up history was loaded and then cut off BEFORE the indicators
     were worked out. A 200-day-average strategy held cash for the first 200
     sessions of every test, and for all of a 3-month one: 0.00% return and
     0% of the time invested, on a price that was above its average every day.
  2. "Monthly" rebalanced only when the 1st of the month was a session: 7
     times in the year to 2026-11-23, not 12. The first quarter never did.
  3. Entering the position held on the first day cost nothing.
  4. Per-year figures compounded over one day too many.

The hand calculation uses nothing from the engine: it reads the same prices
and applies the rule as written on the strategy card.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from app.schemas.strategy import StrategyJSON
from app.services.backtester.engine import BACKTEST_ENGINE_VERSION, BacktestEngine
from app.services.backtester.metrics import compute_buy_and_hold, compute_metrics

END = date(2026, 11, 24)
# US market holidays inside the prices below: the sessions a real calendar skips.
HOLIDAYS = pd.to_datetime([
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04",
    "2025-09-01", "2025-11-27", "2025-12-25", "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
])


def _sessions(start: str = "2025-01-02", end: str = "2026-11-24") -> pd.DatetimeIndex:
    return pd.bdate_range(start, end).difference(HOLIDAYS)


def _prices(seed: int, drift: float = 0.0006) -> pd.DataFrame:
    """A fixed, wandering price history: the same numbers on every run."""
    index = _sessions()
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, 0.014, len(index)))), index=index).round(4)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "adjusted_close": close, "volume": 1_000_000}, index=index)


def _engine(frames: dict) -> BacktestEngine:
    engine = BacktestEngine()

    async def frame(_db, symbol, start, end, lookback_days=0):
        full = frames[symbol]
        first = pd.Timestamp(start - timedelta(days=lookback_days + 10))
        return full[(full.index >= first) & (full.index <= pd.Timestamp(end))]

    engine.market_data.get_price_frame = frame  # type: ignore[method-assign]
    engine.market_data.ensure_last_close = AsyncMock()  # type: ignore[attr-defined]
    return engine


def _months_before(end: date, months: int) -> date:
    return (pd.Timestamp(end) - pd.DateOffset(months=months)).date()


def _strategy(start: date, window: int, cost_bps: float = 5, slippage_bps: float = 5,
              strategy_type: str = "moving_average_filter", rules: Optional[List[dict]] = None,
              universe: Optional[List[str]] = None, rebalance: str = "daily") -> StrategyJSON:
    return StrategyJSON.model_validate({
        "strategy_name": "Short period audit", "strategy_type": strategy_type,
        "universe": universe or ["AAA"], "benchmark": "BBB",
        "start_date": start.isoformat(), "end_date": END.isoformat(), "initial_capital": 100_000,
        "rebalance_frequency": rebalance, "rules": rules if rules is not None else [{"lookback_days": window}],
        "position_sizing": {"method": "equal_weight"},
        "transaction_cost_bps": cost_bps, "slippage_bps": slippage_bps,
    })


def _by_hand(close: pd.Series, start: date, window: int, cost: float) -> dict:
    """Hold the stock on any day after a close above its `window`-day average.

    Worked on the whole history, as a person with a chart would: the average
    on the first day of the test is the average of the `window` closes up to
    and including that day.
    """
    average = [np.nan] * len(close)
    values = close.to_numpy()
    for i in range(window - 1, len(values)):
        average[i] = values[i - window + 1: i + 1].sum() / window
    holds_after_close = [bool(values[i] > average[i]) for i in range(len(values))]

    days = [i for i, day in enumerate(close.index) if day >= pd.Timestamp(start)]
    equity = 1.0
    curve = []
    invested_days = 0
    for position, i in enumerate(days):
        held_today = holds_after_close[i - 1] if position > 0 else False  # the test starts in cash
        day_return = (values[i] / values[i - 1] - 1.0) if held_today else 0.0
        before = held_today
        after = holds_after_close[i]
        traded = 1.0 if before != after else 0.0
        equity *= 1.0 + day_return - traded * cost
        curve.append(equity)
        invested_days += 1 if after else 0
    return {
        "total_return": curve[-1] - 1.0,
        "first_day_equity": curve[0],
        "holds_on_first_day": holds_after_close[days[0]],
        "time_in_market": invested_days / len(days),
        "days": len(days),
    }


# ── 1. Indicators are warm on the first day ──────────────────────────────────

async def test_regression_a_three_month_test_of_a_200_day_average_is_invested_from_day_one() -> None:
    """The reported shape: three months, a 200-day average, a rising stock."""
    frames = {"AAA": _prices(7, drift=0.0025), "BBB": _prices(11)}
    close = frames["AAA"]["adjusted_close"]
    start = _months_before(END, 3)
    hand = _by_hand(close, start, window=200, cost=0.0010)
    # The case is only a test of the warm-up if the stock is above its
    # average at the start, so that cash would be the wrong answer.
    assert hand["holds_on_first_day"] and hand["time_in_market"] > 0.9

    result = await _engine(frames).run(MagicMock(), _strategy(start, 200))

    # Before the fix: total_return 0.0, time_in_market 0.0, no trades.
    assert result.metrics.time_in_market == pytest.approx(hand["time_in_market"])
    assert result.metrics.total_return == pytest.approx(hand["total_return"], abs=1e-12)
    assert result.current_weights == {"AAA": 1.0}
    assert result.engine_version == BACKTEST_ENGINE_VERSION == "2026.11.25"


@pytest.mark.parametrize("months", [3, 4, 5, 7, 12, 18])
@pytest.mark.parametrize("window", [20, 50, 200])
@pytest.mark.parametrize("seed", [3, 7])
async def test_every_period_from_three_months_up_matches_the_hand_calculation(
    months: int, window: int, seed: int
) -> None:
    frames = {"AAA": _prices(seed), "BBB": _prices(11)}
    start = _months_before(END, months)
    hand = _by_hand(frames["AAA"]["adjusted_close"], start, window, cost=0.0010)

    result = await _engine(frames).run(MagicMock(), _strategy(start, window))

    assert len(result.equity_curve) == hand["days"]
    assert result.equity_curve[0].date >= start
    assert result.equity_curve[-1].date == END
    assert result.metrics.total_return == pytest.approx(hand["total_return"], abs=1e-12)
    assert result.metrics.time_in_market == pytest.approx(hand["time_in_market"])
    assert result.equity_curve[0].value == pytest.approx(100_000 * hand["first_day_equity"], abs=1e-6)
    # The benchmark over exactly the same days.
    bench = frames["BBB"]["adjusted_close"]
    bench = bench[bench.index >= pd.Timestamp(start)]
    assert result.metrics.benchmark_total_return == pytest.approx(bench.iloc[-1] / bench.iloc[0] - 1.0, abs=1e-12)


async def test_a_momentum_ranking_has_its_lookback_on_the_first_day() -> None:
    """Rank three stocks by six-month return and hold the best one, monthly."""
    frames = {"AAA": _prices(3), "CCC": _prices(5, drift=0.002), "DDD": _prices(9, drift=-0.001), "BBB": _prices(11)}
    start = _months_before(END, 3)
    strategy = _strategy(
        start, 126, strategy_type="momentum_rotation", universe=["AAA", "CCC", "DDD"], rebalance="monthly",
        rules=[{"ranking_lookback_days": 126, "top_n": 1}], cost_bps=0, slippage_bps=0,
    )
    result = await _engine(frames).run(MagicMock(), strategy)

    # By hand: on the first session of each month, the stock with the best
    # 126-session return; held until the next first session.
    closes = pd.concat([frames[s]["adjusted_close"].rename(s) for s in ("AAA", "CCC", "DDD")], axis=1)
    score = closes / closes.shift(126) - 1.0
    months = pd.Series(closes.index.to_period("M"), index=closes.index)
    first_sessions = closes.index[~months.duplicated()]
    held = pd.Series(index=closes.index, dtype=object)
    for day in first_sessions:
        if score.loc[day].notna().all():
            held[day] = score.loc[day].idxmax()
    held = held.ffill()
    in_test = closes.index[closes.index >= pd.Timestamp(start)]
    equity = 1.0
    for position, day in enumerate(in_test):
        if position == 0:
            continue
        symbol = held[in_test[position - 1]]
        previous = closes.index[closes.index.get_loc(day) - 1]
        equity *= closes.loc[day, symbol] / closes.loc[previous, symbol]

    # It holds something from the first day (before: nothing for six months).
    assert held[in_test[0]] in ("AAA", "CCC", "DDD")
    assert result.metrics.time_in_market == 1.0
    assert result.metrics.total_return == pytest.approx(equity - 1.0, abs=1e-12)


# ── 2. Rebalance dates ───────────────────────────────────────────────────────

def test_regression_monthly_means_the_first_session_of_every_month() -> None:
    engine = BacktestEngine()
    year = _sessions("2025-11-24", "2026-11-23")

    monthly = year[engine._rebalance_mask(year, "monthly").to_numpy()]
    # Every month has one. Before: 7, with Jan, Feb, Mar, Aug and Nov skipped
    # because their 1st was a holiday or a weekend.
    assert [d.strftime("%Y-%m-%d") for d in monthly] == [
        "2025-11-24", "2025-12-01", "2026-01-02", "2026-02-02", "2026-03-02", "2026-04-01", "2026-05-01",
        "2026-06-01", "2026-07-01", "2026-08-03", "2026-09-01", "2026-10-01", "2026-11-02",
    ]

    quarterly = year[engine._rebalance_mask(year, "quarterly").to_numpy()]
    # 1 January is always a holiday, so the first quarter never rebalanced.
    assert [d.strftime("%Y-%m-%d") for d in quarterly] == [
        "2025-11-24", "2026-01-02", "2026-04-01", "2026-07-01", "2026-10-01",
    ]

    weekly = year[engine._rebalance_mask(year, "weekly").to_numpy()]
    # One a week, on Tuesday when Monday is a holiday (before: 49 of 53 weeks).
    assert len(weekly) == year.to_period("W").nunique() == 53
    assert pd.Timestamp("2026-01-20") in weekly and pd.Timestamp("2026-01-19") not in year

    assert engine._rebalance_mask(year, "daily").all()


# ── 3. The first day's entry is paid for ─────────────────────────────────────

async def test_a_test_that_starts_invested_pays_to_get_in() -> None:
    frames = {"AAA": _prices(7, drift=0.0025), "BBB": _prices(11)}
    start = _months_before(END, 3)
    result = await _engine(frames).run(MagicMock(), _strategy(start, 200, cost_bps=5, slippage_bps=5))
    free = await _engine(frames).run(MagicMock(), _strategy(start, 200, cost_bps=0, slippage_bps=0))

    # Held from the first day: 10 bps to enter comes off before any return.
    assert free.equity_curve[0].value == pytest.approx(100_000)
    assert result.equity_curve[0].value == pytest.approx(100_000 * (1 - 0.0010))


# ── 4. Per-year figures ──────────────────────────────────────────────────────

def test_a_year_of_daily_returns_compounds_to_its_own_total() -> None:
    """253 days are 252 daily returns: a year. Its per-year return is its total."""
    daily = 1.10 ** (1 / 252) - 1.0
    index = pd.bdate_range("2025-01-01", periods=253)
    returns = pd.Series([0.0] + [daily] * 252, index=index)
    metrics = compute_metrics(
        portfolio_returns=returns, benchmark_returns=returns, trade_returns=[], holding_periods=[],
        turnover_series=pd.Series(0.0, index=index), time_in_market_series=pd.Series(1.0, index=index),
    )
    assert metrics["total_return"] == pytest.approx(0.10)
    assert metrics["annualized_return"] == pytest.approx(0.10)  # before: 0.0996

    prices = pd.Series((1.0 + returns).cumprod() * 50, index=index)
    held = compute_buy_and_hold(prices, 100_000, len(prices))
    assert held["buy_and_hold_annualized_return"] == pytest.approx(0.10)


def test_a_quarter_is_annualised_over_its_own_returns() -> None:
    """64 days are 63 returns; 5% over them is (1.05)^(252/63) - 1 a year."""
    index = pd.bdate_range("2026-08-24", periods=64)
    daily = 1.05 ** (1 / 63) - 1.0
    returns = pd.Series([0.0] + [daily] * 63, index=index)
    metrics = compute_metrics(
        portfolio_returns=returns, benchmark_returns=returns, trade_returns=[], holding_periods=[],
        turnover_series=pd.Series(0.0, index=index), time_in_market_series=pd.Series(1.0, index=index),
    )
    assert metrics["annualized_return"] == pytest.approx(1.05 ** 4 - 1.0)


# ── A period with no prices ──────────────────────────────────────────────────

async def test_a_period_after_the_last_price_is_a_clear_error() -> None:
    frames = {"AAA": _prices(7), "BBB": _prices(11)}
    strategy = StrategyJSON.model_validate({
        **_strategy(date(2026, 8, 24), 20).model_dump(mode="json"),
        "start_date": "2026-11-25", "end_date": "2026-12-25",
    })
    with pytest.raises(ValueError, match="No historical data"):
        await _engine(frames).run(MagicMock(), strategy)
