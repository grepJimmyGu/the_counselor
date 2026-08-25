"""GET /api/saved-strategies/open-positions — PRD-28 Step 4.

The per-strategy dashboard answers "how is THIS strategy doing". Nothing
answered "what am I holding, and what happens next" without already knowing
which strategy to open — which is the question someone actually has.

Also covers the price regression this step surfaced: the positions grid read
only the intraday cache, so a DAILY position had no current price and no
distance-to-tier at all.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.api.routes.saved_strategies import (
    get_strategy_positions,
    list_open_positions,
)
from app.models.position_state import PositionState
from app.models.price_bar import PriceBar
from app.models.saved_strategy import SavedStrategy

LADDER = [
    {"trigger_pct": -0.08, "action": "sell_all", "label": "Stop"},
    {"trigger_pct": 0.15, "action": "sell_fraction", "fraction": 0.5, "label": "TP1"},
    {"trigger_pct": 0.30, "action": "sell_all", "label": "TP2"},
]


def _strategy(db, user, *, sid, title="Momentum runner", ladder=LADDER,
              bar_resolution="daily"):
    row = SavedStrategy(
        id=sid, user_id=user.id, title=title, is_public=False,
        strategy_json={
            "strategy_name": title, "universe": ["NVDA"],
            "bar_resolution": bar_resolution,
            "risk_management": {"exit_ladder": ladder} if ladder else {},
        },
    )
    db.add(row)
    db.commit()
    return row


def _position(db, *, sid, pid, symbol="NVDA", entry=100.0, shares=120.0,
              log=None, is_open=True):
    pos = PositionState(
        id=pid, saved_strategy_id=sid, symbol=symbol,
        entered_at=datetime.utcnow(), entry_price=entry,
        shares_initial=shares, shares_remaining=shares, is_open=is_open,
        trade_log=log if log is not None else [{"event": "entry", "status": "declared"}],
    )
    db.add(pos)
    db.commit()
    return pos


def _daily_bar(db, symbol, close, *, days_ago=0):
    db.add(PriceBar(
        symbol=symbol, trading_date=date.today() - timedelta(days=days_ago),
        open=close, high=close, low=close, close=close, adjusted_close=close,
        volume=1_000_000, dividend_amount=0.0, split_coefficient=1.0,
    ))
    db.commit()


# ── the price regression ────────────────────────────────────────────────────


def test_REGRESSION_a_daily_position_has_a_current_price(
    make_user, db: Session,
) -> None:
    """The positions grid read ONLY `IntradayBar`.

    A daily strategy has no intraday bars — nothing writes them for it — so
    `latest_price` and `pct_change_from_entry` came back None for every daily
    position, and the dashboard's distance-to-tier bars had nothing to
    render. On the only configuration the product supports.

    Same shape as the daily gates #331/#337/#340 removed: correct when
    active execution meant intraday, never revisited when that inverted.
    """
    user = make_user(email="pos-daily-price@test.com")
    _strategy(db, user, sid="s-dp")
    _position(db, sid="s-dp", pid="p-dp", entry=100.0)
    _daily_bar(db, "NVDA", 108.0)

    rows = list_open_positions(current_user=user, db=db)
    assert len(rows) == 1
    assert rows[0].latest_price == pytest.approx(108.0)
    assert rows[0].pct_change_from_entry == pytest.approx(0.08)
    assert rows[0].price_source == "daily_close"


def test_REGRESSION_the_per_strategy_grid_got_the_same_fix(
    make_user, db: Session,
) -> None:
    """The bug lived in `get_strategy_positions`; the new endpoint would have
    quietly worked around it by having its own resolver. Both call the same
    helper so neither can drift back."""
    user = make_user(email="pos-grid-price@test.com")
    _strategy(db, user, sid="s-grid")
    _position(db, sid="s-grid", pid="p-grid", entry=100.0)
    _daily_bar(db, "NVDA", 92.0)

    resp = get_strategy_positions("s-grid", current_user=user, db=db)
    assert resp.positions[0].latest_price == pytest.approx(92.0)
    assert resp.positions[0].pct_change_from_entry == pytest.approx(-0.08)


def test_a_symbol_with_no_bars_at_all_degrades_rather_than_errors(
    make_user, db: Session,
) -> None:
    """A newly-listed name, or one we have not ingested, must not take the
    whole page down — the other positions are still worth showing."""
    user = make_user(email="pos-nobars@test.com")
    _strategy(db, user, sid="s-nb")
    _position(db, sid="s-nb", pid="p-nb", symbol="ZZZZ", entry=50.0)

    rows = list_open_positions(current_user=user, db=db)
    assert len(rows) == 1
    assert rows[0].latest_price is None
    assert rows[0].price_source == "none"
    # A tier without a price still has its price level; only the distance
    # is unknowable.
    assert rows[0].stop is not None
    assert rows[0].stop.price == pytest.approx(46.0)
    assert rows[0].stop.distance_pct is None


# ── the tiers ───────────────────────────────────────────────────────────────


def test_reports_the_live_stop_and_the_next_target(
    make_user, db: Session,
) -> None:
    """Both, not one. A position has a live stop AND a live target at the
    same time; picking a single "next tier" would be arbitrary."""
    user = make_user(email="pos-tiers@test.com")
    _strategy(db, user, sid="s-t")
    _position(db, sid="s-t", pid="p-t", entry=100.0)
    _daily_bar(db, "NVDA", 105.0)

    p = list_open_positions(current_user=user, db=db)[0]
    assert p.stop.label == "Stop"
    assert p.stop.price == pytest.approx(92.0)
    assert p.next_target.label == "TP1"
    assert p.next_target.price == pytest.approx(115.0)


def test_distance_is_measured_from_here_not_from_entry(
    make_user, db: Session,
) -> None:
    """The trigger is measured from entry; the DISTANCE is what a holder
    wants — how far the price must move from where it is now. At 105 with a
    stop at 92, that is -12.4%, not the tier's -8%."""
    user = make_user(email="pos-dist@test.com")
    _strategy(db, user, sid="s-d")
    _position(db, sid="s-d", pid="p-d", entry=100.0)
    _daily_bar(db, "NVDA", 105.0)

    p = list_open_positions(current_user=user, db=db)[0]
    assert p.stop.trigger_pct == pytest.approx(-0.08)
    assert p.stop.distance_pct == pytest.approx((92.0 - 105.0) / 105.0)
    assert p.next_target.distance_pct == pytest.approx((115.0 - 105.0) / 105.0)


