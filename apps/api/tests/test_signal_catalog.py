"""PRD-16a-1 — catalog data quality tests.

These are the editorial-discipline tests. They enforce the minimums the
PRD calls "editorial product" — description length, parameter presence,
no duplicate IDs, etc. — at CI time so future edits to the catalog
can't silently regress quality.

Tests target the in-memory catalog (`SIGNAL_PRIMITIVES`), not the
endpoint. The endpoint tests live in `test_catalog_endpoint.py`.

Adding a new primitive? Run `pytest tests/test_signal_catalog.py` —
if it fails, you've drifted from the catalog's editorial bar.
"""
from __future__ import annotations

import pytest

from app.data.signal_primitives import (
    SIGNAL_PRIMITIVES,
    get_catalog_version_hash,
)
from app.schemas.signal_primitive import (
    Parameter,
    SignalCategory,
    SignalPrimitive,
)


# ── Catalog-level invariants ─────────────────────────────────────────────────


def test_catalog_meets_acceptance_minimum_50_entries() -> None:
    """PRD-16a acceptance checklist: '≥ 50 entries spanning all 8 categories.'
    We ship 55; this test fails the moment someone drops below 50."""
    assert len(SIGNAL_PRIMITIVES) >= 50, (
        f"Catalog has {len(SIGNAL_PRIMITIVES)} primitives, "
        "PRD acceptance requires ≥ 50."
    )


def test_catalog_covers_all_8_categories() -> None:
    """Every `SignalCategory` value must have at least one primitive.
    An empty category would render an empty filter button in the
    catalog browser — bad UX."""
    covered = {p.category for p in SIGNAL_PRIMITIVES}
    missing = set(SignalCategory) - covered
    assert not missing, f"Catalog missing primitives in categories: {missing}"


def test_no_duplicate_ids() -> None:
    """IDs are the primary key for catalog lookups + URL slugs. A
    duplicate means the second entry silently overrides the first
    when fetched via `_find_primitive(primitive_id)` (PRD-16a-2)."""
    ids = [p.id for p in SIGNAL_PRIMITIVES]
    assert len(ids) == len(set(ids)), (
        "Duplicate primitive IDs: "
        f"{[i for i in ids if ids.count(i) > 1]}"
    )


def test_no_duplicate_names() -> None:
    """Display names should be unique too — two cards with the same name
    in the catalog browser confuses the user."""
    names = [p.name for p in SIGNAL_PRIMITIVES]
    assert len(names) == len(set(names)), (
        "Duplicate primitive names: "
        f"{[n for n in names if names.count(n) > 1]}"
    )


# ── Per-primitive editorial invariants ───────────────────────────────────────


@pytest.mark.parametrize("primitive", SIGNAL_PRIMITIVES, ids=lambda p: p.id)
def test_description_is_at_least_30_chars(primitive: SignalPrimitive) -> None:
    """PRD-16a acceptance: 'description ≥ 30 chars'. Below that you're
    not giving the user enough to understand what the primitive does."""
    assert len(primitive.description) >= 30, (
        f"Primitive '{primitive.id}' has a description of "
        f"{len(primitive.description)} chars; need ≥ 30."
    )


@pytest.mark.parametrize("primitive", SIGNAL_PRIMITIVES, ids=lambda p: p.id)
def test_at_least_one_parameter(primitive: SignalPrimitive) -> None:
    """PRD-16a acceptance: '≥ 1 parameter'. Without a parameter, the
    composer has no knob to expose — the primitive can't be tuned."""
    assert len(primitive.parameters) >= 1, (
        f"Primitive '{primitive.id}' has no parameters — composer can't tune it."
    )


@pytest.mark.parametrize("primitive", SIGNAL_PRIMITIVES, ids=lambda p: p.id)
def test_asset_compat_non_empty(primitive: SignalPrimitive) -> None:
    """If a primitive applies to NO asset class, it shouldn't be in the
    catalog — there's nothing the user could backtest it against."""
    assert len(primitive.asset_compat) >= 1, (
        f"Primitive '{primitive.id}' has empty asset_compat — what does it apply to?"
    )


