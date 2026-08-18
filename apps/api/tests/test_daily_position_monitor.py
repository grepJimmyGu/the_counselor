"""Daily exit monitor — one run per session, after the close.

Like the intraday monitor, this job DETECTS and NOTIFIES; it never mutates
`shares_remaining` / `is_open` / `final_pnl`. The user sells in their own
brokerage the next morning and confirms.

What is deliberately different from the intraday job, and pinned here:
  - tier identity comes from the shared evaluator, so a second negative
    tier cannot disarm the hard stop
  - a split refuses evaluation instead of firing a false "sell everything"
  - one bad position does not kill the rest of the strategy's positions
  - the banner carries a real strategy_slug, so it links somewhere
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest

from app.jobs.daily_position_jobs import (
    _evaluate_position,
    _monitor_daily_positions_async,
)
from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy
from app.schemas.strategy import ExitTier


# ── helpers ─────────────────────────────────────────────────────────────────


def _position(entry: float = 100.0, shares: float = 120.0, log=None) -> PositionState:
    return PositionState(
        id=str(uuid4()),
        saved_strategy_id="s1",
        symbol="MSFT",
        entered_at=datetime.utcnow(),
        entry_price=entry,
        shares_initial=shares,
        shares_remaining=shares,
        trade_log=log if log is not None else [],
        is_open=True,
    )


def _bars(close: float, *, high=None, low=None, split: float = 1.0) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-08-17", "2026-08-18"])
    return pd.DataFrame(
        {
            "open": [close, close],
            "high": [high if high is not None else close] * 2,
            "low": [low if low is not None else close] * 2,
            "close": [close, close],
            "adjusted_close": [close, close],
            "split_coefficient": [1.0, split],
        },
        index=idx,
    )


def _market(frame: pd.DataFrame) -> MagicMock:
    md = MagicMock()
    md.get_price_frame = AsyncMock(return_value=frame)
    return md


def _ladder():
    return [
        ExitTier(trigger_pct=-0.08, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=1 / 3, label="TP1"),
        ExitTier(trigger_pct=+0.30, action="sell_fraction", fraction=1 / 3, label="TP2"),
    ]


def _stats():
    return {
        "strategies_checked": 0, "positions_monitored": 0, "events_fired": 0,
        "notifications_sent": 0, "skipped_no_bar": 0,
        "skipped_corporate_action": 0, "errors": 0,
    }


# ── _evaluate_position ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_fires_and_records_without_mutating_the_position():
    pos = _position()
    db, stats = MagicMock(), _stats()
    fires = await _evaluate_position(
        db, _market(_bars(90.0)), pos, _ladder(), stats, today=date(2026, 8, 18),
    )
    assert len(fires) == 1
    assert fires[0].action == "sell_all"

    # Recorded, but nothing sold: Livermore has not observed a sale.
    assert pos.trade_log[-1]["status"] == "pending_confirmation"
    assert pos.trade_log[-1]["shares"] == pytest.approx(120.0)
    assert pos.shares_remaining == 120.0
    assert pos.is_open is True


@pytest.mark.asyncio
async def test_price_inside_the_ladder_fires_nothing():
    pos = _position()
    stats = _stats()
    fires = await _evaluate_position(
        MagicMock(), _market(_bars(101.0)), pos, _ladder(), stats,
        today=date(2026, 8, 18),
    )
    assert fires == []
    assert pos.trade_log == []


@pytest.mark.asyncio
async def test_a_gap_fires_both_targets_in_one_run():
    """A daily bar can clear more than one rung. Reporting only the first
    would leave the second waiting a whole session."""
    pos = _position()
    stats = _stats()
    fires = await _evaluate_position(
        MagicMock(), _market(_bars(135.0)), pos, _ladder(), stats,
        today=date(2026, 8, 18),
    )
    assert [f.tier_index for f in fires] == [1, 2]
    assert len(pos.trade_log) == 2


@pytest.mark.asyncio
async def test_already_fired_tier_never_refires():
    pos = _position(log=[{"event": "tier0_hit", "status": "pending_confirmation"}])
    stats = _stats()
    fires = await _evaluate_position(
        MagicMock(), _market(_bars(90.0)), pos, _ladder(), stats,
        today=date(2026, 8, 18),
    )
    assert fires == []


@pytest.mark.asyncio
async def test_REGRESSION_a_split_does_not_fire_a_false_sell_everything():
    """A 2:1 split halves the raw price. The position's entry_price is the
    user's real fill in real dollars, so the bar reads as -50% and the stop
    would fire on a position that did not move. Refuse instead: a missed
    day is recoverable, a false liquidation instruction is not.
    """
    pos = _position(entry=100.0)
    stats = _stats()
    fires = await _evaluate_position(
        MagicMock(), _market(_bars(50.0, split=2.0)), pos, _ladder(), stats,
        today=date(2026, 8, 18),
    )
    assert fires == []
    assert pos.trade_log == []
    assert stats["skipped_corporate_action"] == 1


@pytest.mark.asyncio
async def test_missing_bar_is_skipped_not_raised():
    """Holidays, halts and thin symbols all produce this. It must not
    escape into the job loop."""
    pos = _position()
    stats = _stats()
    fires = await _evaluate_position(
        MagicMock(), _market(pd.DataFrame()), pos, _ladder(), stats,
        today=date(2026, 8, 18),
    )
    assert fires == []
    assert stats["skipped_no_bar"] == 1


@pytest.mark.asyncio
async def test_the_daily_bar_high_and_low_reach_the_evaluator():
    """The evaluator decides whether to use them (TRIGGER_FIELD), but the
    job must supply real extremes so flipping that constant needs no change
    here. A daily bar is final, so its high/low are trustworthy."""
    captured = {}

    def _spy(*, ladder, entry_price, bar, already_fired=None):
        captured["bar"] = bar
        return []

    with patch("app.jobs.daily_position_jobs.evaluate_bar", side_effect=_spy):
        await _evaluate_position(
            MagicMock(), _market(_bars(100.0, high=112.0, low=88.0)),
            _position(), _ladder(), _stats(), today=date(2026, 8, 18),
        )
    assert captured["bar"].high == 112.0
    assert captured["bar"].low == 88.0
    assert captured["bar"].close == 100.0


# ── the monitor walk ────────────────────────────────────────────────────────


def _strategy(bar_resolution: str = "daily", ladder=True) -> SavedStrategy:
    rm = {"exit_ladder": [
        {"trigger_pct": -0.08, "action": "sell_all", "label": "Stop"},
    ]} if ladder else {}
    return SavedStrategy(
        id="s1",
        user_id="u1",
        title="Daily runner",
        strategy_json={
            "strategy_name": "Daily runner",
            "strategy_type": "moving_average_filter",
            "universe": ["MSFT"], "benchmark": "SPY",
            "start_date": "2025-01-01", "end_date": "2025-12-31",
            "initial_capital": 100_000, "rebalance_frequency": "monthly",
            "position_sizing": {"method": "equal_weight"},
            "rules": [{"ma_window": 50}],
            "bar_resolution": bar_resolution,
            "risk_management": rm,
        },
        is_public=False,
    )


@pytest.mark.asyncio
async def test_intraday_strategies_are_left_to_the_intraday_monitor():
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.side_effect = [
        ["s1"], [_strategy(bar_resolution="15min")],
    ]
    stats = await _monitor_daily_positions_async(db=db, market_data=MagicMock())
    assert stats["strategies_checked"] == 0


@pytest.mark.asyncio
async def test_nothing_open_is_a_free_run():
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    stats = await _monitor_daily_positions_async(db=db, market_data=MagicMock())
    assert stats == {
        "strategies_checked": 0, "positions_monitored": 0, "events_fired": 0,
        "notifications_sent": 0, "skipped_no_bar": 0,
        "skipped_corporate_action": 0, "errors": 0,
    }


@pytest.mark.asyncio
async def test_REGRESSION_one_bad_position_does_not_kill_the_others():
    """The intraday job wraps only the strategy loop, so a single symbol
    that raises takes every remaining position on that strategy with it for
    the whole run. Here the blast radius is one position."""
    good, bad = _position(), _position()
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.side_effect = [
        ["s1"], [_strategy()], [bad, good],
    ]
    db.execute.return_value.scalar_one_or_none.return_value = None

    calls = {"n": 0}

    async def _flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bad symbol")
        return []

    with patch("app.jobs.daily_position_jobs._evaluate_position", side_effect=_flaky):
        stats = await _monitor_daily_positions_async(db=db, market_data=MagicMock())

    assert stats["errors"] == 1
    assert stats["positions_monitored"] == 2  # the second was still reached
