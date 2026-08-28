"""PRD-43b §3.7 — the deep-view route.

The route assertions here are the ones §6 marks: the handler must be `def`
(trap #21 — a blocking SDK call on the event loop is what cost 14 consecutive
deploys), the cache must actually hit, and the Mirror's summary route must not
have been forked.
"""

from __future__ import annotations

import inspect

from app.api.routes import mirror as mirror_route


def test_the_handler_is_def_not_async_def():
    """MANDATORY. `list_activities` is a blocking SnapTrade SDK call. As
    `async def` it would block the event loop that serves /health, which is
    trap #21's exact production failure."""
    assert not inspect.iscoroutinefunction(mirror_route.mirror_timing)


def test_the_route_is_mounted_where_the_prd_says():
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/api/mirror/timing" in paths
    # 43a's ban is on forking a second *behavior* route; the summary stays put.
    assert "/api/snaptrade/behavior" in paths
    assert "/api/mirror/analyze" not in paths


def test_the_cache_returns_the_stored_view_and_expires():
    mirror_route._cache_clear()
    sentinel = mirror_route.TimingView()
    mirror_route._cache_put("timing:u1", sentinel)
    assert mirror_route._cache_get("timing:u1") is sentinel
    assert mirror_route._cache_get("timing:nobody") is None

    mirror_route._CACHE["timing:u1"] = (0.0, sentinel)      # far in the past
    assert mirror_route._cache_get("timing:u1") is None


def test_the_cache_evicts_rather_than_growing_without_bound():
    mirror_route._cache_clear()
    for i in range(mirror_route._CACHE_MAX_ENTRIES + 25):
        mirror_route._cache_put(f"timing:u{i}", mirror_route.TimingView())
    assert len(mirror_route._CACHE) <= mirror_route._CACHE_MAX_ENTRIES


def test_the_hourly_cap_refuses_rather_than_hammering_the_broker():
    import pytest
    from fastapi import HTTPException

    mirror_route._cache_clear()
    for _ in range(mirror_route._TIMING_HOURLY_CAP):
        mirror_route._rate_limit("u-heavy")
    with pytest.raises(HTTPException) as exc:
        mirror_route._rate_limit("u-heavy")
    assert exc.value.status_code == 429
    # One user's cap is not another's.
    mirror_route._rate_limit("u-quiet")


def test_the_response_can_serialise_an_empty_record():
    """A user who connected an account and has not traded gets an empty view,
    not a 500."""
    view = mirror_route.TimingView()
    payload = view.model_dump()
    assert payload["coverage"]["episodes_total"] == 0
    assert payload["leaks"] == []
    assert payload["opening_entry_profile"]["has_consistent_pattern"] is False
