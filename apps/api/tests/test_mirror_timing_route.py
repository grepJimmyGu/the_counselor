"""PRD-43b §3.7 — the deep-view route.

The route assertions here are the ones §6 marks: the handler must be `def`
(trap #21 — a blocking SDK call on the event loop is what cost 14 consecutive
deploys), the cache must actually hit, and the Mirror's summary route must not
have been forked.
"""

from __future__ import annotations

import inspect

import pytest

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


# ── the exit plan ───────────────────────────────────────────────────────────


def _plan(**over):
    from app.api.routes.mirror import ExitPlanRequest
    payload = {"take_profit_pct": 0.10, "take_profit_fraction": 0.333,
               "stop_pct": -0.08}
    payload.update(over)
    return ExitPlanRequest(**payload)


def test_the_server_cannot_invent_a_stop(db, make_user):
    """PRD-43e §4.2 and the attach endpoint's own rule: a stop the user did
    not choose is one they will not believe when it fires. `stop_pct` is
    required and must be negative — there is no default to fall back on."""
    import pydantic
    from app.api.routes.mirror import ExitPlanRequest

    with pytest.raises(pydantic.ValidationError):
        ExitPlanRequest(take_profit_pct=0.10, take_profit_fraction=0.333)
    with pytest.raises(pydantic.ValidationError):
        _plan(stop_pct=0.08)          # a stop above entry is not a stop


def test_the_take_profit_must_be_a_partial_not_the_whole_position(db, make_user):
    """`sell_fraction` with fraction 1.0 is `sell_all` wearing a disguise, and
    the point of the rung is to take SOME off while the position runs."""
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        _plan(take_profit_fraction=1.0)
    with pytest.raises(pydantic.ValidationError):
        _plan(take_profit_fraction=0.0)


def test_the_ladder_is_ordered_stop_first(db, make_user):
    """Tiers are evaluated in ascending trigger order, so the stop must be the
    first element — otherwise a take-profit could fire on a bar that also
    breached the stop."""
    from app.api.routes.mirror import ExitPlanRequest  # noqa: F401
    from app.schemas.strategy import RiskManagement

    ladder = [
        {"trigger_pct": -0.08, "action": "sell_all", "label": "Stop"},
        {"trigger_pct": 0.10, "action": "sell_fraction", "fraction": 0.333,
         "label": "TP1"},
    ]
    rm = RiskManagement(exit_ladder=ladder)
    triggers = [t.trigger_pct for t in rm.exit_ladder]
    assert triggers == sorted(triggers)
    assert triggers[0] < 0


def test_a_ladder_with_no_stop_is_refused_by_the_real_validator(db, make_user):
    """The reason the form cannot omit one. This asserts against
    `RiskManagement` itself rather than a copy of its rule."""
    from app.schemas.strategy import RiskManagement

    with pytest.raises(Exception, match="stop"):
        RiskManagement(exit_ladder=[
            {"trigger_pct": 0.10, "action": "sell_fraction", "fraction": 0.5},
        ])


def test_the_endpoint_is_def_not_async():
    """It reads brokerage holdings — a blocking SDK call (trap #21)."""
    from app.api.routes.mirror import create_exit_plan
    assert not inspect.iscoroutinefunction(create_exit_plan)


def test_the_ladder_is_set_at_CREATE_time_never_written_onto_a_strategy():
    """The sign-off guard bans assigning `exit_ladder` onto an existing
    strategy; it deliberately permits a ladder that arrived in the creating
    request, because then what landed is what the client rendered.

    This pins that the endpoint takes the second route — the ladder appears
    only inside the strategy payload it builds, never as an assignment.
    """
    import re
    from pathlib import Path
    import app.api.routes.mirror as mod

    src = Path(mod.__file__).read_text()
    assert not re.search(r"""(\[\s*['"]exit_ladder['"]\s*\]|\.exit_ladder)\s*=(?!=)""", src)
    assert '"risk_management": {"exit_ladder": ladder}' in src
