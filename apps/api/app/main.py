import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from app.api.routes.backtest import router as backtest_router
from app.api.routes.company_overview import router as company_overview_router
from app.api.routes.fundamental import router as fundamental_router
from app.api.routes.insights import router as insights_router
from app.api.routes.screener import router as screener_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.qa import router as qa_router
from app.api.routes.robustness import router as robustness_router
from app.api.routes.uiux import router as uiux_router
from app.api.routes.admin import router as admin_router
from app.api.routes.commodities import router as commodities_router
from app.api.routes.auth import router as auth_router
from app.api.routes.community import router as community_router
from app.api.routes.sentiment import router as sentiment_router
from app.api.routes.strategy_storage import router as strategy_storage_router
from app.api.routes.strategy import router as strategy_router
from app.core.config import get_settings
from app.db.migrations import run_startup_migrations
from app.db.session import Base, engine
from app.models import BacktestRecord, DataFetchLog, PriceBar, SymbolCache  # noqa: F401


async def _warmup_market_etfs() -> None:
    """
    Ensure price bars are loaded for all Market Pulse ETFs:
      - US indices (SPY, QQQ, IWM, DIA)
      - US sectors (XLK, XLF, XLE, XLY, XLV, XLI, XLP, XLU, XLB, XLRE, XLC)
      - CN proxies (FXI, KWEB, MCHI)
      - Macro (VXX, UUP, TLT, HYG)
      - Commodities (GLD, USO, COPX, WEAT — already loaded if present)
    Runs on startup, non-blocking, skips symbols already fresh.
    """
    from datetime import date, timedelta
    from app.services.alpha_vantage import AlphaVantageClient
    from app.services.price_cache_service import PriceCacheService
    from app.db.session import SessionLocal

    ALL_MARKET_ETFS = [
        # US indices
        "SPY", "QQQ", "IWM", "DIA",
        # US sectors (SPDR)
        "XLK", "XLF", "XLE", "XLY", "XLV", "XLI", "XLP", "XLU", "XLB", "XLRE", "XLC",
        # CN proxies (US-listed) — must match CN_SECTORS + CN_FEATURED_ETFS in market_pulse_service
        "FXI", "KWEB", "MCHI", "CQQQ", "CHIE", "FLCH", "CNYA",
        # Macro
        "VXX", "UUP", "TLT", "HYG",
        # Commodities
        "GLD", "USO", "COPX", "WEAT",
    ]

    try:
        required_from = date.today() - timedelta(days=365 * 3)  # 3yr for CMF + RS
        client = AlphaVantageClient()
        svc = PriceCacheService(client)
        db = SessionLocal()
        loaded = 0
        try:
            for sym in ALL_MARKET_ETFS:
                try:
                    await svc.ensure_history(db, sym, required_from, force=False)
                    loaded += 1
                except Exception as exc:
                    logger.warning("Market ETF warmup failed for %s: %s", sym, exc)
        finally:
            db.close()
        logger.info("Market ETF warmup complete: %d/%d symbols loaded", loaded, len(ALL_MARKET_ETFS))
    except Exception as exc:
        logger.warning("Market ETF warmup task failed: %s", exc)


async def _warmup_commodity_spots() -> None:
    """
    Fetch actual commodity spot prices from Alpha Vantage's commodity endpoints
    (function=WTI, COPPER, WHEAT) and store in price_bars.
    Gold spot is derived from GLD price_bars (1 GLD ≈ 0.0930 oz).

    Runs after the ETF warmup so GLD bars are available for gold derivation.
    Monthly data on free AV plan is sufficient for spot price display.
    """
    import asyncio
    from app.services.alpha_vantage import AlphaVantageClient
    from app.services.commodity_spot_service import CommoditySpotService
    from app.db.session import SessionLocal

    try:
        client = AlphaVantageClient()
        svc = CommoditySpotService()
        db = SessionLocal()
        try:
            # Fetch WTI, Copper, Wheat spot from AV commodity API
            for commodity in ["WTI", "COPPER", "WHEAT"]:
                try:
                    ok = await svc.warmup(commodity, client, db)
                    if not ok:
                        logger.warning("Commodity spot warmup skipped: %s", commodity)
                except Exception as exc:
                    logger.warning("Commodity spot warmup error for %s: %s", commodity, exc)
                await asyncio.sleep(0.5)  # gentle rate-limit spacing

            # Gold spot derived from GLD (no AV call needed)
            try:
                svc.warmup_gold_from_gld(db)
            except Exception as exc:
                logger.warning("Gold spot from GLD failed: %s", exc)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Commodity spot warmup task failed: %s", exc)


