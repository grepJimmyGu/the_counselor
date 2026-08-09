"""Class-share tickers must reach FMP in the hyphen form — on EVERY endpoint.

Trap #15 says our universes carry the dot form (BRK.B) and FMP wants the hyphen
(BRK-B). The rule was applied per-method, and per-method didn't hold: an audit
found SEVEN of ten symbol-taking methods still missing it (profile, income
statement, cash flow, balance sheet, peers, revenue segments, geo segments).
#283 fixed `get_key_metrics` alone, so a class share got a P/E and then failed
its profile — a half-populated row, which is worse than an empty one because
the stale dividend value survives.

Caught live in the Russell 3000 backfill:

    WARNING BF.A: profile failed (No profile data for BF.A)
    WARNING BRK.B: profile failed (No profile data for BRK.B)

The translation now lives in `_get`, so a new endpoint inherits it. The
important half of this test file is the CN case: `cn_overview_service` calls
`_get("/profile", {"symbol": "000001.SZ"})` directly, so a blanket
`replace(".", "-")` would corrupt every Chinese ticker into `000001-SZ`. Only a
SINGLE-letter suffix is a class share.
"""
from __future__ import annotations

import pytest

from app.services.fmp_client import FMPClient, _to_fmp_symbol


@pytest.mark.parametrize(
    "given,expected",
    [
        ("BRK.B", "BRK-B"),
        ("BF.A", "BF-A"),
        ("BF.B", "BF-B"),
        ("brk.b", "BRK-B"),  # case-normalised on the way out
    ],
)
def test_class_shares_become_hyphenated(given, expected) -> None:
    assert _to_fmp_symbol(given) == expected


@pytest.mark.parametrize("given", ["000001.SZ", "600519.SS", "300750.SZ"])
def test_cn_tickers_are_left_alone(given) -> None:
    """The load-bearing case. `cn_overview_service` sends these to `_get`
    verbatim; hyphenating them would 404 every Chinese company page."""
    assert _to_fmp_symbol(given) == given


@pytest.mark.parametrize("given", ["AAPL", "MSFT", "ABC.DE", "A"])
def test_ordinary_symbols_are_unchanged(given) -> None:
    assert _to_fmp_symbol(given) == given.upper()


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):  # noqa: D102
        return None

    def json(self):  # noqa: D102
        return [{}]


def _capture_outbound(monkeypatch) -> dict:
    """Intercept at the HTTP layer, BELOW `_get`.

    Patching `_get` would remove the code under test — the translation lives
    there. This asserts on the params actually put on the wire.
    """
    sent: dict = {}

    async def fake_http_get(self, url, params=None):
        sent[url.rsplit("/", 1)[-1] or url] = (params or {}).get("symbol")
        return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_http_get)
    monkeypatch.setattr(FMPClient, "_api_key", lambda self: "test-key")
    return sent


@pytest.mark.asyncio
async def test_every_endpoint_translates_not_just_the_ones_we_remembered(monkeypatch) -> None:
    """The regression: this must hold for methods nobody thought about."""
    sent = _capture_outbound(monkeypatch)
    c = FMPClient()

    await c.get_profile("BRK.B")
    await c.get_key_metrics("BRK.B")
    await c.get_income_statement("BRK.B")
    await c.get_cash_flow("BRK.B")
    await c.get_balance_sheet("BRK.B")

    assert sent, "no outbound calls recorded"
    for endpoint, sym in sent.items():
        assert sym == "BRK-B", f"/{endpoint} sent {sym!r}, not the hyphen form"


@pytest.mark.asyncio
async def test_cn_symbol_survives_the_same_path(monkeypatch) -> None:
    sent = _capture_outbound(monkeypatch)
    await FMPClient().get_profile("000001.SZ")
    assert set(sent.values()) == {"000001.SZ"}
