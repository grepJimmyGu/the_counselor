"""PRD-22c slice b — reading layer (`intent_group` + `reading`).

The intent-first composer fronts the catalog with "what are you reading?"
chips. Every primitive must get an `intent_group` (an override or its category
default) and a short `reading` headline, backfilled in one place
(`app/data/signal_primitives.py`). Additive + runtime no-op — only the composer
and the catalog payload read these fields.
"""
from __future__ import annotations

from app.data.signal_primitives import (
    SIGNAL_PRIMITIVES,
    _INTENT_GROUP_OVERRIDES,
    _READINGS,
)
from app.schemas.signal_primitive import IntentGroup


# ── Backfill coverage (the guard) ────────────────────────────────────────────


def test_every_primitive_has_an_intent_group() -> None:
    """The chip grouping is required for every primitive — None would drop it
    out of the composer's 'what are you reading?' chips."""
    for p in SIGNAL_PRIMITIVES:
        assert p.intent_group is not None, f"{p.id} missing intent_group"
        assert isinstance(p.intent_group, IntentGroup)


def test_every_primitive_has_a_reading() -> None:
    """Every primitive carries a short reading headline (this fails the moment
    a new primitive is added without one in `_READINGS`)."""
    for p in SIGNAL_PRIMITIVES:
        assert p.reading, f"{p.id} missing reading headline"
        assert len(p.reading) <= 80, f"{p.id} reading too long: {p.reading!r}"


def test_editorial_maps_reference_only_real_ids() -> None:
    """No typo'd ids in `_READINGS` / `_INTENT_GROUP_OVERRIDES` — a bad id would
    silently never apply."""
    catalog_ids = {p.id for p in SIGNAL_PRIMITIVES}
    assert set(_READINGS) <= catalog_ids, (
        f"unknown ids in _READINGS: {set(_READINGS) - catalog_ids}"
    )
    assert set(_INTENT_GROUP_OVERRIDES) <= catalog_ids, (
        f"unknown ids in overrides: {set(_INTENT_GROUP_OVERRIDES) - catalog_ids}"
    )


# ── Taxonomy ─────────────────────────────────────────────────────────────────


def test_intent_group_enum_has_the_nine_values() -> None:
    assert {g.value for g in IntentGroup} == {
        "trend", "momentum", "overbought_oversold", "breakout", "volatility",
        "volume", "value_quality", "sentiment_events", "relative_strength",
    }


def test_cross_cutting_overrides_applied() -> None:
    by_id = {p.id: p for p in SIGNAL_PRIMITIVES}
    # macd is a TREND-category primitive that reads as a momentum shift.
    assert by_id["macd"].intent_group == IntentGroup.MOMENTUM
    # The breakout / 52-week-extrema family (MOMENTUM category) → BREAKOUT.
    for pid in ("donchian_breakout", "distance_to_52w_high",
                "price_52w_high_breakout", "price_in_52w_high_zone",
                "days_since_52w_high"):
        assert by_id[pid].intent_group == IntentGroup.BREAKOUT, pid
    # Growth/event signals in the FUNDAMENTAL category → SENTIMENT_EVENTS.
    assert by_id["estimate_revision_3m"].intent_group == IntentGroup.SENTIMENT_EVENTS
    assert by_id["earnings_surprise"].intent_group == IntentGroup.SENTIMENT_EVENTS


def test_category_defaults_applied_for_non_overrides() -> None:
    by_id = {p.id: p for p in SIGNAL_PRIMITIVES}
    expected = {
        "sma": IntentGroup.TREND,
        "rsi": IntentGroup.OVERBOUGHT_OVERSOLD,
        "roc": IntentGroup.MOMENTUM,            # MOMENTUM category, no override
        "obv": IntentGroup.VOLUME,
        "atr": IntentGroup.VOLATILITY,
        "fcf_yield": IntentGroup.VALUE_QUALITY,
        "sentiment_score": IntentGroup.SENTIMENT_EVENTS,
        "rank_return_6m": IntentGroup.RELATIVE_STRENGTH,
    }
    for pid, group in expected.items():
        assert by_id[pid].intent_group == group, pid


# ── Serialization ────────────────────────────────────────────────────────────


def test_fields_serialize_as_strings_in_payload() -> None:
    p = next(x for x in SIGNAL_PRIMITIVES if x.id == "rsi")
    dumped = p.model_dump()
    assert dumped["intent_group"] == "overbought_oversold"
    assert isinstance(dumped["intent_group"], str)
    assert dumped["reading"] == "Overbought / oversold extreme"
