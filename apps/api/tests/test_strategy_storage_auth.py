"""Tests for the 2026-05-20 auth + tier hardening of /api/strategies/save.

Prior to that change the endpoint was completely unauthenticated and bypassed
the entire tier system: anyone could save unlimited strategies as anyone,
and Scout's saved_strategies_always_public override was never enforced.

The route now uses get_current_user, counts the user's own slugged
BacktestRecords against ent.saved_strategies_max, forces is_public=True
for Scout, and stamps record.user_id on insert. update_visibility now
requires owner match.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.strategy_storage import save_strategy, update_visibility
from app.models.backtest import BacktestRecord
from app.schemas.strategy_storage import StrategySaveRequest, VisibilityUpdateRequest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_req(
    backtest_id: str = "bt-1",
    name: str = "My Strategy",
    is_public: bool = False,
) -> StrategySaveRequest:
    return StrategySaveRequest(
        backtest_id=backtest_id,
        name=name,
        is_public=is_public,
        strategy_type="momentum",
        result_payload={
            "strategy_json": {"strategy_type": "momentum", "universe": ["AAPL"]},
            "metrics": {"annualized_return": 0.12},
        },
    )


# ── Save: tier cap enforcement ────────────────────────────────────────────────


def test_save_enforces_scout_cap_of_10(make_user, db: Session) -> None:
    """Scout tier saved_strategies_max=10. The 11th save raises 402."""
    user = make_user(email="scout-cap@test.com", tier="scout")
    # Pre-fill 10 slugged records owned by user
    for i in range(10):
        rec = BacktestRecord(
            id=f"bt-pre-{i}",
            strategy_type="momentum",
            strategy_name=f"Strategy {i}",
            result_payload={"strategy_json": {}, "metrics": {}},
            slug=f"strategy-{i}-abc1",
            name=f"Strategy {i}",
            is_public=True,
            user_id=user.id,
        )
        db.add(rec)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        save_strategy(_make_req(backtest_id="bt-new", name="One more"), user=user, db=db)
    assert exc.value.status_code == 402
    entitlement = exc.value.detail["entitlement"]
    assert entitlement["code"] == "saved_strategies_quota_reached"
    assert entitlement["current_tier"] == "scout"
    assert entitlement["current_value"] == "10"
    assert entitlement["limit_value"] == "10"


def test_save_strategist_cap_25(make_user, db: Session) -> None:
    """Strategist's saved_strategies_max is 25; 26th save raises 402."""
    user = make_user(email="strat-cap@test.com", tier="strategist")
    for i in range(25):
        db.add(BacktestRecord(
            id=f"bt-{i}",
            strategy_type="momentum",
            strategy_name=f"S{i}",
            result_payload={"strategy_json": {}, "metrics": {}},
            slug=f"strat-{i}-xyz1",
            name=f"S{i}",
            is_public=False,
            user_id=user.id,
        ))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        save_strategy(_make_req(backtest_id="bt-new"), user=user, db=db)
    assert exc.value.status_code == 402
    assert exc.value.detail["entitlement"]["limit_value"] == "25"


def test_cap_only_counts_records_owned_by_user(make_user, db: Session) -> None:
    """Strategies owned by other users (or anonymous legacy rows) do NOT
    count toward this user's cap — otherwise the cap is shared globally."""
    alice = make_user(email="alice@test.com", tier="scout")
    bob = make_user(email="bob@test.com", tier="scout")
    # 10 records owned by Bob — should not block Alice
    for i in range(10):
        db.add(BacktestRecord(
            id=f"bob-{i}",
            strategy_type="momentum",
            strategy_name=f"BobStrat{i}",
            result_payload={"strategy_json": {}, "metrics": {}},
            slug=f"bob-{i}-aaaa",
            name=f"Bob{i}",
            is_public=True,
            user_id=bob.id,
        ))
    db.commit()

    # Alice's first save must succeed — Bob's 10 records don't count for her.
    resp = save_strategy(_make_req(backtest_id="alice-1"), user=alice, db=db)
    assert resp.is_public is True  # Scout forces public
    assert resp.slug is not None


# ── Save: Scout force-public override ────────────────────────────────────────


def test_scout_save_forces_is_public_true_even_when_request_says_false(
    make_user, db: Session
) -> None:
    """Spec: Scout tier saved_strategies_always_public=True — overrides the
    request body's is_public regardless of what was sent."""
    user = make_user(email="scout-force@test.com", tier="scout")
    resp = save_strategy(
        _make_req(backtest_id="bt-scout-1", is_public=False),
        user=user, db=db,
    )
    assert resp.is_public is True
    # And the DB row is actually marked public, not just the response.
    record = db.query(BacktestRecord).filter(BacktestRecord.slug == resp.slug).one()
    assert record.is_public is True


