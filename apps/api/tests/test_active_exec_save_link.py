"""Saving a strategy must also create the linked SavedStrategy row, because
that row is the only handle every live surface has on the strategy.

CONTRACT CHANGED 2026-08-23, and two tests in this file previously asserted
the OLD behaviour by name:

    test_daily_save_does_not_create_savedstrategy
    test_active_save_without_ladder_does_not_create_savedstrategy

Both were correct when written. `_maybe_create_saved_strategy_for_active_execution`
linked a row only for "active execution", which in early 2026 meant an
intraday bar resolution plus an exit ladder — anything else had no live
machinery to reach, so a row would have been dead weight.

Two product changes invalidated that, and neither updated this file:

  1. The daily-only pivot. #327 added the after-close daily monitor and
     #331/#337 removed the daily gates from the two UI surfaces. Daily
     stopped being the excluded case and became the ONLY supported one —
     so the exclusion now covers essentially every save the product makes.

  2. PRD-28's `track` step attaches a strategy's FIRST exit ladder after
     the save. Refusing to link a ladder-less strategy made that
     impossible: no ladder meant no row, and no row meant nothing to
     attach a ladder to.

The user-visible cost of (1): saving a daily strategy left "My strategies"
empty, because `/account/strategies` lists SavedStrategy rows and none had
been written.

So the rule is now unconditional — a strategy the user chose to save is one
they should be able to find — and the two tests below are inverted, keeping
their original scenarios so the change is legible in the diff.
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


def _linked(db: Session, record_id: str):
    return (
        db.query(SavedStrategy)
        .filter(SavedStrategy.backtest_record_id == record_id)
        .all()
    )


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


def test_REGRESSION_daily_save_creates_savedstrategy(make_user, db: Session) -> None:
    """INVERTED — was `test_daily_save_does_not_create_savedstrategy`.

    Daily is the supported path now, not the excluded one. Without this row
    the user's own strategy is invisible to them: "My strategies" lists
    SavedStrategy rows, `/account/strategies/{id}` renders from one, the
    after-close monitor iterates them, and `declare_position` targets one.
    A daily save used to produce none of that.
    """
    user = make_user(email="daily-save@test.com", tier="strategist")
    save_strategy(
        _req(backtest_id="bt-daily", name="Daily MA", strategy_json=_DAILY_JSON),
        user=user, db=db,
    )
    rows = _linked(db, "bt-daily")
    assert len(rows) == 1
    assert rows[0].title == "Daily MA"
    assert rows[0].strategy_json["bar_resolution"] == "daily"


def test_REGRESSION_save_without_ladder_creates_savedstrategy(
    make_user, db: Session,
) -> None:
    """INVERTED — was `test_active_save_without_ladder_does_not_create_savedstrategy`.

    The old reasoning ("no ladder → nothing to monitor → no row") assumed a
    strategy's ladder is fixed at save time. PRD-28's `track` step attaches
    the first ladder AFTER the save, so refusing the row here made a
    strategy unable to ever acquire one — you needed a ladder to get a row,
    and a row to save a ladder.

    Tracking is a later, explicit decision. Saving is not the moment to
    infer it from a field the user has not been asked about yet.
    """
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
    rows = _linked(db, "bt-noladder")
    assert len(rows) == 1
    # No ladder yet — and that is exactly the state `track` expects to find.
    assert not (rows[0].strategy_json.get("risk_management") or {}).get("exit_ladder")


def test_active_execution_save_is_idempotent_on_relink(
    make_user, db: Session,
) -> None:
    """The link helper skips when a SavedStrategy already points at the
    record (guards re-save / retry from creating duplicates)."""
    from app.api.routes.strategy_storage import _link_saved_strategy
    user = make_user(email="idem-save@test.com", tier="strategist")
    save_strategy(
        _req(backtest_id="bt-idem", name="Idem", strategy_json=_ACTIVE_JSON),
        user=user, db=db,
    )
    record = db.query(BacktestRecord).filter(BacktestRecord.id == "bt-idem").one()
    # Call the linker again directly — should be a no-op.
    _link_saved_strategy(
        db, record, name="Idem", is_public=False, user_id=user.id,
    )
    assert len(_linked(db, "bt-idem")) == 1


def test_the_saved_row_is_what_my_strategies_actually_lists(
    make_user, db: Session,
) -> None:
    """End-to-end on the surface the gate broke.

    `GET /api/saved-strategies` is what "My strategies" renders, so assert
    through it rather than through the table — a row that exists but is
    filtered out of the listing would still leave the page empty.
    """
    from app.api.routes.saved_strategies import list_saved_strategies

    user = make_user(email="mystrats@test.com", tier="strategist")
    save_strategy(
        _req(backtest_id="bt-listed", name="Shows Up", strategy_json=_DAILY_JSON),
        user=user, db=db,
    )
    titles = [s.title for s in list_saved_strategies(current_user=user, db=db)]
    assert "Shows Up" in titles
