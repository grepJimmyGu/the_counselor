"""PRD-16a-3 — KB lookup tests.

Two layers:
  - `test_template_signal_metadata.py`-style: editorial invariants on
    the metadata file (every template has categories + thresholds; the
    threshold primitive IDs are all real catalog entries).
  - Endpoint behavior: representative match queries return the expected
    top result.

Tests target the matcher service + the POST route. No mocking — the
metadata is in-process content.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.data.template_signal_metadata import (
    TEMPLATE_SIGNAL_METADATA,
    all_template_ids,
    get_template_categories,
    get_template_thresholds,
)
from app.main import app
from app.schemas.signal_primitive import SignalCategory
from app.services.signal_combo_matcher import match_templates

client = TestClient(app)


# ── Metadata editorial invariants ────────────────────────────────────────────


def test_every_backend_template_has_signal_metadata() -> None:
    """The chat_tools template catalog has 19 entries. We require
    metadata for every one of them — otherwise the matcher silently
    skips templates and gives weaker recommendations.

    If this test fails on a future PR that adds a new template to
    `template_search.py`, the fix is to author a metadata entry here
    too (categories + thresholds)."""
    from app.services.chat_tools.template_search import _CATALOG
    backend_ids = {t["id"] for t in _CATALOG}
    metadata_ids = set(all_template_ids())
    missing = backend_ids - metadata_ids
    assert not missing, (
        f"Templates without signal metadata: {missing}. "
        "Add entries to TEMPLATE_SIGNAL_METADATA."
    )


@pytest.mark.parametrize("template_id", all_template_ids())
def test_each_template_has_non_empty_categories(template_id: str) -> None:
    cats = get_template_categories(template_id)
    assert cats, f"Template '{template_id}' has empty categories set."


@pytest.mark.parametrize("template_id", all_template_ids())
def test_each_template_has_non_empty_thresholds(template_id: str) -> None:
    thresholds = get_template_thresholds(template_id)
    assert thresholds, f"Template '{template_id}' has empty thresholds map."


@pytest.mark.parametrize("template_id", all_template_ids())
def test_each_template_threshold_primitive_ids_exist_in_catalog(template_id: str) -> None:
    """A typoed primitive_id in the thresholds map would silently fail
    to apply when the user picks that primitive — catch it at CI time
    rather than in production."""
    catalog_ids = {p.id for p in SIGNAL_PRIMITIVES}
    thresholds = get_template_thresholds(template_id)
    bad = set(thresholds.keys()) - catalog_ids
    assert not bad, (
        f"Template '{template_id}' threshold map references non-catalog "
        f"primitive IDs: {bad}."
    )


# ── Matcher algorithm tests ────────────────────────────────────────────────


def test_empty_primitive_list_returns_no_matches() -> None:
    """Edge case: the user hasn't picked anything yet → no matches."""
    matches = match_templates([])
    assert matches == []


def test_unknown_primitive_ids_are_silently_dropped() -> None:
    """The matcher is best-effort. Garbage IDs in the input don't 500;
    they just don't contribute to the user's category set."""
    matches = match_templates(["garbage_primitive", "also-not-real"])
    assert matches == []


def test_rsi_bbands_top_matches_bollinger_mean_reversion() -> None:
    """The PRD's canonical example: {RSI, BBANDS} should match the
    Bollinger Mean Reversion template at the top."""
    matches = match_templates(["rsi", "bbands"])
    assert matches, "Expected at least one match for RSI+Bollinger combo."
    assert matches[0]["template_id"] == "bollinger-mean-reversion"


def test_ma_donchian_atr_top_matches_trend_following() -> None:
    """The PRD's other canonical example: a MA + breakout + ATR combo
    should anchor on the Trend Following template."""
    matches = match_templates(["sma", "donchian_breakout", "atr"])
    assert matches, "Expected at least one match for MA+breakout+ATR combo."
    assert matches[0]["template_id"] == "trend-following"


