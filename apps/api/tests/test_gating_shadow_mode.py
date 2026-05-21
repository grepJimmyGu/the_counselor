"""Stage 3 — shadow-mode behavior.

When GATING_ENABLED=false, the dep emits a structured `gate_event` log line
but does NOT raise 402. The request is allowed through.

Spec acceptance criteria 15 + 16: same setup, opposite outcomes based on flag.
"""
from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from app.services.entitlements import increment_custom_backtest
from tests._gating_helpers import disable_gating, enable_gating, mock_request  # noqa: F401


def test_shadow_mode_allows_request_and_logs_event(
    make_user,
    db: Session,
    caplog,
    disable_gating,
):
    """Scout exceeds 5/week with GATING_ENABLED=false: request succeeds, log fires."""
    user = make_user(email="scout-shadow@test.com", tier="scout")
    for _ in range(5):
        increment_custom_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}})

    with caplog.at_level(logging.INFO, logger="livermore.gating"):
        # No 402 — shadow mode allows the request
        out_user, _ = asyncio.run(dep(request=req, user=user, db=db))

    assert out_user.id == user.id
    assert any(
        "gate_event code=runs_exhausted" in rec.message and "shadow=true" in rec.message
        for rec in caplog.records
    ), f"expected gate_event log line; got: {[r.message for r in caplog.records]}"


def test_enforcement_mode_raises_402(
    make_user,
    db: Session,
    enable_gating,
):
    """Same scenario as above but with GATING_ENABLED=true → 402."""
    user = make_user(email="scout-enforce@test.com", tier="scout")
    for _ in range(5):
        increment_custom_backtest(db, user.id)

    dep = require_entitlement(needs_run_quota=True, template_id_field="template_id")
    req = mock_request(body={"strategy_json": {}})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(request=req, user=user, db=db))
    assert exc.value.status_code == 402
