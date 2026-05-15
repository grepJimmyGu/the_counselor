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


async def _warmup_commodity_etfs() -> None:
    """Ensure GLD, USO, COPX, WEAT price bars are loaded (non-blocking)."""
    try:
        from datetime import date, timedelta
        from app.services.alpha_vantage import AlphaVantageClient
        from app.services.price_cache_service import PriceCacheService
        from app.db.session import SessionLocal

        etfs = ["GLD", "USO", "COPX", "WEAT"]
        required_from = date.today() - timedelta(days=365 * 11)
        client = AlphaVantageClient()
        svc = PriceCacheService(client)
        db = SessionLocal()
        try:
            for etf in etfs:
                try:
                    await svc.ensure_history(db, etf, required_from, force=False)
                    logger.info("Commodity ETF %s: price bars ensured", etf)
                except Exception as exc:
                    logger.warning("Commodity ETF warmup failed for %s: %s", etf, exc)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Commodity ETF warmup task failed: %s", exc)


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


_PREWARM_INTERVAL_DAYS = 7   # re-score all S&P 500 companies weekly


async def _run_prewarm_if_stale() -> None:
    """
    Run the S&P 500 health score prewarm if:
      - The table has fewer than 50 rows (first deploy / after reset), OR
      - The oldest computed_at in the table is > 7 days ago (weekly refresh)
    Logs but never raises — runs in a non-blocking background task.
    """
    try:
        from sqlalchemy import text
        from app.db.session import engine
        from datetime import datetime, timedelta

        with engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM symbol_health_scores")).scalar() or 0
            oldest = None
            if total > 0:
                oldest = conn.execute(
                    text("SELECT MIN(computed_at) FROM symbol_health_scores")
                ).scalar()

        stale_threshold = datetime.utcnow() - timedelta(days=_PREWARM_INTERVAL_DAYS)
        needs_run = total < 50 or (oldest is not None and oldest < stale_threshold)

        if not needs_run:
            logger.info(
                "Health score prewarm skipped — %d rows, oldest computed %s",
                total, oldest
            )
            return

        reason = "table empty/sparse" if total < 50 else f"scores older than {_PREWARM_INTERVAL_DAYS}d"
        logger.info("Health score prewarm starting (%s, %d existing rows)…", reason, total)
        from app.scripts.prewarm_health_scores import run_prewarm
        await run_prewarm()
    except Exception as exc:
        logger.warning("Health score prewarm failed: %s", exc)


async def _weekly_prewarm_loop() -> None:
    """
    Long-running task: fires the prewarm once at startup, then every 7 days.
    Keeps scores fresh without needing an external cron scheduler.
    """
    await _run_prewarm_if_stale()
    while True:
        await asyncio.sleep(_PREWARM_INTERVAL_DAYS * 24 * 3600)
        logger.info("Weekly health score prewarm triggered by background loop")
        await _run_prewarm_if_stale()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)  # creates all tables first
    run_startup_migrations(engine)          # then backfill/alter existing tables
    # Weekly health score prewarm loop — runs now then every 7 days
    asyncio.create_task(_weekly_prewarm_loop())
    # Ensure commodity ETF price bars are loaded (non-blocking)
    asyncio.create_task(_warmup_commodity_etfs())
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
