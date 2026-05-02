from fastapi import APIRouter

from app.schemas.insights import (
    ExplainRequest,
    ExplanationResponse,
    SandboxReviewRequest,
    SandboxReviewResponse,
)
from app.services.insights import build_explanation, build_sandbox_review

router = APIRouter(prefix="/api", tags=["insights"])


@router.post("/insights/explain", response_model=ExplanationResponse)
async def explain_strategy(payload: ExplainRequest) -> ExplanationResponse:
    return await build_explanation(payload.strategy_json, payload.backtest_result, locale=payload.locale)


@router.post("/review/sandbox", response_model=SandboxReviewResponse)
async def review_sandbox(payload: SandboxReviewRequest) -> SandboxReviewResponse:
    return await build_sandbox_review(payload.strategy_json, payload.backtest_result, locale=payload.locale)

