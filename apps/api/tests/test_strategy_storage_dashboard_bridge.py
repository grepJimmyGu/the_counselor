"""PRD-16c dashboard bridge — `/api/strategies/{slug}` response carries
the matching `saved_strategy_id` when one exists.

The frontend uses this to gate the `<ActiveExecutionDashboard>` render
on the public strategy-detail page. The dashboard's endpoints
(PRD-16c-3c) are owner-only on the SavedStrategy UUID; without the
bridge field the frontend has no way to derive the UUID from the
slug-keyed view.
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.api.routes.strategy_storage import get_saved_strategy
from app.models.backtest import BacktestRecord
from app.models.saved_strategy import SavedStrategy


def _make_backtest_record(
    db: Session,
    *,
    slug: str = "test-strategy",
    user_id: str = "user-1",
) -> BacktestRecord:
    rec_id = f"bt-{uuid4().hex[:8]}"
    record = BacktestRecord(
        id=rec_id,
        strategy_type="custom_build",
        strategy_name="Test Strategy",
        slug=slug,
        name="Test Strategy",
        user_id=user_id,
        is_public=True,
        saved_at=datetime.utcnow(),
        result_payload={
            "strategy_json": {"strategy_type": "custom_build"},
            "metrics": {},
            "equity_curve": [],
            "benchmark_curve": [],
            "drawdown_curve": [],
            "trade_log": [],
            "warnings": [],
        },
    )
    db.add(record)
    db.commit()
    return record


def test_saved_strategy_id_present_when_savedstrategy_references_record(
    db: Session,
) -> None:
    record = _make_backtest_record(db, slug="custom-aapl")
    ss = SavedStrategy(
        id=str(uuid4()),
        user_id="user-1",
        title="My Custom Strategy",
        strategy_json={"strategy_type": "custom_build"},
        is_public=True,
        backtest_record_id=record.id,
    )
    db.add(ss)
    db.commit()

    response = get_saved_strategy("custom-aapl", db=db)
    assert response.saved_strategy_id == ss.id


def test_saved_strategy_id_none_when_no_matching_savedstrategy(
    db: Session,
) -> None:
    """A BacktestRecord with no matching SavedStrategy returns
    `saved_strategy_id=None` — the common case for community-only
    backtests, anonymous runs, and ad-hoc workspace runs."""
    _make_backtest_record(db, slug="orphan-record")
    response = get_saved_strategy("orphan-record", db=db)
    assert response.saved_strategy_id is None


def test_saved_strategy_id_picks_the_user_who_saved_it(db: Session) -> None:
    """When multiple users save the same public backtest, the route
    surfaces SOME owner's UUID — the dashboard endpoints will 404 for
    non-owners, which the frontend handles as an error state. The
    contract is "if there's a SavedStrategy at all, give us a UUID we
    can probe", not "give us THIS user's UUID."""
    record = _make_backtest_record(db, slug="popular-strategy")
    saves = []
    for i in range(3):
        ss = SavedStrategy(
            id=str(uuid4()),
            user_id=f"user-{i}",
            title=f"Save #{i}",
            strategy_json={"strategy_type": "custom_build"},
            is_public=False,
            backtest_record_id=record.id,
        )
        db.add(ss)
        saves.append(ss)
    db.commit()

    response = get_saved_strategy("popular-strategy", db=db)
    assert response.saved_strategy_id in {ss.id for ss in saves}


def test_saved_strategy_id_shape_in_response_model() -> None:
    """The schema declares the field as Optional[str] — verify defaults."""
    from app.schemas.strategy_storage import SavedStrategyResponse

    resp = SavedStrategyResponse(
        slug="x",
        name="x",
        saved_at=datetime.utcnow(),
        is_public=True,
        strategy_json={},
        metrics={},
        equity_curve=[],
        benchmark_curve=[],
        drawdown_curve=[],
        trade_log=[],
        warnings=[],
    )
    # Field defaults to None when unset.
    assert resp.saved_strategy_id is None

    resp2 = SavedStrategyResponse(
        slug="x",
        name="x",
        saved_at=datetime.utcnow(),
        is_public=True,
        strategy_json={},
        metrics={},
        equity_curve=[],
        benchmark_curve=[],
        drawdown_curve=[],
        trade_log=[],
        warnings=[],
        saved_strategy_id="abc-123",
    )
    assert resp2.saved_strategy_id == "abc-123"
