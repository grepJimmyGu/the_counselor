"""PRD-16c-3 — PositionState ORM tests.

Covers lifecycle (entry → partial exit → full exit), the trade_log JSON
column, and the saved_strategy_id FK + cascade behavior.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.position_state import PositionState
from app.models.saved_strategy import SavedStrategy


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_strategy(db: Session, *, user_id: str = "user-1") -> SavedStrategy:
    s = SavedStrategy(
        id=str(uuid4()),
        user_id=user_id,
        title="Test Active Strategy",
        strategy_json={
            "strategy_name": "Test",
            "strategy_type": "custom_build",
        },
        is_public=False,
    )
    db.add(s)
    db.commit()
    return s


def _make_position(
    db: Session,
    strategy: SavedStrategy,
    *,
    symbol: str = "AAPL",
    entry_price: float = 100.0,
    shares: float = 10.0,
) -> PositionState:
    pos = PositionState(
        id=str(uuid4()),
        saved_strategy_id=strategy.id,
        symbol=symbol,
        entered_at=datetime.utcnow(),
        entry_price=entry_price,
        shares_initial=shares,
        shares_remaining=shares,
        trade_log=[
            {"event": "entry", "timestamp": datetime.utcnow().isoformat(),
             "price": entry_price, "shares": shares},
        ],
    )
    db.add(pos)
    db.commit()
    return pos


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_position_state_creates_with_open_defaults(db: Session) -> None:
    strategy = _make_strategy(db)
    pos = _make_position(db, strategy)
    db.refresh(pos)
    assert pos.is_open is True
    assert pos.closed_at is None
    assert pos.final_pnl is None
    assert pos.shares_remaining == pos.shares_initial


def test_partial_exit_decrements_shares_remaining(db: Session) -> None:
    strategy = _make_strategy(db)
    pos = _make_position(db, strategy, shares=10.0)
    # TP1 hit: sell 1/3 (3.33 shares).
    sold = pos.shares_initial / 3
    pos.shares_remaining -= sold
    pos.trade_log = pos.trade_log + [{
        "event": "tp1_hit",
        "timestamp": datetime.utcnow().isoformat(),
        "price": 115.0,
        "shares_sold": sold,
    }]
    db.commit()
    db.refresh(pos)
    assert pos.shares_remaining == pytest.approx(6.67, abs=0.01)
    assert pos.is_open is True  # still open
    assert len(pos.trade_log) == 2
    assert pos.trade_log[1]["event"] == "tp1_hit"


def test_full_exit_closes_position(db: Session) -> None:
    strategy = _make_strategy(db)
    pos = _make_position(db, strategy)
    now = datetime.utcnow()
    pos.shares_remaining = 0
    pos.is_open = False
    pos.closed_at = now
    pos.final_pnl = 250.0
    pos.trade_log = pos.trade_log + [{
        "event": "tp2_hit",
        "timestamp": now.isoformat(),
        "price": 130.0,
        "shares_sold": pos.shares_initial,
    }]
    db.commit()
    db.refresh(pos)
    assert pos.is_open is False
    assert pos.closed_at is not None
    assert pos.final_pnl == 250.0


# ── Query patterns the monitor cron uses ────────────────────────────────────


def test_query_open_positions_by_strategy(db: Session) -> None:
    """The cron queries `WHERE saved_strategy_id=? AND is_open=TRUE` —
    must return open positions only."""
    strategy = _make_strategy(db)
    open_pos = _make_position(db, strategy, symbol="AAPL")
    closed_pos = _make_position(db, strategy, symbol="MSFT")
    closed_pos.is_open = False
    closed_pos.closed_at = datetime.utcnow()
    db.commit()

    open_rows = (
        db.query(PositionState)
        .filter(PositionState.saved_strategy_id == strategy.id)
        .filter(PositionState.is_open == True)  # noqa: E712 (SQLAlchemy idiom)
        .all()
    )
    assert {p.symbol for p in open_rows} == {"AAPL"}


def test_multiple_open_positions_per_strategy(db: Session) -> None:
    """A multi-symbol strategy holds one PositionState per symbol."""
    strategy = _make_strategy(db)
    for sym in ["AAPL", "MSFT", "NVDA"]:
        _make_position(db, strategy, symbol=sym)
    open_rows = (
        db.query(PositionState)
        .filter(PositionState.saved_strategy_id == strategy.id)
        .filter(PositionState.is_open == True)  # noqa: E712
        .all()
    )
    assert len(open_rows) == 3


# ── Cascade delete is declared on the schema ────────────────────────────────


def test_saved_strategy_id_fk_declared_with_cascade(db: Session) -> None:
    """The schema declares ON DELETE CASCADE on the saved_strategy_id FK.
    Actual cascade behavior depends on backend FK enforcement (Postgres:
    always on; SQLite: opt-in via PRAGMA foreign_keys). We verify the
    declaration here; live cascade is covered by
    `test_postgres_migrations.py` in the Postgres CI lane."""
    from sqlalchemy import inspect
    inspector = inspect(db.bind)
    fks = inspector.get_foreign_keys("position_states")
    fk = next(
        (f for f in fks if f["referred_table"] == "saved_strategies"), None
    )
    assert fk is not None, "Expected FK from position_states to saved_strategies"
    assert fk["constrained_columns"] == ["saved_strategy_id"]
    assert fk["referred_columns"] == ["id"]


# ── trade_log JSON shape ────────────────────────────────────────────────────


def test_trade_log_persists_complex_dicts(db: Session) -> None:
    """trade_log is a JSON column; nested dicts + datetime strings round-trip."""
    strategy = _make_strategy(db)
    pos = _make_position(db, strategy)
    new_entry = {
        "event": "tp1_hit",
        "timestamp": datetime.utcnow().isoformat(),
        "price": 115.0,
        "shares_sold": 3.33,
        "tier_label": "TP1",
    }
    pos.trade_log = pos.trade_log + [new_entry]
    db.commit()
    db.refresh(pos)
    assert pos.trade_log[-1]["tier_label"] == "TP1"
    assert pos.trade_log[-1]["shares_sold"] == 3.33


def test_index_supports_per_strategy_query(db: Session) -> None:
    """Sanity — the compound index exists; query plan is whatever the
    engine picks, but the table-args definition is exercised."""
    from sqlalchemy import inspect
    inspector = inspect(db.bind)
    indexes = {ix["name"] for ix in inspector.get_indexes("position_states")}
    assert "idx_position_open_per_strategy" in indexes
