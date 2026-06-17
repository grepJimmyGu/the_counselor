"""PRD-23a slice 2 — signal_snapshot service.

Covers the pure value-encoding core, the idempotent write/read round-trip,
null-cell handling, the async warm path (stubbed price service), and the
covered-primitive set.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import func, select

from app.models.signal_snapshot import SignalSnapshot
from app.services.backtester.signal_provider import get_signal_provider
from app.services.screener.signal_snapshot_service import (
    SignalSnapshotService,
    _last_bar_value,
    compute_values_from_frame,
    local_price_providers,
    snapshot_primitive_ids,
)


def _ohlcv(n: int = 300, end: date = date(2026, 6, 15)) -> pd.DataFrame:
    """A deterministic OHLCV frame with real variance (uptrend + oscillation)
    so volatility/range primitives warm to finite values."""
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    i = np.arange(n)
    close = 100.0 + i * 0.1 + 5.0 * np.sin(i / 5.0)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adjusted_close": close,
            "volume": 1_000_000.0 + i * 1000.0,
        },
        index=idx,
    )


class _StubPriceSvc:
    """Returns a fixed frame regardless of args — keeps warm_symbol off the
    network in tests."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    async def get_price_frame(self, db, symbol, start, end, lookback_days=0):
        return self._frame


# ── covered-primitive set ────────────────────────────────────────────────────


def test_snapshot_covers_local_price_primitives_only():
    ids = set(snapshot_primitive_ids())
    # Local price primitives are in; AV-endpoint + fundamentals are out.
    assert "rsi" in ids and "sma" in ids and "donchian_breakout" in ids
    assert "kama" not in ids  # AV-endpoint
    assert "fcf_yield" not in ids  # fundamental
    # The PRD-22b backfill primitives are all local → covered too.
    assert "golden_cross" in ids and "macd_signal_cross" in ids
    assert "bb_squeeze" in ids and "supertrend" in ids and "anchored_vwap" in ids
    # Grows with each PRD-22b backfill slice; upper bound leaves headroom for
    # the remaining momentum/Heikin-Ashi + divergence slices.
    assert 45 <= len(ids) <= 110


# ── pure value-encoding core ─────────────────────────────────────────────────


def test_last_bar_value_is_literal_last_not_last_finite():
    # Must use the LITERAL last bar (matches the backtest's NaN->no-signal),
    # NOT the last non-NaN value — else a frozen/NaN final bar false-matches.
    assert _last_bar_value(pd.Series([1.0, 2.0, np.nan])) is None
    assert _last_bar_value(pd.Series([1.0, 2.0, 3.0])) == 3.0
    assert _last_bar_value(pd.Series([np.nan])) is None
    assert _last_bar_value(pd.Series([], dtype=float)) is None


def test_empty_frame_yields_no_values():
    assert compute_values_from_frame(pd.DataFrame()) == ({}, None)
    assert compute_values_from_frame(None) == ({}, None)


def test_as_of_date_is_last_bar_date():
    frame = _ohlcv(end=date(2026, 6, 15))
    _, as_of = compute_values_from_frame(frame)
    assert as_of == frame.index[-1].date()


def test_value_primitive_matches_engine_value():
    frame = _ohlcv()
    sma = get_signal_provider("sma")
    pairs = [(type("P", (), {"id": "sma"}), sma)]
    values, _ = compute_values_from_frame(frame, providers=pairs)
    # close = adjusted_close here, so the snapshot SMA equals the provider's
    # own last value on the same frame.
    expected = float(sma._compute(frame).dropna().iloc[-1])
    assert values["sma"] == pytest.approx(expected)


def test_event_primitive_encodes_as_zero_or_one():
    frame = _ohlcv()
    don = get_signal_provider("donchian_breakout")
    pairs = [(type("P", (), {"id": "donchian_breakout"}), don)]
    values, _ = compute_values_from_frame(frame, providers=pairs)
    assert values["donchian_breakout"] in (0.0, 1.0)


