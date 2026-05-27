"""Portfolio Mode endpoints — PRD-13b.

Exposes:
  POST /api/portfolio/diagnose   — given a list of holdings, return a
                                    PortfolioDiagnosis + ranked overlay
                                    recommendations.

Caching: in-process LRU keyed by a sha256 of the sorted (ticker, weight,
shares) tuple. 60-minute TTL. Identical re-runs of the same portfolio
hit the cache instantly; first-runs hit fundamentals + price history
(~2-5s for a 10-holding book).

Rate-limit: per-tier hourly cap (Scout: 5, Strategist: 50, Quant:
effectively unlimited). Raises a 402 with code='portfolio_diagnose_rate_limit'
when exceeded.

The endpoint takes `Depends(require_entitlement(needs_run_quota=False))`
so it goes through the standard gating chain (auth + entitlements
resolution) without consuming the 5-runs-per-week backtest budget.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import _LEGACY_USER_ID
from app.api.deps_entitlement import require_entitlement
from app.api.entitlement_errors import upgrade_error
from app.db.session import SessionLocal, get_db
from app.schemas.portfolio import (
    DiagnoseRequest,
    DiagnoseResponse,
    Holding,
)
from app.services.entitlements import (
    PORTFOLIO_DIAGNOSE_HOURLY_CAPS,
    get_portfolio_diagnose_runs_used,
    increment_portfolio_diagnose_run,
)
from app.services.portfolio_diagnosis_service import PortfolioDiagnosisService

logger = logging.getLogger("livermore.portfolio")

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_service = PortfolioDiagnosisService()


# ── In-process cache (Redis fallback per PRD-13b §4) ─────────────────────────

_CACHE_TTL_SECONDS = 60 * 60  # 60 minutes
_CACHE_MAX_ENTRIES = 256

# OrderedDict + manual LRU eviction. Sufficient for a single-process API
# under expected load; the alternative was a Redis dep we don't yet have.
_CACHE: "OrderedDict[str, tuple[float, DiagnoseResponse]]" = OrderedDict()


def _make_cache_key(holdings: list[Holding]) -> str:
    """Stable cache key over a portfolio's identity.

    Sorts by ticker so input order doesn't change the key; rounds
    weights/shares to 4 decimal places so floating-point noise doesn't
    fragment the cache.
    """
    parts = sorted(
        f"{h.ticker}:{round(h.weight or 0.0, 4)}:{round(h.shares or 0.0, 4)}"
        for h in holdings
    )
    return "portfolio_diag:" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _cache_get(key: str) -> Optional[DiagnoseResponse]:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    ts, payload = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        # Expired; remove + treat as miss.
        try:
            del _CACHE[key]
        except KeyError:
            pass
        return None
    # LRU bump
    _CACHE.move_to_end(key)
    return payload


def _cache_set(key: str, value: DiagnoseResponse) -> None:
    _CACHE[key] = (time.time(), value)
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX_ENTRIES:
        _CACHE.popitem(last=False)


def _reset_cache_for_tests() -> None:
    """Test hook — clears the in-memory cache between cases."""
    _CACHE.clear()


# ── Rate-limit ───────────────────────────────────────────────────────────────


def _enforce_diagnose_rate_limit(db: Session, user_id: str, tier: str) -> None:
    """Raise 402 portfolio_diagnose_rate_limit when the user has burned
    their hourly quota. Reads the row but does NOT increment — the
    increment happens after the diagnosis succeeds.

    Anonymous callers (synthetic `legacy-anon-0000` user) share a single
    globally-scoped counter, so a 5/hr Scout cap would mean the 6th
    anonymous visitor across the entire site in any hour gets blocked —
    not the entry-mode UX we want. Treat anonymous as effectively
    uncapped; per-IP / per-anon-session limits are a follow-up if abuse
    becomes an issue.
    """
    if user_id == _LEGACY_USER_ID:
        return
    cap = PORTFOLIO_DIAGNOSE_HOURLY_CAPS.get(tier, PORTFOLIO_DIAGNOSE_HOURLY_CAPS["scout"])
    used = get_portfolio_diagnose_runs_used(db, user_id)
    if used >= cap:
        try:
            from app.services.posthog_service import capture as _ph_capture
            _ph_capture(user_id, "portfolio_diagnose_rate_limited", {
                "current_tier": tier,
                "used": used,
                "cap": cap,
            })
        except Exception:
            pass
        raise upgrade_error(
            "portfolio_diagnose_rate_limit",
            current_tier=tier,
            current_value=f"{used}/{cap}",
            limit_value=str(cap),
        )


# ── Endpoint ─────────────────────────────────────────────────────────────────


@router.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose_portfolio(
    payload: DiagnoseRequest,
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=True),
    ),
    db: Session = Depends(get_db),
) -> DiagnoseResponse:
    user, ent = auth
    # Snapshot the ORM-bound fields we'll need after `db.close()`. Once
    # any code path commits `db` (e.g. `get_or_create_current_weekly_usage`
    # creating a fresh WeeklyUsage row), all `user`/`ent.user` attributes
    # are expired; touching `user.id` after `db.close()` then raises
    # `DetachedInstanceError`. Same lesson as PR #53 (chat hang).
    user_id: str = user.id
    tier: str = ent.tier

    # 1. Rate-limit first — cheaper than the cache lookup, and we don't
    # want a rate-limited user to enjoy unlimited cached re-reads.
    _enforce_diagnose_rate_limit(db, user_id, tier)

    # 2. Cache lookup (60-min TTL).
    cache_key = _make_cache_key(payload.holdings)
    cached = _cache_get(cache_key)
    if cached is not None:
        # Re-emit with cache_hit=True without re-running. We still bump
        # the rate-limit counter so the cache doesn't become a workaround
        # for the hourly cap — except for anonymous, whose counter is the
        # global shared row and isn't gating anyway.
        if user_id != _LEGACY_USER_ID:
            increment_portfolio_diagnose_run(db, user_id)
        return DiagnoseResponse(
            diagnosis=cached.diagnosis,
            recommended_overlays=cached.recommended_overlays,
            cache_hit=True,
        )

    # Release the request-scoped session before the slow external work.
    # `_service.diagnose` awaits ~2-5s of FMP HTTP calls; holding the
    # `Depends(get_db)` connection across that await drains the pool
    # under load (CLAUDE.md trap #13). FastAPI's `get_db` finally-block
    # will call .close() again at request end — that's a no-op.
    db.close()

    # 3. Run the diagnosis (the expensive path: ~2-5s) on a fresh session
    # so the slow FMP roundtrip doesn't sit on a pool connection.
    with SessionLocal() as work_db:
        diagnosis = await _service.diagnose(work_db, payload.holdings)
    recommended = _service.recommend_overlays(diagnosis)

    response = DiagnoseResponse(
        diagnosis=diagnosis,
        recommended_overlays=recommended,
        cache_hit=False,
    )

    # 4. Cache + increment counter (re-acquire a session for the write).
    # Anonymous users share a single global row; skip the write to avoid
    # noisy contention on it.
    _cache_set(cache_key, response)
    if user_id != _LEGACY_USER_ID:
        with SessionLocal() as write_db:
            increment_portfolio_diagnose_run(write_db, user_id)

    # 5. PostHog analytics — fire-and-forget; never breaks the request.
    try:
        from app.services.posthog_service import capture as _ph_capture
        _ph_capture(user_id, "portfolio_diagnosed", {
            "n_holdings": diagnosis.n_holdings,
            "current_tier": tier,
            "top_overlay": recommended[0].overlay if recommended else None,
        })
    except Exception:
        pass

    return response
