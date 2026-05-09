from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.data_quality import DataQualityReport
from app.schemas.market_data import (
    DataStatusResponse,
    MarketSnapshotItem,
    PriceBarResponse,
    SymbolDetailResponse,
    SymbolSearchItem,
    WarmupRequest,
    WarmupResponse,
)
from sqlalchemy import select

from app.models.price_bar import PriceBar
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


@router.get("/data/quality/{symbol}", response_model=DataQualityReport)
async def get_data_quality(
    symbol: str,
    db: Session = Depends(get_db),
) -> DataQualityReport:
    return data_quality_service.check_symbol(db, symbol.upper())


@router.get("/market/overview", response_model=list[MarketSnapshotItem])
async def get_market_overview(
    symbols: str = Query(..., description="Comma-separated list of symbols, max 12"),
    db: Session = Depends(get_db),
) -> list[MarketSnapshotItem]:
    """Return latest price snapshot + 30-day sparkline for a list of symbols."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()][:12]
    results: list[MarketSnapshotItem] = []

    for symbol in symbol_list:
        try:
            # Ensure cache is fresh (non-blocking best-effort)
            await market_data_service.ensure_daily_history(db, symbol, date.today())

            rows = db.execute(
                select(PriceBar)
                .where(PriceBar.symbol == symbol)
                .order_by(PriceBar.trading_date.desc())
                .limit(31)
            ).scalars().all()

            if not rows:
                continue

            rows_asc = sorted(rows, key=lambda r: r.trading_date)
            last = rows_asc[-1]
            prev = rows_asc[-2] if len(rows_asc) >= 2 else None

            change_pct = ((last.adjusted_close - prev.adjusted_close) / prev.adjusted_close) if prev and prev.adjusted_close else 0.0
            change_abs = (last.adjusted_close - prev.adjusted_close) if prev else 0.0
            sparkline = [r.adjusted_close for r in rows_asc]

            detail = symbol_service.get_detail(db, symbol)
            name = detail.name if detail else symbol

            results.append(MarketSnapshotItem(
                symbol=symbol,
                name=name,
                last_price=round(last.adjusted_close, 2),
                prev_close=round(prev.adjusted_close, 2) if prev else round(last.adjusted_close, 2),
                change_pct=round(change_pct, 5),
                change_abs=round(change_abs, 4),
                last_date=last.trading_date,
                sparkline=[round(v, 2) for v in sparkline],
            ))
        except Exception:
            continue

    return results
