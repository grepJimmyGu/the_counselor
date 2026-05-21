"""Stage 3 — gating on POST /api/robustness/run.

Tests:
  - Strategist gets parameter_sensitivity + benchmark_comparison (2 of 5).
  - Strategist requesting subperiod / transaction_cost / peer_ticker returns 402.
  - Quant runs any of the 5 tests.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from tests._gating_helpers import enable_gating, mock_request  # noqa: F401


def _make_dep():
    return require_entitlement(
        needs_run_quota=True,
        robustness_tests_field="tests_to_run",
        template_id_field=None,  # robustness has no template concept
    )


def _body(tests: list[str]) -> dict:
    return {"strategy_json": {}, "tests_to_run": tests}


def test_strategist_parameter_sensitivity_passes(make_user, db: Session, enable_gating):
    user = make_user(email="strat-param@test.com", tier="strategist")
    dep = _make_dep()
    req = mock_request(body=_body(["parameter_sensitivity"]))
    out_user, _ = asyncio.run(dep(request=req, user=user, db=db))
    assert out_user.id == user.id


def test_strategist_benchmark_comparison_passes(make_user, db: Session, enable_gating):
    user = make_user(email="strat-bench@test.com", tier="strategist")
    dep = _make_dep()
    req = mock_request(body=_body(["benchmark_comparison"]))
    asyncio.run(dep(request=req, user=user, db=db))  # no raise


def test_strategist_subperiod_returns_402(make_user, db: Session, enable_gating):
    user = make_user(email="strat-sub@test.com", tier="strategist")
    dep = _make_dep()
    req = mock_request(body=_body(["subperiod"]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=user, db=db))
    assert exc.value.status_code == 402
    assert exc.value.detail["entitlement"]["code"] == "robustness_test_locked"
    assert exc.value.detail["entitlement"]["current_value"] == "subperiod"


def test_strategist_peer_ticker_returns_402(make_user, db: Session, enable_gating):
    user = make_user(email="strat-peer@test.com", tier="strategist")
    dep = _make_dep()
    req = mock_request(body=_body(["peer_ticker"]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=user, db=db))
    assert exc.value.detail["entitlement"]["code"] == "robustness_test_locked"


def test_strategist_mixed_tests_returns_402_on_first_locked(make_user, db: Session, enable_gating):
    """If the request mixes allowed + locked tests, the locked one trips the gate."""
    user = make_user(email="strat-mix@test.com", tier="strategist")
    dep = _make_dep()
    req = mock_request(body=_body(["parameter_sensitivity", "transaction_cost"]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=user, db=db))
    assert exc.value.detail["entitlement"]["code"] == "robustness_test_locked"
    assert exc.value.detail["entitlement"]["current_value"] == "transaction_cost"


def test_quant_all_five_tests_pass(make_user, db: Session, enable_gating):
    """Spec acceptance criterion 9: Quant unlocks all 5."""
    user = make_user(email="quant-all@test.com", tier="quant")
    dep = _make_dep()
    req = mock_request(body=_body([
        "parameter_sensitivity",
        "subperiod",
        "transaction_cost",
        "benchmark_comparison",
        "peer_ticker",
    ]))
    asyncio.run(dep(request=req, user=user, db=db))  # no raise
