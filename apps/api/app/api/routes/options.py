"""Option chains for the options builder, and the plans people save from it.

Everything here is for signed-in users. Prices are the last close, from one
provider call per symbol however many people ask (`option_chain_service`).
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.option_plan import OptionPlan
from app.models.user import User
from app.schemas.options import (
    SYMBOL,
    OptionChainView,
    OptionContractView,
    OptionExpirationView,
    OptionPlanCreate,
    OptionPlanView,
)
from app.services.options.chain_service import (
    NO_OPTIONS,
    OptionsUnavailable,
    option_chain_service,
    today_et,
)

router = APIRouter(prefix="/api/options", tags=["options"])

# Enough for anyone using it by hand; a ceiling so the table cannot be filled.
MAX_PLANS_PER_USER = 200


def _plan_view(row: OptionPlan) -> OptionPlanView:
    return OptionPlanView(
        id=row.id, symbol=row.symbol, strategy=row.strategy, legs=row.legs,
        underlying_price=row.underlying_price, as_of=row.as_of, created_at=row.created_at,
    )


# Declared before /{symbol}/chain so "plans" is never read as a ticker.
@router.get("/plans", response_model=List[OptionPlanView])
def list_plans(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[OptionPlanView]:
    """The user's saved plans, newest first."""
    rows = db.execute(
        select(OptionPlan).where(OptionPlan.user_id == user.id).order_by(OptionPlan.created_at.desc())
    ).scalars().all()
    return [_plan_view(row) for row in rows]


@router.post("/plans", response_model=OptionPlanView, status_code=201)
def save_plan(
    payload: OptionPlanCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptionPlanView:
    saved = db.execute(
        select(func.count()).select_from(OptionPlan).where(OptionPlan.user_id == user.id)
    ).scalar_one()
    if saved >= MAX_PLANS_PER_USER:
        raise HTTPException(
            status_code=409,
            detail=f"You have {MAX_PLANS_PER_USER} saved plans, the most there can be. Delete one to save another.",
        )
    row = OptionPlan(
        id=str(uuid.uuid4()),
        user_id=user.id,
        symbol=payload.symbol,
        strategy=payload.strategy,
        legs=[leg.model_dump(mode="json") for leg in payload.legs],
        underlying_price=payload.underlying_price,
        as_of=payload.as_of,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _plan_view(row)


@router.delete("/plans/{plan_id}", status_code=204, response_class=Response)
def delete_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = db.get(OptionPlan, plan_id)
    # Someone else's plan is "not found", the same as one that does not exist.
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Plan not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/{symbol}/chain", response_model=OptionChainView)
async def get_chain(
    symbol: str,
    expiration: Optional[date] = None,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptionChainView:
    """One expiry of `symbol`'s option chain, and the list of every expiry.

    Without `expiration` it is the default one: the first monthly expiry at
    least 30 days out. 404 when the stock has no listed options, 503 when the
    prices cannot be fetched right now.
    """
    sym = symbol.strip().upper()
    if not SYMBOL.match(sym):
        raise HTTPException(status_code=404, detail="Not a ticker symbol.")
    # Signing in has finished with the database. Give the connection back
    # before waiting on the provider (apps/api/CLAUDE.md, trap 13).
    db.close()
    try:
        part = await option_chain_service.slice(sym, expiration, today_et())
    except OptionsUnavailable as exc:
        status = 404 if exc.reason == NO_OPTIONS else 503
        raise HTTPException(status_code=status, detail=exc.message) from None
    return OptionChainView(
        symbol=part.symbol,
        as_of=part.as_of,
        underlying_price=part.underlying_price,
        expirations=[
            OptionExpirationView(date=e.date, days=e.days, monthly=e.monthly, implied_move_pct=e.implied_move_pct)
            for e in part.expirations
        ],
        default_expiration=part.default_expiration,
        expiration=part.expiration,
        contracts=[
            OptionContractView(
                contract_id=c.contract_id, kind=c.kind, strike=c.strike, bid=c.bid, ask=c.ask,
                mid=c.mid, last=c.last, volume=c.volume, open_interest=c.open_interest,
            )
            for c in part.contracts
        ],
    )
