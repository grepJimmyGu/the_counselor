"""Saved strategies CRUD (Stage 1a).

POST   /api/strategies          — create (Scout cap + auto-public enforced)
GET    /api/strategies          — list current user's saves
GET    /api/strategies/{id}     — read (owner or public)
DELETE /api/strategies/{id}     — delete (owner only)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest

# NOTE: mounted at /api/saved-strategies (not /api/strategies) to avoid colliding
# with the legacy PRD-02 strategy_storage.py routes which still serve the slug-based
# Workspace flow. Stage 4 will reconcile the two surfaces.
router = APIRouter(prefix="/api/saved-strategies", tags=["saved_strategies"])


class SavedStrategyResponse(BaseModel):
    id: str
    user_id: str
    title: str
    strategy_json: dict
    is_public: bool
    backtest_record_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=SavedStrategyResponse, status_code=201)
def create_saved_strategy(
    payload: SaveStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedStrategyResponse:
    """Save a strategy. Scout: forced public + 10 cap; Strategist+: respects is_public + 25/unlimited cap."""
    strategy = saved_strategy_service.save_strategy(db, current_user, payload)
    return SavedStrategyResponse.model_validate(strategy)


@router.get("", response_model=list[SavedStrategyResponse])
def list_saved_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedStrategyResponse]:
    rows = saved_strategy_service.list_user_strategies(db, current_user.id)
    return [SavedStrategyResponse.model_validate(r) for r in rows]


@router.get("/{strategy_id}", response_model=SavedStrategyResponse)
def get_saved_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedStrategyResponse:
    row = saved_strategy_service.get_strategy(db, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    # Public strategies are readable by anyone authenticated; private only by owner.
    if not row.is_public and row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return SavedStrategyResponse.model_validate(row)


@router.delete("/{strategy_id}", status_code=204, response_class=Response)
def delete_saved_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    deleted = saved_strategy_service.delete_strategy(db, current_user.id, strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return Response(status_code=204)
