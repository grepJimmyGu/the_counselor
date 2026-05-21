"""Stage 3 — gating on POST /api/backtest/run.

Tests the dep's runs-quota check (custom only; templates exempt) and the
route's inline universe + history validators. The "templates exempt"
invariant from Stage 1a is also retested at this layer."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from app.api.routes.backtest import _enforce_custom_caps
from app.schemas.identity import Entitlements
from app.schemas.strategy import (
    CashManagement,
    PositionSizing,
    RiskManagement,
    StrategyJSON,
)
from app.services.entitlements import (
    get_entitlements,
    get_or_create_current_weekly_usage,
    increment_custom_backtest,
    increment_template_backtest,
)
from tests._gating_helpers import enable_gating, mock_request  # noqa: F401


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_strategy(
    *,
    universe: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> StrategyJSON:
    """Build a minimal valid StrategyJSON for cap testing."""
    return StrategyJSON(
        strategy_name="test-strategy",
        strategy_type="moving_average_filter",
        universe=universe or ["AAPL"],
        benchmark="SPY",
        start_date=start_date or (date.today() - timedelta(days=200)),
        end_date=end_date or date.today(),
        initial_capital=10_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=10,
        slippage_bps=5,
        rules=[],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(hold_cash_when_no_signal=True),
    )


def _ent_for(user, db) -> Entitlements:
    weekly = get_or_create_current_weekly_usage(db, user.id)
    return get_entitlements(user, weekly)


# ── Runs quota (custom-only; templates exempt) ────────────────────────────────


def test_scout_6th_custom_run_raises_402(make_user, db: Session, enable_gating):
    """Spec acceptance criterion 1."""
    user = make_user(email="scout-quota@test.com", tier="scout")
    for _ in range(5):
        increment_custom_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}})  # no template_id → custom

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=user, db=db))
    assert exc.value.status_code == 402
    assert exc.value.detail["entitlement"]["code"] == "runs_exhausted"
    assert exc.value.detail["entitlement"]["required_tier"] == "strategist"


def test_scout_template_runs_dont_decrement_custom_quota(make_user, db: Session, enable_gating):
    """Spec acceptance criterion 2. The central Stage 1a invariant retested at the route layer."""
    user = make_user(email="scout-template@test.com", tier="scout")
    # 100 template runs — should not touch custom quota
    for _ in range(100):
        increment_template_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}})  # custom this time
    # 5 customs allowed, 0 used so far → 1st must pass
    user_out, ent_out = asyncio.run(dep(request=req, user=user, db=db))
    assert ent_out.custom_backtest_runs_remaining == 5


def test_scout_template_request_skips_runs_quota(make_user, db: Session, enable_gating):
    """Even at 5/5 custom usage, a template run must still pass — template_id present."""
    user = make_user(email="scout-tpl-bypass@test.com", tier="scout")
    for _ in range(5):
        increment_custom_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}, "template_id": "mag7-rotation"})
    # No 402 — template_id present bypasses the quota check
    user_out, _ = asyncio.run(dep(request=req, user=user, db=db))
    assert user_out.id == user.id


def test_strategist_unlimited_custom_runs(make_user, db: Session, enable_gating):
    user = make_user(email="strat-unlimited@test.com", tier="strategist")
    for _ in range(100):
        increment_custom_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}})
    # No 402 — Strategist has no custom_backtest_runs_per_week cap
    user_out, ent = asyncio.run(dep(request=req, user=user, db=db))
    assert ent.custom_backtest_runs_remaining is None


# ── Universe + history (route-inline checks) ──────────────────────────────────


def test_universe_6_custom_returns_402_for_scout(make_user, db: Session, enable_gating):
    """Spec acceptance criterion 3."""
    user = make_user(email="scout-univ@test.com", tier="scout")
    ent = _ent_for(user, db)
    strategy = _make_strategy(universe=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"])

    with pytest.raises(HTTPException) as exc:
        _enforce_custom_caps(strategy, ent, user_id=user.id)
    assert exc.value.status_code == 402
    assert exc.value.detail["entitlement"]["code"] == "universe_too_large"
    assert exc.value.detail["entitlement"]["current_value"] == "6"
    assert exc.value.detail["entitlement"]["limit_value"] == "5"


def test_universe_5_custom_for_scout_succeeds(make_user, db: Session, enable_gating):
    user = make_user(email="scout-univ-5@test.com", tier="scout")
    ent = _ent_for(user, db)
    strategy = _make_strategy(universe=["AAPL", "MSFT", "GOOGL", "AMZN", "META"])
    _enforce_custom_caps(strategy, ent, user_id=user.id)  # no raise


def test_universe_25_custom_for_strategist_succeeds(make_user, db: Session, enable_gating):
    user = make_user(email="strat-univ-25@test.com", tier="strategist")
    ent = _ent_for(user, db)
    strategy = _make_strategy(universe=[f"T{i}" for i in range(25)])
    _enforce_custom_caps(strategy, ent, user_id=user.id)  # no raise


def test_universe_26_custom_for_strategist_returns_402(make_user, db: Session, enable_gating):
    user = make_user(email="strat-univ-26@test.com", tier="strategist")
    ent = _ent_for(user, db)
    strategy = _make_strategy(universe=[f"T{i}" for i in range(26)])
    with pytest.raises(HTTPException) as exc:
        _enforce_custom_caps(strategy, ent, user_id=user.id)
    assert exc.value.detail["entitlement"]["code"] == "universe_too_large"


def test_history_6yr_custom_returns_402_for_scout(make_user, db: Session, enable_gating):
    """Spec acceptance criterion 5."""
    user = make_user(email="scout-hist@test.com", tier="scout")
    ent = _ent_for(user, db)
    strategy = _make_strategy(
        start_date=date.today() - timedelta(days=int(365.25 * 6)),
        end_date=date.today(),
    )
    with pytest.raises(HTTPException) as exc:
        _enforce_custom_caps(strategy, ent, user_id=user.id)
    assert exc.value.detail["entitlement"]["code"] == "history_too_long"


def test_history_5yr_custom_for_scout_succeeds(make_user, db: Session, enable_gating):
    user = make_user(email="scout-hist-5@test.com", tier="scout")
    ent = _ent_for(user, db)
    strategy = _make_strategy(
        start_date=date.today() - timedelta(days=int(365.25 * 4.9)),
        end_date=date.today(),
    )
    _enforce_custom_caps(strategy, ent, user_id=user.id)  # no raise


def test_history_20yr_for_quant_succeeds(make_user, db: Session, enable_gating):
    user = make_user(email="quant-hist@test.com", tier="quant")
    ent = _ent_for(user, db)
    strategy = _make_strategy(
        start_date=date.today() - timedelta(days=int(365.25 * 19)),
        end_date=date.today(),
    )
    _enforce_custom_caps(strategy, ent, user_id=user.id)  # no raise


# ── Boundary trio for history_too_long ────────────────────────────────────────
# Codifies the May 21 regression: 5-year backtest from 2021-05-20 to 2026-05-21
# is 1827 days = 5.0027 years; strict `> 5` tripped a gate that the displayed
# "5.0 yr" said it shouldn't. Tolerance lives in deps_entitlement.py.


def test_scout_history_exactly_5_years_passes(make_user, db: Session, enable_gating):
    """5 calendar years (1825-1827 days) must NOT block Scout — matches what
    the user picks when they choose '5 years' from a date picker."""
    user = make_user(email="scout-hist-exact-5y@test.com", tier="scout")
    ent = _ent_for(user, db)
    end = date.today()
    strategy = _make_strategy(start_date=end.replace(year=end.year - 5), end_date=end)
    _enforce_custom_caps(strategy, ent, user_id=user.id)  # no raise


def test_scout_history_5y_plus_1_day_passes(make_user, db: Session, enable_gating):
    """The literal May 21 regression case: 1827 days = 5.0027 yr. Tolerance
    absorbs this; bug pre-fix would have raised history_too_long."""
    user = make_user(email="scout-hist-5y1d@test.com", tier="scout")
    ent = _ent_for(user, db)
    strategy = _make_strategy(
        start_date=date.today() - timedelta(days=1827),
        end_date=date.today(),
    )
    _enforce_custom_caps(strategy, ent, user_id=user.id)  # no raise


def test_scout_history_5y_plus_2_weeks_still_blocks(make_user, db: Session, enable_gating):
    """The tolerance is small — 14 days past the cap still blocks. Catches
    a future regression where someone widens the tolerance too far."""
    user = make_user(email="scout-hist-5y2w@test.com", tier="scout")
    ent = _ent_for(user, db)
    # 5 years + 14 days = ~5.038 yr, comfortably past the 7-day tolerance
    strategy = _make_strategy(
        start_date=date.today() - timedelta(days=int(365.25 * 5) + 14),
        end_date=date.today(),
    )
    with pytest.raises(HTTPException) as exc:
        _enforce_custom_caps(strategy, ent, user_id=user.id)
    assert exc.value.detail["entitlement"]["code"] == "history_too_long"


# ── Boundary trio for runs_exhausted ──────────────────────────────────────────


def test_scout_4_of_5_runs_used_passes(make_user, db: Session, enable_gating):
    """Just-under the cap: 4 used → 1 remaining → 5th custom run passes."""
    user = make_user(email="scout-runs-4@test.com", tier="scout")
    for _ in range(4):
        increment_custom_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}})
    out_user, ent = asyncio.run(dep(request=req, user=user, db=db))
    assert ent.custom_backtest_runs_remaining == 1


def test_scout_5_of_5_runs_used_blocks(make_user, db: Session, enable_gating):
    """At the cap: 5 used → 0 remaining → 6th must 402. Distinct from the
    existing `test_scout_6th_custom_run_raises_402` which validates the
    same boundary but reads more like 'the 6th run' than 'at the cap'."""
    user = make_user(email="scout-runs-5@test.com", tier="scout")
    for _ in range(5):
        increment_custom_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=user, db=db))
    assert exc.value.detail["entitlement"]["code"] == "runs_exhausted"
    assert exc.value.detail["entitlement"]["current_value"] == "5/5"
