"""Intraday monitor cron — active-execution-v2 (detect + notify).

The cron DETECTS exit-ladder triggers and NOTIFIES the user. It MUST NOT
mutate the position (no shares_remaining / is_open / closed_at / final_pnl
change) — the user confirms the real sale via Mark-as-Executed (PR3).

Tests:
  - _tier_trigger_type mapping
  - _evaluate_position: no fire within range; fire on trigger records a
    `pending_confirmation` event WITHOUT mutating shares/is_open;
    already-fired tier never re-notifies (permanent guard); empty frame
  - _dispatch_position_event: renders + sends email + writes banner
  - monitor walk: daily + no-ladder strategies skipped; end-to-end fire
    dispatches a notification + leaves the position untouched
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.jobs.intraday_jobs import (
    PendingFire,
    _dispatch_position_event,
    _evaluate_position,
    _monitor_active_positions_async,
    _record_pending_tier,
    _tier_already_fired,
    _tier_trigger_type,
)
from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy
from app.models.user import User
from app.schemas.strategy import ExitTier


# ── _tier_trigger_type ──────────────────────────────────────────────────────


def test_negative_trigger_maps_to_stop_hit() -> None:
    tier = ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")
    assert _tier_trigger_type(tier, 0) == "stop_hit"


def test_positive_trigger_maps_to_indexed_tp() -> None:
    t1 = ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1")
    t2 = ExitTier(trigger_pct=+0.30, action="sell_all", label="TP2")
    assert _tier_trigger_type(t1, 1) == "tp1_hit"
    assert _tier_trigger_type(t2, 2) == "tp2_hit"


# ── helpers ──────────────────────────────────────────────────────────────────


def _new_position(symbol: str = "AAPL", entry: float = 100.0, shares: float = 10.0) -> PositionState:
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


def _mock_bar_service(latest_price: float) -> AsyncMock:
    svc = AsyncMock()
    df = pd.DataFrame(
        {"open": [latest_price], "high": [latest_price], "low": [latest_price],
         "close": [latest_price], "volume": [10_000.0]},
        index=pd.DatetimeIndex([datetime.utcnow()]),
    )
    svc.get_bars = AsyncMock(return_value=df)
    return svc


# ── _record_pending_tier (the compliance invariant) ─────────────────────────


def test_record_pending_tier_does_not_mutate_shares_or_close() -> None:
    """THE compliance invariant: recording a pending tier appends to
    trade_log but NEVER touches shares_remaining / is_open / closed_at /
    final_pnl. The user confirms the real sale."""
    pos = _new_position(entry=100.0, shares=10.0)
    tier = ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")
    _record_pending_tier(
        pos, "stop_hit", tier, current_price=88.0, pct_change=-0.12,
        suggested_action="sell_all", suggested_shares=10.0,
    )
    # Shares + open-state UNCHANGED.
    assert pos.shares_remaining == 10.0
    assert pos.is_open is True
    assert pos.closed_at is None
    assert pos.final_pnl is None
    # Pending event recorded.
    last = pos.trade_log[-1]
    assert last["event"] == "stop_hit"
    assert last["status"] == "pending_confirmation"
    assert last["suggested_action"] == "sell_all"
    assert last["suggested_shares"] == 10.0
    assert last["tier_label"] == "Stop"


def test_tier_already_fired_guard() -> None:
    pos = _new_position()
    assert _tier_already_fired(pos, "stop_hit") is False
    pos.trade_log = [{"event": "stop_hit", "status": "pending_confirmation"}]
    assert _tier_already_fired(pos, "stop_hit") is True
    # A different tier is not blocked.
    assert _tier_already_fired(pos, "tp1_hit") is False


# ── _evaluate_position (detect, mocked bar service) ─────────────────────────


@pytest.mark.asyncio
async def test_evaluate_no_tier_fires_when_price_within_range(db: Session) -> None:
    pos = _new_position(entry=100.0)
    db.add(pos)
    db.commit()
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
    ]
    fire = await _evaluate_position(
        db, _mock_bar_service(105.0), pos, ladder, "15min",
    )
    assert fire is None
    db.refresh(pos)
    assert pos.is_open is True
    assert pos.trade_log == []


@pytest.mark.asyncio
async def test_evaluate_stop_fires_records_pending_without_mutation(db: Session) -> None:
    pos = _new_position(entry=100.0, shares=10.0)
    db.add(pos)
    db.commit()
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    fire = await _evaluate_position(
        db, _mock_bar_service(88.0), pos, ladder, "15min",
    )
    assert fire is not None
    assert fire.trigger_type == "stop_hit"
    assert fire.suggested_action == "sell_all"
    assert fire.suggested_shares == pytest.approx(10.0)
    db.refresh(pos)
    # Compliance invariant: position NOT mutated by the cron.
    assert pos.is_open is True
    assert pos.shares_remaining == 10.0
    assert pos.final_pnl is None
    # Pending event recorded.
    assert pos.trade_log[-1]["event"] == "stop_hit"
    assert pos.trade_log[-1]["status"] == "pending_confirmation"


@pytest.mark.asyncio
async def test_evaluate_tp_fraction_suggests_fraction_of_initial(db: Session) -> None:
    pos = _new_position(entry=100.0, shares=10.0)
    db.add(pos)
    db.commit()
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
    ]
    fire = await _evaluate_position(
        db, _mock_bar_service(115.0), pos, ladder, "15min",
    )
    assert fire is not None
    assert fire.trigger_type == "tp1_hit"
    # 0.33 * 10 initial = 3.3 suggested shares.
    assert fire.suggested_shares == pytest.approx(3.3, abs=1e-6)
    db.refresh(pos)
    assert pos.shares_remaining == 10.0  # unchanged


@pytest.mark.asyncio
async def test_evaluate_already_fired_tier_does_not_renotify(db: Session) -> None:
    """Permanent guard: a tier with a pending event in trade_log never
    re-fires — even on a later tick / day."""
    pos = _new_position(entry=100.0, shares=10.0)
    pos.trade_log = [{
        "event": "stop_hit", "status": "pending_confirmation",
        "timestamp": datetime.utcnow().isoformat(),
    }]
    db.add(pos)
    db.commit()
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    fire = await _evaluate_position(
        db, _mock_bar_service(80.0), pos, ladder, "15min",
    )
    assert fire is None
    db.refresh(pos)
    # No second event added.
    assert len(pos.trade_log) == 1


@pytest.mark.asyncio
async def test_evaluate_empty_frame_skips(db: Session) -> None:
    pos = _new_position(entry=100.0)
    db.add(pos)
    db.commit()
    svc = AsyncMock()
    svc.get_bars = AsyncMock(return_value=pd.DataFrame())
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    fire = await _evaluate_position(db, svc, pos, ladder, "15min")
    assert fire is None


# ── _dispatch_position_event ────────────────────────────────────────────────


def test_dispatch_renders_and_sends(db: Session) -> None:
    user = User(id="u-1", email="active@test.com")
    strat = SavedStrategy(
        id="s-dispatch", user_id="u-1", title="SpaceX Active",
        strategy_json={}, is_public=False,
    )
    pos = _new_position(entry=100.0, shares=10.0)
    pos.saved_strategy_id = "s-dispatch"
    fire = PendingFire(
        trigger_type="tp1_hit",
        tier=ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
        current_price=115.0,
        pct_change=0.15,
        suggested_action="sell_fraction",
        suggested_shares=3.3,
    )
    with patch("app.services.email_service.send_email", return_value=True) as mock_send, \
         patch("app.jobs.intraday_jobs._write_position_banner") as mock_banner:
        sent = _dispatch_position_event(db, user, strat, pos, fire)
    assert sent is True
    mock_send.assert_called_once()
    # Right template + transactional category.
    _, kwargs = mock_send.call_args
    assert kwargs["template"] == "position_event"
    assert kwargs["category"] == "transactional"
    # Subject names the symbol.
    assert "AAPL" in kwargs["subject"]
    # Banner written.
    mock_banner.assert_called_once()


def test_dispatch_email_failure_is_swallowed(db: Session) -> None:
    """A failed email doesn't crash the cron — the signal is still in the
    trade_log + dashboard. Returns False."""
    user = User(id="u-2", email="active2@test.com")
    strat = SavedStrategy(
        id="s-fail", user_id="u-2", title="X", strategy_json={}, is_public=False,
    )
    pos = _new_position()
    pos.saved_strategy_id = "s-fail"
    fire = PendingFire(
        trigger_type="stop_hit",
        tier=ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        current_price=88.0, pct_change=-0.12,
        suggested_action="sell_all", suggested_shares=10.0,
    )
    with patch("app.services.email_service.send_email", side_effect=RuntimeError("smtp down")), \
         patch("app.jobs.intraday_jobs._write_position_banner"):
        sent = _dispatch_position_event(db, user, strat, pos, fire)
    assert sent is False


# ── End-to-end monitor walk ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_monitor_skips_daily_and_no_ladder_strategies(db: Session) -> None:
    daily_strategy = SavedStrategy(
        id="s-daily", user_id="u-1", title="Daily MA Filter",
        strategy_json={"bar_resolution": "daily"}, is_public=False,
    )
    intraday_no_ladder = SavedStrategy(
        id="s-no-ladder", user_id="u-1", title="Intraday No Ladder",
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
        bar_service=_mock_bar_service(105.0), db=db,
    )
    assert stats["strategies_checked"] == 0
    assert stats["positions_monitored"] == 0
    assert stats["errors"] == 0


@pytest.mark.asyncio
async def test_monitor_end_to_end_fire_dispatches_and_leaves_position(db: Session) -> None:
    """Full walk: an open position on an active-execution strategy hits a
    stop → a notification dispatches + a pending event records, and the
    position is NOT mutated."""
    user = User(id="u-e2e", email="e2e@test.com")
    db.add(user)
    strat = SavedStrategy(
        id="s-e2e", user_id="u-e2e", title="SpaceX",
        strategy_json={
            "strategy_name": "SpaceX", "strategy_type": "custom_build",
            "universe": ["AAPL"], "benchmark": "SPY",
            "start_date": "2025-01-01", "end_date": "2025-12-31",
            "initial_capital": 100_000, "rebalance_frequency": "monthly",
            "position_sizing": {"method": "equal_weight"},
            "rules": [{"primitive_id": "rsi", "operator": "lt", "threshold": 30}],
            "risk_management": {
                "exit_ladder": [
                    {"trigger_pct": -0.10, "action": "sell_all", "label": "Stop"},
                ]
            },
            "bar_resolution": "15min",
        },
        is_public=False,
    )
    db.add(strat)
    pos = _new_position(entry=100.0, shares=10.0)
    pos.saved_strategy_id = "s-e2e"
    db.add(pos)
    db.commit()

    with patch("app.services.email_service.send_email", return_value=True) as mock_send, \
         patch("app.jobs.intraday_jobs._write_position_banner"):
        stats = await _monitor_active_positions_async(
            bar_service=_mock_bar_service(85.0), db=db,
        )

    assert stats["strategies_checked"] == 1
    assert stats["positions_monitored"] == 1
    assert stats["events_fired"] == 1
    assert stats["notifications_sent"] == 1
    mock_send.assert_called_once()
    db.refresh(pos)
    # Position untouched by the cron.
    assert pos.is_open is True
    assert pos.shares_remaining == 10.0
    assert pos.trade_log[-1]["status"] == "pending_confirmation"
