"""Keep a symbol's stored adjusted closes on one basis: today's.

The provider's `adjusted_close` is relative to the day it was fetched: every
later dividend or split changes the adjusted value of every earlier day.
`PriceCacheService._upsert_bars` only ever inserts (ON CONFLICT DO NOTHING),
so rows stored before a dividend kept the old basis and rows stored after it
got the new one. On 2026-11-25 production showed AAPL's 2026 dividends in
none of the earlier rows, SPY's factor jumping 0.9943 -> 1.0 between two
fetches with no dividend between them, and two SPY ex-date rows stored with
a dividend of zero. A backtest or a chart reads each of those seams as a
price move; a split after a symbol's first load would be a cliff of the
whole split ratio.

A reconcile fetches the provider's whole series and rewrites only the rows
that differ. It runs for symbols a person opens or backtests, never for the
startup warmups or the 3,000-symbol sweeps: after a dividend every earlier
row of that symbol changes (about 6,800 for a long-listed one), and a sweep
would rewrite most of the table in one cycle. apps/api/CLAUDE.md trap 10 is
the disk-full outage a much smaller burst caused.

A symbol is due when its newest stored bar was written after its last
successful reconcile (or it has never had one): a bar that arrived since may
carry a dividend or a split, and nothing else can change the basis. That is
at most once per trading day per symbol, and never on a weekend.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.concurrency import PerLoop, SingleFlight
from app.core.config import get_settings
from app.models.data_fetch_log import DataFetchLog
from app.models.price_bar import PriceBar
from app.services.alpha_vantage import (
    AlphaVantageClient,
    AlphaVantageError,
    AlphaVantageRateLimitError,
)

logger = logging.getLogger("livermore.price_basis")

FETCH_TYPE = "basis_reconcile"
SOURCE = "alpha_vantage"

# Everything the provider states about a day. A row that differs in any of
# them takes the provider's whole row: `adjusted_close / close` is the ratio
# the engine adjusts opens with, so the two must come from the same answer.
VALUE_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend_amount",
    "split_coefficient",
)

# A backtest waits for its symbols when there are this many or fewer, and for
# no longer than this. A larger universe is reconciled behind the test.
AWAIT_MAX_SYMBOLS = 26  # 25 names and a benchmark
AWAIT_SECONDS = 20.0
# Provider downloads running at once (per event loop; trap 22).
_CONCURRENT = 4
# After a failed attempt a symbol is left alone this long.
_RETRY_SECONDS = 600.0
# PostgreSQL caps a statement at 65,535 parameters; 12 per row.
_CHUNK = 1000

_flights = SingleFlight()
_slots: PerLoop[asyncio.Semaphore] = PerLoop(lambda: asyncio.Semaphore(_CONCURRENT))
_retry_after: Dict[str, float] = {}
_budget_warned_on: Optional[date] = None


def _now() -> float:
    return time.monotonic()


def _own_session(bind: Engine) -> Session:
    return sessionmaker(bind=bind, autoflush=False, autocommit=False, future=True)()


def reconcile_due(db: Session, symbol: str) -> bool:
    """True when a bar has been stored since the symbol was last reconciled."""
    newest = db.execute(
        select(PriceBar.fetched_at, PriceBar.source)
        .where(PriceBar.symbol == symbol)
        .order_by(desc(PriceBar.trading_date))
        .limit(1)
    ).first()
    # Nothing stored is `ensure_history`'s job. Index and spot series come
    # from other sources and carry no adjustment.
    if newest is None or newest.source != SOURCE:
        return False
    last = db.scalar(
        select(DataFetchLog.fetched_at)
        .where(
            DataFetchLog.symbol == symbol,
            DataFetchLog.fetch_type == FETCH_TYPE,
            DataFetchLog.status == "success",
        )
        .order_by(desc(DataFetchLog.fetched_at))
        .limit(1)
    )
    return last is None or newest.fetched_at > last


def rows_rewritten_today(db: Session) -> int:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.scalar(
            select(func.coalesce(func.sum(DataFetchLog.bars_upserted), 0)).where(
                DataFetchLog.fetch_type == FETCH_TYPE,
                DataFetchLog.fetched_at >= start,
            )
        )
        or 0
    )


def apply_provider_bars(db: Session, symbol: str, bars: List[dict], fetched_at: datetime) -> int:
    """Make the stored rows for `symbol` say what the provider says now.

    Returns the number of rows written. The caller commits.

    The stored rows are read and compared here first, and only the days that
    differ are sent. Postgres locks every conflicting row of an
    ON CONFLICT DO UPDATE even when its WHERE is false, so sending all 6,800
    rows of an unchanged symbol would still touch every page they sit on.

    No bar newer than the newest stored one is added: that day may be a
    session still in progress, and adding days is the cache service's job.
    """
    stored = {
        row.trading_date: row
        for row in db.execute(
            select(
                PriceBar.trading_date,
                PriceBar.source,
                *[getattr(PriceBar, c) for c in VALUE_COLUMNS],
            ).where(PriceBar.symbol == symbol)
        )
    }
    if not stored:
        return 0
    newest = max(stored)

    changed: List[dict] = []
    for bar in bars:
        day = bar["trading_date"]
        if day > newest:
            continue
        row = {
            "symbol": symbol,
            "trading_date": day,
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "adjusted_close": bar["adjusted_close"],
            "volume": bar["volume"],
            "dividend_amount": bar.get("dividend_amount", 0.0),
            "split_coefficient": bar.get("split_coefficient", 1.0),
            "source": SOURCE,
            "fetched_at": fetched_at,
        }
        have = stored.get(day)
        if have is None:
            changed.append(row)  # a hole inside the stored history
        elif have.source == SOURCE and any(getattr(have, c) != row[c] for c in VALUE_COLUMNS):
            changed.append(row)
    return upsert_changed(db, changed)


def upsert_changed(db: Session, rows: List[dict]) -> int:
    """Insert `rows`, or overwrite the stored row for a day where the two
    differ. Returns the number of rows written.

    The difference is checked again in the database: a row may have changed
    since it was read, and another source's row is never overwritten.
    """
    if not rows:
        return 0
    if db.get_bind().dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert

    written = 0
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i : i + _CHUNK]
        stmt = dialect_insert(PriceBar).values(chunk)
        new = stmt.excluded
        updates = {c: new[c] for c in VALUE_COLUMNS}
        updates["fetched_at"] = new.fetched_at
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "trading_date"],
            set_=updates,
            where=and_(
                PriceBar.source == SOURCE,
                or_(*[getattr(PriceBar, c).is_distinct_from(new[c]) for c in VALUE_COLUMNS]),
            ),
        )
        # Counted from RETURNING, which lists only the rows inserted or
        # updated. `rowcount` is -1 for this statement on Postgres (psycopg
        # 3), and the daily allowance is counted from this number.
        written += len(db.execute(stmt.returning(PriceBar.trading_date)).all())
    return written


class PriceBasisService:
    def __init__(self, client: Optional[AlphaVantageClient] = None) -> None:
        self.client = client or AlphaVantageClient()

    def start(self, bind: Engine, symbol: str) -> None:
        """Reconcile `symbol` behind the caller, if it is due. Never raises."""
        sym = symbol.upper()
        _flights.start(("basis", sym), lambda: self._reconcile(bind, sym))

    async def settle(
        self, bind: Engine, symbols: Iterable[str], wait_seconds: float = AWAIT_SECONDS
    ) -> None:
        """Reconcile the symbols that are due, waiting when there are few.

        Never raises. What has not finished within `wait_seconds` carries on
        behind the caller.
        """
        syms = list(dict.fromkeys(s.upper() for s in symbols))
        tasks = [
            _flights.start(("basis", s), lambda s=s: self._reconcile(bind, s)) for s in syms
        ]
        if not tasks or len(tasks) > AWAIT_MAX_SYMBOLS:
            return
        await asyncio.wait(tasks, timeout=wait_seconds)

    async def _reconcile(self, bind: Engine, sym: str) -> None:
        try:
            await self._reconcile_if_due(bind, sym)
        except Exception:
            # Not a provider error (those are handled where they happen, and
            # their text can hold the API key): a database one. Trap 20.
            _retry_after[sym] = _now() + _RETRY_SECONDS
            logger.exception("basis reconcile of %s failed", sym)

    async def _reconcile_if_due(self, bind: Engine, sym: str) -> None:
        retry = _retry_after.get(sym)
        if retry is not None and _now() < retry:
            return

        # Each database step opens and closes its own session, so none is
        # held across the download (trap 13).
        db = _own_session(bind)
        try:
            if not reconcile_due(db, sym) or not _budget_left(db):
                return
        finally:
            db.close()

        async with _slots.get():
            started = datetime.utcnow()
            t0 = time.monotonic()
            try:
                bars = await self.client.fetch_daily_adjusted(sym, outputsize="full")
            except Exception as exc:  # noqa: BLE001 — what is stored is served
                _retry_after[sym] = _now() + _RETRY_SECONDS
                status = "rate_limited" if isinstance(exc, AlphaVantageRateLimitError) else "error"
                # Only a provider message is safe to keep: an httpx error's
                # text holds the request URL, and with it the API key.
                message = str(exc) if isinstance(exc, AlphaVantageError) else type(exc).__name__
                logger.warning("basis reconcile: download of %s failed: %s", sym, message)
                _write_log(bind, sym, status, 0, message, started, t0)
                return

            # Postgres work goes to a worker thread: comparing and rewriting
            # a full history takes long enough to hold up every other request
            # on this loop. SQLite (tests, local) stays on the caller's
            # thread, where an in-memory database keeps its one connection.
            if bind.dialect.name == "sqlite":
                written = _store(bind, sym, bars, started, t0)
            else:
                written = await asyncio.to_thread(_store, bind, sym, bars, started, t0)
            _retry_after.pop(sym, None)
            if written:
                logger.info("basis reconcile: %s — %d rows moved to the current basis", sym, written)


def _budget_left(db: Session) -> bool:
    """False once today's reconciles have rewritten the daily allowance.

    The allowance bounds the disk a day can use (trap 10). Zero turns
    reconciling off.
    """
    global _budget_warned_on
    budget = get_settings().price_basis_daily_row_budget
    if budget > 0 and rows_rewritten_today(db) < budget:
        return True
    today = datetime.utcnow().date()
    if budget > 0 and _budget_warned_on != today:
        _budget_warned_on = today
        logger.warning(
            "basis reconcile: today's allowance of %d rows is spent; resuming tomorrow (UTC)",
            budget,
        )
    return False


def _store(bind: Engine, sym: str, bars: List[dict], started: datetime, t0: float) -> int:
    db = _own_session(bind)
    try:
        # Stamped with the time the download began, on the rows and on the
        # log alike: a bar another request stores while this one runs is
        # newer than the log, so the symbol is due again.
        written = apply_provider_bars(db, sym, bars, fetched_at=started)
        db.add(
            DataFetchLog(
                symbol=sym,
                fetch_type=FETCH_TYPE,
                status="success",
                bars_upserted=written,
                duration_ms=int((time.monotonic() - t0) * 1000),
                fetched_at=started,
            )
        )
        db.commit()
        return written
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _write_log(
    bind: Engine, sym: str, status: str, written: int, message: Optional[str],
    started: datetime, t0: float,
) -> None:
    db = _own_session(bind)
    try:
        db.add(
            DataFetchLog(
                symbol=sym,
                fetch_type=FETCH_TYPE,
                status=status,
                bars_upserted=written,
                error_message=message,
                duration_ms=int((time.monotonic() - t0) * 1000),
                fetched_at=started,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


price_basis_service = PriceBasisService()
