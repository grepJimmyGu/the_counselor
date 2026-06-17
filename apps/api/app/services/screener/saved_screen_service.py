"""Saved-screen tracking (PRD-23c §3.1-3.2).

A *saved screen* is a `SavedStrategy` whose `strategy_json.kind == "screen"`
and which carries `{universe_id, rules}`. Unlike a single-asset strategy, its
"position" is a *basket* of names that changes as the market moves. This
service re-runs the scan and diffs the result against the persisted basket
(`screen_basket_members`); the cron then notifies on each NEW entrant.

The re-scan goes through the SAME `scan()` the live `/api/screen/scan` route
uses, so a tracked screen and a fresh scan return byte-identical baskets.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional, Sequence
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.sp500_tickers import SP500_TICKERS
from app.models.saved_strategy import SavedStrategy
from app.models.screen_basket_member import ScreenBasketMember
from app.models.symbol import SymbolCache
from app.schemas.strategy import StrategyRule
from app.services.screener.scan_service import scan

logger = logging.getLogger("livermore.screener.track")

SCREEN_KIND = "screen"


def is_screen(saved: SavedStrategy) -> bool:
    """True if a SavedStrategy is a tracked screen (vs a single-asset strategy)."""
    sj = saved.strategy_json
    return isinstance(sj, dict) and sj.get("kind") == SCREEN_KIND


def screen_strategy_json(universe_id: str, rules: Sequence[StrategyRule]) -> dict:
    """The canonical persisted shape of a screen — rehydrated by `rescan_and_diff`."""
    return {
        "kind": SCREEN_KIND,
        "universe_id": universe_id,
        "rules": [r.model_dump(mode="json") for r in rules],
    }


def _db_sector_membership(db: Session) -> Callable[[str], List[str]]:
    """sector_<key> -> SP500-intersected members.

    NOTE: mirrors `screen.py`'s route-level `_db_sector_membership`; both
    should collapse into one shared screener helper in a follow-up (the same
    sector-label-normalization TODO applies to both)."""

    def lookup(key: str) -> List[str]:
        rows = (
            db.execute(
                select(SymbolCache.symbol).where(
                    func.lower(SymbolCache.sector) == key.lower()
                )
            )
            .scalars()
            .all()
        )
        return [s for s in rows if s in SP500_TICKERS]

    return lookup


@dataclass
class ScreenDiff:
    new_entrants: List[str]
    exits: List[str]
    as_of_date: Optional[date]
    basket: List[str]  # the current basket AFTER applying this diff
    universe_size: int


def _parse_screen(saved: SavedStrategy):
    sj = saved.strategy_json or {}
    universe_id = sj.get("universe_id")
    rules = [StrategyRule.model_validate(r) for r in sj.get("rules", [])]
    return universe_id, rules


def current_basket(db: Session, saved_strategy_id: str) -> List[ScreenBasketMember]:
    """The screen's current members (rows with `exited_date IS NULL`)."""
    return list(
        db.execute(
            select(ScreenBasketMember).where(
                ScreenBasketMember.saved_strategy_id == saved_strategy_id,
                ScreenBasketMember.exited_date.is_(None),
            )
        )
        .scalars()
        .all()
    )


def rescan_and_diff(db: Session, saved: SavedStrategy) -> ScreenDiff:
    """Re-scan a saved screen, diff today's matched basket vs the persisted
    current basket, and update membership in place: insert a row per new
    entrant, set `exited_date` on each exit. Commits, then returns the diff.

    Does NOT notify — the cron owns dispatch so the throttle + subscription
    checks live in one place. Idempotent for a given `as_of_date`: a symbol
    already current is neither re-added nor re-reported as a new entrant, so a
    re-run (redeploy, manual trigger) fires nothing.
    """
    universe_id, rules = _parse_screen(saved)
    if not universe_id:
        logger.warning("saved screen %s has no universe_id; skipping", saved.id)
        return ScreenDiff([], [], None, [], 0)

    result = scan(db, universe_id, rules, sector_membership=_db_sector_membership(db))
    matched = set(result.matched)
    anchor = result.as_of_date or date.today()

    members = current_basket(db, saved.id)
    current = {m.symbol for m in members}

    new_entrants = sorted(matched - current)
    exits = sorted(current - matched)

    for sym in new_entrants:
        db.add(
            ScreenBasketMember(
                id=str(uuid4()),
                saved_strategy_id=saved.id,
                symbol=sym,
                entered_date=anchor,
                exited_date=None,
            )
        )
    by_symbol = {m.symbol: m for m in members}
    for sym in exits:
        by_symbol[sym].exited_date = anchor

    db.commit()

    basket = sorted((current - set(exits)) | set(new_entrants))
    return ScreenDiff(
        new_entrants=new_entrants,
        exits=exits,
        as_of_date=result.as_of_date,
        basket=basket,
        universe_size=result.universe_size,
    )
