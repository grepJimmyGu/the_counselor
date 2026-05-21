"""Stage 3 — Market Pulse S&P 500 gating.

Tests:
  - Scout requesting an S&P 500 ticker (AAPL) passes.
  - Scout requesting a non-S&P-500 ticker (SMCI) returns 402.
  - Strategist + Quant pass any ticker.
  - Anonymous (legacy-anon synthetic user) is treated as Scout-tier.
  - 402 envelope sets is_anonymous=True for anonymous violators.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps_entitlement import _LEGACY_ANON_ID, require_entitlement
from app.models.user import Plan, User
from tests._gating_helpers import enable_gating, mock_request  # noqa: F401


def _make_dep():
    return require_entitlement(
        market_pulse_ticker_field="symbol",
        template_id_field=None,
        allow_anonymous=True,
    )


def test_scout_sp500_ticker_passes(make_user, db: Session, enable_gating):
    user = make_user(email="scout-sp500@test.com", tier="scout")
    dep = _make_dep()
    req = mock_request(
        method="GET",
        path_params={"symbol": "AAPL"},
        path="/api/company/AAPL/overview",
    )
    out_user, _ = asyncio.run(dep(request=req, user=user, db=db))
    assert out_user.id == user.id


def test_scout_non_sp500_ticker_returns_402(make_user, db: Session, enable_gating):
    """Spec acceptance criterion 10."""
    user = make_user(email="scout-smci@test.com", tier="scout")
    dep = _make_dep()
    req = mock_request(
        method="GET",
        path_params={"symbol": "SMCI"},
        path="/api/company/SMCI/overview",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=user, db=db))
    assert exc.value.status_code == 402
    assert exc.value.detail["entitlement"]["code"] == "market_pulse_ticker_out_of_scope"
    assert exc.value.detail["entitlement"]["current_value"] == "SMCI"
    assert exc.value.detail["entitlement"]["limit_value"] == "S&P 500"
    # Scout is authenticated, so is_anonymous=False
    assert exc.value.detail["entitlement"]["is_anonymous"] is False
    assert exc.value.detail["entitlement"]["cta_action"] == "upgrade"


def test_strategist_non_sp500_ticker_passes(make_user, db: Session, enable_gating):
    user = make_user(email="strat-smci@test.com", tier="strategist")
    dep = _make_dep()
    req = mock_request(
        method="GET",
        path_params={"symbol": "SMCI"},
        path="/api/company/SMCI/overview",
    )
    asyncio.run(dep(request=req, user=user, db=db))  # no raise


def test_quant_non_sp500_ticker_passes(make_user, db: Session, enable_gating):
    user = make_user(email="quant-smci@test.com", tier="quant")
    dep = _make_dep()
    req = mock_request(
        method="GET",
        path_params={"symbol": "SMCI"},
        path="/api/company/SMCI/overview",
    )
    asyncio.run(dep(request=req, user=user, db=db))  # no raise


def test_anonymous_non_sp500_ticker_returns_402_signup(db: Session, enable_gating):
    """Anonymous (legacy-anon synthetic user) is Scout-tier; non-S&P-500 → 402
    with is_anonymous=True + cta_action='signup'."""
    # Construct the legacy-anon synthetic user directly (not via make_user).
    anon = User(id=_LEGACY_ANON_ID, email="legacy@livermore.app", locale="en")
    anon.plan = Plan(user_id=_LEGACY_ANON_ID, tier="scout", status="active")

    dep = _make_dep()
    req = mock_request(
        method="GET",
        path_params={"symbol": "SMCI"},
        path="/api/company/SMCI/overview",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=anon, db=db))
    detail = exc.value.detail["entitlement"]
    assert detail["code"] == "market_pulse_ticker_out_of_scope"
    assert detail["is_anonymous"] is True
    assert detail["cta_action"] == "signup"
