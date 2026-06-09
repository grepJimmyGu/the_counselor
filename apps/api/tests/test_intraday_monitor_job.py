"""PRD-16c-3b — Intraday monitor cron + per-position throttle.

Tests:
  - Throttle key helpers
  - _apply_tier mutation logic (sell_all + sell_fraction shapes)
  - End-to-end monitor walk over synthetic positions:
      * tier doesn't fire when pct < trigger
      * tier fires when pct >= trigger
      * fired tier persists to PositionState + trade_log
      * throttle blocks same-tier re-firing on the next tick
      * daily strategies skipped entirely
      * strategies without exit_ladder skipped
  - Seed throttle counter from past trade_log events
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.jobs.intraday_jobs import (
    _apply_tier,
    _evaluate_position,
    _monitor_active_positions_async,
    _seed_position_throttle,
    _tier_trigger_type,
)
from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy
from app.schemas.strategy import ExitTier
from app.services.notification_throttle import (
    position_throttle_key,
    throttle_position_daily,
)


# ── Throttle helpers ────────────────────────────────────────────────────────


def test_position_throttle_key_format() -> None:
    k = position_throttle_key("strat-1", "AAPL", "tp1_hit", date(2026, 6, 9))
    assert k == "strat-1:AAPL:tp1_hit:2026-06-09"


def test_throttle_position_daily_cap_is_1() -> None:
    assert throttle_position_daily(0) is False
    assert throttle_position_daily(1) is True
    assert throttle_position_daily(2) is True


def test_position_throttle_distinguishes_symbols_and_triggers() -> None:
    """Stops on different symbols + different tiers must NOT collide."""
    d = date(2026, 6, 9)
    keys = {
        position_throttle_key("s1", "AAPL", "stop_hit", d),
        position_throttle_key("s1", "MSFT", "stop_hit", d),
        position_throttle_key("s1", "AAPL", "tp1_hit", d),
        position_throttle_key("s1", "AAPL", "tp2_hit", d),
    }
    assert len(keys) == 4  # all distinct


# ── _tier_trigger_type ──────────────────────────────────────────────────────


def test_negative_trigger_maps_to_stop_hit() -> None:
    tier = ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")
    assert _tier_trigger_type(tier, 0) == "stop_hit"


def test_positive_trigger_maps_to_indexed_tp() -> None:
    t1 = ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1")
    t2 = ExitTier(trigger_pct=+0.30, action="sell_all", label="TP2")
    assert _tier_trigger_type(t1, 1) == "tp1_hit"
    assert _tier_trigger_type(t2, 2) == "tp2_hit"


# ── _apply_tier ─────────────────────────────────────────────────────────────


def _new_position(symbol: str = "AAPL", entry: float = 100.0, shares: float = 10.0) -> PositionState:
    # Set is_open=True explicitly — SQLAlchemy's column default only
    # kicks in on commit, and these helpers construct unsaved rows.
    return PositionState(
        id=str(uuid4()),
        saved_strategy_id="s1",
        symbol=symbol,
        entered_at=datetime.utcnow(),
        entry_price=entry,
        shares_initial=shares,
        shares_remaining=shares,
        trade_log=[],
        is_open=True,
    )


def test_apply_sell_all_closes_position() -> None:
    pos = _new_position(entry=100.0, shares=10.0)
    tier = ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")
    _apply_tier(pos, tier, current_price=88.0, trigger_type="stop_hit")
    assert pos.shares_remaining == 0
    assert pos.is_open is False
    assert pos.closed_at is not None
    # final_pnl = (88 - 100) * 10 = -120
    assert pos.final_pnl == pytest.approx(-120.0)
    assert pos.trade_log[-1]["event"] == "stop_hit"
    assert pos.trade_log[-1]["shares_sold"] == 10.0
    assert pos.trade_log[-1]["tier_label"] == "Stop"


def test_apply_sell_fraction_reduces_shares() -> None:
    pos = _new_position(entry=100.0, shares=10.0)
    tier = ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1")
    _apply_tier(pos, tier, current_price=115.0, trigger_type="tp1_hit")
    # shares_initial * fraction = 10 * 0.33 = 3.3
    assert pos.shares_remaining == pytest.approx(6.7, abs=1e-6)
    assert pos.is_open is True
    assert pos.closed_at is None
    assert pos.final_pnl is None
    assert pos.trade_log[-1]["event"] == "tp1_hit"
    assert pos.trade_log[-1]["shares_sold"] == pytest.approx(3.3, abs=1e-6)


# ── _evaluate_position (end-to-end with mocked bar service) ────────────────


def _mock_bar_service(latest_price: float) -> AsyncMock:
    svc = AsyncMock()
    df = pd.DataFrame(
        {"open": [latest_price], "high": [latest_price], "low": [latest_price],
         "close": [latest_price], "volume": [10_000.0]},
        index=pd.DatetimeIndex([datetime.utcnow()]),
    )
    svc.get_bars = AsyncMock(return_value=df)
    return svc


@pytest.mark.asyncio
async def test_evaluate_no_tier_fires_when_price_within_range(db: Session) -> None:
    pos = _new_position(entry=100.0)
    db.add(pos)
    db.commit()
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
    ]
    counts: dict[str, int] = {}
    fired = await _evaluate_position(
        db, _mock_bar_service(105.0), "s1", pos, ladder,
        "15min", date.today(), counts,
    )
    assert fired == 0
    db.refresh(pos)
    assert pos.is_open is True
    assert pos.trade_log == []


@pytest.mark.asyncio
async def test_evaluate_stop_fires_on_drawdown(db: Session) -> None:
    pos = _new_position(entry=100.0, shares=10.0)
    db.add(pos)
    db.commit()
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    counts: dict[str, int] = {}
    fired = await _evaluate_position(
        db, _mock_bar_service(88.0), "s1", pos, ladder,
        "15min", date.today(), counts,
    )
    assert fired == 1
    db.refresh(pos)
    assert pos.is_open is False
    assert pos.trade_log[-1]["event"] == "stop_hit"
    # Throttle counter incremented.
    key = position_throttle_key("s1", "AAPL", "stop_hit", date.today())
    assert counts[key] == 1


@pytest.mark.asyncio
async def test_evaluate_throttle_blocks_refire(db: Session) -> None:
    pos = _new_position(entry=100.0, shares=10.0)
    db.add(pos)
    db.commit()
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    today_d = date.today()
    # Pre-seed throttle as if a stop already fired today.
    counts = {
        position_throttle_key("s1", "AAPL", "stop_hit", today_d): 1,
    }
    fired = await _evaluate_position(
        db, _mock_bar_service(88.0), "s1", pos, ladder,
        "15min", today_d, counts,
    )
    assert fired == 0
    db.refresh(pos)
    # Position untouched.
    assert pos.is_open is True
    assert pos.trade_log == []


@pytest.mark.asyncio
async def test_evaluate_empty_frame_skips(db: Session) -> None:
    """If the bar service returns an empty frame (no data fetched), the
    cron logs + skips without crashing."""
    pos = _new_position(entry=100.0)
    db.add(pos)
    db.commit()
    svc = AsyncMock()
    svc.get_bars = AsyncMock(return_value=pd.DataFrame())
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    counts: dict[str, int] = {}
    fired = await _evaluate_position(
        db, svc, "s1", pos, ladder, "15min", date.today(), counts,
    )
    assert fired == 0


# ── _seed_position_throttle ─────────────────────────────────────────────────


def test_seed_position_throttle_from_today_events(db: Session) -> None:
    """Trade_log events from today seed the throttle counter; older
    events are ignored."""
    strategy = SavedStrategy(
        id="s-seed",
        user_id="u-1",
        title="Seed Test",
        strategy_json={},
        is_public=False,
    )
    db.add(strategy)
    pos = PositionState(
        id="p-seed",
        saved_strategy_id="s-seed",
        symbol="AAPL",
        entered_at=datetime.utcnow() - timedelta(days=2),
        entry_price=100.0,
        shares_initial=10.0,
        shares_remaining=6.7,
        trade_log=[
            {"event": "entry", "timestamp": (datetime.utcnow() - timedelta(days=2)).isoformat(),
             "price": 100.0, "shares": 10.0},
            # TP1 fired today.
            {"event": "tp1_hit", "timestamp": datetime.utcnow().isoformat(),
             "price": 115.0, "shares_sold": 3.3},
        ],
    )
    db.add(pos)
    db.commit()

    counts: dict[str, int] = {}
    _seed_position_throttle(db, date.today(), counts)
    key = position_throttle_key("s-seed", "AAPL", "tp1_hit", date.today())
    assert counts.get(key) == 1
    # Entry event isn't tracked by the throttle.
    entry_key = position_throttle_key("s-seed", "AAPL", "entry", date.today())
    assert entry_key not in counts


# ── End-to-end monitor walk over multiple strategies ───────────────────────


@pytest.mark.asyncio
async def test_monitor_skips_daily_and_no_ladder_strategies(db: Session) -> None:
    """Strategies with bar_resolution='daily' OR without exit_ladder are
    counted as not-monitored (skipped before the bar fetch)."""
    daily_strategy = SavedStrategy(
        id="s-daily",
        user_id="u-1",
        title="Daily MA Filter",
        strategy_json={"bar_resolution": "daily"},
        is_public=False,
    )
    intraday_no_ladder = SavedStrategy(
        id="s-no-ladder",
        user_id="u-1",
        title="Intraday No Ladder",
        strategy_json={
            "strategy_name": "No Ladder", "strategy_type": "moving_average_filter",
            "universe": ["AAPL"], "benchmark": "AAPL",
            "start_date": "2025-01-01", "end_date": "2025-12-31",
            "initial_capital": 100_000, "rebalance_frequency": "monthly",
            "position_sizing": {"method": "equal_weight"},
            "rules": [{"ma_window": 50}],
            "bar_resolution": "15min",
        },
        is_public=False,
    )
    db.add(daily_strategy)
    db.add(intraday_no_ladder)
    db.commit()

    stats = await _monitor_active_positions_async(
        bar_service=_mock_bar_service(105.0),
        db=db,
    )
    # Neither strategy passes both filters → strategies_checked = 0.
    assert stats["strategies_checked"] == 0
    assert stats["positions_monitored"] == 0
    assert stats["errors"] == 0
