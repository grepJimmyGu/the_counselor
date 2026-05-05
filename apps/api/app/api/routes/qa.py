from fastapi import APIRouter

from app.schemas.qa import QAReviewRequest, QAReviewResponse
from app.services.qa_service import run_qa_review

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("/review", response_model=QAReviewResponse)
async def qa_review(request: QAReviewRequest) -> QAReviewResponse:
    return await run_qa_review(request)
