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
from app.api.routes.me import router as me_router
from app.api.routes.billing import router as billing_router
from app.api.routes.stripe_webhook import router as stripe_webhook_router
from app.api.routes.community import router as community_router
from app.api.routes.sentiment import router as sentiment_router
from app.api.routes.strategy_storage import router as strategy_storage_router
from app.api.routes.strategy import router as strategy_router
from app.api.routes.anonymous import router as anonymous_router
from app.api.routes.asset_behavior import router as asset_behavior_router  # Module 2
from app.api.routes.chat import (
    anonymous_router as anonymous_chat_router,
    router as chat_router,
)
from app.api.routes.live_quotes import router as live_quotes_router
from app.api.routes.community_publish import (
    attribution_router,
    router as community_publish_router,
)
from app.api.routes.email import prefs_router as email_prefs_router, unsub_router as email_unsub_router
from app.api.routes.saved_strategies import router as saved_strategies_router
from app.api.routes.signals import router as signals_router
from app.api.routes.portfolio import router as portfolio_router  # PRD-13b — Portfolio Mode
from app.core.config import get_settings
from app.db.migrations import run_startup_migrations
from app.db.session import Base, engine
from app.models import BacktestRecord, DataFetchLog, PriceBar, SymbolCache, User, Plan, MonthlyUsage, StripeEvent  # noqa: F401


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
        # Macro — History Rhymes basket (SPY, TLT, SHY, UUP, HYG, GLD)
        "SPY", "SHY", "VXX", "UUP", "TLT", "HYG",
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



def _start_scheduler() -> None:
    """Daily GC: purge monthly_usage rows older than 13 months."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import timedelta
        from app.db.session import SessionLocal
        from app.models.user import MonthlyUsage as _MU
        import datetime as _dt

        def _cleanup_old_usage() -> None:
            cutoff = _dt.date.today() - timedelta(days=400)
            db = SessionLocal()
            try:
                db.query(_MU).filter(_MU.period_start < cutoff).delete()
                db.commit()
            finally:
                db.close()

        scheduler = BackgroundScheduler()
        scheduler.add_job(_cleanup_old_usage, "cron", hour=4, minute=0)
        # Stage 2: billing jobs
        from app.jobs.billing_jobs import expire_trials_job, dunning_expiry_job
        scheduler.add_job(expire_trials_job, "cron", minute=15)
        scheduler.add_job(dunning_expiry_job, "cron", minute=30)
        # QA tripwires — daily schema-drift check (see app/jobs/qa_jobs.py).
        # Violations log `INVARIANT_BROKEN: schema_drift ...` to Railway,
        # grep-able alongside the existing `DEFERRED_TRIGGER:` lines.
        from app.jobs.qa_jobs import (
            audit_chat_responses_job,
            audit_chat_tool_errors_job,
            chat_guardrails_digest_job,
            check_schema_drift_job,
        )
        scheduler.add_job(check_schema_drift_job, "cron", hour=3, minute=0)
        # Ticket #9 — chat guardrails. Auditor samples 50 convs nightly;
        # digest aggregates the week's refusals + uncited events on Sunday.
        scheduler.add_job(audit_chat_responses_job, "cron", hour=2, minute=0)
        scheduler.add_job(chat_guardrails_digest_job, "cron", day_of_week="sun", hour=9, minute=0)
        # Chat-tool error auditor (2026-05-23) — sibling to the LLM-judge
        # auditor above. Scans chat_messages.tool_results for the dispatch
        # loop's `{"error": "Tool ... failed: ..."}` envelopes that would
        # otherwise only surface as LLM-friendly apology copy to the user.
        # Offset to 02:30 UTC so it doesn't race the 02:00 LLM auditor for
        # DB connections.
        scheduler.add_job(audit_chat_tool_errors_job, "cron", hour=2, minute=30)
        scheduler.start()
    except Exception as exc:
        logger.warning("APScheduler failed to start: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)  # creates all tables first
    run_startup_migrations(engine)          # then backfill/alter existing tables
    # Surface the gating flag on every deploy. After the 2026-05-20 QA audit
    # found that GATING_ENABLED defaulted to False and no Stage 3 cap was
    # firing in prod, we want a single grep-able log line to confirm the env
    # var picked up on each rollout.
    _s = get_settings()
    logger.info(
        "feature_flags gating_enabled=%s app_env=%s",
        _s.gating_enabled, _s.app_env,
    )
    _start_scheduler()
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
    # Vercel auto-generates a fresh preview URL per PR — the format is
    # `the-counselor-web-git-<branch-slug>-grepjimmygus-projects.vercel.app`
    # or `the-counselor-web-<hash>-grepjimmygus-projects.vercel.app` for
    # individual deploys. A static allowed_origins list can't keep up with
    # PR churn; this regex covers every preview of this project without
    # admitting other Vercel apps. Added 2026-05-21 after PR #41's Market
    # Pulse preview rendered with empty data because Railway rejected the
    # CORS preflight.
    allow_origin_regex=r"https://the-counselor-web-.*\.vercel\.app",
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
app.include_router(me_router)
app.include_router(billing_router)
app.include_router(stripe_webhook_router)
app.include_router(community_router)
app.include_router(sentiment_router)
app.include_router(anonymous_router)  # Stage 1a
app.include_router(asset_behavior_router)  # Module 2 — Asset Behavior Fingerprint
app.include_router(chat_router)  # Stage 7 ticket #5 — authed chat + SSE
app.include_router(anonymous_chat_router)  # Stage 7 ticket #6 — anonymous chat + SSE
app.include_router(live_quotes_router)  # 2026-05-21 — live quote cache
app.include_router(saved_strategies_router)  # Stage 1a
app.include_router(community_publish_router)  # Stage 4a
app.include_router(attribution_router)  # Stage 4a
app.include_router(email_prefs_router)  # Stage 6a
app.include_router(email_unsub_router)  # Stage 6a
app.include_router(portfolio_router)  # PRD-13b — Portfolio Mode
# Stage 8 v0 — signals & alerts. Gated on settings.signal_alerts_enabled so the
# endpoints remain absent (→ 404) in production until lawyer review of the
# disclaimer copy is complete (build_specs/research_execution_v0_signals_and_alerts.md §11).
if get_settings().signal_alerts_enabled:
    app.include_router(signals_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
