"""Intraday live-chart endpoint — /api/saved-strategies/{id}/intraday-chart.

Returns, per OPEN position: the cached intraday price series, the exit-tier
price LEVELS (entry_price * (1 + trigger_pct)), and the trade-log events
(entry + fired tiers) as point markers. Cache-only read (cron keeps it
fresh); daily strategies get an empty series; owner-gated 404.

Handlers invoked directly with fixtures, per the project test pattern.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.saved_strategies import get_intraday_chart
from app.models.intraday_bar import IntradayBar
from app.models.position_state import PositionState
from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest


def _save_active_strategy(db: Session, user):
    return saved_strategy_service.save_strategy(
        db, user,
        SaveStrategyRequest(
            title="MACD intraday",
            strategy_json={
                "strategy_type": "custom_build",
                "universe": ["MSFT"],
                "bar_resolution": "15min",
                "risk_management": {
                    "exit_ladder": [
                        {"trigger_pct": -0.10, "action": "sell_all", "label": "Stop"},
                        {"trigger_pct": 0.05, "action": "sell_fraction",
                         "fraction": 0.5, "label": "TP1"},
                    ]
                },
            },
        ),
    )


def _seed_bar(db: Session, *, symbol: str, price: float, minutes_ago: int,
              resolution: str = "15min") -> None:
    bar_time = (datetime.utcnow() - timedelta(minutes=minutes_ago)).replace(microsecond=0)
    db.add(IntradayBar(
        symbol=symbol, resolution=resolution, bar_time=bar_time,
        open=price - 0.5, high=price + 0.5, low=price - 1.0,
        close=price, volume=1_000.0,
    ))
    db.commit()


def _open_position(db: Session, strategy_id: str, **over) -> PositionState:
    entered = datetime.utcnow() - timedelta(hours=1)
    defaults = dict(
        id=str(uuid4()), saved_strategy_id=strategy_id, symbol="MSFT",
        entered_at=entered, entry_price=391.0,
        shares_initial=500.0, shares_remaining=500.0,
        trade_log=[{
            "event": "entry", "timestamp": entered.isoformat(),
            "price": 391.0, "shares": 500.0,
        }],
        is_open=True,
    )
    defaults.update(over)
    pos = PositionState(**defaults)
    db.add(pos)
    db.commit()
    return pos


def test_chart_returns_bars_tiers_events(make_user, db: Session) -> None:
    user = make_user(email="chart-ok@test.com")
    strategy = _save_active_strategy(db, user)
    _open_position(db, strategy.id)
    _seed_bar(db, symbol="MSFT", price=388.0, minutes_ago=30)
    _seed_bar(db, symbol="MSFT", price=389.5, minutes_ago=15)

    resp = get_intraday_chart(strategy.id, current_user=user, db=db)
    assert resp.bar_resolution == "15min"
    assert len(resp.series) == 1
    s = resp.series[0]
    assert s.symbol == "MSFT"
    assert s.entry_price == pytest.approx(391.0)
    assert len(s.bars) == 2
    # Tier levels are entry * (1 + trigger_pct): -10% -> 351.9, +5% -> 410.55.
    levels = {t.label: t.price_level for t in s.tiers}
    assert levels["Stop"] == pytest.approx(391.0 * 0.90)
    assert levels["TP1"] == pytest.approx(391.0 * 1.05)
    assert any(e.event == "entry" for e in s.events)


def test_chart_empty_bars_when_cache_cold(make_user, db: Session) -> None:
    """A cold cache returns an empty bars list (not an error) but still
    reports the tier levels, which don't depend on bars."""
    user = make_user(email="chart-cold@test.com")
    strategy = _save_active_strategy(db, user)
    _open_position(db, strategy.id)

    resp = get_intraday_chart(strategy.id, current_user=user, db=db)
    assert len(resp.series) == 1
    assert resp.series[0].bars == []
    assert len(resp.series[0].tiers) == 2


def test_chart_daily_strategy_empty_series(make_user, db: Session) -> None:
    user = make_user(email="chart-daily@test.com")
    strategy = saved_strategy_service.save_strategy(
        db, user,
        SaveStrategyRequest(
            title="Daily MA",
            strategy_json={
                "strategy_type": "moving_average_filter",
                "universe": ["NVDA"], "bar_resolution": "daily",
            },
        ),
    )
    resp = get_intraday_chart(strategy.id, current_user=user, db=db)
    assert resp.bar_resolution == "daily"
    assert resp.series == []


def test_chart_only_open_positions(make_user, db: Session) -> None:
    user = make_user(email="chart-open@test.com")
    strategy = _save_active_strategy(db, user)
    _open_position(db, strategy.id, symbol="MSFT")
    _open_position(
        db, strategy.id, id=str(uuid4()), symbol="AAPL",
        is_open=False, closed_at=datetime.utcnow(), final_pnl=10.0,
    )
    resp = get_intraday_chart(strategy.id, current_user=user, db=db)
    assert len(resp.series) == 1
    assert resp.series[0].symbol == "MSFT"


def test_chart_404_for_non_owner(make_user, db: Session) -> None:
    owner = make_user(email="chart-owner@test.com")
    other = make_user(email="chart-other@test.com")
    strategy = _save_active_strategy(db, owner)
    with pytest.raises(HTTPException) as exc:
        get_intraday_chart(strategy.id, current_user=other, db=db)
    assert exc.value.status_code == 404
