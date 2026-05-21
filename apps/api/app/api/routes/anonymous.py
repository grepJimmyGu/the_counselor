"""Anonymous viewer endpoints (Stage 1a).

The one-shot taste-without-signup surface. Two endpoints:

  GET  /api/anonymous/entitlements — returns AnonymousEntitlements; sets
       the livermore_anon_id cookie if missing. Used by the frontend to
       decide between the 'Run free' CTA and the 'Sign up to keep going' CTA.

  POST /api/anonymous/backtest/run — runs a single backtest with strict
       anonymous constraints (template_id required, universe ≤ 1 ticker,
       equities only, runs_used < 1). After the run, the BacktestRecord is
       persisted with user_id=NULL; on signup, merge_anonymous_into_user
       attaches it to the new user.

For Stage 1a the backend does NOT maintain a template registry — the
frontend constructs the strategy_json from its researchTemplates source
of truth and sends it along with template_id (treated as a free-form
string for telemetry; Stage 5 will introduce a server-side whitelist).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.entitlement_errors import upgrade_error
from app.db.session import get_db
from app.schemas.backtest import BacktestResult
from app.schemas.identity import AnonymousEntitlements
from app.schemas.strategy import StrategyJSON
from app.services.anonymous_service import (
    get_or_create_anonymous_session,
    increment_anonymous_run,
    record_anonymous_referrer,
)
from app.services.backtester import engine
from app.services.entitlements import get_anonymous_entitlements

router = APIRouter(prefix="/api/anonymous", tags=["anonymous"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class AnonymousBacktestRunRequest(BaseModel):
    """Anonymous one-shot backtest. template_id is required so the frontend
    cannot accidentally route chat-built (custom) strategies here."""
    template_id: str = Field(..., min_length=1, max_length=128)
    strategy_json: StrategyJSON
    via_handle: Optional[str] = Field(default=None, max_length=32)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/entitlements", response_model=AnonymousEntitlements)
def anonymous_entitlements(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AnonymousEntitlements:
    """Read or create the anonymous session and return its entitlements snapshot."""
    session = get_or_create_anonymous_session(request, response, db)
    return get_anonymous_entitlements(session)


@router.post("/backtest/run", response_model=BacktestResult)
async def anonymous_backtest_run(
    payload: AnonymousBacktestRunRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> BacktestResult:
    session = get_or_create_anonymous_session(request, response, db)

    # Policy (2026-05-22): anonymous viewers get ONE backtest per session —
    # template OR chat-built ("custom"). Previously we rejected
    # `template_id == "custom"` unconditionally, which blocked the chat
    # builder's entire funnel for anonymous users and was the dominant
    # source of `anonymous_chat_locked` 402s in the wild. The change is
    # explicit: let them taste their custom strategy once, then ask them
    # to sign up. The universe-size + asset-class gates below still apply.
    # Stage 5 will replace template_id with a server-side whitelist.

    # First-touch referrer preservation (Creator Program credit through funnel).
    if payload.via_handle:
        record_anonymous_referrer(db, session, payload.via_handle)

    # Anonymous cap: 1 fresh backtest per session (template OR custom).
    if session.runs_used >= 1:
        raise upgrade_error("anonymous_runs_exhausted", is_anonymous=True)

    # Universe gate: anonymous one-shot is single-ticker only.
    universe = list(payload.strategy_json.universe or [])
    if len(universe) > 1:
        raise upgrade_error(
            "anonymous_universe_too_large",
            is_anonymous=True,
            current_value=str(len(universe)),
            limit_value="1",
        )

    # Asset-class gate: equities only. Block known A-share suffixes and any
    # universe that looks like commodities. The full asset-class taxonomy
    # ships in Stage 3; this is a minimum safety net.
    for sym in universe:
        if sym.upper().endswith((".SHH", ".SHZ")):
            raise upgrade_error(
                "anonymous_asset_class_locked",
                is_anonymous=True,
                current_value=sym,
                limit_value="equities",
            )

    # Run the backtest. Engine persists a BacktestRecord with user_id=NULL;
    # merge_anonymous_into_user will set user_id on signup.
    result = await engine.run(db, payload.strategy_json)

    increment_anonymous_run(db, session, backtest_id=result.backtest_id)
    return result
