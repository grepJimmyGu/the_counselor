from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_data import (
    DataStatusResponse,
    PriceBarResponse,
    SymbolDetailResponse,
    SymbolSearchItem,
    WarmupRequest,
    WarmupResponse,
)
from app.services.alpha_vantage import AlphaVantageClient
from app.services.data_quality_service import DataQualityService
from app.services.market_data import MarketDataService
from app.services.price_data_service import PriceDataService
from app.services.symbol_service import SymbolService

router = APIRouter(prefix="/api", tags=["market-data"])

_av_client = AlphaVantageClient()
market_data_service = MarketDataService()
price_data_service = PriceDataService()
symbol_service = SymbolService(_av_client)
data_quality_service = DataQualityService()


@router.get("/symbols/search", response_model=list[SymbolSearchItem])
async def search_symbols(
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> list[SymbolSearchItem]:
    return await symbol_service.search(db, query)


@router.get("/symbols/{symbol}", response_model=SymbolDetailResponse)
async def get_symbol(
    symbol: str,
    db: Session = Depends(get_db),
) -> SymbolDetailResponse:
    detail = symbol_service.get_detail(db, symbol.upper())
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol.upper()} not found in cache.")
    return detail


@router.get("/data/daily/{symbol}", response_model=list[PriceBarResponse])
async def get_daily_prices(
    symbol: str,
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PriceBarResponse]:
    end_date = end or date.today()
    return await market_data_service.get_cached_bars(db, symbol.upper(), end_date)


@router.post("/data/warmup", response_model=WarmupResponse)
async def warmup_symbols(
    payload: WarmupRequest,
    db: Session = Depends(get_db),
) -> WarmupResponse:
    symbols = [s.strip().upper() for s in payload.symbols if s.strip()]
    return await data_quality_service.warmup(db, symbols, lookback_days=payload.lookback_days)


@router.get("/data/status/{symbol}", response_model=DataStatusResponse)
async def get_data_status(
    symbol: str,
    db: Session = Depends(get_db),
) -> DataStatusResponse:
    return await price_data_service.get_status(db, symbol.upper())
