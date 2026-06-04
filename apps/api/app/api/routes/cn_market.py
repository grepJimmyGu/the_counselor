"""CN market endpoints — stock search + technical indicators.

Phase 3c (2026-06-04): CN stock search by Chinese name or ticker code,
backed by local CSI 300+500+1000 index constituent data. The CSV files
(china_a_share_universes/*.csv) are loaded once at module import so
searches are fast, reliable, and work with Chinese characters (unlike
the AV SYMBOL_SEARCH endpoint which has limited CN language support).

Technical indicator proxy delegates directly to AV so the frontend
doesn't store API keys.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/cn", tags=["cn-market"])

AV_BASE = "https://www.alphavantage.co/query"

_log = logging.getLogger("livermore.cn_market")


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


# ── Local search index ──────────────────────────────────────────────────────


def _load_cn_tickers() -> list[dict]:
    """Load CSI 300 + 500 + 1000 constituent data from the local CSV files.
    Returns a deduplicated list of {symbol, name_cn, exchange} dicts.

    Looks for CSVs at `china_a_share_universes/` under the repo root."""
    csv_dir = Path(__file__).resolve().parents[2] / "data"
    seen: set[str] = set()
    rows: list[dict] = []
    for fname in [
        "csi300_constituents.csv",
        "csi500_constituents.csv",
        "csi1000_constituents.csv",
    ]:
        path = csv_dir / fname
        if not path.exists():
            _log.warning("cn_market: missing %s — skipping", fname)
            continue
        with open(path, encoding="utf-8-sig") as fh:
            for rec in csv.DictReader(fh):
                sym = rec.get("yahoo_ticker", "").strip()
                if not sym or sym in seen:
                    continue
                seen.add(sym)
                # Derive exchange label from the ticker suffix
                exchange = "上海" if sym.endswith(".SS") else "深圳" if sym.endswith(".SZ") else ""
                rows.append({
                    "symbol": sym,
                    "name_cn": rec.get("name_cn", "").strip(),
                    "exchange": exchange,
                })
    _log.info("cn_market: loaded %d unique CN tickers from CSVs", len(rows))
    return rows


_CN_TICKERS: list[dict] = _load_cn_tickers()


def _search_local(query: str, max_results: int = 8) -> list[CnSearchResult]:
    """Fast local search against the pre-loaded CSV data. Supports:
    - Chinese name (partial match)
    - Ticker code (6-digit code, with or without .SS/.SZ suffix)
    - English name (partial match, case-insensitive)
    """
    q = query.strip().lower()
    results: list[CnSearchResult] = []
    for row in _CN_TICKERS:
        sym = row["symbol"]
        code = sym.split(".")[0]
        # Match against ticker code (partial), Chinese name (contains),
        # or English name (the CSV name_cn field IS Chinese, so this
        # is the primary matching path).
        if (
            q in row["name_cn"].lower()
            or q in sym.lower()
            or q in code
        ):
            results.append(CnSearchResult(
                symbol=sym,
                name_cn=row["name_cn"],
                exchange=row["exchange"],
            ))
            if len(results) >= max_results:
                break
    return results


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/stocks/search", response_model=list[CnSearchResult])
def cn_stock_search(
    q: str = Query(min_length=1, description="Chinese name or ticker code"),
):
    """Search CN stocks by Chinese name or 6-digit ticker code.
    Uses the local CSI 300+500+1000 index data — instant, reliable,
    and supports Chinese characters (unlike AV's SYMBOL_SEARCH)."""
    return _search_local(q)


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
