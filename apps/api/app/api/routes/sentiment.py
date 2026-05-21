from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from app.db.session import get_db
from app.schemas.sentiment import (
    CommunityMention,
    NewsArticle,
    ProvidersStatusResponse,
    SentimentAnalyzeRequest,
    SentimentAnalyzeResponse,
    SentimentSandboxRequest,
    SentimentSandboxResponse,
    SentimentSummaryResponse,
)
from app.services.sentiment_sandbox_reviewer import SentimentSandboxReviewer
from app.services.sentiment_service import SentimentService
from app.services.sentiment_toolkit_service import SentimentToolkitService, list_toolkits

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])
_service = SentimentService()
_toolkit_service = SentimentToolkitService()
_sandbox = SentimentSandboxReviewer()

# Stage 3: per-ticker sentiment routes gated to S&P 500 for Scout + anonymous.
_market_pulse_gate = require_entitlement(
    market_pulse_ticker_field="symbol",
    allow_anonymous=True,
)


@router.get("/providers/status", response_model=ProvidersStatusResponse)
def get_providers_status() -> ProvidersStatusResponse:
    return _service.get_provider_status()


@router.get("/toolkits")
def get_toolkits() -> list[dict]:
    return list_toolkits()


@router.get("/{symbol}/summary", response_model=SentimentSummaryResponse)
async def get_sentiment_summary(
    symbol: str,
    refresh: bool = Query(default=False, description="Force-refresh ignoring cache"),
    _gate=Depends(_market_pulse_gate),
    db: Session = Depends(get_db),
) -> SentimentSummaryResponse:
    """Gated: Scout + anonymous → S&P 500 only."""
    try:
        return await _service.get_summary(symbol.upper(), db, refresh=refresh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{symbol}/news", response_model=list[NewsArticle])
async def get_raw_news(
    symbol: str,
    _gate=Depends(_market_pulse_gate),
    db: Session = Depends(get_db),
) -> list[NewsArticle]:
    """Gated: Scout + anonymous → S&P 500 only."""
    try:
        return await _service.get_raw_articles(symbol.upper(), db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{symbol}/community", response_model=list[CommunityMention])
async def get_raw_community(
    symbol: str,
    _gate=Depends(_market_pulse_gate),
    db: Session = Depends(get_db),
) -> list[CommunityMention]:
    """Gated: Scout + anonymous → S&P 500 only."""
    try:
        return await _service.get_raw_mentions(symbol.upper(), db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze", response_model=SentimentAnalyzeResponse)
async def analyze_symbols(
    request: SentimentAnalyzeRequest,
    db: Session = Depends(get_db),
) -> SentimentAnalyzeResponse:
    if not request.symbols:
        raise HTTPException(status_code=400, detail="symbols list is required")
    if len(request.symbols) > 50:
        raise HTTPException(status_code=400, detail="max 50 symbols per request")

    try:
        sentinel_summaries: dict = {}
        for sym in request.symbols:
            summary = await _service.get_summary(sym.upper(), db, refresh=request.refresh)
            sentinel_summaries[sym.upper()] = summary.model_dump()

        return await _toolkit_service.run(request, db, sentinel_summaries)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/review", response_model=SentimentSandboxResponse)
async def sandbox_review(
    request: SentimentSandboxRequest,
) -> SentimentSandboxResponse:
    try:
        return await _sandbox.review(request.symbol, request.sentiment_summary)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
