"""active-execution-v2: saving an active-execution strategy must also
create the linked SavedStrategy so the live machinery (dashboard, cron,
positions) can find it. Daily strategies must NOT create one (unchanged
common path).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.routes.strategy_storage import save_strategy
from app.models.backtest import BacktestRecord
from app.models.saved_strategy import SavedStrategy
from app.schemas.strategy_storage import StrategySaveRequest


def _req(
    *, backtest_id: str, name: str, strategy_json: dict, is_public: bool = False,
) -> StrategySaveRequest:
    return StrategySaveRequest(
        backtest_id=backtest_id,
        name=name,
        is_public=is_public,
        strategy_type="custom_build",
        result_payload={"strategy_json": strategy_json, "metrics": {}},
    )


_ACTIVE_JSON = {
    "strategy_type": "custom_build",
    "universe": ["AAPL"],
    "bar_resolution": "15min",
    "risk_management": {
        "exit_ladder": [
            {"trigger_pct": -0.10, "action": "sell_all", "label": "Stop"},
        ]
    },
}

_DAILY_JSON = {
    "strategy_type": "moving_average_filter",
    "universe": ["NVDA"],
    "bar_resolution": "daily",
}


def test_active_execution_save_creates_linked_savedstrategy(
    make_user, db: Session,
) -> None:
    user = make_user(email="ae-save@test.com", tier="strategist")
    resp = save_strategy(
        _req(backtest_id="bt-ae", name="SpaceX Active", strategy_json=_ACTIVE_JSON),
        user=user, db=db,
    )
    assert resp.slug
    record = db.query(BacktestRecord).filter(BacktestRecord.id == "bt-ae").one()
    # A SavedStrategy now references this BacktestRecord — the bridge will
    # resolve `saved_strategy_id` on /strategies/{slug}.
    ss = (
        db.query(SavedStrategy)
        .filter(SavedStrategy.backtest_record_id == record.id)
        .one()
    )
    assert ss.user_id == user.id
    assert ss.title == "SpaceX Active"
    # The strategy_json carries bar_resolution + exit_ladder so the cron
    # can act on it.
    assert ss.strategy_json["bar_resolution"] == "15min"
    assert ss.strategy_json["risk_management"]["exit_ladder"]


def test_daily_save_does_not_create_savedstrategy(make_user, db: Session) -> None:
    user = make_user(email="daily-save@test.com", tier="strategist")
    save_strategy(
        _req(backtest_id="bt-daily", name="Daily MA", strategy_json=_DAILY_JSON),
        user=user, db=db,
    )
    count = (
        db.query(SavedStrategy)
        .filter(SavedStrategy.backtest_record_id == "bt-daily")
        .count()
    )
    assert count == 0


def test_active_save_without_ladder_does_not_create_savedstrategy(
    make_user, db: Session,
) -> None:
    """Non-daily but no exit_ladder → nothing to monitor → no SavedStrategy."""
    user = make_user(email="noladder-save@test.com", tier="strategist")
    json_no_ladder = {
        "strategy_type": "custom_build",
        "universe": ["AAPL"],
        "bar_resolution": "15min",
    }
    save_strategy(
        _req(backtest_id="bt-noladder", name="No Ladder", strategy_json=json_no_ladder),
        user=user, db=db,
    )
    count = (
        db.query(SavedStrategy)
        .filter(SavedStrategy.backtest_record_id == "bt-noladder")
        .count()
    )
    assert count == 0


def test_active_execution_save_is_idempotent_on_relink(
    make_user, db: Session,
) -> None:
    """The link helper skips when a SavedStrategy already points at the
    record (guards re-save / retry from creating duplicates)."""
    from app.api.routes.strategy_storage import (
        _maybe_create_saved_strategy_for_active_execution,
    )
    user = make_user(email="idem-save@test.com", tier="strategist")
    save_strategy(
        _req(backtest_id="bt-idem", name="Idem", strategy_json=_ACTIVE_JSON),
        user=user, db=db,
    )
    record = db.query(BacktestRecord).filter(BacktestRecord.id == "bt-idem").one()
    # Call the linker again directly — should be a no-op.
    _maybe_create_saved_strategy_for_active_execution(
        db, record, name="Idem", is_public=False, user_id=user.id,
    )
    count = (
        db.query(SavedStrategy)
        .filter(SavedStrategy.backtest_record_id == "bt-idem")
        .count()
    )
    assert count == 1
