"""PRD-13b follow-up — anonymous access to POST /api/portfolio/diagnose.

The route shipped sign-in-only (Depends(require_entitlement(needs_run_quota=False))),
which surfaced as the generic "We couldn't diagnose your portfolio. Try
again." error for every anonymous visitor because the catch-all branch in
the frontend brick maps unrecognised errors (including 401) to that copy.

Fix: `allow_anonymous=True` on the dep, plus skip the rate-limit
enforce/increment for the synthetic `legacy-anon-0000` user. All
anonymous calls share that one user row globally, so a Scout 5/hr cap
would mean the 6th anonymous visitor across the entire site in any hour
gets blocked — that's a gating story for sign-up nudges, not for an
entry-mode flow.

These tests exercise the route module directly (matching the existing
portfolio test style) and additionally introspect the FastAPI app to
confirm the dep is wired the way we claim.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.deps import _LEGACY_USER_ID
from app.api.routes import portfolio as portfolio_route
from app.models.user import Plan, User
from app.schemas.identity import Entitlements
from app.schemas.portfolio import (
    BehaviorAggregate,
    DiagnoseRequest,
    FactorExposure,
    Holding,
    PortfolioDiagnosis,
    SectorBreakdown,
    StyleMix,
)
from app.services.entitlements import (
    get_or_create_current_weekly_usage,
    increment_portfolio_diagnose_run,
)


def _make_entitlements(tier: str) -> Entitlements:
    """Minimal Entitlements payload for the route's `auth=(user, ent)` shape."""
    return Entitlements(
        tier=tier,
        status="active",
        custom_backtest_runs_remaining=None,
        week_start="2026-05-26",
        template_runs_unlimited=True,
        universe_size_max_custom=100,
        history_window_years_custom=20,
        asset_classes=["equity"],
        robustness_tests=[
            "parameter_sensitivity",
            "subperiod",
            "transaction_cost",
            "benchmark_comparison",
            "peer_ticker",
        ],
        market_pulse_ticker_scope="all_us_plus_alerts",
        business_model_section="full_plus_supply_chain",
        commodity_framework=True,
        saved_strategies_max=100,
        saved_strategies_always_public=False,
        community_badge="verified",
    )


def _dummy_diagnosis(n: int = 1) -> PortfolioDiagnosis:
    return PortfolioDiagnosis(
        n_holdings=n,
        style_mix=StyleMix(growth=1.0),
        factor_exposure=FactorExposure(),
        behavior=BehaviorAggregate(mixed_pct=1.0),
        sectors=SectorBreakdown(),
    )


def _seed_legacy_anon(db) -> User:
    """The conftest's `db` fixture runs `run_startup_migrations` which
    already inserts the legacy-anon row. Look it up rather than
    re-inserting (which would 23505 on the email UNIQUE constraint)."""
    return db.get(User, _LEGACY_USER_ID)


# ── Route dep wiring ─────────────────────────────────────────────────────────


def test_route_dep_is_configured_allow_anonymous():
    """Smoke-introspect the FastAPI app to confirm the diagnose route uses
    `get_current_user_or_anonymous` (the allow_anonymous=True branch),
    not the strict `get_current_user`. If a future edit accidentally
    flips this back, the test catches it without needing a live HTTP
    request."""
    from app.api.deps import get_current_user, get_current_user_or_anonymous
    from app.main import app

    # Find the POST /api/portfolio/diagnose route.
    target = None
    for route in app.routes:
        if getattr(route, "path", None) == "/api/portfolio/diagnose":
            target = route
            break
    assert target is not None, "POST /api/portfolio/diagnose route not registered"

    # Walk the dependant tree for the user dep.
    deps_seen: list = []

    def _walk(d):
        deps_seen.append(d.call)
        for sub in d.dependencies:
            _walk(sub)

    _walk(target.dependant)

    assert get_current_user_or_anonymous in deps_seen, (
        "expected diagnose route to depend on get_current_user_or_anonymous; "
        f"saw {[getattr(c, '__name__', repr(c)) for c in deps_seen]}"
    )
    assert get_current_user not in deps_seen, (
        "diagnose route still pulls strict get_current_user; "
        "anonymous callers will 401"
    )


# ── Rate-limit behaviour for the synthetic anon user ─────────────────────────


def test_enforce_rate_limit_skips_legacy_anon(db):
    """The shared anonymous counter must NOT gate the flow — even after
    arbitrarily many simulated previous anon runs, the enforce helper
    returns silently for `legacy-anon-0000`."""
    _seed_legacy_anon(db)
    # Pretend the synthetic user has already burned a huge number of
    # runs this hour (e.g. global traffic spike).
    for _ in range(50):
        increment_portfolio_diagnose_run(db, _LEGACY_USER_ID)
    # The helper must still return cleanly — no 402.
    portfolio_route._enforce_diagnose_rate_limit(db, _LEGACY_USER_ID, "scout")


