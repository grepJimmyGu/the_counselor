"""PRD-16a-2 — preview endpoint tests.

Mocks `PriceDataService.get_price_frame` so tests don't hit the real
db cache or Alpha Vantage. Also overrides `get_db` to return None — the
route threads `db` through to the (mocked) provider, which ignores it.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def _noop_db():
    """Stub get_db override — yields None so the route's `db` arg is
    set, but the real DB never opens. The route uses `db` only as an
    argument to the provider's `get_signal_frame`, which the test
    fixture below mocks."""
    yield None


app.dependency_overrides[get_db] = _noop_db
client = TestClient(app)


def _stub_frame(periods: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0005, 0.012, periods)
    closes = 100 * np.exp(np.cumsum(returns))
    highs = closes * 1.01
    lows = closes * 0.99
    opens = closes
    volume = np.ones(periods) * 1_000_000
    dates = pd.date_range(end=date.today(), periods=periods, freq="B")
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "adjusted_close": closes, "volume": volume,
    }, index=dates)


@pytest.fixture(autouse=True)
def patch_price_service():
    """Every test in this file gets a stub PriceDataService so they
    don't hit real DB or Alpha Vantage.

    Patches the method on the class so already-instantiated registry
    instances pick up the stub too (the registry instantiates providers
    at module load, before any test fixture runs)."""
    async def fake_get(self, _db, _symbol, _start, _end, lookback_days=0):
        return _stub_frame(periods=300 + lookback_days)

    from app.services.price_data_service import PriceDataService
    with patch.object(PriceDataService, "get_price_frame", fake_get):
        yield


def test_preview_rsi_returns_series() -> None:
    r = client.get("/api/signal-primitives/rsi/preview?symbol=SPY&days=120")
    assert r.status_code == 200
    body = r.json()
    assert body["primitive_id"] == "rsi"
    assert body["symbol"] == "SPY"
    assert "series" in body
    assert len(body["series"]) > 50
    # The default RSI period of 14 should appear in the parameters echo.
    assert body["parameters"]["period"] == 14


def test_preview_supports_parameter_override_via_query() -> None:
    """Per Mr Gu's 2026-06-09 call: allow query-string override on the
    preview endpoint. Passing `period=21` should flow through to the
    provider."""
    r = client.get("/api/signal-primitives/rsi/preview?symbol=SPY&period=21")
    assert r.status_code == 200
    body = r.json()
    assert body["parameters"]["period"] == 21


def test_preview_404s_for_unknown_primitive_id() -> None:
    r = client.get("/api/signal-primitives/does-not-exist/preview")
    assert r.status_code == 404


def test_preview_400s_on_invalid_parameter_value() -> None:
    """A non-int value for an int parameter should produce a 400, not
    silently coerce to something wrong."""
    r = client.get("/api/signal-primitives/rsi/preview?period=not-a-number")
    assert r.status_code == 400
    assert "period" in r.json()["detail"]


def test_preview_default_symbol_is_spy() -> None:
    """If no symbol query param is provided, default to SPY."""
    r = client.get("/api/signal-primitives/rsi/preview")
    assert r.status_code == 200
    assert r.json()["symbol"] == "SPY"


def test_preview_symbol_uppercased_in_response() -> None:
    """Backend uppercases for cache consistency — response should reflect."""
    r = client.get("/api/signal-primitives/rsi/preview?symbol=nvda")
    assert r.status_code == 200
    assert r.json()["symbol"] == "NVDA"


def test_preview_series_dates_are_iso_strings() -> None:
    """Frontend chart libraries expect ISO date strings, not Timestamp objects."""
    r = client.get("/api/signal-primitives/rsi/preview?days=60")
    body = r.json()
    if body["series"]:
        sample = body["series"][0]["date"]
        # YYYY-MM-DD format.
        assert len(sample) == 10
        assert sample[4] == "-" and sample[7] == "-"


def test_preview_nan_values_serialize_as_null() -> None:
    """JSON has no NaN — pandas NaN must serialize as null.

    The route slices warmup bars OUT before returning, so for a typical
    well-warmed indicator like RSI(14) on a 60-day request, no nulls
    should appear in the visible series — but the serialization path
    must still produce valid JSON. We verify by checking that no `value`
    is a string "NaN" (would indicate a json.dumps default-handler bug).
    """
    r = client.get("/api/signal-primitives/rsi/preview?days=60")
    body = r.json()
    for pt in body["series"]:
        assert pt["value"] is None or isinstance(pt["value"], (int, float))


def test_preview_days_clamped_to_reasonable_range() -> None:
    """`days` has explicit min/max in the route signature."""
    r = client.get("/api/signal-primitives/rsi/preview?days=10")
    assert r.status_code == 422  # below min=30
    r = client.get("/api/signal-primitives/rsi/preview?days=999999")
    assert r.status_code == 422  # above max=2000


def test_preview_unknown_query_params_ignored_not_400() -> None:
    """The frontend may pass garbage query params (URL-builder noise).
    The route should ignore them, not 400."""
    r = client.get(
        "/api/signal-primitives/rsi/preview?symbol=SPY&fbclid=abc&_=12345"
    )
    assert r.status_code == 200
