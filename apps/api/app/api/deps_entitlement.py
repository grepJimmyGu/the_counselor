"""Stage 3 — gating dependency.

Provides `require_entitlement()`, a FastAPI dependency factory that wraps gated
routes. It resolves the current user's entitlements, validates the request
against the per-tier caps, and either:
  - raises HTTPException(402) with the standardized EntitlementErrorDetail
    envelope when GATING_ENABLED=true (enforcement mode), or
  - emits a structured `gate_event` log line and allows the request through
    when GATING_ENABLED=false (shadow mode for safe rollout).

The dep returns `(user, entitlements)` so the route handler doesn't need to
re-fetch them.

Body re-read note: FastAPI's underlying request stream can only be read once.
We cache the parsed JSON on `request.state._cached_body` so a route handler
that also wants to read the body (or has a Pydantic body parameter) sees
the same payload.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_or_anonymous
from app.api.entitlement_errors import CodeT, upgrade_error
from app.core.config import get_settings
from app.data.sp500_tickers import is_sp500
from app.db.session import get_db
from app.models.user import User
from app.schemas.identity import Entitlements
from app.services.entitlements import (
    get_entitlements,
    get_or_create_current_weekly_usage,
)

_LEGACY_ANON_ID = "legacy-anon-0000"

_log = logging.getLogger("livermore.gating")


def require_entitlement(
    *,
    needs_run_quota: bool = False,
    universe_field: Optional[str] = None,
    history_field: Optional[str] = None,
    template_id_field: Optional[str] = "template_id",
    robustness_tests_field: Optional[str] = None,
    market_pulse_ticker_field: Optional[str] = None,
    allow_anonymous: bool = False,
):
    """Return a FastAPI dependency that validates the request against the
    current user's entitlements.

    Args:
        needs_run_quota: gate on Scout's 5-custom-runs-per-week cap.
            Skipped automatically when the request body has a non-null
            template_id (template runs are unlimited for all tiers).
        universe_field: name of the top-level body field holding the universe
            list. Skipped on template runs.
        history_field: name of the top-level body field holding the start_date
            (ISO string). Skipped on template runs.
        template_id_field: name of the top-level body field that distinguishes
            template runs from custom runs. Defaults to "template_id".
        robustness_tests_field: name of the top-level body field holding a
            list of robustness test names. Each must be in ent.robustness_tests.
        market_pulse_ticker_field: name of the URL path parameter holding a
            stock ticker. Scout tier (and anonymous, if allow_anonymous=True)
            requires it to be in the S&P 500 set.
        allow_anonymous: if True, uses get_current_user_or_anonymous so the
            route accepts unauthenticated requests. The legacy-anon synthetic
            user is treated as Scout-tier for entitlements purposes. When the
            gate fires for an anonymous user, the 402 envelope sets
            is_anonymous=True and cta_action="signup".

    Returns the (user, entitlements) tuple.
    """
    user_dep = get_current_user_or_anonymous if allow_anonymous else get_current_user

    async def _dep(
        request: Request,
        user: User = Depends(user_dep),
        db: Session = Depends(get_db),
    ) -> tuple[User, Entitlements]:
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
        body = await _safe_body(request)

        is_template = bool(body.get(template_id_field)) if template_id_field else False

        # ── Runs quota — custom-only (templates unlimited) ────────────────
        if needs_run_quota and not is_template:
            if ent.custom_backtest_runs_remaining is not None and ent.custom_backtest_runs_remaining <= 0:
                used = 5 - ent.custom_backtest_runs_remaining
                _violation(
                    "runs_exhausted", ent, user,
                    current_value=f"{used}/5", limit_value="5",
                    path=request.url.path,
                )

        # ── Universe size — custom-only ───────────────────────────────────
        if universe_field and not is_template and body.get(universe_field):
            requested = len(body[universe_field])
            if requested > ent.universe_size_max_custom:
                _violation(
                    "universe_too_large", ent, user,
                    current_value=str(requested),
                    limit_value=str(ent.universe_size_max_custom),
                    path=request.url.path,
                )

        # ── History window — custom-only ──────────────────────────────────
        if history_field and not is_template and body.get(history_field):
            requested_years = _compute_history_years(
                body[history_field], body.get("end_date"),
            )
            if requested_years is not None and requested_years > ent.history_window_years_custom:
                _violation(
                    "history_too_long", ent, user,
                    current_value=f"{requested_years:.1f} yr",
                    limit_value=f"{ent.history_window_years_custom} yr",
                    path=request.url.path,
                )

        # ── Robustness test names ─────────────────────────────────────────
        if robustness_tests_field and body.get(robustness_tests_field):
            tests = body[robustness_tests_field]
            if isinstance(tests, list):
                for test in tests:
                    if test not in ent.robustness_tests:
                        _violation(
                            "robustness_test_locked", ent, user,
                            current_value=str(test),
                            limit_value=",".join(ent.robustness_tests) or "—",
                            path=request.url.path,
                        )

        # ── Market Pulse — S&P 500 for Scout ──────────────────────────────
        if market_pulse_ticker_field:
            ticker = request.path_params.get(market_pulse_ticker_field, "")
            if ticker and ent.market_pulse_ticker_scope == "top_250" and not is_sp500(ticker):
                _violation(
                    "market_pulse_ticker_out_of_scope", ent, user,
                    current_value=ticker.upper(),
                    limit_value="S&P 500",
                    path=request.url.path,
                )

        return user, ent

    return _dep


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _safe_body(request: Request) -> dict:
    """Read the JSON body if present, caching on request.state so a downstream
    route handler (or Pydantic body parameter) can re-read."""
    if request.method not in ("POST", "PUT", "PATCH"):
        return {}
    if not hasattr(request.state, "_cached_body"):
        try:
            request.state._cached_body = await request.json()
        except Exception:
            request.state._cached_body = {}
    return request.state._cached_body or {}


def _compute_history_years(start_date_raw, end_date_raw) -> Optional[float]:
    """Parse ISO date strings (or datetime/date instances) → years between.
    Returns None if either side can't be parsed."""
    start = _parse_date(start_date_raw)
    if start is None:
        return None
    end = _parse_date(end_date_raw) or date.today()
    return (end - start).days / 365.25


def _parse_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _violation(
    code: CodeT,
    ent: Entitlements,
    user: User,
    *,
    current_value: str,
    limit_value: str,
    path: str,
) -> None:
    """Either raise 402 (enforcement) or log a shadow-mode event (observe-only).

    The log line is grep-able / structured for Stage 6 aggregation:
        gate_event code=runs_exhausted tier=scout user_id=abc path=/api/backtest/run
                   current=5/5 limit=5 shadow=true
    """
    settings = get_settings()
    is_anonymous = user.id == _LEGACY_ANON_ID

    # Stage 6a: paywall_hit event — fires whether enforcement or shadow mode.
    try:
        from app.services.posthog_service import capture as _ph_capture
        _ph_capture(user.id, "paywall_hit", {
            "code": code,
            "current_tier": ent.tier,
            "path": path,
            "is_anonymous": is_anonymous,
            "enforced": settings.gating_enabled,
        })
    except Exception:
        pass

    if settings.gating_enabled:
        raise upgrade_error(
            code,
            current_tier=ent.tier,
            current_value=current_value,
            limit_value=limit_value,
            is_anonymous=is_anonymous,
        )
    _log.info(
        "gate_event code=%s tier=%s user_id=%s path=%s current=%s limit=%s shadow=true%s",
        code, ent.tier, user.id, path, current_value, limit_value,
        " anonymous=true" if is_anonymous else "",
    )
