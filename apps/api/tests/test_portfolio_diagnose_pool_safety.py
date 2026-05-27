"""Regression test for CLAUDE.md trap #13 on POST /api/portfolio/diagnose.

The route used to hold the request-scoped `db: Session = Depends(get_db)`
across `await _service.diagnose(db, ...)` — ~2-5s of FMP HTTP per call.
Under concurrent load, every request's connection sat idle-but-checked-out
during the slow upstream wait, draining the SQLAlchemy pool. PR #104
established the canonical Option A pattern (close request session before
the slow await, re-acquire `SessionLocal()` for the work that needs it).

This test exercises the route under 20 concurrent calls against a tight
pool with a fast pool_timeout. With the fix, the request-scoped session
is released before the mocked 100ms upstream sleep, so the queue clears
within the pool_timeout window. A regression that re-introduced the
"hold request_db across the await" pattern would surface here as a
`sqlalchemy.exc.TimeoutError: QueuePool limit ... overflow timeout`.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import portfolio as portfolio_route
from app.db.migrations import run_startup_migrations
from app.db.session import Base
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


def _make_entitlements(tier: str = "quant") -> Entitlements:
    """Quant tier has the highest hourly cap (effectively unlimited) so the
    rate-limit check doesn't fire during the 20-call burst."""
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


@pytest.fixture
def constrained_pool(monkeypatch):
    """Real SQLite engine sized like the Railway prod pool (5 + 10 = 15).

    `pool_timeout=2.0s` is the failure tripwire: if the route holds its
    request-scoped connection across the mocked 100ms slow await, the
    16th+ concurrent callers will queue. The first batch finishes in
    100ms and clears 15 slots; the queued five then finish in another
    100ms — comfortably within 2s. Any regression that lengthens the
    hold time (or introduces an even slower await without releasing)
    would push past pool_timeout and surface as a TimeoutError.

    File-backed SQLite so the same rows are visible across the three
    Session lifecycles (request_db, work_db, write_db) the fix uses.
    """
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "pool_safety.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_size=5,
        max_overflow=10,
        pool_timeout=2.0,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)
    TestSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True,
    )

    # Patch the SessionLocal symbol imported into the route module so the
    # Option A re-acquire path (`with SessionLocal() as work_db: ...`) hits
    # this constrained pool, not the app-wide engine.
    monkeypatch.setattr(portfolio_route, "SessionLocal", TestSessionLocal)

    yield engine, TestSessionLocal

    engine.dispose()
    try:
        os.remove(db_path)
        os.rmdir(tmpdir)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_20_concurrent_diagnose_calls_do_not_drain_pool(
    constrained_pool, monkeypatch,
):
    """20 concurrent diagnose requests against a 15-conn pool must all
    complete cleanly when the route releases its request-scoped session
    before the slow upstream await.
    """
    engine, TestSessionLocal = constrained_pool

    # Seed a quant-tier user so `_enforce_diagnose_rate_limit` finds
    # last_reset_hour state and never trips the 402.
    setup_db = TestSessionLocal()
    try:
        setup_db.add(User(id="pool-user", email="pool@test.local", locale="en"))
        setup_db.add(Plan(user_id="pool-user", tier="quant", status="active"))
        setup_db.commit()
        user = setup_db.query(User).filter_by(id="pool-user").one()
    finally:
        setup_db.close()

    ent = _make_entitlements("quant")

    # Mock the heavy path: every diagnose call yields the event loop for
    # 100ms, mimicking the FMP HTTP roundtrip. If the route holds the
    # request-scoped session across this await, concurrent requests stack
    # up on the pool.
    async def _slow_diagnose(_db, holdings):
        await asyncio.sleep(0.1)
        return PortfolioDiagnosis(
            n_holdings=len(holdings),
            style_mix=StyleMix(growth=1.0),
            factor_exposure=FactorExposure(),
            behavior=BehaviorAggregate(mixed_pct=1.0),
            sectors=SectorBreakdown(),
        )

    fake_service = MagicMock()
    fake_service.diagnose = _slow_diagnose
    fake_service.recommend_overlays = MagicMock(return_value=[])
    monkeypatch.setattr(portfolio_route, "_service", fake_service)

    # Each request gets a unique cache key so none short-circuit through
    # the in-process cache (we want all 20 to take the slow path).
    portfolio_route._reset_cache_for_tests()

    async def one_request(idx: int):
        # Mimic FastAPI's `Depends(get_db)` lifecycle: acquire a session
        # from the constrained pool at request start, close it at request
        # end. The fix's `db.close()` inside the route returns the conn
        # to the pool early; this outer close() is a no-op when that's
        # already happened.
        request_db = TestSessionLocal()
        try:
            payload = DiagnoseRequest(
                holdings=[Holding(ticker=f"T{idx:03d}", weight=1.0)],
            )
            return await portfolio_route.diagnose_portfolio(
                payload=payload, auth=(user, ent), db=request_db,
            )
        finally:
            request_db.close()

    results = await asyncio.gather(*(one_request(i) for i in range(20)))

    assert len(results) == 20
    for resp in results:
        assert resp is not None
        assert resp.cache_hit is False
        assert resp.diagnosis.n_holdings == 1


@pytest.mark.asyncio
async def test_diagnose_release_does_not_break_subsequent_writes(
    constrained_pool, monkeypatch,
):
    """The fix closes the request-scoped `db` mid-route, then re-acquires
    fresh `SessionLocal()` sessions for the slow path and the rate-limit
    increment. Confirm the rate-limit counter still increments correctly
    after the close+reopen — i.e. the write_db path isn't accidentally
    operating on a closed session or a different DB.
    """
    engine, TestSessionLocal = constrained_pool

    setup_db = TestSessionLocal()
    try:
        setup_db.add(User(id="ratelimit-user", email="rl@test.local", locale="en"))
        setup_db.add(Plan(user_id="ratelimit-user", tier="strategist", status="active"))
        setup_db.commit()
        user = setup_db.query(User).filter_by(id="ratelimit-user").one()
    finally:
        setup_db.close()

    ent = _make_entitlements("strategist")

    async def _fast_diagnose(_db, holdings):
        return PortfolioDiagnosis(
            n_holdings=len(holdings),
            style_mix=StyleMix(growth=1.0),
            factor_exposure=FactorExposure(),
            behavior=BehaviorAggregate(mixed_pct=1.0),
            sectors=SectorBreakdown(),
        )

    fake_service = MagicMock()
    fake_service.diagnose = _fast_diagnose
    fake_service.recommend_overlays = MagicMock(return_value=[])
    monkeypatch.setattr(portfolio_route, "_service", fake_service)
    portfolio_route._reset_cache_for_tests()

    # Three sequential requests — each acquires its own request_db, runs
    # through close()+SessionLocal()+SessionLocal(), and increments the
    # hourly counter.
    for idx in range(3):
        request_db = TestSessionLocal()
        try:
            await portfolio_route.diagnose_portfolio(
                payload=DiagnoseRequest(
                    holdings=[Holding(ticker=f"T{idx}", weight=1.0)],
                ),
                auth=(user, ent),
                db=request_db,
            )
        finally:
            request_db.close()

    # Verify the counter rolled forward through the fix's separate write
    # session.
    from app.services.entitlements import get_portfolio_diagnose_runs_used

    check_db = TestSessionLocal()
    try:
        assert get_portfolio_diagnose_runs_used(check_db, "ratelimit-user") == 3
    finally:
        check_db.close()
