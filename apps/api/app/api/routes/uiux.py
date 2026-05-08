from fastapi import APIRouter

from app.schemas.uiux import UXReviewRequest, UXReviewResponse
from app.services.uiux_service import review_ux

router = APIRouter(prefix="/api/uiux", tags=["uiux"])


@router.post("/review", response_model=UXReviewResponse)
async def uiux_review(request: UXReviewRequest) -> UXReviewResponse:
    return await review_ux(request)
