"""The FMP client's connection pool.

Measured 2026-11-20: a call on a new connection takes ~0.44 s, on a kept-alive
one ~0.09 s. `FMPClient._get` opened a client, and so a connection, per call.
On the loop that serves requests it now reuses one pool; on any other loop it
behaves as before, because an httpx client belongs to the loop that made it.
"""
from __future__ import annotations

import asyncio
from typing import List

import httpx
import pytest

from app.core import concurrency
from app.services import fmp_client
from app.services.fmp_client import FMPClient, FMPRateLimitError


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else [{"symbol": "AAPL", "price": 1.0}]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]

    def json(self):
        return self._payload


class _FakeClient:
    """Counts how many clients are made and what each is asked."""
    made: List["_FakeClient"] = []
    script: List[object] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.calls = 0
        self.is_closed = False
        _FakeClient.made.append(self)

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc) -> None:
        self.is_closed = True

    async def aclose(self) -> None:
        self.is_closed = True

    async def get(self, url, params=None):
        self.calls += 1
        step = _FakeClient.script.pop(0) if _FakeClient.script else _FakeResponse()
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def fake_http(monkeypatch):
    _FakeClient.made = []
    _FakeClient.script = []
    monkeypatch.setattr(fmp_client.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(fmp_client, "_shared", None)
    monkeypatch.setattr(fmp_client, "_shared_loop", None)
    monkeypatch.setattr(FMPClient, "_api_key", lambda self: "test-key")

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(fmp_client.asyncio, "sleep", no_sleep)
    yield _FakeClient
    concurrency.set_main_loop(None)


def _on_main_loop(coro_factory):
    async def run():
        concurrency.set_main_loop(asyncio.get_running_loop())
        try:
            return await coro_factory()
        finally:
            await fmp_client.close_shared_client()
            concurrency.set_main_loop(None)

    return asyncio.run(run())


def test_calls_on_the_request_loop_share_one_client(fake_http) -> None:
    async def three_calls():
        client = FMPClient()
        for _ in range(3):
            await client._get("/quote", {"symbol": "AAPL"})
        await FMPClient()._get("/quote", {"symbol": "MSFT"})  # another instance, same pool

    _on_main_loop(three_calls)
    assert len(fake_http.made) == 1
    assert fake_http.made[0].calls == 4
    assert fake_http.made[0].is_closed  # closed at shutdown


def test_the_pool_caps_simultaneous_calls_at_the_known_safe_number(fake_http) -> None:
    _on_main_loop(lambda: FMPClient()._get("/quote", {"symbol": "AAPL"}))
    limits = fake_http.made[0].kwargs["limits"]
    assert limits.max_connections == FMPClient.CONCURRENT_QUOTE_LIMIT


def test_calls_on_any_other_loop_open_and_close_their_own_client(fake_http) -> None:
    """The warmups run on worker-thread loops. A client shared with them would
    be bound to a loop that goes away (trap 22)."""
    async def two_calls():
        client = FMPClient()
        await client._get("/quote", {"symbol": "AAPL"})
        await client._get("/quote", {"symbol": "AAPL"})

    asyncio.run(two_calls())  # no main loop registered
    assert len(fake_http.made) == 2
    assert all(made.is_closed for made in fake_http.made)


def test_a_new_request_loop_gets_a_new_pool(fake_http) -> None:
    _on_main_loop(lambda: FMPClient()._get("/quote", {"symbol": "AAPL"}))
    _on_main_loop(lambda: FMPClient()._get("/quote", {"symbol": "AAPL"}))
    assert len(fake_http.made) == 2


def test_a_dropped_kept_alive_connection_is_retried_once(fake_http) -> None:
    """The cost of keeping connections: the far end may have closed one that
    sat idle. That fails the first use and says nothing about the request."""
    fake_http.script = [httpx.RemoteProtocolError("Server disconnected"), _FakeResponse(payload=[{"ok": 1}])]
    assert _on_main_loop(lambda: FMPClient()._get("/quote", {"symbol": "AAPL"})) == [{"ok": 1}]


def test_a_connection_that_drops_twice_is_an_error(fake_http) -> None:
    fake_http.script = [httpx.RemoteProtocolError("gone"), httpx.RemoteProtocolError("gone again")]
    with pytest.raises(httpx.RemoteProtocolError):
        _on_main_loop(lambda: FMPClient()._get("/quote", {"symbol": "AAPL"}))


def test_a_one_off_client_does_not_retry_a_dropped_connection(fake_http) -> None:
    """Unchanged behaviour off the request loop: a new connection that fails
    is a real failure."""
    fake_http.script = [httpx.RemoteProtocolError("gone"), _FakeResponse()]
    with pytest.raises(httpx.RemoteProtocolError):
        asyncio.run(FMPClient()._get("/quote", {"symbol": "AAPL"}))


def test_rate_limiting_is_still_retried_then_reported(fake_http) -> None:
    fake_http.script = [_FakeResponse(429), _FakeResponse(payload=[{"ok": 1}])]
    assert _on_main_loop(lambda: FMPClient()._get("/quote", {"symbol": "AAPL"})) == [{"ok": 1}]

    fake_http.script = [_FakeResponse(429), _FakeResponse(429), _FakeResponse(429)]
    with pytest.raises(FMPRateLimitError):
        _on_main_loop(lambda: FMPClient()._get("/quote", {"symbol": "AAPL"}))
