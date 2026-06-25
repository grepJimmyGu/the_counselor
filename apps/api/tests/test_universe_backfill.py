"""Unit tests for the server-side universe backfill
(`app/services/universe_backfill.py`).

The AV-fetch loop itself is verified end-to-end against production after deploy
(repo philosophy: end-to-end audits beat mocked unit tests). These cover the
pure, DB-free logic: universe resolution, status math, and the double-run guard.
"""
from __future__ import annotations

import pytest

from app.services import universe_backfill as ub


def test_resolve_universe_russell3000():
    syms = ub.resolve_universe("russell3000")
    assert len(syms) == 2552
    assert syms == sorted(syms)        # the trigger relies on a stable order
    assert "BRK.B" in syms             # dot-normalized class share
    assert "HOLX" in syms              # recovered Hologic row


def test_resolve_universe_sp500():
    syms = ub.resolve_universe("sp500")
    assert len(syms) > 400
    assert syms == sorted(syms)


def test_resolve_universe_unknown_raises():
    with pytest.raises(ValueError):
        ub.resolve_universe("nasdaq100")


def test_status_snapshot_pct_and_eta():
    s = ub.BackfillStatus()
    s.reset(label="russell3000", total=200, rate_per_min=50)
    s.processed = 50
    snap = s.snapshot()
    assert snap["pct"] == 25.0
    assert snap["eta_minutes"] == 3.0  # (200 - 50) / 50
    assert snap["state"] == "running"
    assert snap["total"] == 200


def test_status_snapshot_empty_is_safe():
    snap = ub.BackfillStatus().snapshot()
    assert snap["pct"] == 0.0
    assert snap["eta_minutes"] is None  # rate_per_min == 0 → no divide-by-zero


def test_status_snapshot_caps_failed_symbols():
    s = ub.BackfillStatus()
    s.reset(label="x", total=300, rate_per_min=50)
    s.failed_symbols = [f"SYM{i}" for i in range(120)]
    assert len(s.snapshot()["failed_symbols"]) == 50  # payload capped


def test_start_guard_blocks_double_run(monkeypatch):
    # Force "running"; the guard must refuse without spawning a worker thread
    # (returns before any asyncio.create_task, so this is safe outside a loop).
    monkeypatch.setattr(ub._STATUS, "state", "running")
    assert ub.start_backfill_thread(["AAPL"], "test", 50, 3) is False
