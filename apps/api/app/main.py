import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from app.api.routes.backtest import router as backtest_router
from app.api.routes.cn_company import router as cn_company_router
from app.api.routes.cn_market import router as cn_market_router
from app.api.routes.company_overview import router as company_overview_router
from app.api.routes.fundamental import router as fundamental_router
from app.api.routes.insights import router as insights_router
from app.api.routes.screener import router as screener_router
from app.api.routes.screen import router as screen_router
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
from app.api.routes.notifications import router as notifications_router
from app.api.routes.signal_primitives import router as signal_primitives_router
from app.api.routes.triage import router as triage_router  # PR-D — ops triage bundle
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


async def _warmup_gspc() -> None:
    """Refresh ^GSPC price data via FMP. Alpha Vantage doesn't serve index
    symbols; FMP's /historical-price-eod/full does. Uses the same format as
    the backfill script (backfill_gspc.py)."""
    from datetime import date, datetime, timedelta

    from app.db.session import SessionLocal as _Db
    from app.models.price_bar import PriceBar
    from app.services.fmp_client import FMPClient
    from sqlalchemy import select, delete

    try:
        fmp = FMPClient()
        today = date.today()
        from_date = (today - timedelta(days=30))  # date object, not string
        rows = await fmp.get_historical_eod("^GSPC", from_date.isoformat(), today.isoformat())
        if not rows:
            return

        db = _Db()
        try:
            # Delete recent bars so we can re-insert fresh ones (avoids dupes)
            db.execute(
                delete(PriceBar).where(
                    PriceBar.symbol == "^GSPC",
                    PriceBar.trading_date >= from_date,  # date object — Match
                )
            )
            for r in rows:
                try:
                    d = r["date"].split("T")[0] if "date" in r else str(r["date"])
                    db.add(PriceBar(
                        symbol="^GSPC",
                        trading_date=datetime.strptime(d, "%Y-%m-%d").date(),
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        adjusted_close=float(r["close"]),
                        volume=int(r.get("volume") or 0),
                        dividend_amount=0.0,
                        split_coefficient=1.0,
                        source="fmp_index",
                        fetched_at=datetime.utcnow(),
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("^GSPC warmup failed: %s", exc)


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
        # PR-C — health monitor: poll /health every minute, fire ops
        # email when pulse warmup flips to degraded. Job no-ops when
        # `OPS_HEALTH_ALERTS_ENABLED` is false (default), so registering
        # unconditionally is safe.
        from app.jobs.health_monitor_job import health_monitor_job
        scheduler.add_job(health_monitor_job, "cron", minute="*", id="health_monitor")
        # PRD-19 — daily signal recompute cron (populates signal state + live perf)
        from app.jobs.signal_cron import compute_all_signals
        scheduler.add_job(
            compute_all_signals, "cron", hour=22, minute=0,
            id="signal_recompute",
            max_instances=1,               # prevent overlap if prev run is slow
            misfire_grace_time=3600,       # fire within 1h of scheduled time
        )
        # PRD-19 Step 4b — morning brief digest cron. Fires ~9am ET so the
        # previous trading day's signal_cron tick (22:00 UTC ≈ 6pm ET) has
        # already written SignalEvents for the daily aggregation.
        from app.jobs.daily_digest_job import run_daily_digest_job
        scheduler.add_job(
            run_daily_digest_job, "cron", hour=13, minute=0,
            id="daily_digest",
            max_instances=1,
            misfire_grace_time=3600,
        )
        # PRD-23a — daily Market Screener snapshot warm. Fires at 23:00 UTC,
        # after the 22:00 signal_recompute tick has warmed today's price_bars,
        # so each symbol is a cache-hit frame read + local compute (no AV
        # storm). The job no-ops unless SCREENER_SNAPSHOT_ENABLED is set
        # (default off) so it adds zero load until PRD-23b ships the UI —
        # same convention as health_monitor. Sync wrapper around asyncio.run
        # (trap #21 safe); the warm path holds no shared asyncio primitives
        # (trap #22 safe).
        from app.jobs.signal_snapshot_job import warm_signal_snapshot_job
        scheduler.add_job(
            warm_signal_snapshot_job, "cron", hour=23, minute=0,
            id="signal_snapshot_warm",
            max_instances=1,
            misfire_grace_time=3600,
        )
        # PRD-23c — saved-screen tracker. Fires at 23:30 UTC, AFTER the 23:00
        # signal_snapshot_warm has refreshed today's snapshot, so each screen's
        # re-scan reads current values. Re-scans every subscribed screen, diffs
        # its basket, and notifies on new entrants (transition-only). No-ops
        # unless SCREENER_SNAPSHOT_ENABLED is set (same gate as the warm).
        # Plain def on APScheduler's threadpool — mirrors compute_all_signals'
        # dispatch path (traps #21/#22 safe; holds no shared asyncio primitives).
        from app.jobs.saved_screen_cron import monitor_saved_screens
        scheduler.add_job(
            monitor_saved_screens, "cron", hour=23, minute=30,
            id="saved_screen_monitor",
            max_instances=1,
            misfire_grace_time=3600,
        )
        # PRD-16c — intraday position monitor. Every 5 minutes during US
        # market hours (M-F, 14:00-20:55 UTC ≈ 10am-4:55pm ET; one hour
        # ahead of NYSE open to cover any pre-market positions). The job
        # itself is cheap when there's nothing to do: it iterates
        # SavedStrategy rows, skips any without bar_resolution != 'daily'
        # or without exit_ladder, and only fetches bars for open
        # PositionState rows. Most ticks will return strategies_checked=0.
        # The function is a sync wrapper around asyncio.run(...) (trap #21
        # safe). Trap #22 is honored — `IntradayBarService` holds no
        # asyncio primitives so it's safe to use from the cron loop.
        from app.jobs.intraday_jobs import monitor_active_positions
        scheduler.add_job(
            monitor_active_positions, "cron",
            day_of_week="mon-fri", hour="14-20", minute="*/5",
            id="intraday_monitor",
            max_instances=1,
            misfire_grace_time=120,
        )
        scheduler.start()
    except Exception as exc:
        logger.warning("APScheduler failed to start: %s", exc)


def _db_init(engine):
    """Run create_all + startup migrations in a background thread.
    Decoupled from the lifespan so Postgres autovacuum/recovery doesn't
    block the Railway deploy healthcheck. Tables from prior deploys are
    already present — this is a best-effort idempotent safety net."""
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
        run_startup_migrations(engine)
        logger.info("_db_init: create_all + migrations complete")
    except Exception as exc:
        logger.warning("_db_init: %s — tables may not be current", exc)


# Module-level health state for the recurring pulse warmup. Updated by
# `_warmup_market_pulse_loop` on every tick (success + failure paths). Read by
# `/health` to surface warmup freshness as a programmatic signal.
#
# Why this exists: the 2026-06-07 outage failed every warmup tick for 28+ minutes
# while only emitting `logger.exception` lines that nobody was watching. By the
# time Jimmy noticed (via a broken page), 9 user requests were already queued on
# wedged locks. Surfacing the same failure on `/health` means a one-minute scrape
# would have flipped to "degraded" within 4 minutes of the first failed tick.
#
# Schema:
#   last_success_at: datetime | None — UTC timestamp of the most recent successful tick
#   consecutive_failures: int — number of consecutive failures since the last success
#   last_error: str | None — single-line summary of the most recent exception
from datetime import datetime as _datetime, timezone as _timezone
from typing import Any as _Any

_pulse_warmup_state: dict[str, _Any] = {
    "last_success_at": None,
    "consecutive_failures": 0,
    "last_error": None,
}


def _record_pulse_warmup_success() -> None:
    _pulse_warmup_state["last_success_at"] = _datetime.now(_timezone.utc)
    _pulse_warmup_state["consecutive_failures"] = 0
    _pulse_warmup_state["last_error"] = None


def _record_pulse_warmup_failure(exc: BaseException) -> None:
    _pulse_warmup_state["consecutive_failures"] += 1
    # Single-line summary — full traceback is in the log via `logger.exception`.
    _pulse_warmup_state["last_error"] = f"{type(exc).__name__}: {exc}"[:500]


async def _warmup_market_pulse_loop() -> None:
    """Recurring background refresh of the Market Pulse base `_CACHE` for
    US + CN. Calls `get_pulse` (NOT `get_live_pulse`) — see trap #22.

    The expensive part of the cold path is the base computation itself
    (~30–50s of N+1 `_load_bars` queries against the SP500 / CSI universes).
    Pre-warming `_CACHE` (60-min TTL) keeps the DB cost paid in the
    background; user requests still trigger their own FMP live overlay
    on the main event loop where `live_quote_service`'s per-symbol
    asyncio.Locks belong.

    **Why not `get_live_pulse`?** (See trap #22 for the full post-mortem.)
    The warmup runs in a worker thread with its own event loop (via
    `_run_async_in_thread`, per trap #21). `live_quote_service` is a
    module-level singleton that lazily creates per-symbol `asyncio.Lock`
    objects on first touch — those locks bind to whichever event loop
    creates them. Calling `get_live_pulse` from the warmup's thread loop
    binds the locks to that thread's loop; subsequent user requests on
    the main loop then raise `RuntimeError: ... is bound to a different
    event loop`. Worse, locks the warmup managed to acquire-but-never-
    release stay wedged forever, queuing real user requests as waiters
    until they time out (PR #138 → 2026-06-07 outage).

    The fix: stop touching `live_quote_service` from this thread. Users
    fire the overlay themselves on cold `_LIVE_CACHE` (~15-20s cost on
    cold; warm path stays ~2s for 5 minutes after).

    This is `async def` and opens `SessionLocal()` with sync DB inside,
    so it MUST run via `_run_async_in_thread` (trap #21). Each iteration
    is wrapped in try/except with `logger.exception` (trap #20) so a
    single transient failure doesn't kill the recurring loop.
    """
    from app.db.session import SessionLocal
    from app.services.market_pulse_service import MarketPulseService

    # Instance is cheap — the caches (_CACHE, _LIVE_CACHE, _NARRATIVE_CACHE)
    # are module-level dicts shared across all MarketPulseService() instances,
    # so this warmup populates the same cache the route reads from.
    svc = MarketPulseService()

    while True:
        try:
            with SessionLocal() as db:
                # Base computation only — populates _CACHE (60-min TTL).
                # MUST NOT call get_live_pulse here (trap #22, see docstring).
                svc.get_pulse("US", db)
                svc.get_pulse("CN", db)
            _record_pulse_warmup_success()  # surfaced via /health
            logger.info("Market Pulse warmup tick complete (base, US + CN)")
        except Exception as exc:
            _record_pulse_warmup_failure(exc)  # surfaced via /health
            logger.exception("Market Pulse warmup tick failed")  # trap #20
        # 4 min — keeps base _CACHE warm. _LIVE_CACHE still uses 5-min TTL,
        # populated lazily by user requests when they fire the FMP overlay.
        await asyncio.sleep(240)


def _run_async_in_thread(coro) -> None:
    """Run an async coroutine inside a worker thread with its own event loop.

    Used to schedule lifespan warmups (`_warmup_*`, `_seed_*`, `_invalidate_*`)
    without blocking the main asyncio event loop. The warmups are declared
    `async def` but call SYNCHRONOUS `SessionLocal()` + `db.execute(...)`
    internally — without this bridge they block the main loop, preventing
    `/health` from responding and failing the Railway healthcheck under any
    autovacuum stress.

    Each warmup gets its own thread + fresh event loop (created by
    `asyncio.run`). The thread's loop can `await` async client calls AND
    block on sync DB work; neither path touches the main loop that serves
    user requests.

    2026-06-04 outage post-mortem: 14 consecutive Railway deploys failed
    because the warmups blocked `/health` while autovacuum ran on a
    freshly-grown `price_bars` table. This bridge makes the failure mode
    structurally impossible regardless of DB latency.

    Failures use `logger.exception` per trap #20 (warmup failures silenced
    by `logger.warning` lose the traceback).
    """
    try:
        asyncio.run(coro)
    except Exception:
        logger.exception("background warmup failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fire DB init in background. Postgres autovacuum can hold table locks
    # for minutes — rather than block the healthcheck, let the app start
    # immediately and let DB init complete whenever the DB is ready.
    # Tables already exist from prior deploys; this is idempotent.
    asyncio.create_task(asyncio.to_thread(_db_init, engine))

    # Surface the gating flag on every deploy.
    _s = get_settings()
    logger.info(
        "feature_flags gating_enabled=%s app_env=%s",
        _s.gating_enabled, _s.app_env,
    )
    _start_scheduler()
    # Warmups run on dedicated threads (see `_run_async_in_thread` above) so
    # their internal SYNCHRONOUS DB calls can't block the main event loop —
    # the failure mode of the 2026-06-04 outage. Each warmup gets its own
    # fresh asyncio event loop inside its thread; the main loop stays free
    # for `/health` and user requests.
    asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_market_etfs()))
    asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_gspc()))
    asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_commodity_spots()))
    asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _seed_and_warmup_stock_universe()))
    asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _invalidate_stale_bi_caches()))
    # Recurring pulse pre-warm — keeps `_LIVE_CACHE` populated so users
    # never pay the 80-second cold-cache cost. Runs every 4 min on its
    # own thread + event loop (trap #21 — sync DB inside the service).
    asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_market_pulse_loop()))
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
app.include_router(cn_company_router)
app.include_router(cn_market_router)
app.include_router(commodities_router)
app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(fundamental_router)
app.include_router(screener_router)
app.include_router(screen_router)
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