def test_enforce_rate_limit_still_gates_scout(db):
    """Sign-in path is unchanged — Scout still hits the 5/hr cap."""
    from fastapi import HTTPException

    user = User(id="scout-user", email="scout@test.local", locale="en")
    db.add(user)
    db.add(Plan(user_id="scout-user", tier="scout", status="active"))
    db.commit()
    for _ in range(5):
        increment_portfolio_diagnose_run(db, "scout-user")
    with pytest.raises(HTTPException) as excinfo:
        portfolio_route._enforce_diagnose_rate_limit(db, "scout-user", "scout")
    assert excinfo.value.status_code == 402


# ── End-to-end route call as anonymous ───────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnose_route_succeeds_for_anonymous(db, monkeypatch):
    """Call the route function directly with the synthetic anonymous user
    as if `require_entitlement(allow_anonymous=True)` had resolved it.
    Must return a DiagnoseResponse without raising 401 or 402."""
    user = _seed_legacy_anon(db)
    ent = _make_entitlements("scout")

    # Mock the heavy service so we don't hit FMP.
    fake_service = MagicMock()
    fake_service.diagnose = AsyncMock(return_value=_dummy_diagnosis(1))
    fake_service.recommend_overlays = MagicMock(return_value=[])
    monkeypatch.setattr(portfolio_route, "_service", fake_service)
    portfolio_route._reset_cache_for_tests()

    # Route uses `with SessionLocal() as ...` for the slow path; route on
    # `SessionLocal` returning a fresh session bound to the test DB.
    from sqlalchemy.orm import sessionmaker

    test_session_factory = sessionmaker(
        bind=db.get_bind(), autoflush=False, autocommit=False, future=True,
    )
    monkeypatch.setattr(portfolio_route, "SessionLocal", test_session_factory)

    payload = DiagnoseRequest(holdings=[Holding(ticker="AAPL", weight=1.0)])
    resp = await portfolio_route.diagnose_portfolio(
        payload=payload, auth=(user, ent), db=db,
    )

    assert resp is not None
    assert resp.cache_hit is False
    assert resp.diagnosis.n_holdings == 1


@pytest.mark.asyncio
async def test_anonymous_diagnose_does_not_increment_shared_counter(
    db, monkeypatch,
):
    """The legacy-anon synthetic user's weekly_usage row should NOT
    accumulate counter increments — otherwise the row's
    `portfolio_diagnose_runs_hourly` would balloon globally."""
    user = _seed_legacy_anon(db)
    ent = _make_entitlements("scout")

    fake_service = MagicMock()
    fake_service.diagnose = AsyncMock(return_value=_dummy_diagnosis(1))
    fake_service.recommend_overlays = MagicMock(return_value=[])
    monkeypatch.setattr(portfolio_route, "_service", fake_service)
    portfolio_route._reset_cache_for_tests()

    from sqlalchemy.orm import sessionmaker
    test_session_factory = sessionmaker(
        bind=db.get_bind(), autoflush=False, autocommit=False, future=True,
    )
    monkeypatch.setattr(portfolio_route, "SessionLocal", test_session_factory)

    payload = DiagnoseRequest(holdings=[Holding(ticker="AAPL", weight=1.0)])
    await portfolio_route.diagnose_portfolio(
        payload=payload, auth=(user, ent), db=db,
    )

    # Row may or may not exist; if it does, the counter must be 0.
    row = get_or_create_current_weekly_usage(db, _LEGACY_USER_ID)
    assert (row.portfolio_diagnose_runs_hourly or 0) == 0


@pytest.mark.asyncio
async def test_signed_in_diagnose_still_increments_counter(db, monkeypatch):
    """Sign-in path unchanged — counter increments normally so the per-tier
    cap still gates abusers."""
    user = User(id="signed-user", email="signed@test.local", locale="en")
    db.add(user)
    db.add(Plan(user_id="signed-user", tier="strategist", status="active"))
    db.commit()
    db.refresh(user)
    ent = _make_entitlements("strategist")

    fake_service = MagicMock()
    fake_service.diagnose = AsyncMock(return_value=_dummy_diagnosis(1))
    fake_service.recommend_overlays = MagicMock(return_value=[])
    monkeypatch.setattr(portfolio_route, "_service", fake_service)
    portfolio_route._reset_cache_for_tests()

    from sqlalchemy.orm import sessionmaker
    test_session_factory = sessionmaker(
        bind=db.get_bind(), autoflush=False, autocommit=False, future=True,
    )
    monkeypatch.setattr(portfolio_route, "SessionLocal", test_session_factory)

    payload = DiagnoseRequest(holdings=[Holding(ticker="AAPL", weight=1.0)])
    await portfolio_route.diagnose_portfolio(
        payload=payload, auth=(user, ent), db=db,
    )

    row = get_or_create_current_weekly_usage(db, "signed-user")
    assert (row.portfolio_diagnose_runs_hourly or 0) == 1