def test_strategist_save_honors_is_public_false(make_user, db: Session) -> None:
    """Strategist+ may save as private (saved_strategies_always_public=False)."""
    user = make_user(email="strat-priv@test.com", tier="strategist")
    resp = save_strategy(
        _make_req(backtest_id="bt-strat-priv", is_public=False),
        user=user, db=db,
    )
    assert resp.is_public is False


# ── Save: user_id stamping ───────────────────────────────────────────────────


def test_save_stamps_user_id_on_new_record(make_user, db: Session) -> None:
    user = make_user(email="stamp@test.com", tier="strategist")
    resp = save_strategy(_make_req(backtest_id="bt-stamp"), user=user, db=db)
    record = db.query(BacktestRecord).filter(BacktestRecord.slug == resp.slug).one()
    assert record.user_id == user.id


def test_save_claims_legacy_anonymous_record(make_user, db: Session) -> None:
    """Anonymous-era records have user_id=None; the first authed save claims them."""
    user = make_user(email="claim@test.com", tier="strategist")
    db.add(BacktestRecord(
        id="bt-legacy",
        strategy_type="momentum",
        strategy_name="Legacy run",
        result_payload={"strategy_json": {}, "metrics": {}},
        user_id=None,  # legacy
    ))
    db.commit()

    resp = save_strategy(_make_req(backtest_id="bt-legacy"), user=user, db=db)
    record = db.query(BacktestRecord).filter(BacktestRecord.id == "bt-legacy").one()
    assert record.user_id == user.id
    assert record.slug == resp.slug


def test_save_rejects_record_owned_by_another_user(make_user, db: Session) -> None:
    """A user cannot save someone else's existing BacktestRecord."""
    alice = make_user(email="alice-own@test.com")
    bob = make_user(email="bob-own@test.com")
    db.add(BacktestRecord(
        id="bt-alice",
        strategy_type="momentum",
        strategy_name="Alice's run",
        result_payload={"strategy_json": {}, "metrics": {}},
        user_id=alice.id,
    ))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        save_strategy(_make_req(backtest_id="bt-alice"), user=bob, db=db)
    assert exc.value.status_code == 403


# ── update_visibility: owner check ───────────────────────────────────────────


def test_update_visibility_rejects_non_owner(make_user, db: Session) -> None:
    alice = make_user(email="alice-vis@test.com", tier="strategist")
    bob = make_user(email="bob-vis@test.com", tier="strategist")
    save_strategy(_make_req(backtest_id="bt-vis-1"), user=alice, db=db)
    # Find Alice's slug
    record = db.query(BacktestRecord).filter(BacktestRecord.user_id == alice.id).one()
    slug = record.slug
    assert slug is not None

    with pytest.raises(HTTPException) as exc:
        update_visibility(
            slug,
            VisibilityUpdateRequest(is_public=False),
            user=bob, db=db,
        )
    assert exc.value.status_code == 403


def test_update_visibility_allows_owner(make_user, db: Session) -> None:
    user = make_user(email="vis-owner@test.com", tier="strategist")
    save_strategy(_make_req(backtest_id="bt-vis-own"), user=user, db=db)
    record = db.query(BacktestRecord).filter(BacktestRecord.user_id == user.id).one()
    slug = record.slug
    assert slug is not None

    resp = update_visibility(
        slug,
        VisibilityUpdateRequest(is_public=False),
        user=user, db=db,
    )
    assert resp.is_public is False
    db.refresh(record)
    assert record.is_public is False


def test_update_visibility_allows_anyone_for_legacy_record(make_user, db: Session) -> None:
    """Legacy anonymous-era records (user_id=None) remain editable — pragmatic
    compatibility shim; the audit notes this should tighten in a follow-up."""
    user = make_user(email="legacy-vis@test.com", tier="strategist")
    db.add(BacktestRecord(
        id="bt-orphan",
        strategy_type="momentum",
        strategy_name="Orphan",
        result_payload={"strategy_json": {}, "metrics": {}},
        slug="orphan-strategy",
        name="Orphan",
        is_public=True,
        user_id=None,
    ))
    db.commit()

    resp = update_visibility(
        "orphan-strategy",
        VisibilityUpdateRequest(is_public=False),
        user=user, db=db,
    )
    assert resp.is_public is False