# PRD-19 — notification endpoints (always mounted)
app.include_router(notifications_router)

# PRD-16a — signal primitive catalog endpoint (always mounted; the catalog
# is content, not user data, and the same for every visitor).
app.include_router(signal_primitives_router)

# PR-D — triage context bundle. Always mounted (the route gates on the
# token at request time + 403's if no token is configured). Mounting
# unconditionally keeps the URL stable across redeploys so the link in
# the PR-C alert email always resolves.
app.include_router(triage_router)


# Thresholds for /health to flip "healthy" → "degraded" on the pulse warmup.
# Both must hold to stay healthy:
#   - Most recent successful tick within `_PULSE_WARMUP_MAX_AGE_SECONDS`
#   - Fewer than `_PULSE_WARMUP_MAX_FAILURES` consecutive failures
# Picked so a single transient blip doesn't flip the signal but the
# 2026-06-07 pattern (every tick fails) flips within ~12 minutes.
_PULSE_WARMUP_MAX_AGE_SECONDS = 600  # 10 min — 2.5× the 4-min tick cadence
_PULSE_WARMUP_MAX_FAILURES = 3       # 3 consecutive ticks = ~12 min of failure


def compute_health_state() -> dict[str, _Any]:
    """Compute the /health response payload from the current pulse
    warmup state. Extracted from the `/health` handler so the email
    alerter cron (`health_monitor_job`, PR-C) can read the same payload
    without an HTTP round-trip.
    """
    last_success = _pulse_warmup_state["last_success_at"]
    consecutive_failures = _pulse_warmup_state["consecutive_failures"]

    if last_success is None:
        age_seconds: Optional[int] = None
    else:
        age_seconds = int((_datetime.now(_timezone.utc) - last_success).total_seconds())

    pulse_warmup_healthy = (
        age_seconds is not None
        and age_seconds <= _PULSE_WARMUP_MAX_AGE_SECONDS
        and consecutive_failures < _PULSE_WARMUP_MAX_FAILURES
    )

    overall_status = "ok" if pulse_warmup_healthy else "degraded"

    return {
        "status": overall_status,
        "pulse_warmup": {
            "healthy": pulse_warmup_healthy,
            "last_success_at": last_success.isoformat() if last_success else None,
            "age_seconds": age_seconds,
            "consecutive_failures": consecutive_failures,
            "last_error": _pulse_warmup_state["last_error"],
            "thresholds": {
                "max_age_seconds": _PULSE_WARMUP_MAX_AGE_SECONDS,
                "max_consecutive_failures": _PULSE_WARMUP_MAX_FAILURES,
            },
        },
    }


@app.get("/health")
async def health() -> dict[str, _Any]:
    """Returns service health + the pulse warmup freshness signal.

    Backwards compatible: the top-level `status` field still exists and is
    `"ok"` when healthy (was a string before; preserves that for Railway's
    healthcheck which only inspects the response code). Anything degraded
    surfaces in `pulse_warmup` for external scrapers / the email alerter.
    """
    return compute_health_state()
