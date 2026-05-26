from __future__ import annotations

from datetime import date, datetime
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
from app.services.sector_comparison_service import (
    SectorComparisonResponse,
    get_comparison as _get_sector_comparison,
)
from app.services.macro_similarity_service import (
    get_history_rhymes as _get_history_rhymes,
    invalidate_cache as _invalidate_history_rhymes_cache,
)

_pulse_svc = MarketPulseService()


@router.get("/market/pulse")
async def get_market_pulse(
    market: str = Query(default="US", pattern="^(US|CN)$"),
    bypass_cache: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    """
    Market Pulse: index ETF performance, macro chips, sector capital flow signals
    (Chaikin Money Flow 20d), and the full Top Movers candidate universe.
    The base snapshot comes from price_bars; an FMP live-quote overlay updates
    prices, 1D moves, and live-current CMF before the frontend ranks/render.

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
        r = await _pulse_svc.get_live_pulse(market, db)

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

        # Phase 1g — narrative date anchor. Set on the cached narrative
        # so subsequent cache hits within the 60-min TTL stamp the same
        # date string. The narrative cache invalidates daily via the
        # natural TTL roll, so the date stays correct in normal use; if
        # the cache survives across midnight UTC, the next refresh will
        # update it. Cheap: just a .strftime() call per request.
        if narrative is not None:
            # %A = weekday, %B = full month, %-d = day no leading zero
            # (POSIX; on Windows %#d). Railway runs Linux so %-d is fine.
            narrative.as_of = date.today().strftime("%A, %B %-d, %Y")

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


# ── Phase 1d: sector vs SPY comparison series ───────────────────────────────

# 5-min TTL cache keyed by (symbol, range). Sector tile re-clicks within
# the cache window skip the DB hit entirely.
from datetime import datetime as _dt, timedelta as _td
_SECTOR_COMPARISON_CACHE: dict[tuple[str, str], tuple[_dt, SectorComparisonResponse]] = {}
_SECTOR_COMPARISON_TTL = _td(minutes=5)


@router.get("/market/sector-comparison/{symbol}")
def get_sector_comparison(
    symbol: str,
    range: str = Query(default="1Y", pattern="^(1M|6M|YTD|1Y|3Y)$"),
    db: Session = Depends(get_db),
) -> dict:
    """Sector-ETF vs SPY cumulative-return comparison for the inline
    chart that expands under each sector tile in Market Pulse.

    Returns a {date, sector, spy} series normalized to 0% at series
    start (so both lines render cleanly from the same y-axis origin),
    plus pre-computed Day / YTD / 1Y / 3Y totals for the returns
    table underneath the chart.

    Cached 5 min per `(symbol, range)`. All data sourced from
    `price_bars` — no external API calls.
    """
    sym = symbol.upper()
    key = (sym, range)
    now = _dt.utcnow()

    cached = _SECTOR_COMPARISON_CACHE.get(key)
    if cached:
        cached_at, payload = cached
        if (now - cached_at) < _SECTOR_COMPARISON_TTL:
            return _serialize_comparison(payload)

    try:
        resp = _get_sector_comparison(db, sym, range)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not resp.series:
        # No bars in window — fall back to whatever we can build over the
        # full available history. Frontend shows a "Data loading" hint.
        raise HTTPException(
            status_code=404,
            detail=(
                f"No price history for {sym} in window {range}. "
                "Load via /api/data/warmup."
            ),
        )

    _SECTOR_COMPARISON_CACHE[key] = (now, resp)
    return _serialize_comparison(resp)


def _serialize_comparison(resp: SectorComparisonResponse) -> dict:
    return {
        "symbol": resp.symbol,
        "sector_name": resp.sector_name,
        "range": resp.range,
        "series": [vars(p) for p in resp.series],
        "sector_day": resp.sector_day,
        "sector_ytd": resp.sector_ytd,
        "sector_1y": resp.sector_1y,
        "sector_3y": resp.sector_3y,
        "spy_day": resp.spy_day,
        "spy_ytd": resp.spy_ytd,
        "spy_1y": resp.spy_1y,
        "spy_3y": resp.spy_3y,
    }


# ── Phase 1e: History Rhymes ────────────────────────────────────────────────


@router.get("/market/history-rhymes")
def get_history_rhymes(
    market: str = Query(default="US", pattern="^(US|CN)$"),
    bypass_cache: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    """History Rhymes — cosine similarity of today's 5-day macro vector
    against ~5y of historical 5-day windows. Returns the top 3
    matches with their post-window 30-trading-day SPY outcome.

    Macro basket: TLT (rates), VXX (vol), UUP (dollar), HYG (credit),
    GLD (gold), USO (oil). All ETFs — full daily OHLCV in `price_bars`.

    Cached 4h server-side. v1 supports `market=US` only; CN returns an
    empty payload with a "v1 is US-only" caveat.
    """
    try:
        if bypass_cache:
            _invalidate_history_rhymes_cache()
        resp = _get_history_rhymes(market, db)
        return {
            "market": resp.market,
            "as_of": resp.as_of,
            "today_vector": resp.today_vector,
            "matches": [vars(m) for m in resp.matches],
            "caveat": resp.caveat,
        }
    except Exception as exc:  # noqa: BLE001 — never crash the page
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Phase 1g: data latency report ────────────────────────────────────────────


from app.services.price_cache_service import PriceCacheService as _PriceCacheService
_price_cache_svc = _PriceCacheService(_av_client)


# Calendar-day thresholds applied to the freshest bar per source.
# `fresh` accommodates weekends — the price feed naturally skips
# Sat/Sun, so anything within 4 days is considered current. `stale`
# is the warning zone; beyond that is `missing` / `very_stale`.
_LATENCY_FRESH_DAYS = 4
_LATENCY_STALE_DAYS = 10


_LATENCY_SOURCES = [
    # (group_label, [symbols], description shown in UI)
    ("Benchmarks", ["SPY", "^GSPC"], "S&P 500 — ETF + index"),
    ("Sector ETFs", [
        "XLK", "XLC", "XLY", "XLP", "XLV",
        "XLF", "XLI", "XLE", "XLB", "XLRE", "XLU",
    ], "11 SPDR sector ETFs (oldest reported)"),
    ("Macro basket", ["TLT", "VXX", "UUP", "HYG", "GLD", "USO"],
     "Rates / vol / dollar / credit / gold / oil"),
    ("CN proxies", ["FXI", "KWEB", "MCHI"], "China ETFs (used for CN view)"),
]


def _classify_latency(latest: Optional[date], today: date) -> tuple[str, Optional[int]]:
    """Return (status, hours_stale). `hours_stale` measured at start of
    today (UTC), since price_bars are EOD — granularity is days, not
    minutes."""
    if latest is None:
        return "missing", None
    delta_days = (today - latest).days
    hours = delta_days * 24
    if delta_days <= _LATENCY_FRESH_DAYS:
        return "fresh", hours
    if delta_days <= _LATENCY_STALE_DAYS:
        return "stale", hours
    return "very_stale", hours


@router.get("/market/data-latency")
def get_data_latency(db: Session = Depends(get_db)) -> dict:
    """Per-data-source freshness report for the Market Pulse page.

    Surfaces "is the website showing today's data or yesterday's
    leftover?" The frontend `<DataFreshnessFooter />` consumes this
    and renders a one-line summary + hover-to-expand source list.

    For symbol *groups* (sector ETFs, macro basket, CN proxies) we
    report the OLDEST `latest_date` across the group — the worst-case
    is what matters for the freshness signal. Individual symbols
    inside the group are still listed under `members`.
    """
    today = date.today()
    sources_out: list[dict] = []

    for group_label, symbols, description in _LATENCY_SOURCES:
        members: list[dict] = []
        oldest: Optional[date] = None
        for sym in symbols:
            latest = _price_cache_svc.get_latest_date(db, sym)
            status, hours = _classify_latency(latest, today)
            members.append({
                "symbol": sym,
                "latest_date": latest.isoformat() if latest else None,
                "status": status,
                "hours_stale": hours,
            })
            if latest is not None and (oldest is None or latest < oldest):
                oldest = latest
            elif latest is None and oldest is None:
                # leave oldest as None — will reflect "missing"
                pass

        group_status, group_hours = _classify_latency(oldest, today)
        sources_out.append({
            "group": group_label,
            "description": description,
            "latest_date": oldest.isoformat() if oldest else None,
            "status": group_status,
            "hours_stale": group_hours,
            "members": members,
        })

    # Roll-up: the page's "snapshot freshness" is the oldest among group
    # latests (so a single stale source pulls the overall down).
    rollup_latest: Optional[date] = None
    for s in sources_out:
        if s["latest_date"]:
            ld = date.fromisoformat(s["latest_date"])
            if rollup_latest is None or ld < rollup_latest:
                rollup_latest = ld
    overall_status, overall_hours = _classify_latency(rollup_latest, today)

    return {
        "as_of": datetime.utcnow().isoformat(),
        "today": today.isoformat(),
        "overall_status": overall_status,
        "overall_hours_stale": overall_hours,
        "overall_latest_date": rollup_latest.isoformat() if rollup_latest else None,
        "sources": sources_out,
    }
