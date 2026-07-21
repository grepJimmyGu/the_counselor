"""Regression tests for the boot-time startup-warmup deadlock fix (2026-07).

Symptom: on a migrating deploy, the lifespan fired all 5 one-shot warmups +
the pulse loop + `_db_init` concurrently on separate threads, so
`create_all`/`run_startup_migrations` (DDL → ACCESS EXCLUSIVE table locks)
deadlocked against the warmups' DML → Postgres `DeadlockDetected` →
`InFailedSqlTransaction` → container stop (self-healed on the retry).

Fix: warmups gate on `_db_ready` (set by `_db_init`, even on failure) and the
one-shots run SEQUENTIALLY via `_run_startup_warmups`; the pulse loop waits on
`_db_ready` + `_startup_warmups_done` before its first DB read. These tests
lock in that contract.
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

import app.main as m


@pytest.fixture(autouse=True)
def _reset_events():
    """Isolate the module-level threading.Events around each test."""
    m._db_ready.clear()
    m._startup_warmups_done.clear()
    yield
    m._db_ready.clear()
    m._startup_warmups_done.clear()


def test_db_init_signals_ready_even_on_failure():
    # `_db_init` must set `_db_ready` in `finally` so the gated warmups never
    # block forever, even when create_all / migrations raise.
    with patch.object(m.Base.metadata, "create_all", side_effect=RuntimeError("boom")):
        m._db_init(object())
    assert m._db_ready.is_set()


def test_db_init_signals_ready_on_success():
    with patch.object(m.Base.metadata, "create_all", return_value=None), \
         patch.object(m, "run_startup_migrations", return_value=None):
        m._db_init(object())
    assert m._db_ready.is_set()


def test_startup_warmups_run_sequentially_and_survive_failure():
    m._db_ready.set()  # don't block on the gate
    order = []

    def make(name, fail=False):
        async def _fn():
            order.append(name)
            if fail:
                raise RuntimeError(f"{name} boom")
        return _fn

    with patch.object(m, "_warmup_market_etfs", make("market_etfs")), \
         patch.object(m, "_warmup_gspc", make("gspc", fail=True)), \
         patch.object(m, "_warmup_commodity_spots", make("commodity_spots")), \
         patch.object(m, "_seed_and_warmup_stock_universe", make("stock_universe")), \
         patch.object(m, "_invalidate_stale_bi_caches", make("stale_bi_caches")):
        asyncio.run(m._run_startup_warmups())

    # All five ran, in registration order, despite `gspc` raising mid-sequence.
    assert order == [
        "market_etfs", "gspc", "commodity_spots",
        "stock_universe", "stale_bi_caches",
    ]
    # The "done" gate is set so the pulse loop can proceed.
    assert m._startup_warmups_done.is_set()


def test_startup_warmups_gate_on_db_ready_before_running():
    # The runner must wait on `_db_ready` before running any warmup, and set
    # `_startup_warmups_done` at the end (the pulse loop's go-ahead).
    fake_ready = MagicMock()
    fake_ready.wait.return_value = True
    fake_done = MagicMock()
    ran = []

    async def noop():
        ran.append(1)

    with patch.object(m, "_db_ready", fake_ready), \
         patch.object(m, "_startup_warmups_done", fake_done), \
         patch.object(m, "_warmup_market_etfs", noop), \
         patch.object(m, "_warmup_gspc", noop), \
         patch.object(m, "_warmup_commodity_spots", noop), \
         patch.object(m, "_seed_and_warmup_stock_universe", noop), \
         patch.object(m, "_invalidate_stale_bi_caches", noop):
        asyncio.run(m._run_startup_warmups())

    fake_ready.wait.assert_called_once()
    fake_done.set.assert_called_once()
    assert len(ran) == 5
