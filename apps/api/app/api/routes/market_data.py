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
            # Force-refresh if display-stale (> 3 calendar days behind today)
            await market_data_service.ensure_display_fresh(db, symbol)

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


# ── PRD-15: Market Pulse ──────────────────────────────────────────────────────

from app.services.market_pulse_service import MarketPulseService

_pulse_svc = MarketPulseService()


@router.get("/market/pulse")
async def get_market_pulse(
    market: str = Query(default="US", pattern="^(US|CN)$"),
    bypass_cache: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    """
    Market Pulse: index ETF performance, macro chips, sector capital flow signals
    (Chaikin Money Flow 20d), and dynamic top 10 assets by CMF.
    All data from price_bars — no FMP calls at request time. 1h cache.

    Phase 1b: response also carries an optional LLM-generated `narrative`
    block ({ headline, sector_rotation, watch_items }). Generated on the
    first cache-miss request per market and reused for the rest of the
    60-min window. Returns null when `LLM_PROVIDER` is unset — frontend
    falls back to the deterministic template in
    `lib/market-pulse-narrative.ts`.

    Phase 1c: response also carries `macro_signals` — the 4-row payload
    used by `MacroPulseTable` (Growth / Inflation / Rates / Stress).
    Rates + Inflation are real (Alpha Vantage TREASURY_YIELD + CPI);
    Growth + Stress remain mock pending a FRED key. Cached 24h
    server-side and surfaced as part of the pulse response so the
    frontend doesn't need a second round-trip.

    Pass bypass_cache=true to force recomputation (clears both pulse and
    narrative caches).
    """
    market = market.upper()
    try:
        if bypass_cache:
            _pulse_svc.invalidate_cache()
        r = _pulse_svc.get_pulse(market, db)

        # Lazy narrative generation. Cached separately from pulse so a
        # single LLM failure doesn't invalidate the (sync, deterministic)
        # pulse data. Returns None when LLM_PROVIDER is unset — frontend
        # falls back to the deterministic template.
        narrative = _pulse_svc.get_cached_narrative(market)
        if narrative is None:
            from app.services.market_pulse_narrative_service import (
                generate_narrative,
            )
            try:
                narrative = await generate_narrative(r)
            except Exception as exc:  # noqa: BLE001 — never fail the page
                import logging
                logging.getLogger("livermore.market_pulse").warning(
                    "market_pulse narrative generation failed: %r", exc,
                )
                narrative = None
            _pulse_svc.set_cached_narrative(market, narrative)

        # Phase 1c — macro signals (Growth / Inflation / Rates / Stress).
        # The service has its own 24h cache; calling it here is cheap.
        # Defensive: any failure falls back to an empty list so the page
        # doesn't error (frontend then uses its hardcoded mock).
        from app.services.macro_signals_service import get_macro_signals
        try:
            macro_signals = await get_macro_signals()
            macro_signals_payload = [vars(s) for s in macro_signals]
        except Exception as exc:  # noqa: BLE001 — never fail the page
            import logging
            logging.getLogger("livermore.market_pulse").warning(
                "macro_signals fetch failed: %r", exc,
            )
            macro_signals_payload = []

        return {
            "market": r.market,
            "as_of": r.as_of,
            "indices": [vars(i) for i in r.indices],
            "macro": [vars(m) for m in r.macro],
            "sectors": [vars(s) for s in r.sectors],
            "top_assets": [vars(a) for a in r.top_assets],
            "featured_etfs": [vars(a) for a in r.featured_etfs],
            "narrative": narrative.model_dump() if narrative else None,
            "macro_signals": macro_signals_payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