@pytest.mark.parametrize("primitive", SIGNAL_PRIMITIVES, ids=lambda p: p.id)
def test_no_prescriptive_language_in_description(primitive: SignalPrimitive) -> None:
    """Pitfall A in PRD-16a: descriptions are descriptive ('measures X')
    not prescriptive ('buy when Y'). Catches the most common drift —
    'Buy when RSI < 30' creeping into the description field.

    Word list is intentionally conservative; if a legitimate use needs
    one of these words, add `# noqa: prescriptive` to the entry and
    update this skip list.
    """
    prescriptive_words = {
        "buy when",
        "sell when",
        "long when",
        "short when",
        "exit when",
        "enter when",
    }
    lower = primitive.description.lower()
    matches = [w for w in prescriptive_words if w in lower]
    assert not matches, (
        f"Primitive '{primitive.id}' uses prescriptive language "
        f"in description: {matches}. PRD-16a pitfall A: catalog "
        "voice is descriptive ('measures X'), not prescriptive."
    )


@pytest.mark.parametrize("primitive", SIGNAL_PRIMITIVES, ids=lambda p: p.id)
def test_parameters_have_default_values(primitive: SignalPrimitive) -> None:
    """The composer needs a default to pre-fill. A missing default
    (None) renders an empty input — user has to guess what the
    canonical value is."""
    for param in primitive.parameters:
        assert param.default is not None, (
            f"Primitive '{primitive.id}' parameter '{param.name}' "
            "has no default — composer can't pre-fill."
        )


# ── Existing-provider sanity ─────────────────────────────────────────────────


_EXISTING_PROVIDER_KEYS = {
    "fcf_yield",
    "book_to_market",
    "ebitda_ev",
    "f_score",
    "buyback_yield_ttm",
    "estimate_revision_3m",
    "sentiment_score",
    "earnings_surprise",
    "insider_net_buy",
}


def test_provider_impls_pointing_to_existing_registry_actually_exist() -> None:
    """For the subset of catalog entries whose `provider_impl` matches a
    registry key that's already on `main`, ensure the lookup actually
    resolves — i.e. we didn't typo a key.

    PRD-16a-2 will fill in the ~46 new keys; for now, only validate the
    9 existing ones.
    """
    from app.services.backtester.signal_provider import get_signal_provider

    for primitive in SIGNAL_PRIMITIVES:
        if primitive.provider_impl in _EXISTING_PROVIDER_KEYS:
            try:
                get_signal_provider(primitive.provider_impl)
            except KeyError as exc:
                pytest.fail(
                    f"Primitive '{primitive.id}' references "
                    f"provider_impl='{primitive.provider_impl}' "
                    f"which is in EXISTING_PROVIDER_KEYS but not "
                    f"actually registered: {exc}"
                )


def test_all_catalog_provider_impls_are_registered() -> None:
    """PRD-16a-2 ships all ~46 new SignalProvider impls. Every catalog
    entry's `provider_impl` should now resolve via `get_signal_provider`.

    Before 16a-2 this test asserted the opposite ("not yet in registry");
    16a-2 flipped the semantics. The catalog and the registry should
    stay in lockstep — adding a new primitive without a provider impl
    is a contract violation.

    Uses `all_registered_provider_names()` instead of `_REGISTRY` directly
    so the lazy-registration trigger fires (`_REGISTRY` is initially
    only fundamentals + sentiment until the technical providers are
    folded in on first call).
    """
    from app.services.backtester.signal_provider import (
        all_registered_provider_names,
    )

    catalog_keys = {p.provider_impl for p in SIGNAL_PRIMITIVES}
    registered = set(all_registered_provider_names())
    missing = catalog_keys - registered
    assert not missing, (
        f"Catalog references provider impls {missing} that are not "
        "in _REGISTRY. Either the technical_signal_providers module "
        "didn't register them, or the catalog has a typo."
    )


# ── Version hash ──────────────────────────────────────────────────────────────


def test_version_hash_is_deterministic_across_calls() -> None:
    """Same catalog content → same hash. The endpoint's ETag depends on
    this; an unstable hash would break the conditional-GET pattern."""
    h1 = get_catalog_version_hash()
    h2 = get_catalog_version_hash()
    assert h1 == h2


def test_version_hash_is_short_and_url_safe() -> None:
    """ETags travel in HTTP headers — keep them short. We use 16-char
    sha256 prefix; ~17 bits of collision space per character, plenty
    for catalog versioning."""
    h = get_catalog_version_hash()
    assert len(h) == 16
    assert h.isalnum()
