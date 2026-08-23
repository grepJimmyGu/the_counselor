"""POST /api/saved-strategies/{id}/exit-ladder — the save-strategy sign-off.

`test_exit_ladder_signoff_guard.py` proves nothing ELSE can write a ladder.
This file proves this endpoint does it correctly, and that the thing it
unlocks actually works: a strategy saved without an exit rule can acquire
one and then be tracked.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.saved_strategies import (
    AttachExitLadderRequest,
    attach_exit_ladder,
    declare_position,
    DeclarePositionRequest,
)
from app.models.saved_strategy import SavedStrategy

LADDER = [
    {"trigger_pct": -0.08, "action": "sell_all", "label": "Stop"},
    {"trigger_pct": 0.15, "action": "sell_fraction", "fraction": 0.5, "label": "TP1"},
    {"trigger_pct": 0.30, "action": "sell_all", "label": "TP2"},
]


def _strategy(db: Session, user, *, sid: str, strategy_json: dict) -> SavedStrategy:
    row = SavedStrategy(
        id=sid, user_id=user.id, title="Momentum runner",
        strategy_json=strategy_json, is_public=False,
    )
    db.add(row)
    db.commit()
    return row


def _bare(**extra) -> dict:
    """A strategy as `track` finds it: saved, backtested, no exit rule."""
    return {
        "strategy_name": "Momentum runner",
        "strategy_type": "custom_build",
        "universe": ["NVDA"],
        "bar_resolution": "daily",
        **extra,
    }


def _attach(db, user, sid, ladder):
    return attach_exit_ladder(
        sid, AttachExitLadderRequest(exit_ladder=ladder),
        current_user=user, db=db,
    )


# ── the write ───────────────────────────────────────────────────────────────


def test_attaching_a_ladder_actually_persists(make_user, db: Session) -> None:
    """REGRESSION for the JSON-column trap, and the reason the endpoint
    reassigns `strategy_json` rather than mutating it.

    `SavedStrategy.strategy_json` is a plain `JSON` column with no
    `MutableDict` wrapper, so SQLAlchemy's dirty-check compares object
    IDENTITY. Mutating the nested dict in place leaves the row unflagged and
    `db.commit()` writes nothing — the endpoint returns 200 with the new
    ladder in the response body, and the next read has the old one. A
    silent no-op that looks like a success is the worst available outcome
    for a control that decides when someone's position gets sold.

    Asserted after an `expire_all`, so the check goes to the database
    rather than the identity map.
    """
    user = make_user(email="ladder-persist@test.com")
    _strategy(db, user, sid="s-persist", strategy_json=_bare())

    _attach(db, user, "s-persist", LADDER)

    db.expire_all()
    fresh = db.get(SavedStrategy, "s-persist")
    tiers = fresh.strategy_json["risk_management"]["exit_ladder"]
    assert [t["trigger_pct"] for t in tiers] == [-0.08, 0.15, 0.30]
    assert tiers[1]["fraction"] == 0.5
    assert tiers[0]["label"] == "Stop"


def test_a_ladder_replaces_rather_than_merges(make_user, db: Session) -> None:
    """The client renders the whole ladder and the user edits it there, so
    what comes back is the entire intended state. Merging would leave the
    saved ladder in a shape neither side ever displayed — e.g. a deleted
    tier quietly surviving."""
    user = make_user(email="ladder-replace@test.com")
    _strategy(db, user, sid="s-replace", strategy_json=_bare(
        risk_management={"exit_ladder": LADDER},
    ))

    _attach(db, user, "s-replace", [
        {"trigger_pct": -0.05, "action": "sell_all", "label": "Tighter stop"},
    ])

    db.expire_all()
    tiers = db.get(SavedStrategy, "s-replace").strategy_json["risk_management"]["exit_ladder"]
    assert len(tiers) == 1
    assert tiers[0]["trigger_pct"] == -0.05


def test_other_risk_settings_survive(make_user, db: Session) -> None:
    """Only the ladder is this endpoint's business. A user who set a
    max-drawdown stop should not lose it by editing their exits."""
    user = make_user(email="ladder-siblings@test.com")
    _strategy(db, user, sid="s-siblings", strategy_json=_bare(
        risk_management={"max_drawdown_stop": 0.25},
    ))

    _attach(db, user, "s-siblings", LADDER)

    db.expire_all()
    risk = db.get(SavedStrategy, "s-siblings").strategy_json["risk_management"]
    assert risk["max_drawdown_stop"] == 0.25
    assert len(risk["exit_ladder"]) == 3


# ── the refusals ────────────────────────────────────────────────────────────


def test_a_stranger_cannot_change_your_stop(make_user, db: Session) -> None:
    """404, not 403 — don't confirm the strategy exists to someone who
    doesn't own it."""
    owner = make_user(email="ladder-owner@test.com")
    other = make_user(email="ladder-other@test.com")
    _strategy(db, owner, sid="s-owned", strategy_json=_bare())

    with pytest.raises(HTTPException) as exc:
        _attach(db, other, "s-owned", LADDER)
    assert exc.value.status_code == 404


