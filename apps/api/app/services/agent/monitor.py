"""One scan of one user: gather what is true now, run the checks, keep what is new.

`scan_user` is a coroutine that runs on the application's main event loop,
where the shared connection pool to FMP lives. Everything in it that blocks,
the database and the brokerage SDK, runs on a worker thread with its own
session (traps 13 and 21). The scheduled job, which lives on APScheduler's
thread, hands its scans to the main loop rather than running them itself.

How this holds up with many users:

  - A fixed number of scans run at once (`agent_scan_concurrency`), whether
    they come from the scheduled job or from people tapping "Check now". The
    job is given two fewer than the total, so a person never waits behind it.
  - The blocking half of a scan runs on the agent's own small thread pool,
    not the server's shared one, so a wave of scans cannot take the threads
    that everything else's database work needs, and the size of that pool is
    also the most database connections scans can hold.
  - What scans have in common is fetched once: quotes through the live quote
    service, which sends everyone's symbols in one call, and filings through
    a cache that shares an in-flight read.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import concurrency
from app.core.concurrency import PerLoop
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.agent import AgentInsight, AgentProfile
from app.services.agent import checks
from app.services.agent.checks import Finding, Holding

logger = logging.getLogger("livermore.agent")

# A scan reads a quote for each of these and a filing for some. Bounded so
# one user with a very long list cannot make a scan slow for everyone.
MAX_SYMBOLS = 40
MAX_FILINGS = 12
# A filing older than this was news before the agent was watching.
FILING_IS_NEW_FOR = timedelta(days=30)

# One user's scan may take this long before it is given up on.
SCAN_TIMEOUT_SECONDS = 90.0

_T = TypeVar("_T")
_pool: Optional[ThreadPoolExecutor] = None
_SCAN_SLOTS: "PerLoop[asyncio.Semaphore]" = PerLoop(
    lambda: asyncio.Semaphore(max(1, get_settings().agent_scan_concurrency))
)


async def run_blocking(fn: Callable[..., _T], *args: Any) -> _T:
    """Run the agent's blocking work (database, brokerage SDK) on its own
    threads: twice the number of scans allowed at once, so every scan can
    always get one and the conversation's tools have as many again. That
    number is also the most database connections the agent can hold."""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(
            max_workers=2 * max(1, get_settings().agent_scan_concurrency), thread_name_prefix="agent",
        )
    return await asyncio.get_running_loop().run_in_executor(_pool, fn, *args)


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    concurrency.set_main_loop(loop)


def main_loop() -> Optional[asyncio.AbstractEventLoop]:
    return concurrency.main_loop()


@dataclass
class ScanResult:
    checked_at: datetime
    new_insights: int = 0
    symbols_checked: int = 0
    brokerage_linked: bool = False
    # Things the scan could not do, in words for the user.
    notes: List[str] = field(default_factory=list)
    # The findings this scan stored for the first time.
    new_findings: List[Finding] = field(default_factory=list)


@dataclass
class _Inputs:
    watchlist: List[str]
    move_alert_pct: float
    max_position_pct: float
    holdings: List[Holding]
    brokerage_linked: bool
    exits: List[Dict[str, Any]]
    notes: List[str]


def get_or_create_profile(db: Session, user_id: str) -> AgentProfile:
    profile = db.get(AgentProfile, user_id)
    if profile is None:
        profile = AgentProfile(user_id=user_id, watchlist=[])
        db.add(profile)
        try:
            db.commit()
        except IntegrityError:
            # Two first requests at once: the other one made it.
            db.rollback()
            profile = db.get(AgentProfile, user_id)
        else:
            db.refresh(profile)
    return profile


def read_holdings(db: Session, user_id: str) -> Optional[List[Holding]]:
    """The user's holdings from their broker, one row per symbol, or None if
    no brokerage is linked. Cash-like positions and ones with no price are
    left out: neither is something the user sized."""
    from app.services import snaptrade_service as st

    if not st.is_configured() or st.get_registration(db, user_id) is None:
        return None
    by_symbol: Dict[str, Holding] = {}
    for row in st.list_positions(db, user_id):
        if row.cash_equivalent or not row.symbol or not row.last_price or not row.units:
            continue
        existing = by_symbol.get(row.symbol)
        if existing is None:
            by_symbol[row.symbol] = Holding(symbol=row.symbol, units=float(row.units), price=float(row.last_price))
        else:
            existing.units += float(row.units)
    return list(by_symbol.values())


def read_unresolved_exits(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """Exits the user's strategies have signalled and the user has not yet
    resolved. The same reading as GET /api/saved-strategies/unresolved-exits,
    which is the screen this insight sends the user to."""
    from app.models.position_state import PositionState
    from app.services import saved_strategy_service

    strategies = saved_strategy_service.list_user_strategies(db, user_id)
    if not strategies:
        return []
    positions = db.execute(
        select(PositionState)
        .where(PositionState.saved_strategy_id.in_([s.id for s in strategies]))
        .where(PositionState.is_open == True)  # noqa: E712
    ).scalars().all()
    waiting = []
    for position in positions:
        for event in (position.trade_log or []):
            if event.get("status") == "pending_confirmation":
                waiting.append({"symbol": position.symbol, "trigger_type": event.get("event", "")})
    return waiting


def _gather(user_id: str) -> _Inputs:
    notes: List[str] = []
    # Two sessions on purpose. The first is quick and gives its connection
    # straight back. The second stays open while the broker is read, which
    # can take seconds, and only users with a brokerage linked get that far
    # with it (trap 13).
    with SessionLocal() as db:
        profile = get_or_create_profile(db, user_id)
        watchlist = [str(s).upper() for s in (profile.watchlist or [])][:MAX_SYMBOLS]
        move_alert_pct = float(profile.move_alert_pct)
        max_position_pct = float(profile.max_position_pct)
        try:
            exits = read_unresolved_exits(db, user_id)
        except Exception:  # noqa: BLE001
            logger.exception("agent: exits read failed user=%s", user_id)
            exits = []
    holdings: List[Holding] = []
    linked = False
    try:
        with SessionLocal() as db:
            read = read_holdings(db, user_id)
        if read is None:
            notes.append("No brokerage is linked, so holdings were not checked.")
        else:
            holdings, linked = read, True
    except Exception:  # noqa: BLE001
        logger.exception("agent: holdings read failed user=%s", user_id)
        notes.append("Your broker could not be read this time, so holdings were not checked.")
    return _Inputs(watchlist, move_alert_pct, max_position_pct, holdings, linked, exits, notes)


def _persist(user_id: str, findings: List[Finding], checked_at: datetime) -> List[Finding]:
    """Store the findings that are not already known, and return those."""
    new: List[Finding] = []
    with SessionLocal() as db:
        known = set(db.execute(
            select(AgentInsight.dedupe_key).where(
                AgentInsight.user_id == user_id,
                AgentInsight.dedupe_key.in_([f.dedupe_key for f in findings] or [""]),
            )
        ).scalars().all())
        for finding in findings:
            if finding.dedupe_key in known:
                continue
            known.add(finding.dedupe_key)
            db.add(AgentInsight(
                id=str(uuid.uuid4()),
                user_id=user_id,
                dedupe_key=finding.dedupe_key,
                kind=finding.kind,
                severity=finding.severity,
                symbol=finding.symbol,
                title=finding.title,
                body=finding.body,
                facts=finding.facts,
                action=finding.action,
                created_at=checked_at,
            ))
            new.append(finding)
        profile = db.get(AgentProfile, user_id)
        if profile is not None:
            profile.last_scan_at = checked_at
        db.commit()
    return new


async def _quotes(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    from app.services.live_quote_service import live_quote_service

    quotes = await live_quote_service.get_quotes(symbols)
    return {s: {"price": q.price, "change_percent": q.change_percent} for s, q in quotes.items()}


async def _filing_findings(symbols: List[str], today) -> List[Finding]:
    from app.services import sec_company_facts

    async def one(symbol: str) -> List[Finding]:
        try:
            analysis = await sec_company_facts.filing_analysis(symbol)
        except Exception:  # noqa: BLE001 — funds, foreign filers and bad tickers have none
            return []
        if not analysis.quarters:
            return []
        latest = analysis.quarters[-1]
        if latest.filed is None or today - latest.filed > FILING_IS_NEW_FOR:
            return []
        watch = [f for f in analysis.findings if f.severity == "watch"]
        return checks.filing(symbol, latest.label, [f.title for f in watch], [f.detail for f in watch])

    # Together rather than one after another: a first scan of twelve symbols
    # is twelve downloads, and the filings module limits how many go to the
    # SEC at once. Order is kept so the findings read the same every time.
    per_symbol = await asyncio.gather(*(one(symbol) for symbol in symbols[:MAX_FILINGS]))
    return [finding for found in per_symbol for finding in found]


async def scan_user(user_id: str) -> ScanResult:
    """Look at everything the agent watches for one user, once.

    Waits its turn when the allowed number of scans is already running."""
    async with _SCAN_SLOTS.get():
        return await _scan(user_id)


async def scan_many(
    user_ids: Sequence[str], *, at_once: int, timeout: float = SCAN_TIMEOUT_SECONDS,
) -> List[Tuple[str, Optional[ScanResult]]]:
    """Scan several users, `at_once` at a time. One user's failure or
    timeout is logged and reported as None; it never stops the others."""
    gate = asyncio.Semaphore(max(1, at_once))

    async def one(user_id: str) -> Tuple[str, Optional[ScanResult]]:
        async with gate:
            try:
                return user_id, await asyncio.wait_for(scan_user(user_id), timeout)
            except Exception:  # noqa: BLE001
                logger.exception("agent: scan failed user=%s", user_id)
                return user_id, None

    return list(await asyncio.gather(*(one(user_id) for user_id in user_ids)))


async def _scan(user_id: str) -> ScanResult:
    checked_at = datetime.utcnow()
    today = datetime.now(timezone.utc).date()
    inputs = await run_blocking(_gather, user_id)

    held = [h.symbol for h in sorted(inputs.holdings, key=lambda h: h.value, reverse=True)]
    # Holdings first: if the list has to be cut, what is owned matters more.
    symbols = list(dict.fromkeys(held + inputs.watchlist))[:MAX_SYMBOLS]
    notes = list(inputs.notes)

    findings: List[Finding] = []
    findings += checks.exits_waiting(inputs.exits, today)
    findings += checks.concentration(inputs.holdings, inputs.max_position_pct, today)
    if symbols:
        # Prices and filings do not depend on each other.
        quotes, filing_findings = await asyncio.gather(
            _quotes(symbols), _filing_findings(symbols, today), return_exceptions=True,
        )
        if isinstance(quotes, BaseException):
            logger.error("agent: quotes failed user=%s", user_id, exc_info=quotes)
            notes.append("Prices could not be read this time.")
        else:
            findings += checks.price_moves(quotes, inputs.move_alert_pct, inputs.holdings, today)
        if isinstance(filing_findings, BaseException):
            logger.error("agent: filings failed user=%s", user_id, exc_info=filing_findings)
        else:
            findings += filing_findings
    else:
        notes.append("Nothing to watch yet: add symbols to your watchlist or link a brokerage.")

    new = await run_blocking(_persist, user_id, findings, checked_at)
    return ScanResult(
        checked_at=checked_at,
        new_insights=len(new),
        new_findings=new,
        symbols_checked=len(symbols),
        brokerage_linked=inputs.brokerage_linked,
        notes=notes,
    )


def email_new_findings(user_id: str, findings: List[Finding]) -> bool:
    """Email the user what a scheduled check just found, if they want that.

    One email per check, and only for findings marked to watch: a stock that
    is merely up on the day can wait until the app is opened. Each finding is
    stored once, so it is emailed once.
    """
    worth = [f for f in findings if f.severity == "watch"]
    if not worth:
        return False
    from app.models.user import User
    from app.services.email_service import send_email

    with SessionLocal() as db:
        profile = db.get(AgentProfile, user_id)
        user = db.get(User, user_id)
        if profile is None or user is None or not profile.email_alerts:
            return False
        count = len(worth)
        subject = worth[0].title if count == 1 else "Your agent found %d things to look at" % count
        lines = ["%s\n%s" % (f.title, f.body) for f in worth]
        footer = ("Open the Livermore app and go to Agent to act on these. Your agent reports what "
                  "happened under limits you set; it does not place orders.\n"
                  "To stop these emails: Agent, then settings, then turn off email.")
        text = "\n\n".join(lines) + "\n\n" + footer
        html = (
            '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:16px;'
            'line-height:1.5;color:#111;max-width:520px">'
            + "".join('<p><strong>%s</strong><br>%s</p>' % (_escape(f.title), _escape(f.body)) for f in worth)
            + '<p style="color:#666;font-size:13px">%s</p></div>' % _escape(footer).replace("\n", "<br>")
        )
        return send_email(db, user, template="agent_findings", subject=subject, html=html, text=text,
                          category="transactional")


def _escape(text: str) -> str:
    import html
    return html.escape(text)

