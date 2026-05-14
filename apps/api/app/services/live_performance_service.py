from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.strategy import StrategyJSON

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 24
_MIN_TRACKING_DAYS = 1  # need at least 1 trading day of data


@dataclass
class LivePerformance:
    slug: str
    published_at: date
    total_return: Optional[float]          # e.g. 0.042 = +4.2 %
    days_tracked: int
    current_signal: Optional[str]          # "long" | "cash" | "mixed"
    last_price_date: Optional[date]
    equity_curve: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    computed_at: Optional[datetime] = None


def get_cached_performance(slug: str, db: Session) -> LivePerformance | None:
    """
    Return cached live performance only — never triggers a new computation.
    Used by the public listing so the endpoint stays fast.
    Returns None if no valid cache exists yet.
    """
    return _load_cache(slug, db, datetime.utcnow())


async def get_live_performance(
    slug: str,
    published_at: date,
    strategy_json: dict,
    db: Session,
    force_refresh: bool = False,
) -> LivePerformance:
    """
    Return the strategy's actual return since its publish date.
    Uses a 24-hour DB cache so the backtester isn't re-run on every request.
    """
    now = datetime.utcnow()

    if not force_refresh:
        cached = _load_cache(slug, db, now)
        if cached:
            return cached

    result = await _compute(slug, published_at, strategy_json, db, now)
    _save_cache(result, db, now)
    return result


async def _compute(
    slug: str,
    published_at: date,
    strategy_json_dict: dict,
    db: Session,
    now: datetime,
) -> LivePerformance:
    today = now.date()

    # Coerce published_at to date — PostgreSQL may return datetime or date objects
    if isinstance(published_at, datetime):
        published_at = published_at.date()
    elif isinstance(published_at, str):
        published_at = date.fromisoformat(published_at[:10])

    if today <= published_at:
        return LivePerformance(
            slug=slug,
            published_at=published_at,
            total_return=None,
            days_tracked=0,
            current_signal=None,
            last_price_date=None,
            error="Published today — no trading days elapsed yet.",
            computed_at=now,
        )

    try:
        # Patch start/end dates onto the saved strategy_json
        patched = dict(strategy_json_dict)
        patched["start_date"] = published_at.isoformat()
        patched["end_date"] = today.isoformat()
        strategy = StrategyJSON.model_validate(patched)
    except Exception as exc:
        return LivePerformance(
            slug=slug,
            published_at=published_at,
            total_return=None,
            days_tracked=0,
            current_signal=None,
            last_price_date=None,
            error=f"Strategy parse error: {exc}",
            computed_at=now,
        )

    try:
        # Ensure price data is up to date for all tickers in the strategy
        # (mirrors what run_backtest does — without this, stale/missing tickers silently fail)
        from app.services.alpha_vantage import AlphaVantageClient
        from app.services.price_cache_service import PriceCacheService
        cache_svc = PriceCacheService(AlphaVantageClient())
        all_symbols = list(strategy.universe) + [strategy.benchmark]
        for symbol in all_symbols:
            try:
                await cache_svc.ensure_history(db, symbol, published_at)
            except Exception:
                pass  # best-effort; engine will surface missing data errors

        from app.services.backtester.engine import BacktestEngine
        engine = BacktestEngine()
        result = await engine.run(db, strategy)
        m = result.metrics
        # p.date is a date object — convert to ISO string for JSON storage
        curve = [{"date": p.date.isoformat(), "value": p.value} for p in result.equity_curve]

        # Derive current signal from last position in equity curve
        current_signal = _infer_signal(result)

        # Count trading days with data
        days_tracked = len(result.equity_curve)
        last_price_date = (
            result.equity_curve[-1].date  # already a date object from Pydantic
            if result.equity_curve else None
        )

        return LivePerformance(
            slug=slug,
            published_at=published_at,
            total_return=m.total_return,
            days_tracked=days_tracked,
            current_signal=current_signal,
            last_price_date=last_price_date,
            equity_curve=curve,
            computed_at=now,
        )
    except Exception as exc:
        logger.warning("Live performance backtest failed for %s: %s", slug, exc)
        return LivePerformance(
            slug=slug,
            published_at=published_at,
            total_return=None,
            days_tracked=0,
            current_signal=None,
            last_price_date=None,
            error=str(exc)[:200],
            computed_at=now,
        )


def _infer_signal(result) -> str:
    """Best-effort: check whether the last trade log entry was a buy or sell."""
    try:
        log = result.trade_log
        if not log:
            return "unknown"
        last = log[-1]
        action = getattr(last, "action", None) or (last.get("action") if isinstance(last, dict) else None)
        if action and "buy" in str(action).lower():
            return "long"
        if action and "sell" in str(action).lower():
            return "cash"
    except Exception:
        pass
    return "unknown"


# ── DB cache helpers ──────────────────────────────────────────────────────────

def _load_cache(slug: str, db: Session, now: datetime) -> Optional[LivePerformance]:
    row = db.execute(
        text(
            "SELECT slug, published_at, computed_at, total_return, days_tracked,"
            " current_signal, last_price_date, equity_curve, error"
            " FROM strategy_live_performance"
            " WHERE slug = :slug AND expires_at > :now"
        ),
        {"slug": slug, "now": now},
    ).fetchone()
    if not row:
        return None
    r = row._mapping  # type: ignore[attr-defined]

    def _to_date(v):
        if v is None:
            return None
        if isinstance(v, (date, datetime)):
            return v if isinstance(v, date) and not isinstance(v, datetime) else v.date()
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:
            return None

    curve = r["equity_curve"]
    if isinstance(curve, str):
        try:
            curve = json.loads(curve)
        except Exception:
            curve = []

    return LivePerformance(
        slug=r["slug"],
        published_at=_to_date(r["published_at"]) or date.today(),
        total_return=r["total_return"],
        days_tracked=r["days_tracked"] or 0,
        current_signal=r["current_signal"],
        last_price_date=_to_date(r["last_price_date"]),
        equity_curve=curve or [],
        error=r.get("error"),
        computed_at=r["computed_at"],
    )


def _save_cache(perf: LivePerformance, db: Session, now: datetime) -> None:
    expires_at = now + timedelta(hours=_CACHE_TTL_HOURS)
    try:
        db.execute(
            text(
                "INSERT INTO strategy_live_performance"
                " (slug, published_at, computed_at, expires_at, total_return,"
                "  days_tracked, current_signal, last_price_date, equity_curve, error)"
                " VALUES"
                " (:slug, :pub, :now, :exp, :ret,"
                "  :days, :signal, :lpd, :curve, :err)"
                " ON CONFLICT (slug) DO UPDATE SET"
                "  computed_at=:now, expires_at=:exp, total_return=:ret,"
                "  days_tracked=:days, current_signal=:signal,"
                "  last_price_date=:lpd, equity_curve=:curve, error=:err"
            ),
            {
                "slug": perf.slug,
                "pub": perf.published_at,
                "now": now,
                "exp": expires_at,
                "ret": perf.total_return,
                "days": perf.days_tracked,
                "signal": perf.current_signal,
                "lpd": perf.last_price_date,
                "curve": json.dumps(perf.equity_curve),
                "err": perf.error,
            },
        )
        db.commit()
    except Exception as exc:
        logger.warning("Failed to cache live performance for %s: %s", perf.slug, exc)
        db.rollback()
