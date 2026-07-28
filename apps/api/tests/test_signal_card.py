"""PRD-25 — unified signal card service.

Maps the existing per-strategy signal state onto the uniform SignalCard,
with no new computation. Covers: state mapping (long/cash/basket/pending),
L2 fired-primitive humanization, non-prescriptive copy, and the batch
ownership + ordering contract.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.schemas.signal_card import SignalCardState
from app.services.signal_card_service import card_from_state, evaluate_cards


def _strategy(
    sid: str = "s1",
    user_id: str = "u1",
    title: str = "My Strat",
    strategy_json: dict = None,
    backtest_id: str = None,
) -> SavedStrategy:
    return SavedStrategy(
        id=sid,
        user_id=user_id,
        title=title,
        strategy_json=strategy_json
        or {"strategy_type": "rsi_mean_reversion", "universe": ["NVDA"]},
        is_public=False,
        backtest_record_id=backtest_id,
    )


def _state(
    sid: str = "s1",
    signal: dict = None,
    display: str = "LONG NVDA",
    as_of: date = None,
) -> SavedStrategySignalState:
    return SavedStrategySignalState(
        saved_strategy_id=sid,
        current_signal=signal if signal is not None else {"position": "long", "ticker": "NVDA"},
        current_signal_display=display,
        as_of_date=as_of or date(2026, 7, 28),
    )


# ── state mapping ─────────────────────────────────────────────────────────


def test_long_maps_to_in_signal() -> None:
    card = card_from_state(_strategy(), _state(signal={"position": "long", "ticker": "NVDA"}))
    assert card.state == SignalCardState.IN_SIGNAL
    assert card.symbol == "NVDA"
    assert card.display == "LONG NVDA"
    assert card.as_of == "2026-07-28"


def test_cash_maps_to_flat() -> None:
    card = card_from_state(_strategy(), _state(signal={"position": "cash"}, display="CASH"))
    assert card.state == SignalCardState.FLAT
    assert card.symbol is None


def test_basket_maps_to_basket() -> None:
    card = card_from_state(
        _strategy(strategy_json={"strategy_type": "momentum", "universe": ["A", "B"]}),
        _state(signal={"holdings": [{"ticker": "A"}, {"ticker": "B"}]}, display="A, B"),
    )
    assert card.state == SignalCardState.BASKET
    assert "2 names" in card.reason


def test_none_state_maps_to_pending() -> None:
    card = card_from_state(_strategy(), None)
    assert card.state == SignalCardState.PENDING
    assert card.as_of is None
    # backtest link still surfaces (L3) even when the signal is pending.
    card2 = card_from_state(_strategy(backtest_id="bt-1"), None)
    assert card2.backtest_id == "bt-1"


def test_empty_signal_maps_to_pending() -> None:
    card = card_from_state(_strategy(), _state(signal={}, display="—"))
    assert card.state == SignalCardState.PENDING


# ── L2 fired-primitive humanization ───────────────────────────────────────


def test_fired_primitives_humanizes_custom_build_rules() -> None:
    sj = {
        "strategy_type": "custom_build",
        "rules": [
            {"primitive_id": "rsi", "operator": "lt", "threshold": 30},
            {"primitive_id": "sma_200", "operator": "gt"},
        ],
    }
    card = card_from_state(
        _strategy(strategy_json=sj), _state(signal={"position": "cash"}, display="CASH")
    )
    assert card.fired_primitives == ["rsi lt 30", "sma 200"]


def test_fired_primitives_empty_for_classic_type() -> None:
    card = card_from_state(_strategy(), _state(signal={"position": "cash"}, display="CASH"))
    assert card.fired_primitives == []


# ── compliance: descriptive, never prescriptive ───────────────────────────


def test_reason_is_non_prescriptive() -> None:
    for signal, display in (
        ({"position": "long", "ticker": "NVDA"}, "LONG NVDA"),
        ({"position": "cash"}, "CASH"),
        ({"holdings": [{"ticker": "A"}]}, "A"),
    ):
        card = card_from_state(_strategy(), _state(signal=signal, display=display))
        low = card.reason.lower()
        assert "buy" not in low and "sell" not in low and "should" not in low


# ── batch: ownership + ordering (two queries, order preserved) ─────────────


def test_batch_returns_only_owned_in_request_order(db: Session, make_user) -> None:
    user = make_user(email="cards@test.com")
    other = make_user(email="other@test.com")
    db.add_all(
        [
            _strategy(sid="s1", user_id=user.id, title="One"),
            _strategy(sid="s2", user_id=user.id, title="Two"),
            _strategy(sid="s3", user_id=other.id, title="Nope"),
        ]
    )
    db.commit()
    db.add(_state(sid="s1", signal={"position": "long", "ticker": "NVDA"}))
    db.commit()

    cards = evaluate_cards(db, ["s2", "s1", "s3"], user.id)
    assert [c.saved_strategy_id for c in cards] == ["s2", "s1"]  # s3 not owned → dropped
    assert cards[0].state == SignalCardState.PENDING  # s2 has no state row
    assert cards[1].state == SignalCardState.IN_SIGNAL  # s1 has a long state


def test_batch_empty_returns_empty(db: Session, make_user) -> None:
    user = make_user(email="empty@test.com")
    assert evaluate_cards(db, [], user.id) == []


def test_batch_dedupes_ids(db: Session, make_user) -> None:
    user = make_user(email="dedupe@test.com")
    db.add(_strategy(sid="s1", user_id=user.id, title="One"))
    db.commit()
    cards = evaluate_cards(db, ["s1", "s1", "s1"], user.id)
    assert len(cards) == 1