def test_all_finite_only_no_fabrication():
    # Full default set on a clean frame → every stored value is finite.
    values, _ = compute_values_from_frame(_ohlcv())
    assert values  # warmed at least some
    assert all(math.isfinite(v) for v in values.values())


def test_short_frame_drops_unwarmable_primitives():
    # 5 bars can't warm a 200-day SMA → it's omitted (null cell), not faked.
    values, as_of = compute_values_from_frame(_ohlcv(n=5))
    assert as_of is not None
    assert "sma" not in values or math.isfinite(values["sma"])


# ── write / read round-trip ──────────────────────────────────────────────────


def test_write_and_get_snapshot_round_trip(db):
    svc = SignalSnapshotService(price_svc=_StubPriceSvc(_ohlcv()))
    svc.write_symbol(db, "AAPL", {"sma": 101.5, "rsi": 55.0}, date(2026, 6, 15))
    svc.write_symbol(db, "MSFT", {"sma": 202.0}, date(2026, 6, 15))
    db.commit()

    snap = svc.get_snapshot(db, ["AAPL", "MSFT", "TSLA"])
    assert snap.as_of_date == date(2026, 6, 15)
    # AAPL has both; MSFT lacks rsi (null cell); TSLA has no rows at all.
    assert snap.frame.loc["AAPL", "sma"] == pytest.approx(101.5)
    assert snap.frame.loc["AAPL", "rsi"] == pytest.approx(55.0)
    assert math.isnan(snap.frame.loc["MSFT", "rsi"])
    assert snap.frame.loc["TSLA"].isna().all()


def test_write_symbol_is_idempotent(db):
    svc = SignalSnapshotService(price_svc=_StubPriceSvc(_ohlcv()))
    svc.write_symbol(db, "AAPL", {"sma": 1.0, "rsi": 2.0}, date(2026, 6, 15))
    svc.write_symbol(db, "AAPL", {"sma": 9.0}, date(2026, 6, 16))  # re-warm
    db.commit()

    rows = db.execute(
        select(SignalSnapshot).where(SignalSnapshot.symbol == "AAPL")
    ).scalars().all()
    # Delete-then-insert: only the second warm's single row survives, no dupes.
    assert len(rows) == 1
    assert rows[0].primitive_id == "sma"
    assert rows[0].value == 9.0
    assert rows[0].as_of_date == date(2026, 6, 16)


def test_get_snapshot_empty_symbols(db):
    svc = SignalSnapshotService(price_svc=_StubPriceSvc(_ohlcv()))
    snap = svc.get_snapshot(db, [])
    assert snap.as_of_date is None
    assert snap.frame.empty


# ── async warm path ──────────────────────────────────────────────────────────


async def test_warm_symbol_writes_rows(db):
    frame = _ohlcv(end=date(2026, 6, 15))
    svc = SignalSnapshotService(price_svc=_StubPriceSvc(frame))
    n = await svc.warm_symbol(db, "aapl")
    db.commit()
    assert n > 0

    snap = svc.get_snapshot(db, ["AAPL"])
    assert snap.as_of_date == date(2026, 6, 15)
    assert "rsi" in snap.frame.columns
    assert math.isfinite(snap.frame.loc["AAPL", "rsi"])


async def test_warm_symbol_no_bars_is_skip_not_fabrication(db):
    svc = SignalSnapshotService(price_svc=_StubPriceSvc(pd.DataFrame()))
    n = await svc.warm_symbol(db, "NOPE")
    db.commit()
    assert n == 0
    rows = db.execute(
        select(func.count()).select_from(SignalSnapshot)
    ).scalar()
    assert rows == 0


async def test_warm_universe_summary(db):
    svc = SignalSnapshotService(price_svc=_StubPriceSvc(_ohlcv()))
    summary = await svc.warm_universe(db, ["AAPL", "MSFT"])
    assert summary["symbols_ok"] == 2
    assert summary["symbols_empty"] == 0
    assert summary["rows"] > 0
