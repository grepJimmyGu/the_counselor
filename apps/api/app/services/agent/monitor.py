"""One scan of one user: gather what is true now, run the checks, keep what is new.

`scan_user` is a coroutine that must run on the application's main event
loop, because the live quote service holds asyncio locks bound to that loop
(apps/api/CLAUDE.md, trap 22). Everything in it that blocks, the database and
the brokerage SDK, runs on a worker thread with its own session (traps 13
and 21). The scheduled job, which lives on APScheduler's thread, hands the
coroutine to the main loop rather than running it itself.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def main_loop() -> Optional[asyncio.AbstractEventLoop]:
    return _main_loop


@dataclass
class ScanResult:
    checked_at: datetime
    new_insights: int = 0
    symbols_checked: int = 0
    brokerage_linked: bool = False
    # Things the scan could not do, in words for the user.
    notes: List[str] = field(default_factory=list)


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
    with SessionLocal() as db:
        profile = get_or_create_profile(db, user_id)
        watchlist = [str(s).upper() for s in (profile.watchlist or [])][:MAX_SYMBOLS]
        move_alert_pct = float(profile.move_alert_pct)
        max_position_pct = float(profile.max_position_pct)
        holdings: List[Holding] = []
        linked = False
        try:
            read = read_holdings(db, user_id)
            if read is None:
                notes.append("No brokerage is linked, so holdings were not checked.")
            else:
                holdings, linked = read, True
        except Exception:  # noqa: BLE001
            logger.exception("agent: holdings read failed user=%s", user_id)
            notes.append("Your broker could not be read this time, so holdings were not checked.")
        try:
            exits = read_unresolved_exits(db, user_id)
        except Exception:  # noqa: BLE001
            logger.exception("agent: exits read failed user=%s", user_id)
            exits = []
    return _Inputs(watchlist, move_alert_pct, max_position_pct, holdings, linked, exits, notes)


def _persist(user_id: str, findings: List[Finding], checked_at: datetime) -> int:
    """Store the findings that are not already known. Returns how many were new."""
    new = 0
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
            new += 1
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

    found: List[Finding] = []
    for symbol in symbols[:MAX_FILINGS]:
        try:
            analysis = await sec_company_facts.filing_analysis(symbol)
        except Exception:  # noqa: BLE001 — funds, foreign filers and bad tickers have none
            continue
        if not analysis.quarters:
            continue
        latest = analysis.quarters[-1]
        if latest.filed is None or today - latest.filed > FILING_IS_NEW_FOR:
            continue
        watch = [f for f in analysis.findings if f.severity == "watch"]
        found += checks.filing(symbol, latest.label, [f.title for f in watch], [f.detail for f in watch])
    return found


async def scan_user(user_id: str) -> ScanResult:
    """Look at everything the agent watches for one user, once."""
    checked_at = datetime.utcnow()
    today = datetime.now(timezone.utc).date()
    inputs = await asyncio.to_thread(_gather, user_id)

    held = [h.symbol for h in sorted(inputs.holdings, key=lambda h: h.value, reverse=True)]
    # Holdings first: if the list has to be cut, what is owned matters more.
    symbols = list(dict.fromkeys(held + inputs.watchlist))[:MAX_SYMBOLS]
    notes = list(inputs.notes)

    findings: List[Finding] = []
    findings += checks.exits_waiting(inputs.exits, today)
    findings += checks.concentration(inputs.holdings, inputs.max_position_pct, today)
    if symbols:
        try:
            quotes = await _quotes(symbols)
            findings += checks.price_moves(quotes, inputs.move_alert_pct, inputs.holdings, today)
        except Exception:  # noqa: BLE001
            logger.exception("agent: quotes failed user=%s", user_id)
            notes.append("Prices could not be read this time.")
        findings += await _filing_findings(symbols, today)
    else:
        notes.append("Nothing to watch yet: add symbols to your watchlist or link a brokerage.")

    new = await asyncio.to_thread(_persist, user_id, findings, checked_at)
    return ScanResult(
        checked_at=checked_at,
        new_insights=new,
        symbols_checked=len(symbols),
        brokerage_linked=inputs.brokerage_linked,
        notes=notes,
    )
