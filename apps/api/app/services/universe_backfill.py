"""Server-side one-shot universe backfill.

Loads a ticker universe's full daily history into `price_bars` from Alpha
Vantage, running on a dedicated worker thread, with in-memory progress and a
configurable per-minute throttle. Triggered + monitored via the admin router
(`POST /api/admin/backfill/universe`, `GET /api/admin/backfill/status`).

Design notes (each maps to a documented trap in apps/api/CLAUDE.md):

* **Worker thread (trap #21).** This is a long (~30-50 min) job that mixes
  async AV fetches with SYNCHRONOUS SQLAlchemy. Running it on the main event
  loop would block `/health` and trip Railway's healthcheck. The trigger
  spawns it via `asyncio.to_thread(_run_in_thread, coro)` so the backfill's
  own event loop lives on a dedicated thread; its sync DB calls block only
  that thread.
* **Fresh AV/cache instances (trap #22).** `AlphaVantageClient` /
  `PriceCacheService` hold no shared `asyncio` primitives today, but we build
  our own instances anyway so the worker thread never binds a module-level
  singleton's lock to its loop.
* **Throttle.** The AV paid tier is 75 req/min, shared with the live app. We
  pace only the iterations that actually hit AV (a fresh-cached symbol is a
  cheap DB check, not a fetch), capped at `rate_per_min` (default 50) so live
  on-demand fetches keep >= ~25/min of headroom.
* **Disk (trap #10).** The caller is expected to have confirmed Postgres disk
  headroom; the full R3000 backfill is ~1.8 GB.

In-memory status is safe because the app runs single-process (APScheduler +
lifespan warmups assume it). The worker thread writes `_STATUS`; the status
request handler reads it. Coarse progress fields are advisory, so no lock.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.db.session import SessionLocal
from app.models.symbol import SymbolCache
from app.services.alpha_vantage import AlphaVantageClient
from app.services.price_cache_service import PriceCacheService

logger = logging.getLogger("livermore.universe_backfill")

# Clamp the trigger's rate so we can never starve the live app's AV budget
# (paid tier = 75/min). Default leaves >= 25/min for on-demand fetches.
DEFAULT_RATE_PER_MIN = 50
MAX_RATE_PER_MIN = 70
DEFAULT_LOOKBACK_YEARS = 3


@dataclass
class BackfillStatus:
    state: str = "idle"  # idle | running | completed | failed
    label: str = ""
    total: int = 0
    processed: int = 0
    loaded: int = 0
    skipped_fresh: int = 0
    failed: int = 0
    failed_symbols: List[str] = field(default_factory=list)
    current_symbol: Optional[str] = None
    rate_per_min: int = 0
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None

    def reset(self, *, label: str, total: int, rate_per_min: int) -> None:
        self.state = "running"
        self.label = label
        self.total = total
        self.processed = 0
        self.loaded = 0
        self.skipped_fresh = 0
        self.failed = 0
        self.failed_symbols = []
        self.current_symbol = None
        self.rate_per_min = rate_per_min
        self.started_at = _now_iso()
        self.updated_at = self.started_at
        self.finished_at = None
        self.error = None

    def snapshot(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pct"] = round(100.0 * self.processed / self.total, 1) if self.total else 0.0
        remaining = max(0, self.total - self.processed)
        # ETA off the observed loaded-rate, not wall time — skip-fresh symbols
        # fly by, so wall-rate would lie. Fall back to the configured cap.
        d["eta_minutes"] = (
            round(remaining / self.rate_per_min, 1) if self.rate_per_min else None
        )
        d["failed_symbols"] = self.failed_symbols[:50]  # cap the payload
        return d


# Single-process app → one module-level status object is the source of truth.
_STATUS = BackfillStatus()
# Hold a strong ref to the spawned task so it isn't garbage-collected mid-run.
_BACKFILL_TASK: Optional["asyncio.Task[Any]"] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_status() -> Dict[str, Any]:
    """Current backfill progress (read by the status endpoint)."""
    return _STATUS.snapshot()


def resolve_universe(universe_id: str) -> List[str]:
    """Map a universe id to its sorted ticker list. Raises ValueError on an
    unknown id (the endpoint turns that into a 400)."""
    if universe_id == "russell3000":
        from app.data.russell3000_tickers import RUSSELL3000_TICKERS

        return sorted(RUSSELL3000_TICKERS)
    if universe_id == "sp500":
        from app.data.sp500_tickers import SP500_TICKERS

        return sorted(SP500_TICKERS)
    raise ValueError(f"unknown universe_id {universe_id!r}")


def _run_in_thread(coro: "asyncio.Future[Any]") -> None:
    """Run an async coroutine on a dedicated thread with its own event loop
    (trap #21 bridge). Sync DB calls inside `coro` block ONLY this thread's
    loop, never the main loop that serves /health and user requests."""
    try:
        asyncio.run(coro)
    except Exception:  # noqa: BLE001 — trap #20: surface the traceback
        logger.exception("universe backfill thread crashed")
        _STATUS.state = "failed"
        _STATUS.error = "thread crashed — see logs"
        _STATUS.finished_at = _now_iso()


def start_backfill_thread(
    universe: List[str],
    label: str,
    rate_per_min: int,
    lookback_years: int,
) -> bool:
    """Kick the backfill onto a worker thread. Returns False (no-op) if one is
    already running — guards against a double-trigger."""
    global _BACKFILL_TASK
    if _STATUS.state == "running":
        return False
    _STATUS.reset(label=label, total=len(universe), rate_per_min=rate_per_min)
    _BACKFILL_TASK = asyncio.create_task(
        asyncio.to_thread(
            _run_in_thread, _backfill(universe, label, rate_per_min, lookback_years)
        )
    )
    return True


async def _ensure_symbol_row(db: Any, symbol: str, now: datetime) -> None:
    """Insert a placeholder SymbolCache row if missing (name=symbol; the real
    name/sector populate lazily via FMP on first /stocks/<symbol> load)."""
    if db.get(SymbolCache, symbol) is not None:
        return
    db.add(
        SymbolCache(
            symbol=symbol,
            name=symbol,
            instrument_type="Equity",
            region="US",
            is_active=True,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


async def _backfill(
    universe: List[str], label: str, rate_per_min: int, lookback_years: int
) -> None:
    """The actual loop. Idempotent: `ensure_history(force=False)` skips symbols
    that already have fresh bars covering `required_from`, so re-runs are cheap
    DB checks. Only iterations that actually fetch from AV are throttled."""
    client = AlphaVantageClient()
    svc = PriceCacheService(client)
    db = SessionLocal()
    required_from = date.today() - timedelta(days=365 * lookback_years)
    now = datetime.utcnow()
    min_interval = 60.0 / rate_per_min if rate_per_min > 0 else 0.0

    try:
        for i, symbol in enumerate(universe, 1):
            t0 = time.monotonic()
            _STATUS.current_symbol = symbol
            fetched = False
            try:
                await _ensure_symbol_row(db, symbol, now)
                pre = svc.get_latest_date(db, symbol)
                await svc.ensure_history(db, symbol, required_from, force=False)
                post = svc.get_latest_date(db, symbol)
                if pre is not None and pre == post:
                    _STATUS.skipped_fresh += 1
                else:
                    _STATUS.loaded += 1
                    fetched = True
            except Exception:  # noqa: BLE001 — trap #20: log full traceback
                logger.exception("universe backfill failed for %s", symbol)
                db.rollback()
                _STATUS.failed += 1
                if len(_STATUS.failed_symbols) < 200:
                    _STATUS.failed_symbols.append(symbol)

            _STATUS.processed = i
            _STATUS.updated_at = _now_iso()

            # Throttle only the iterations that hit AV — a fresh-cached symbol
            # is a cheap DB check and shouldn't burn the per-minute budget.
            if fetched and min_interval > 0:
                elapsed = time.monotonic() - t0
                if min_interval > elapsed:
                    await asyncio.sleep(min_interval - elapsed)

        _STATUS.state = "completed"
        _STATUS.current_symbol = None
        _STATUS.finished_at = _now_iso()
        logger.info(
            "universe backfill %s done: %d loaded · %d fresh · %d failed",
            label,
            _STATUS.loaded,
            _STATUS.skipped_fresh,
            _STATUS.failed,
        )
    finally:
        db.close()
