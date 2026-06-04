"""CN company overview route — Phase 3d (2026-06-04).

Serves GET /api/cn/company/{symbol}/overview for A-share stocks.
Delegates to cn_overview_service which returns the same
CompanyOverviewResponse shape the US company page expects.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company_overview import CompanyOverviewResponse
from app.services.cn_overview_service import get_cn_company_overview

router = APIRouter(prefix="/api/cn", tags=["cn-company"])


@router.get("/company/{symbol}/overview", response_model=CompanyOverviewResponse)
async def cn_company_overview(
    symbol: str,
    db: Session = Depends(get_db),
) -> CompanyOverviewResponse:
    """CN company overview — FMP profile + peers + AKShare financials/news.
    Degrades gracefully when AKShare is unavailable."""
    try:
        return await get_cn_company_overview(symbol.upper())
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"CN company overview unavailable for {symbol}: {exc}",
        ) from exc