def test_an_empty_ladder_is_refused(make_user, db: Session) -> None:
    """"No tiers" is not a ladder, and accepting it would leave a tracked
    position with nothing monitoring it — worse than untracked, because the
    dashboard still says the strategy is live."""
    user = make_user(email="ladder-empty@test.com")
    _strategy(db, user, sid="s-empty", strategy_json=_bare())

    with pytest.raises(HTTPException) as exc:
        _attach(db, user, "s-empty", [])
    assert exc.value.status_code == 400


def test_a_ladder_with_no_stop_is_refused_in_words_a_person_can_read(
    make_user, db: Session,
) -> None:
    """Targets without a stop is the dangerous shape: unlimited downside,
    capped upside. `RiskManagement` already rejects it — the point here is
    that the reason reaches the user.

    The tiers came from a form they just filled in, so the message has to be
    a sentence, not a pydantic envelope.
    """
    user = make_user(email="ladder-nostop@test.com")
    _strategy(db, user, sid="s-nostop", strategy_json=_bare())

    with pytest.raises(HTTPException) as exc:
        _attach(db, user, "s-nostop", [
            {"trigger_pct": 0.15, "action": "sell_fraction", "fraction": 0.5},
            {"trigger_pct": 0.30, "action": "sell_all"},
        ])
    assert exc.value.status_code == 400
    detail = str(exc.value.detail)
    assert "stop tier" in detail
    # Not the raw pydantic wrapper.
    assert "Value error" not in detail
    assert "AttachExitLadderRequest" not in detail


def test_out_of_order_tiers_are_refused(make_user, db: Session) -> None:
    """The evaluator relies on index order BEING ascending order — it checks
    the most negative stop first and stops at the first `sell_all`. An
    unsorted ladder would fire the wrong tier."""
    user = make_user(email="ladder-order@test.com")
    _strategy(db, user, sid="s-order", strategy_json=_bare())

    with pytest.raises(HTTPException) as exc:
        _attach(db, user, "s-order", [
            {"trigger_pct": 0.30, "action": "sell_all"},
            {"trigger_pct": -0.08, "action": "sell_all"},
        ])
    assert exc.value.status_code == 400


def test_a_fractional_tier_without_a_fraction_is_refused(
    make_user, db: Session,
) -> None:
    """`sell_fraction` with no fraction has no meaning — the monitor would
    have to guess how much of the position to sell."""
    user = make_user(email="ladder-frac@test.com")
    _strategy(db, user, sid="s-frac", strategy_json=_bare())

    with pytest.raises(HTTPException) as exc:
        _attach(db, user, "s-frac", [
            {"trigger_pct": -0.08, "action": "sell_all"},
            {"trigger_pct": 0.15, "action": "sell_fraction"},
        ])
    assert exc.value.status_code == 400


# ── what it unlocks ─────────────────────────────────────────────────────────


def test_attaching_a_ladder_makes_the_strategy_trackable(
    make_user, db: Session,
) -> None:
    """The whole point of the step, end to end.

    `declare_position` 400s on a strategy with no exit ladder — there is
    nothing to monitor a position against. That was an inescapable dead end
    for template strategies, which arrive with no exit rule and had no way
    to acquire one. Attach, then declare.
    """
    user = make_user(email="ladder-unlock@test.com")
    _strategy(db, user, sid="s-unlock", strategy_json=_bare())

    # Before: refused, and the message says why.
    with pytest.raises(HTTPException) as exc:
        declare_position(
            "s-unlock",
            DeclarePositionRequest(symbol="NVDA", shares=120, entry_price=118.40),
            current_user=user, db=db,
        )
    assert exc.value.status_code == 400
    assert "exit ladder" in str(exc.value.detail)

    _attach(db, user, "s-unlock", LADDER)

    # After: tracked, against the ladder the user just signed off on.
    pos = declare_position(
        "s-unlock",
        DeclarePositionRequest(symbol="NVDA", shares=120, entry_price=118.40),
        current_user=user, db=db,
    )
    assert pos.symbol == "NVDA"
    assert pos.shares_remaining == 120


def test_the_saved_ladder_is_the_one_the_evaluator_reads(
    make_user, db: Session,
) -> None:
    """Cross-check against the real evaluator rather than the stored JSON.

    A ladder can round-trip through the database intact and still be inert
    — that is exactly what `ladderFromNatr`'s unit bug did, storing `-6.0`
    where `-0.06` was meant and passing every persistence check. So assert
    the saved tiers actually fire on a price move.
    """
    from types import SimpleNamespace
    from app.services.exit_ladder import Bar, evaluate_bar

    user = make_user(email="ladder-fires@test.com")
    _strategy(db, user, sid="s-fires", strategy_json=_bare())
    _attach(db, user, "s-fires", LADDER)

    db.expire_all()
    tiers = db.get(SavedStrategy, "s-fires").strategy_json["risk_management"]["exit_ladder"]
    ladder = [SimpleNamespace(**{"fraction": None, **t}) for t in tiers]

    entry = 100.0
    # -8% closes it; -7% does not.
    assert [f.tier_label for f in
            evaluate_bar(ladder=ladder, entry_price=entry, bar=Bar.from_close(92.0))] == ["Stop"]
    assert evaluate_bar(ladder=ladder, entry_price=entry, bar=Bar.from_close(93.0)) == []
    # +30% clears both targets.
    fired = evaluate_bar(ladder=ladder, entry_price=entry, bar=Bar.from_close(130.0))
    assert [f.tier_label for f in fired] == ["TP1", "TP2"]
