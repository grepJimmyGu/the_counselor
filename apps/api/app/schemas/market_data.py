from typing import Optional

from datetime import date

from pydantic import BaseModel


class SymbolSearchItem(BaseModel):
    symbol: str
    name: str
    region: Optional[str] = None
    currency: Optional[str] = None
    instrument_type: Optional[str] = None


class PriceBarResponse(BaseModel):
    symbol: str
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
    dividend_amount: float
    split_coefficient: float
