from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_data import PriceBarResponse, SymbolSearchItem
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/api", tags=["market-data"])
market_data_service = MarketDataService()


@router.get("/symbols/search", response_model=list[SymbolSearchItem])
async def search_symbols(query: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> list[SymbolSearchItem]:
    return await market_data_service.search_symbols(db, query)


@router.get("/data/daily/{symbol}", response_model=list[PriceBarResponse])
async def get_daily_prices(symbol: str, db: Session = Depends(get_db)) -> list[PriceBarResponse]:
    return await market_data_service.get_cached_bars(db, symbol.upper(), date.today())