_TOP_US_STOCKS = [
    ("AAPL",  "Apple Inc",                  "Technology"),
    ("MSFT",  "Microsoft Corp",             "Technology"),
    ("NVDA",  "NVIDIA Corp",                "Technology"),
    ("GOOGL", "Alphabet Inc",               "Communication Services"),
    ("AMZN",  "Amazon.com Inc",             "Consumer Discretionary"),
    ("META",  "Meta Platforms Inc",         "Technology"),
    ("TSLA",  "Tesla Inc",                  "Consumer Discretionary"),
    ("LLY",   "Eli Lilly and Co",           "Healthcare"),
    ("JPM",   "JPMorgan Chase & Co",        "Financials"),
    ("AVGO",  "Broadcom Inc",               "Technology"),
    ("UNH",   "UnitedHealth Group",         "Healthcare"),
    ("V",     "Visa Inc",                   "Financials"),
    ("WMT",   "Walmart Inc",                "Consumer Staples"),
    ("XOM",   "Exxon Mobil Corp",           "Energy"),
    ("MA",    "Mastercard Inc",             "Financials"),
    ("ORCL",  "Oracle Corp",               "Technology"),
    ("COST",  "Costco Wholesale Corp",      "Consumer Staples"),
    ("HD",    "Home Depot Inc",             "Consumer Discretionary"),
    ("NFLX",  "Netflix Inc",               "Communication Services"),
    ("AMD",   "Advanced Micro Devices",     "Technology"),
    ("PG",    "Procter & Gamble Co",        "Consumer Staples"),
    ("BAC",   "Bank of America Corp",       "Financials"),
    ("JNJ",   "Johnson & Johnson",          "Healthcare"),
    ("ABBV",  "AbbVie Inc",                 "Healthcare"),
    ("CRM",   "Salesforce Inc",             "Technology"),
    ("CVX",   "Chevron Corp",               "Energy"),
    ("CSCO",  "Cisco Systems Inc",          "Technology"),
    ("MCD",   "McDonald's Corp",            "Consumer Discretionary"),
    ("INTU",  "Intuit Inc",                 "Technology"),
    ("CAT",   "Caterpillar Inc",            "Industrials"),
]


async def _seed_and_warmup_stock_universe() -> None:
    """
    Seed top US stocks into the symbols table (name + sector only, no hardcoded
    market cap) and warmup their price bars so the Market Pulse Stocks tab is
    populated on a fresh deployment.  Skips symbols already present in the DB.
    Rate-limit failures are logged and skipped — data builds up over multiple days.
    """
    from datetime import date, datetime, timedelta
    from app.models.symbol import SymbolCache
    from app.services.alpha_vantage import AlphaVantageClient
    from app.services.price_cache_service import PriceCacheService
    from app.db.session import SessionLocal

    try:
        required_from = date.today() - timedelta(days=365 * 3)
        client = AlphaVantageClient()
        svc = PriceCacheService(client)
        db = SessionLocal()
        loaded = 0
        now = datetime.utcnow()
        try:
            for sym, name, sector in _TOP_US_STOCKS:
                # Insert into symbols table if not already present
                try:
                    if db.get(SymbolCache, sym) is None:
                        db.add(SymbolCache(
                            symbol=sym,
                            name=name,
                            sector=sector,
                            instrument_type="Equity",
                            is_active=True,
                            last_seen_at=now,
                            created_at=now,
                            updated_at=now,
                        ))
                        db.commit()
                except Exception:
                    db.rollback()

                # Warmup price bars (skips if already fresh)
                try:
                    await svc.ensure_history(db, sym, required_from, force=False)
                    loaded += 1
                except Exception as exc:
                    logger.warning("Stock universe warmup failed for %s: %s", sym, exc)
        finally:
            db.close()
        logger.info(
            "Stock universe warmup complete: %d/%d symbols loaded", loaded, len(_TOP_US_STOCKS)
        )
    except Exception as exc:
        logger.warning("Stock universe warmup task failed: %s", exc)


async def _invalidate_stale_bi_caches() -> None:
    """
    Delete BI cache rows that predate the upstream_suppliers/downstream_customers fields
    (those rows will have NULL for these columns). Forces re-extraction on next page load.
    """
    try:
        from sqlalchemy import text
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            result = db.execute(text(
                "DELETE FROM company_business_intelligence "
                "WHERE upstream_suppliers IS NULL OR upstream_suppliers = '[]'"
            ))
            db.commit()
            if result.rowcount > 0:
                logger.info(
                    "Invalidated %d stale BI cache rows (missing supply chain fields)",
                    result.rowcount,
                )
        finally:
            db.close()
    except Exception as exc:
        logger.warning("BI cache invalidation failed: %s", exc)



@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)  # creates all tables first
    run_startup_migrations(engine)          # then backfill/alter existing tables
    # Ensure all Market Pulse ETF price bars are loaded (non-blocking)
    asyncio.create_task(_warmup_market_etfs())
    # Fetch actual commodity spot prices (WTI $/bbl, gold $/oz, copper $/lb, wheat ¢/bu)
    asyncio.create_task(_warmup_commodity_spots())
    # Seed top US stocks into symbols table and warmup their price bars
    asyncio.create_task(_seed_and_warmup_stock_universe())
    # Invalidate stale BI caches (symbols with empty supply chain fields) in background
    asyncio.create_task(_invalidate_stale_bi_caches())
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(commodities_router)
app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(fundamental_router)
app.include_router(screener_router)
app.include_router(company_overview_router)
app.include_router(insights_router)
app.include_router(market_data_router)
app.include_router(robustness_router)
app.include_router(qa_router)
app.include_router(uiux_router)
app.include_router(strategy_storage_router)
app.include_router(auth_router)
app.include_router(community_router)
app.include_router(sentiment_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
