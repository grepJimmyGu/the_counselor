from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company_overview import CompanyOverviewResponse
from app.services.company_overview_service import CompanyOverviewService

router = APIRouter(prefix="/api/company", tags=["company-overview"])
_service = CompanyOverviewService()


@router.get("/{symbol}/overview", response_model=CompanyOverviewResponse)
async def get_company_overview(
    symbol: str,
    db: Session = Depends(get_db),
) -> CompanyOverviewResponse:
    """
    Full company overview: Business Map (partial) + Market Position (partial)
    + Financial Check (complete). Business Map and Market Position fields that
    require analytical intelligence are left blank, reserved for PRD-08b.
    """
    try:
        return await _service.get_overview(db, symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