def test_fundamental_ranked_matches_value_composite() -> None:
    """Three fundamental value primitives should anchor on the Value
    Composite template, which is the multi-fundamental cross-sectional
    template in the catalog."""
    matches = match_templates(["book_to_market", "ebitda_ev", "fcf_yield"])
    assert matches
    # Either Value Composite or Quality Piotroski could plausibly tie on
    # similarity (both are FUNDAMENTAL + CROSS_SECTIONAL); the matcher
    # ties-breaks alphabetically. We just check Value Composite is in
    # the top 3.
    top_3_ids = {m["template_id"] for m in matches[:3]}
    assert "value-composite-cs" in top_3_ids


def test_top_n_caps_result_length() -> None:
    matches = match_templates(["rsi", "bbands"], top_n=1)
    assert len(matches) == 1


def test_top_n_clamped_to_max_10() -> None:
    """The endpoint clamps top_n to [1, 10]. The service doesn't enforce
    its own ceiling, but the endpoint test verifies the response is
    capped — we'd be returning 19 rows for any matched-everywhere query
    otherwise."""
    r = client.post(
        "/api/signal-combos/match-templates",
        json={"primitive_ids": ["rsi", "macd"], "top_n": 100},
    )
    assert r.status_code == 200
    assert len(r.json()["matches"]) <= 10


def test_thresholds_only_include_user_picked_primitives() -> None:
    """Composer's pre-fill needs the thresholds for primitives the user
    actually selected — surfacing other primitives' thresholds would be
    UX noise."""
    matches = match_templates(["bbands"])
    bm = next(m for m in matches if m["template_id"] == "bollinger-mean-reversion")
    # Bollinger Mean Reversion's catalog has only `bbands` as a threshold
    # primitive — and the user picked bbands — so we should see it.
    assert "bbands" in bm["thresholds_for_user_primitives"]
    # No threshold for primitives the template uses that the user didn't.
    # (BMR currently only has bbands threshold, so this case is implicit.)


def test_similarity_descending_order() -> None:
    """Results sorted by similarity descending — otherwise the composer
    can't reliably pick 'best match.'"""
    matches = match_templates(["rsi", "bbands", "sma"])
    similarities = [m["similarity"] for m in matches]
    assert similarities == sorted(similarities, reverse=True)


def test_shared_categories_field_is_subset_of_both() -> None:
    matches = match_templates(["rsi", "bbands"])
    if matches:
        top = matches[0]
        user_cats = {SignalCategory.MEAN_REVERSION}
        template_cats = get_template_categories(top["template_id"])
        for cat in top["shared_categories"]:
            assert cat in user_cats
            assert cat in template_cats


# ── Endpoint tests ──────────────────────────────────────────────────────────


def test_endpoint_returns_matches_for_rsi_bbands() -> None:
    r = client.post(
        "/api/signal-combos/match-templates",
        json={"primitive_ids": ["rsi", "bbands"], "top_n": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert "matches" in body
    assert len(body["matches"]) > 0
    assert body["matches"][0]["template_id"] == "bollinger-mean-reversion"


def test_endpoint_returns_empty_for_empty_input() -> None:
    r = client.post(
        "/api/signal-combos/match-templates",
        json={"primitive_ids": []},
    )
    assert r.status_code == 200
    assert r.json()["matches"] == []


def test_endpoint_shared_categories_serialized_as_strings() -> None:
    """JSON response shape — shared_categories must be string values, not
    enum instances, so the frontend can filter on them."""
    r = client.post(
        "/api/signal-combos/match-templates",
        json={"primitive_ids": ["rsi", "bbands"]},
    )
    body = r.json()
    for match in body["matches"]:
        for cat in match["shared_categories"]:
            assert isinstance(cat, str)
            # Must be a known SignalCategory value.
            assert cat in {c.value for c in SignalCategory}


def test_endpoint_requires_primitive_ids_field() -> None:
    r = client.post("/api/signal-combos/match-templates", json={})
    assert r.status_code == 422
