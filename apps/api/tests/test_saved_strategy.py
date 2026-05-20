"""Stage 1a — saved strategy service: Scout force-public, tier caps."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest


def _make_payload(title: str = "Test Strategy", is_public: bool = False) -> SaveStrategyRequest:
    return SaveStrategyRequest(
        title=title,
        strategy_json={"strategy_type": "momentum", "universe": ["AAPL"]},
        is_public=is_public,
    )


# ── Scout force-public + cap ─────────────────────────────────────────────────


def test_scout_save_forces_is_public_true_even_when_payload_says_false(
    make_user, db: Session
) -> None:
    user = make_user(email="scout-save@test.com", tier="scout")
    strategy = saved_strategy_service.save_strategy(
        db, user, _make_payload(is_public=False)
    )
    assert strategy.is_public is True


def test_scout_save_forces_is_public_when_omitted(make_user, db: Session) -> None:
    user = make_user(email="scout-default@test.com", tier="scout")
    strategy = saved_strategy_service.save_strategy(db, user, _make_payload())
    assert strategy.is_public is True


def test_scout_10_save_cap_succeeds_at_10(make_user, db: Session) -> None:
    user = make_user(email="cap10@test.com", tier="scout")
    for i in range(10):
        saved_strategy_service.save_strategy(db, user, _make_payload(title=f"S{i}"))
    assert len(saved_strategy_service.list_user_strategies(db, user.id)) == 10


def test_scout_11th_save_returns_402(make_user, db: Session) -> None:
    user = make_user(email="cap11@test.com", tier="scout")
    for i in range(10):
        saved_strategy_service.save_strategy(db, user, _make_payload(title=f"S{i}"))

    with pytest.raises(HTTPException) as exc_info:
        saved_strategy_service.save_strategy(db, user, _make_payload(title="S11"))
    assert exc_info.value.status_code == 402
    detail = exc_info.value.detail
    assert detail["entitlement"]["code"] == "saved_strategies_quota_reached"
    assert detail["entitlement"]["current_tier"] == "scout"
    assert detail["entitlement"]["required_tier"] == "strategist"
    assert detail["entitlement"]["current_value"] == "10"
    assert detail["entitlement"]["limit_value"] == "10"


# ── Strategist respects is_public + larger cap ───────────────────────────────


def test_strategist_save_respects_is_public_flag(make_user, db: Session) -> None:
    user = make_user(email="strat@test.com", tier="strategist")
    private = saved_strategy_service.save_strategy(
        db, user, _make_payload(title="priv", is_public=False)
    )
    public = saved_strategy_service.save_strategy(
        db, user, _make_payload(title="pub", is_public=True)
    )
    assert private.is_public is False
    assert public.is_public is True


def test_strategist_25_cap(make_user, db: Session) -> None:
    user = make_user(email="strat25@test.com", tier="strategist")
    for i in range(25):
        saved_strategy_service.save_strategy(db, user, _make_payload(title=f"P{i}"))
    with pytest.raises(HTTPException) as exc_info:
        saved_strategy_service.save_strategy(db, user, _make_payload(title="P26"))
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail["entitlement"]["limit_value"] == "25"


# ── Listing / deleting ───────────────────────────────────────────────────────


def test_list_returns_newest_first(make_user, db: Session) -> None:
    user = make_user(email="list@test.com")
    a = saved_strategy_service.save_strategy(db, user, _make_payload(title="A"))
    b = saved_strategy_service.save_strategy(db, user, _make_payload(title="B"))
    c = saved_strategy_service.save_strategy(db, user, _make_payload(title="C"))
    titles = [s.title for s in saved_strategy_service.list_user_strategies(db, user.id)]
    assert titles == ["C", "B", "A"]


def test_delete_only_works_for_owner(make_user, db: Session) -> None:
    alice = make_user(email="alice@test.com")
    bob = make_user(email="bob@test.com")
    s = saved_strategy_service.save_strategy(db, alice, _make_payload())

    # Bob tries to delete Alice's strategy — must fail.
    assert saved_strategy_service.delete_strategy(db, bob.id, s.id) is False
    assert saved_strategy_service.get_strategy(db, s.id) is not None

    # Alice deletes her own — succeeds.
    assert saved_strategy_service.delete_strategy(db, alice.id, s.id) is True
    assert saved_strategy_service.get_strategy(db, s.id) is None