def test_a_fired_tier_is_not_reported_as_live(make_user, db: Session) -> None:
    """REGRESSION-shaped. A stop that already fired must not still show as
    protection — a user reading "stop at $92" on a position whose stop went
    yesterday believes they are covered when they are not.

    Fired-ness comes from `trigger_type_for`, the same indexing the monitor
    and the backtester use, rather than a local rule that could drift.
    """
    user = make_user(email="pos-fired@test.com")
    _strategy(db, user, sid="s-f")
    _position(db, sid="s-f", pid="p-f", entry=100.0, log=[
        {"event": "entry", "status": "declared"},
        # tier index 1 == TP1
        {"event": "tier1_hit", "status": "executed", "tier_label": "TP1"},
    ])
    _daily_bar(db, "NVDA", 120.0)

    p = list_open_positions(current_user=user, db=db)[0]
    assert p.stop.label == "Stop"          # tier 0 never fired
    assert p.next_target.label == "TP2"    # TP1 did, so TP2 is next


def test_a_strategy_with_no_ladder_reports_no_tiers(
    make_user, db: Session,
) -> None:
    """Possible now that `track` can leave a strategy untracked — report the
    position honestly rather than inventing rungs for it."""
    user = make_user(email="pos-noladder@test.com")
    _strategy(db, user, sid="s-nl", ladder=None)
    _position(db, sid="s-nl", pid="p-nl")

    p = list_open_positions(current_user=user, db=db)[0]
    assert p.stop is None and p.next_target is None


# ── scope and ordering ──────────────────────────────────────────────────────


def test_spans_every_strategy_and_names_each(make_user, db: Session) -> None:
    """The reason the endpoint exists. Per-strategy grids require knowing
    which strategy to open first."""
    user = make_user(email="pos-span@test.com")
    _strategy(db, user, sid="s-a", title="Momentum runner")
    _strategy(db, user, sid="s-b", title="Mean reversion")
    _position(db, sid="s-a", pid="p-a", symbol="NVDA")
    _position(db, sid="s-b", pid="p-b", symbol="MSFT")

    rows = list_open_positions(current_user=user, db=db)
    assert {r.symbol for r in rows} == {"NVDA", "MSFT"}
    assert {r.strategy_title for r in rows} == {"Momentum runner", "Mean reversion"}


def test_a_position_with_an_open_decision_sorts_first(
    make_user, db: Session,
) -> None:
    """An unresolved tier is a decision the user owes; everything else is
    just a holding. It must not be somewhere down the list."""
    user = make_user(email="pos-order@test.com")
    _strategy(db, user, sid="s-o")
    _position(db, sid="s-o", pid="p-quiet", symbol="MSFT")
    _position(db, sid="s-o", pid="p-loud", symbol="NVDA", log=[
        {"event": "entry", "status": "declared"},
        {"event": "tier0_hit", "status": "pending_confirmation", "tier_label": "Stop"},
    ])

    rows = list_open_positions(current_user=user, db=db)
    assert rows[0].position_id == "p-loud"
    assert rows[0].unresolved_count == 1
    assert rows[1].unresolved_count == 0


def test_closed_positions_are_not_listed(make_user, db: Session) -> None:
    user = make_user(email="pos-closed@test.com")
    _strategy(db, user, sid="s-c")
    _position(db, sid="s-c", pid="p-closed", is_open=False)
    assert list_open_positions(current_user=user, db=db) == []


def test_another_users_positions_are_never_returned(
    make_user, db: Session,
) -> None:
    """The query is scoped by the caller's strategies, so this is really a
    test that the scoping is by OWNERSHIP and not by anything guessable."""
    owner = make_user(email="pos-owner@test.com")
    other = make_user(email="pos-other@test.com")
    _strategy(db, owner, sid="s-priv")
    _position(db, sid="s-priv", pid="p-priv")

    assert list_open_positions(current_user=other, db=db) == []
    assert len(list_open_positions(current_user=owner, db=db)) == 1


def test_a_user_with_nothing_tracked_gets_an_empty_list(
    make_user, db: Session,
) -> None:
    user = make_user(email="pos-empty@test.com")
    assert list_open_positions(current_user=user, db=db) == []
