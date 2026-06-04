"""CN market endpoints — stock search + technical indicators.

Phase 3c (2026-06-04): CN stock search by Chinese name or ticker code,
backed by Alpha Vantage SYMBOL_SEARCH filtered to .SS/.SZ exchanges.
Technical indicator proxy delegates directly to AV so the frontend
doesn't store API keys.
"""
from datetime import date, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/cn", tags=["cn-market"])

AV_BASE = "https://www.alphavantage.co/query"


# ── Output shapes ──────────────────────────────────────────────────────────────


class CnSearchResult(BaseModel):
    symbol: str
    name_cn: str
    exchange: str


class IndicatorPoint(BaseModel):
    date: str
    value: float


class IndicatorResponse(BaseModel):
    symbol: str
    function: str
    points: list[IndicatorPoint]
    latest_value: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    signal: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _av_key() -> str:
    key = get_settings().alpha_vantage_api_key
    if not key:
        raise HTTPException(status_code=503, detail="AV API key not configured")
    return key


def _signal_note(function: str, value: Optional[float]) -> Optional[str]:
    """Human-readable interpretation of the latest indicator value."""
    if value is None:
        return None
    if function == "RSI":
        if value > 70:
            return "超买 (overbought)"
        if value < 30:
            return "超卖 (oversold)"
        return "中性区间"
    if function == "MACD":
        return "看涨信号 (bullish)" if value > 0 else "看跌信号 (bearish)"
    if function == "BBANDS":
        return "价格位于布林带区间内"
    return None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/stocks/search", response_model=list[CnSearchResult])
async def cn_stock_search(
    q: str = Query(min_length=1, description="Chinese name or ticker code"),
):
    """Search CN stocks by name or code. Filters to .SS/.SZ results only."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.api_timeout_seconds) as client:
        resp = await client.get(AV_BASE, params={
            "function": "SYMBOL_SEARCH",
            "keywords": q,
            "apikey": _av_key(),
        })
        resp.raise_for_status()
        payload = resp.json()

    matches = payload.get("bestMatches", [])
    results: list[CnSearchResult] = []
    seen = set()
    for m in matches:
        sym = m.get("1. symbol", "")
        # Only CN exchanges — Alpha Vantage uses .SHH/.SHZ suffixes
        if not (sym.endswith(".SHH") or sym.endswith(".SHZ") or
                sym.endswith(".SS") or sym.endswith(".SZ")):
            continue
        if sym in seen:
            continue
        seen.add(sym)
        exchange = "上海" if ("SHH" in sym or ".SS" in sym) else "深圳"
        results.append(CnSearchResult(
            symbol=sym.replace(".SHH", ".SS").replace(".SHZ", ".SZ"),
            name_cn=m.get("2. name", sym),
            exchange=exchange,
        ))
    return results[:8]


@router.get("/indicators", response_model=IndicatorResponse)
async def cn_technical_indicator(
    symbol: str = Query(min_length=6, description="Ticker like 600519.SS"),
    function: str = Query(pattern=r"^(SMA|RSI|MACD|BBANDS)$"),
    time_period: int = Query(default=20, ge=2, le=200),
    range_: str = Query(default="6M", alias="range"),
):
    """Proxy Alpha Vantage technical indicator endpoint. Returns time-series
    data formatted for a Recharts line chart. Cached by AV on their side."""
    settings = get_settings()
    params: dict = {
        "function": function,
        "symbol": symbol,
        "interval": "daily",
        "series_type": "close",
        "apikey": _av_key(),
        "time_period": str(time_period),
    }
    if function == "MACD":
        # MACD uses default fast=12 slow=26 signal=9
        params.pop("time_period", None)
    async with httpx.AsyncClient(timeout=settings.api_timeout_seconds) as client:
        resp = await client.get(AV_BASE, params=params)
        resp.raise_for_status()
        payload = resp.json()

    # AV returns "Technical Analysis: {FUNCTION_NAME}"
    key = f"Technical Analysis: {function}"
    raw = payload.get(key, {})
    if not raw:
        raise HTTPException(
            status_code=502, detail=f"AV returned no data for {function} on {symbol}"
        )

    # Build date-sorted points, applying the range filter
    dates = sorted(raw.keys(), reverse=True)
    range_days = {"1M": 22, "3M": 66, "6M": 132, "1Y": 252, "ALL": 999999}
    max_days = range_days.get(range_, 132)
    cutoff = (date.today() - timedelta(days=int(max_days * 1.2))).isoformat()

    points: list[IndicatorPoint] = []
    values: list[float] = []
    for d in dates:
        if d < cutoff:
            continue
        entry = raw[d]
        # Pick the primary value line — SMA/RSI/BBANDS have the function name,
        # MACD has MACD + MACD_Signal + MACD_Hist.
        if function == "MACD":
            val = float(entry.get("MACD", 0))
        elif function == "BBANDS":
            # Return the Real Middle Band as the representative value
            val = float(entry.get("Real Middle Band", 0))
        elif function == "SMA":
            val = float(entry.get("SMA", 0))
        else:  # RSI
            val = float(entry.get("RSI", 0))
        points.append(IndicatorPoint(date=d, value=round(val, 4)))
        values.append(val)

    # Most-recent-first from AV → reverse to chronological for chart rendering
    points.reverse()
    latest = values[0] if values else None
    high = max(values) if values else None
    low = min(values) if values else None

    return IndicatorResponse(
        symbol=symbol,
        function=function,
        points=points,
        latest_value=latest,
        high=high,
        low=low,
        signal=_signal_note(function, latest),
    )
