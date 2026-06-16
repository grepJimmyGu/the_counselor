"""PRD-22a — SignalPrimitive semantics layer (output_kind / output_channels /
composes).

Two jobs:
  1. The three new schema fields default to backward-compatible values, so
     every v1 primitive that omits them behaves as VALUE / ["value"] / [].
  2. The v1 catalog backfill matches the PRD-22a §3.2 audit table EXACTLY.
     This is the regression lock: if someone changes a primitive's kind, or
     forgets to tag a new non-VALUE primitive, the test fails and names it.

PRD-22a is provably a runtime no-op — the backtest engine and the
SignalProvider impls never read these fields (grep-verified: no consumers
outside the schema, the catalog data, and these tests). The proof-of-no-op
is the rest of the suite staying green; this file only covers the new
metadata.
"""
from __future__ import annotations

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.schemas.signal_primitive import (
    OutputKind,
    Parameter,
    SignalCategory,
    SignalPrimitive,
)


def _bare_primitive(**overrides) -> SignalPrimitive:
    """Minimal valid primitive for default-behavior tests."""
    base = dict(
        id="x",
        category=SignalCategory.TREND,
        family="X",
        name="X",
        description="a placeholder description over thirty chars",
        parameters=[Parameter(name="period", default=14, description="window")],
        asset_compat=["equity"],
        evidence_tier="A",
        provider_impl="x",
        data_source="price",
    )
    base.update(overrides)
    return SignalPrimitive(**base)


# ── Schema defaults (backward compat) ────────────────────────────────────────


def test_output_kind_defaults_to_value() -> None:
    p = _bare_primitive()
    assert p.output_kind == OutputKind.VALUE
    assert p.output_channels == ["value"]
    assert p.composes == []


def test_list_field_defaults_are_per_instance_not_shared() -> None:
    """default_factory must hand each instance its own list — a shared
    mutable default would leak edits across every primitive."""
    a = _bare_primitive()
    b = _bare_primitive()
    a.output_channels.append("leak")
    a.composes.append("leak")
    assert b.output_channels == ["value"]
    assert b.composes == []


def test_output_kind_serializes_as_string() -> None:
    """`str, Enum` → the catalog JSON payload carries the value string,
    not a Python enum repr."""
    dumped = _bare_primitive(output_kind=OutputKind.EVENT).model_dump()
    assert dumped["output_kind"] == "event"
    assert isinstance(dumped["output_kind"], str)


def test_output_kind_enum_has_the_seven_v2_values() -> None:
    assert {k.value for k in OutputKind} == {
        "value", "event", "regime", "level", "distance", "cross", "divergence",
    }


# ── v1 catalog backfill lock (PRD-22a §3.2 audit table) ──────────────────────

# Ground truth: every v1 primitive whose kind is NOT the VALUE default.
# Everything else in the catalog must be VALUE.
_NON_VALUE_KINDS = {
    "ma_crossover": OutputKind.CROSS,
    "donchian_breakout": OutputKind.EVENT,
    "vol_regime": OutputKind.REGIME,
}

# Ground truth: every v1 primitive that emits MORE than a single "value"
# channel. These channel names are a PUBLIC CONTRACT — saved strategies
# reference them. Never rename; only add or deprecate.
_MULTI_CHANNEL = {
    "macd": ["macd_line", "signal_line", "histogram"],
    "adx": ["adx", "plus_di", "minus_di"],
    "stoch": ["k", "d"],
    "bbands": ["upper", "lower", "middle"],
}

# The frozen v1 catalog (PRD-16a, 55 entries). This lock scopes the
# "default-kind" assertions to v1 ONLY — PRD-22b+ adds primitives with
# legitimately non-VALUE kinds / composes, which must not trip the v1 audit.
_V1_IDS = frozenset({
    "sma", "ema", "wma", "dema", "tema", "kama", "ma_crossover", "macd", "adx",
    "aroon", "sar", "ht_trendline", "rsi", "stoch", "stochrsi", "willr", "cci",
    "cmo", "bbands", "mfi", "ultosc", "roc", "mom", "trix", "apo", "ppo",
    "donchian_breakout", "time_series_momentum", "bop", "adxr", "aroonosc",
    "obv", "ad", "adosc", "vwap", "avg_dollar_volume", "atr", "natr", "trange",
    "realized_vol", "vol_regime", "fcf_yield", "book_to_market", "ebitda_ev",
    "f_score", "buyback_yield_ttm", "estimate_revision_3m", "earnings_surprise",
    "sentiment_score", "insider_net_buy", "analyst_rating_change",
    "rank_return_6m", "rank_composite_score", "sector_rotation_rank",
    "pair_spread_zscore",
})


def test_v1_id_set_is_present_and_complete() -> None:
    """The 55 v1 ids must all still exist in the catalog (guards against a
    v1 primitive being renamed/dropped, which would silently weaken the
    audit below)."""
    catalog_ids = {p.id for p in SIGNAL_PRIMITIVES}
    assert len(_V1_IDS) == 55
    missing = _V1_IDS - catalog_ids
    assert not missing, f"v1 primitives missing from catalog: {missing}"


def test_v1_output_kind_backfill_matches_audit() -> None:
    """Lock every primitive's output_kind to the §3.2 table. Non-VALUE
    ones are pinned explicitly; every other primitive must be VALUE.
    Catches both a mis-tagged kind and a silently-defaulted one."""
    by_id = {p.id: p for p in SIGNAL_PRIMITIVES}
    for pid, expected in _NON_VALUE_KINDS.items():
        assert pid in by_id, f"audit references unknown primitive '{pid}'"
        assert by_id[pid].output_kind == expected, (
            f"'{pid}' should be {expected}, got {by_id[pid].output_kind}"
        )
    for p in SIGNAL_PRIMITIVES:
        if p.id in _V1_IDS and p.id not in _NON_VALUE_KINDS:
            assert p.output_kind == OutputKind.VALUE, (
                f"'{p.id}' should be VALUE (default), got {p.output_kind}"
            )


def test_v1_multi_channel_declarations_match_audit() -> None:
    """The four multi-channel primitives declare exactly their documented
    channels; every other primitive stays single-channel ["value"]."""
    by_id = {p.id: p for p in SIGNAL_PRIMITIVES}
    for pid, channels in _MULTI_CHANNEL.items():
        assert pid in by_id, f"audit references unknown primitive '{pid}'"
        assert by_id[pid].output_channels == channels, (
            f"'{pid}' channels drifted: {by_id[pid].output_channels} != {channels}"
        )
    for p in SIGNAL_PRIMITIVES:
        if p.id in _V1_IDS and p.id not in _MULTI_CHANNEL:
            assert p.output_channels == ["value"], (
                f"'{p.id}' should be single-channel ['value'], "
                f"got {p.output_channels}"
            )


def test_no_v1_primitive_is_derived() -> None:
    """`composes` stays [] for the v1 primitives — derived primitives
    (macd_signal_cross, divergences, …) arrive in PRD-22b and declare their
    own parents, so this lock is scoped to the frozen v1 set."""
    for p in SIGNAL_PRIMITIVES:
        if p.id in _V1_IDS:
            assert p.composes == [], f"'{p.id}' unexpectedly composes {p.composes}"


def test_cross_event_regime_kinds_all_present() -> None:
    """Smoke: the three non-VALUE kinds actually made it into the catalog —
    guards against the backfill being dropped wholesale."""
    kinds = {p.output_kind for p in SIGNAL_PRIMITIVES}
    assert OutputKind.CROSS in kinds
    assert OutputKind.EVENT in kinds
    assert OutputKind.REGIME in kinds
