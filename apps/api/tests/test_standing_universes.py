"""Tests for the standing-universe registry (app/data/standing_universes.py)
and its wiring through the resolver + the scan/save request validators
(R3000 expansion — PROJECT_BACKLOG §4 prewarm-universe registry)."""
from __future__ import annotations

import pytest

from app.data.standing_universes import (
    STANDING_UNIVERSES,
    all_standing_symbols,
    is_standing_id,
    standing_universe_ids,
    standing_universe_symbols,
)
from app.schemas.screener_scan import ScreenSaveRequest, ScreenScanRequest
from app.services.screener.universe_resolver import (
    is_standing_universe,
    resolve_universe,
)


def test_registry_has_sp500_and_russell3000():
    assert {"sp500", "russell3000"} <= set(STANDING_UNIVERSES)
    assert is_standing_id("russell3000")
    assert not is_standing_id("nasdaq100")
    assert standing_universe_ids() == frozenset(STANDING_UNIVERSES)


def test_russell3000_symbols_and_union():
    r3 = standing_universe_symbols("russell3000")
    assert len(r3) == 2552
    assert r3 == sorted(r3)  # the scan relies on a stable order
    union = all_standing_symbols()
    assert union == sorted(set(union))  # deduped + sorted
    # the union covers every standing member (the warm warms it once)
    assert set(STANDING_UNIVERSES["sp500"]) <= set(union)
    assert set(r3) <= set(union)
    assert len(union) >= len(r3)


def test_resolver_treats_russell3000_as_standing():
    assert is_standing_universe("russell3000") is True
    assert is_standing_universe("sp500") is True
    assert is_standing_universe("symbols") is False
    assert resolve_universe("russell3000") == standing_universe_symbols("russell3000")


def test_scan_and_save_accept_russell3000():
    assert ScreenScanRequest(universe_id="russell3000", rules=[]).universe_id == "russell3000"
    saved = ScreenSaveRequest(title="broad-market momentum", universe_id="russell3000", rules=[])
    assert saved.universe_id == "russell3000"


def test_unregistered_universe_rejected():
    with pytest.raises(Exception):
        ScreenScanRequest(universe_id="nasdaq100", rules=[])
    with pytest.raises(Exception):
        ScreenSaveRequest(title="a valid screen title", universe_id="nasdaq100", rules=[])
    with pytest.raises(ValueError):
        resolve_universe("nasdaq100")
