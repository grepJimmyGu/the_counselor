"""Stage 1a — anonymous session service + merge on signup."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.models.anonymous_session import AnonymousSession
from app.models.backtest import BacktestRecord
from app.services.anonymous_service import (
    COOKIE_NAME,
    get_anonymous_session_by_user_id,
    get_or_create_anonymous_session,
    increment_anonymous_run,
    merge_anonymous_into_user,
    record_anonymous_referrer,
)


def _stub_request(cookies: dict | None = None, ua: str = "pytest", lang: str = "en") -> MagicMock:
    req = MagicMock()
    req.cookies = cookies or {}
    req.headers = {"user-agent": ua, "accept-language": lang}
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _stub_response() -> MagicMock:
    return MagicMock()


# ── Session creation + cookie ────────────────────────────────────────────────


def test_session_creates_on_first_request_and_sets_cookie(db: Session) -> None:
    """Dev/test path: APP_ENV != production → SameSite=Lax + Secure=False
    so local HTTP fetches across same-origin localhost still send the
    cookie back. Browsers reject SameSite=None when Secure=False, so we
    must NOT set None in dev — would break local development entirely."""
    req, resp = _stub_request(), _stub_response()
    with patch(
        "app.services.anonymous_service._is_production", return_value=False,
    ):
        session = get_or_create_anonymous_session(req, resp, db)

    assert session.id is not None
    assert session.runs_used == 0
    # Cookie was set
    resp.set_cookie.assert_called_once()
    args, kwargs = resp.set_cookie.call_args
    assert args[0] == COOKIE_NAME
    assert args[1] == session.id
    assert kwargs["httponly"] is True
    assert kwargs["samesite"] == "lax"
    assert kwargs["secure"] is False


def test_session_cookie_uses_samesite_none_in_production(db: Session) -> None:
    """Production path (KNOWN_ISSUES 2026-05-24): SameSite=None + Secure=True
    so the browser sends the anonymous cookie on cross-site POSTs from
    livermorealpha.com (or any Vercel preview origin) to
    thecounselor-production.up.railway.app. Without this, every anonymous
    request creates a fresh AnonymousSession — silently bypassing the
    1-backtest cap (Stage 1a) AND surfacing as "Conversation not found"
    after turn 1 of anonymous chat (ticket #6). PR #72 fixed the
    Set-Cookie propagation through StreamingResponse; this test guards
    the SameSite/Secure pair that makes the browser echo it back."""
    req, resp = _stub_request(), _stub_response()
    with patch(
        "app.services.anonymous_service._is_production", return_value=True,
    ):
        get_or_create_anonymous_session(req, resp, db)

    resp.set_cookie.assert_called_once()
    _args, kwargs = resp.set_cookie.call_args
    assert kwargs["samesite"] == "none", (
        "Production must use SameSite=None so cookies round-trip across the "
        "frontend↔backend origin boundary."
    )
    assert kwargs["secure"] is True, (
        "SameSite=None requires Secure=True — every modern browser rejects "
        "the cookie otherwise. Production is HTTPS-only so Secure is fine."
    )


def test_is_production_falls_back_to_railway_env_var(monkeypatch) -> None:
    """The fallback path added 2026-05-24 after PR #82 silently failed
    on Railway. `_is_production()` reads `settings.app_env` first
    (documented contract), but if that's still the default
    "development" — which Railway will silently allow because the
    `APP_ENV` env var was never set — it should fall back to Railway's
    native `RAILWAY_ENVIRONMENT=production` signal so the production
    cookie branch fires. Without this, PR #82's SameSite=None branch
    silently never fires in production."""
    from app.services import anonymous_service as svc
    # Force settings.app_env to the dev default so the primary check
    # returns False. (Settings is a cached Pydantic singleton; we mock
    # `get_settings()` itself rather than mutating its return value.)
    mock_settings = type("S", (), {"app_env": "development"})()
    monkeypatch.setattr(svc, "get_settings", lambda: mock_settings)

    # Without the Railway signal: should be False
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    assert svc._is_production() is False

    # With RAILWAY_ENVIRONMENT=production: should be True (fallback fires)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert svc._is_production() is True, (
        "Fallback path broken — Railway-deployed services would never "
        "be detected as production unless APP_ENV is also set, "
        "silently breaking PR #82's SameSite=None cookie branch."
    )

    # Other RAILWAY_ENVIRONMENT values (staging, preview, etc.) should NOT
    # trigger the production branch
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "staging")
    assert svc._is_production() is False


def test_session_reused_on_second_request(db: Session) -> None:
    req1, resp1 = _stub_request(), _stub_response()
    first = get_or_create_anonymous_session(req1, resp1, db)

    # Browser sends the cookie back on the next request
    req2, resp2 = _stub_request(cookies={COOKIE_NAME: first.id}), _stub_response()
    second = get_or_create_anonymous_session(req2, resp2, db)

    assert second.id == first.id
    # No new cookie set when reusing
    resp2.set_cookie.assert_not_called()


def test_stale_cookie_creates_new_session(db: Session) -> None:
    """A cookie pointing at a deleted/missing session should fall through to create a new one."""
    req = _stub_request(cookies={COOKIE_NAME: "00000000-0000-0000-0000-000000000000"})
    resp = _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    assert session.id != "00000000-0000-0000-0000-000000000000"
    resp.set_cookie.assert_called_once()


# ── One-shot cap behavior ────────────────────────────────────────────────────


def test_anonymous_one_shot_and_then_exhausted(db: Session) -> None:
    """First run succeeds; runs_used flips to 1."""
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    new_count = increment_anonymous_run(db, session, backtest_id="bt-1")
    assert new_count == 1
    assert session.runs_used == 1
    assert session.last_backtest_id == "bt-1"


# ── Referrer attribution ─────────────────────────────────────────────────────


def test_via_handle_recorded_first_touch_wins(db: Session) -> None:
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    record_anonymous_referrer(db, session, "alice")
    assert session.via_handle == "alice"

    # Second visit via a different creator — first-touch must win.
    record_anonymous_referrer(db, session, "bob")
    assert session.via_handle == "alice"


# ── Merge into user on signup ────────────────────────────────────────────────


def test_merge_into_user_sets_user_id_and_marks_converted(make_user, db: Session) -> None:
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    # Pretend an anonymous backtest ran and got persisted with user_id=NULL
    bt = BacktestRecord(
        id="bt-anon-1",
        strategy_type="momentum",
        strategy_name="Test",
        result_payload={},
        user_id=None,
    )
    db.add(bt)
    db.commit()
    increment_anonymous_run(db, session, backtest_id="bt-anon-1")

    # User signs up
    user = make_user(email="convert@test.com")
    merge_anonymous_into_user(db, session, user.id)

    db.refresh(session)
    db.refresh(bt)
    assert session.converted_to_user_id == user.id
    assert session.converted_at is not None
    assert bt.user_id == user.id


def test_merge_is_idempotent(make_user, db: Session) -> None:
    """Re-running merge for the same user should be a no-op (not raise, not change times)."""
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)
    user = make_user(email="idem-merge@test.com")

    merge_anonymous_into_user(db, session, user.id)
    first_converted_at = session.converted_at
    merge_anonymous_into_user(db, session, user.id)
    assert session.converted_at == first_converted_at


def test_lookup_by_converted_user_id(make_user, db: Session) -> None:
    """Stripe webhook attribution path uses this to find via_handle from user_id."""
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)
    record_anonymous_referrer(db, session, "creator-jimmy")

    user = make_user(email="paying@test.com")
    merge_anonymous_into_user(db, session, user.id)

    found = get_anonymous_session_by_user_id(db, user.id)
    assert found is not None
    assert found.id == session.id
    assert found.via_handle == "creator-jimmy"


# ── Endpoint-level: anonymous custom-run policy (2026-05-22) ─────────────────
#
# Policy change: anonymous viewers get ONE backtest per session — template
# OR custom (chat-built). The frontend sends `template_id="custom"` when no
# template is loaded; the backend used to 402 with `anonymous_chat_locked`
# but now lets it through on the first run and applies the same gates that
# apply to template runs (universe size, asset class, runs_used).


def _stub_strategy(universe=None):
    """Minimal valid StrategyJSON for endpoint-level tests."""
    from datetime import date, timedelta
    from app.schemas.strategy import (
        CashManagement,
        PositionSizing,
        RiskManagement,
        StrategyJSON,
    )
    return StrategyJSON(
        strategy_name="test-strategy",
        strategy_type="moving_average_filter",
        universe=universe or ["AAPL"],
        benchmark="SPY",
        start_date=date.today() - timedelta(days=200),
        end_date=date.today(),
        initial_capital=10_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=10,
        slippage_bps=5,
        rules=[],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(hold_cash_when_no_signal=True),
    )


def test_anonymous_custom_template_id_blocked_only_after_first_run(db: Session) -> None:
    """Regression for the May 22 policy change. A SECOND attempt with
    template_id='custom' must 402 with anonymous_runs_exhausted (not the
    removed anonymous_chat_locked). Proves the first attempt is allowed
    through to the actual backtest engine and the second is gated."""
    import asyncio
    import pytest as _pt
    from fastapi import HTTPException
    from app.api.routes.anonymous import (
        anonymous_backtest_run,
        AnonymousBacktestRunRequest,
    )

    # Simulate a session that has already used its one free run.
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)
    increment_anonymous_run(db, session, backtest_id="bt-prior")

    # Replay the same session via cookie on the next request.
    req2 = _stub_request(cookies={COOKIE_NAME: session.id})
    resp2 = _stub_response()

    payload = AnonymousBacktestRunRequest(
        template_id="custom",
        strategy_json=_stub_strategy(),
    )

    with _pt.raises(HTTPException) as exc:
        asyncio.run(anonymous_backtest_run(
            payload=payload, request=req2, response=resp2, db=db,
        ))
    assert exc.value.status_code == 402
    assert exc.value.detail["entitlement"]["code"] == "anonymous_runs_exhausted"
    assert exc.value.detail["entitlement"]["is_anonymous"] is True
    assert exc.value.detail["entitlement"]["cta_action"] == "signup"


def test_anonymous_first_run_multi_ticker_universe_passes_gate(db: Session) -> None:
    """Regression for the May 22 'first run always passes' policy: a 5-ticker
    custom strategy on a fresh session must NOT be blocked by a universe-size
    gate (the gate was removed). We can't actually run the engine without
    Alpha Vantage data, but we can prove the request passes through the
    gating block by pre-populating runs_used=1 → expect runs_exhausted
    (not universe_too_large) on the SECOND attempt with the same body."""
    import asyncio
    import pytest as _pt
    from fastapi import HTTPException
    from app.api.routes.anonymous import (
        anonymous_backtest_run,
        AnonymousBacktestRunRequest,
    )

    # Already-exhausted session; we're testing which code fires.
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)
    increment_anonymous_run(db, session, backtest_id="bt-prior")

    req2 = _stub_request(cookies={COOKIE_NAME: session.id})
    resp2 = _stub_response()

    payload = AnonymousBacktestRunRequest(
        template_id="custom",
        strategy_json=_stub_strategy(universe=["AAPL", "MSFT", "GOOGL", "AMZN", "META"]),
    )

    with _pt.raises(HTTPException) as exc:
        asyncio.run(anonymous_backtest_run(
            payload=payload, request=req2, response=resp2, db=db,
        ))
    # Multi-ticker no longer blocks; only runs_exhausted fires after first run.
    assert exc.value.detail["entitlement"]["code"] == "anonymous_runs_exhausted"


def test_anonymous_first_run_a_share_ticker_passes_gate(db: Session) -> None:
    """Same as above but with an A-share suffix. The asset-class gate was
    removed; the engine handles missing data cleanly downstream."""
    import asyncio
    import pytest as _pt
    from fastapi import HTTPException
    from app.api.routes.anonymous import (
        anonymous_backtest_run,
        AnonymousBacktestRunRequest,
    )

    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)
    increment_anonymous_run(db, session, backtest_id="bt-prior")

    req2 = _stub_request(cookies={COOKIE_NAME: session.id})
    resp2 = _stub_response()

    payload = AnonymousBacktestRunRequest(
        template_id="custom",
        strategy_json=_stub_strategy(universe=["600519.SHH"]),
    )

    with _pt.raises(HTTPException) as exc:
        asyncio.run(anonymous_backtest_run(
            payload=payload, request=req2, response=resp2, db=db,
        ))
    # A-share ticker no longer blocks; only runs_exhausted fires.
    assert exc.value.detail["entitlement"]["code"] == "anonymous_runs_exhausted"
