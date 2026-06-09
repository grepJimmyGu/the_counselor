"""PRD-16c-3c — Active execution dashboard endpoints.

Three endpoints under /api/saved-strategies/{strategy_id}/:

  - universe-state — latest cached intraday price per universe ticker
  - positions      — open + closed PositionState rows with distance metrics
  - trade-log      — flattened paginated trade events

Tests follow the project pattern of invoking handlers directly with
fixtures (see test_mark_as_executed.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.saved_strategies import (
    get_strategy_positions,
    get_strategy_trade_log,
    get_universe_state,
)
from app.models.intraday_bar import IntradayBar
from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy
from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _save_intraday_strategy(db: Session, user, *, universe=None) -> SavedStrategy:
    return saved_strategy_service.save_strategy(
        db, user,
        SaveStrategyRequest(
            title="SpaceX Active",
            strategy_json={
                "strategy_type": "custom_build",
                "universe": universe or ["AAPL", "MSFT"],
                "bar_resolution": "15min",
            },
        ),
    )


def _save_daily_strategy(db: Session, user) -> SavedStrategy:
    return saved_strategy_service.save_strategy(
        db, user,
        SaveStrategyRequest(
            title="Daily MA",
            strategy_json={
                "strategy_type": "moving_average_filter",
                "universe": ["NVDA"],
                "bar_resolution": "daily",
            },
        ),
    )


def _seed_intraday_bar(
    db: Session, *, symbol: str, price: float, minutes_ago: int = 5,
    resolution: str = "15min",
) -> None:
    bar_time = (datetime.utcnow() - timedelta(minutes=minutes_ago)).replace(microsecond=0)
    db.add(IntradayBar(
        symbol=symbol, resolution=resolution, bar_time=bar_time,
        open=price - 0.5, high=price + 0.5, low=price - 1.0,
        close=price, volume=10_000.0,
    ))
    db.commit()


def _new_position(strategy_id: str, **overrides) -> PositionState:
    defaults = {
        "id": str(uuid4()),
        "saved_strategy_id": strategy_id,
        "symbol": "AAPL",
        "entered_at": datetime.utcnow(),
        "entry_price": 100.0,
        "shares_initial": 10.0,
        "shares_remaining": 10.0,
        "trade_log": [],
        "is_open": True,
    }
    defaults.update(overrides)
    return PositionState(**defaults)


# ── universe-state ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_universe_state_returns_intraday_prices(make_user, db: Session) -> None:
    user = make_user(email="us-intraday@test.com")
    strategy = _save_intraday_strategy(db, user, universe=["AAPL", "MSFT"])
    _seed_intraday_bar(db, symbol="AAPL", price=180.5)
    _seed_intraday_bar(db, symbol="MSFT", price=420.0)

    response = await get_universe_state(strategy.id, current_user=user, db=db)
    assert response.bar_resolution == "15min"
    symbols = {row.symbol: row for row in response.universe}
    assert symbols["AAPL"].latest_price == pytest.approx(180.5)
    assert symbols["AAPL"].source == "intraday"
    assert symbols["MSFT"].latest_price == pytest.approx(420.0)
    assert symbols["MSFT"].source == "intraday"


@pytest.mark.asyncio
async def test_universe_state_returns_no_data_for_uncached_symbols(make_user, db: Session) -> None:
    user = make_user(email="us-nodata@test.com")
    strategy = _save_intraday_strategy(db, user, universe=["AAPL", "TSLA"])
    _seed_intraday_bar(db, symbol="AAPL", price=180.5)
    # TSLA has no cached bar.

    response = await get_universe_state(strategy.id, current_user=user, db=db)
    symbols = {row.symbol: row for row in response.universe}
    assert symbols["AAPL"].source == "intraday"
    assert symbols["TSLA"].source == "no_data"
    assert symbols["TSLA"].latest_price is None


@pytest.mark.asyncio
async def test_universe_state_daily_strategy_returns_no_data(make_user, db: Session) -> None:
    """Daily strategies don't query the intraday cache — they get
    no_data placeholders + bar_resolution='daily'."""
    user = make_user(email="us-daily@test.com")
    strategy = _save_daily_strategy(db, user)

    response = await get_universe_state(strategy.id, current_user=user, db=db)
    assert response.bar_resolution == "daily"
    assert len(response.universe) == 1
    assert response.universe[0].source == "no_data"


@pytest.mark.asyncio
async def test_universe_state_404_for_non_owner(make_user, db: Session) -> None:
    owner = make_user(email="us-owner@test.com")
    other = make_user(email="us-other@test.com")
    strategy = _save_intraday_strategy(db, owner)

    with pytest.raises(HTTPException) as exc:
        await get_universe_state(strategy.id, current_user=other, db=db)
    assert exc.value.status_code == 404


# ── positions ───────────────────────────────────────────────────────────────


def test_positions_returns_open_and_closed(make_user, db: Session) -> None:
    user = make_user(email="pos-mixed@test.com")
    strategy = _save_intraday_strategy(db, user)
    open_pos = _new_position(strategy.id, symbol="AAPL")
    closed_pos = _new_position(
        strategy.id, symbol="MSFT", is_open=False,
        closed_at=datetime.utcnow(), final_pnl=120.0,
    )
    db.add(open_pos)
    db.add(closed_pos)
    db.commit()

    response = get_strategy_positions(strategy.id, current_user=user, db=db)
    assert response.open_count == 1
    assert response.closed_count == 1
    assert len(response.positions) == 2
    # Open positions sorted first.
    assert response.positions[0].is_open is True


def test_positions_includes_latest_price_and_pct_change(make_user, db: Session) -> None:
    user = make_user(email="pos-pct@test.com")
    strategy = _save_intraday_strategy(db, user)
    pos = _new_position(strategy.id, symbol="AAPL", entry_price=100.0)
    db.add(pos)
    db.commit()
    _seed_intraday_bar(db, symbol="AAPL", price=115.0)

    response = get_strategy_positions(strategy.id, current_user=user, db=db)
    assert response.positions[0].latest_price == pytest.approx(115.0)
    assert response.positions[0].pct_change_from_entry == pytest.approx(0.15)


def test_positions_pct_change_none_when_no_bar_cached(make_user, db: Session) -> None:
    user = make_user(email="pos-nobar@test.com")
    strategy = _save_intraday_strategy(db, user)
    pos = _new_position(strategy.id, symbol="AAPL", entry_price=100.0)
    db.add(pos)
    db.commit()

    response = get_strategy_positions(strategy.id, current_user=user, db=db)
    assert response.positions[0].latest_price is None
    assert response.positions[0].pct_change_from_entry is None


def test_positions_404_for_non_owner(make_user, db: Session) -> None:
    owner = make_user(email="pos-owner@test.com")
    other = make_user(email="pos-other@test.com")
    strategy = _save_intraday_strategy(db, owner)

    with pytest.raises(HTTPException) as exc:
        get_strategy_positions(strategy.id, current_user=other, db=db)
    assert exc.value.status_code == 404


def test_positions_empty_when_no_positions(make_user, db: Session) -> None:
    user = make_user(email="pos-empty@test.com")
    strategy = _save_intraday_strategy(db, user)

    response = get_strategy_positions(strategy.id, current_user=user, db=db)
    assert response.positions == []
    assert response.open_count == 0
    assert response.closed_count == 0


# ── trade-log ───────────────────────────────────────────────────────────────


def test_trade_log_flattens_events_newest_first(make_user, db: Session) -> None:
    user = make_user(email="tl-flatten@test.com")
    strategy = _save_intraday_strategy(db, user)
    t0 = datetime(2026, 6, 9, 14, 30, 0)
    t1 = t0 + timedelta(minutes=5)
    t2 = t0 + timedelta(minutes=10)
    pos1 = _new_position(strategy.id, symbol="AAPL", trade_log=[
        {"event": "entry", "timestamp": t0.isoformat(), "price": 100.0, "shares": 10.0},
        {"event": "tp1_hit", "timestamp": t2.isoformat(), "price": 115.0, "shares_sold": 3.3, "tier_label": "TP1"},
    ])
    pos2 = _new_position(strategy.id, symbol="MSFT", trade_log=[
        {"event": "entry", "timestamp": t1.isoformat(), "price": 420.0, "shares": 5.0},
    ])
    db.add(pos1)
    db.add(pos2)
    db.commit()

    response = get_strategy_trade_log(strategy.id, current_user=user, db=db)
    assert response.total == 3
    assert len(response.events) == 3
    # Newest first.
    assert response.events[0].timestamp == t2
    assert response.events[0].event == "tp1_hit"
    assert response.events[0].tier_label == "TP1"


def test_trade_log_paginates_via_before(make_user, db: Session) -> None:
    user = make_user(email="tl-page@test.com")
    strategy = _save_intraday_strategy(db, user)
    base = datetime(2026, 6, 9, 14, 0, 0)
    events = [
        {"event": "entry", "timestamp": (base + timedelta(minutes=i)).isoformat(),
         "price": 100.0 + i, "shares": 1.0}
        for i in range(5)
    ]
    pos = _new_position(strategy.id, symbol="AAPL", trade_log=events)
    db.add(pos)
    db.commit()

    # First page: limit=2 → newest 2 events.
    first = get_strategy_trade_log(strategy.id, current_user=user, db=db, limit=2)
    assert len(first.events) == 2
    assert first.events[0].timestamp == base + timedelta(minutes=4)
    assert first.events[1].timestamp == base + timedelta(minutes=3)
    assert first.next_before == base + timedelta(minutes=3)

    # Next page: before=first.next_before → next 2 events.
    second = get_strategy_trade_log(
        strategy.id, current_user=user, db=db,
        limit=2, before=first.next_before,
    )
    assert len(second.events) == 2
    assert second.events[0].timestamp == base + timedelta(minutes=2)


def test_trade_log_skips_events_with_invalid_timestamp(make_user, db: Session) -> None:
    user = make_user(email="tl-bad@test.com")
    strategy = _save_intraday_strategy(db, user)
    pos = _new_position(strategy.id, symbol="AAPL", trade_log=[
        {"event": "entry", "timestamp": "not-a-date"},
        {"event": "entry", "timestamp": None},
        {"event": "entry", "timestamp": datetime.utcnow().isoformat()},
    ])
    db.add(pos)
    db.commit()

    response = get_strategy_trade_log(strategy.id, current_user=user, db=db)
    assert response.total == 1  # only the valid event


def test_trade_log_404_for_non_owner(make_user, db: Session) -> None:
    owner = make_user(email="tl-owner@test.com")
    other = make_user(email="tl-other@test.com")
    strategy = _save_intraday_strategy(db, owner)

    with pytest.raises(HTTPException) as exc:
        get_strategy_trade_log(strategy.id, current_user=other, db=db)
    assert exc.value.status_code == 404


def test_trade_log_empty_for_strategy_with_no_positions(make_user, db: Session) -> None:
    user = make_user(email="tl-empty@test.com")
    strategy = _save_intraday_strategy(db, user)

    response = get_strategy_trade_log(strategy.id, current_user=user, db=db)
    assert response.events == []
    assert response.total == 0
    assert response.next_before is None
