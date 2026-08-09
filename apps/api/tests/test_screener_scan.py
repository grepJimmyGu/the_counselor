"""PRD-23a slice 3 — scan service.

The boolean filter over the snapshot. Verifies operator correctness via the
shared evaluator, AND/OR folds, null-cell exclusion (the key correctness
guard for shape ops), unsupported-primitive surfacing, and the per-symbol
satisfied-readings breakdown.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.schemas.strategy import StrategyRule
from app.services.screener.scan_service import readings_for_rules, scan
from app.services.screener.signal_snapshot_service import SignalSnapshotService

AS_OF = date(2026, 6, 15)

CATALOG = {p.id: p for p in SIGNAL_PRIMITIVES}


def _readings(rules):
    return readings_for_rules(rules, CATALOG)


@pytest.fixture
def seeded(db):
    """Hand-seed a 3-symbol snapshot.

    AAPL: rsi=25, sma=150, donchian_breakout=1
    MSFT: rsi=55, sma=200
    TSLA: rsi=20            (no sma, no donchian → null cells)
    """
    svc = SignalSnapshotService()
    svc.write_symbol(db, "AAPL", {"rsi": 25.0, "sma": 150.0, "donchian_breakout": 1.0}, AS_OF)
    svc.write_symbol(db, "MSFT", {"rsi": 55.0, "sma": 200.0}, AS_OF)
    svc.write_symbol(db, "TSLA", {"rsi": 20.0}, AS_OF)
    db.commit()
    return svc


def _scan(db, svc, rules):
    return scan(db, "symbols", rules, symbols=["AAPL", "MSFT", "TSLA"], snapshot_svc=svc)


def test_single_value_rule(seeded, db):
    rules = [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)]
    res = _scan(db, seeded, rules)
    assert set(res.matched) == {"AAPL", "TSLA"}  # rsi 25, 20
    assert res.matched_count == 2
    assert res.universe_size == 3
    assert res.as_of_date == AS_OF


def test_and_fold_excludes_null_cell(seeded, db):
    # RSI<30 AND sma>100. TSLA passes RSI but has no sma row → excluded.
    rules = [
        StrategyRule(primitive_id="rsi", operator="lt", threshold=30),
        StrategyRule(primitive_id="sma", operator="gt", threshold=100, logic_with_prior="AND"),
    ]
    res = _scan(db, seeded, rules)
    assert res.matched == ["AAPL"]


def test_or_fold(seeded, db):
    # RSI>50 OR sma>180 → MSFT (both), and nobody else.
    rules = [
        StrategyRule(primitive_id="rsi", operator="gt", threshold=50),
        StrategyRule(primitive_id="sma", operator="gt", threshold=180, logic_with_prior="OR"),
    ]
    res = _scan(db, seeded, rules)
    assert res.matched == ["MSFT"]


def test_event_fires_excludes_missing_cell(seeded, db):
    # The critical guard: `fires` is `value != 0`, and NaN != 0 is True in
    # pandas. Only AAPL has a donchian row (=1); MSFT/TSLA have null cells and
    # must NOT match.
    rules = [StrategyRule(primitive_id="donchian_breakout", operator="fires")]
    res = _scan(db, seeded, rules)
    assert res.matched == ["AAPL"]


def test_unsupported_primitive_is_surfaced_not_silent(seeded, db):
    # fcf_yield is a fundamental — not in the daily snapshot. It can't match,
    # and the result says so rather than silently returning empty.
    rules = [StrategyRule(primitive_id="fcf_yield", operator="gt", threshold=5)]
    res = _scan(db, seeded, rules)
    assert res.matched == []
    assert res.unsupported_primitives == ["fcf_yield"]


def test_param_override_on_covered_primitive_is_surfaced(seeded, db):
    # A period override on a covered primitive is scanned at default params
    # (the snapshot only has the default column) — surfaced, never silent.
    rules = [
        StrategyRule(
            primitive_id="rsi", operator="lt", threshold=30,
            primitive_params={"period": 7},
        )
    ]
    res = _scan(db, seeded, rules)
    assert res.default_param_primitives == ["rsi"]
    # Still evaluates against the default-param column (approximation, not empty).
    assert set(res.matched) == {"AAPL", "TSLA"}


def test_default_param_rule_not_flagged(seeded, db):
    rules = [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)]
    res = _scan(db, seeded, rules)
    assert res.default_param_primitives == []


def test_readings_explain_each_match(seeded, db):
    rules = [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)]
    res = _scan(db, seeded, rules)
    # The catalog reading headline for rsi is surfaced per matched symbol.
    assert res.readings["AAPL"]
    assert all(isinstance(r, str) and r for r in res.readings["AAPL"])


# ── Reading disambiguation ───────────────────────────────────────────────────
# The catalog's `reading` is keyed on `primitive_id` alone, so two rules on the
# same primitive used to collapse to one string. "Best Momentum Pick" carries a
# 200-day AND a 50-day `price_above_ma`; every matched row rendered "Price above
# its moving average" twice, verbatim, with no way to tell the two conditions
# apart. Readings must disambiguate by the rule's effective params.


def test_same_primitive_different_params_get_distinct_readings():
    rules = [
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 200}),
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 50}, logic_with_prior="AND"),
    ]
    out = _readings(rules)
    assert out[0] != out[1]
    assert len(set(out)) == 2
    assert "200-day" in out[0]
    assert "50-day" in out[1]
    # The catalog copy is still the head of the chip — only the param is added.
    assert all(r.startswith("Price above its moving average") for r in out)


def test_disambiguation_resolves_catalog_defaults_not_just_overrides():
    # Only the second rule sets `primitive_params`; the first inherits the
    # catalog default (200). Both must still label their real window, or the
    # pair reads as "…moving average" vs "…moving average · 50-day".
    rules = [
        StrategyRule(primitive_id="price_above_ma", operator="is_true"),
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 50}, logic_with_prior="AND"),
    ]
    out = _readings(rules)
    assert out == [
        "Price above its moving average · 200-day",
        "Price above its moving average · 50-day",
    ]


def test_multi_param_primitive_suffixes_only_the_differing_params():
    # MACD default is fast 12 / slow 26 / signal 9. Only fast+slow differ here,
    # so `signal_period` stays out of the chip — it adds no distinction.
    rules = [
        StrategyRule(primitive_id="macd", operator="gt", threshold=0),
        StrategyRule(primitive_id="macd", operator="gt", threshold=0,
                     primitive_params={"fast_period": 5, "slow_period": 35},
                     logic_with_prior="AND"),
    ]
    out = _readings(rules)
    assert out[0] != out[1]
    assert "fast 12-day, slow 26-day" in out[0]
    assert "fast 5-day, slow 35-day" in out[1]
    assert "signal" not in out[0] and "signal" not in out[1]


def test_identical_rules_keep_the_plain_catalog_reading():
    # Same primitive, same effective window (200 vs 200.0) — genuinely the same
    # condition. There is nothing to disambiguate, so no suffix noise.
    rules = [
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 200}),
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 200.0}, logic_with_prior="AND"),
    ]
    assert _readings(rules) == ["Price above its moving average"] * 2


def test_non_colliding_rules_are_never_suffixed():
    # The common case: distinct primitives keep the editorial copy verbatim.
    rules = [
        StrategyRule(primitive_id="rsi", operator="lt", threshold=30),
        StrategyRule(primitive_id="adx", operator="gte", threshold=25,
                     logic_with_prior="AND"),
    ]
    assert _readings(rules) == ["Overbought / oversold extreme", "How strong the trend is"]


def test_best_momentum_pick_renders_six_distinct_chips():
    # The reported rule set, verbatim from `recommended-templates.ts`.
    rules = [
        StrategyRule(primitive_id="rank_return_6m", operator="gte", threshold=0.8),
        StrategyRule(primitive_id="time_series_momentum", operator="gt",
                     threshold=0.15, logic_with_prior="AND"),
        StrategyRule(primitive_id="adx", operator="gte", threshold=25,
                     logic_with_prior="AND"),
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 200}, logic_with_prior="AND"),
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 50}, logic_with_prior="AND"),
        StrategyRule(primitive_id="sector_rotation_rank", operator="lte",
                     threshold=3, logic_with_prior="AND"),
    ]
    out = _readings(rules)
    assert len(out) == 6
    assert len(set(out)) == 6, f"duplicate chip in {out}"


def test_scan_readings_disambiguate_end_to_end(db):
    # Both rules read the same default-param snapshot column (the documented
    # approximation), so both fire for AAPL — the exact shape that produced the
    # duplicate chip on screen.
    svc = SignalSnapshotService()
    svc.write_symbol(db, "AAPL", {"price_above_ma": 1.0}, AS_OF)
    db.commit()

    rules = [
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 200}),
        StrategyRule(primitive_id="price_above_ma", operator="is_true",
                     primitive_params={"period": 50}, logic_with_prior="AND"),
    ]
    res = scan(db, "symbols", rules, symbols=["AAPL"], snapshot_svc=svc)

    assert res.matched == ["AAPL"]
    chips = res.readings["AAPL"]
    assert len(chips) == 2
    assert len(set(chips)) == 2, f"duplicate chip rendered: {chips}"


def test_empty_rules_match_nothing(seeded, db):
    res = _scan(db, seeded, [])
    assert res.matched == []
    assert res.matched_count == 0


def test_count_equals_len_matched(seeded, db):
    # /count (slice 4) is just matched_count — must equal len(scan().matched).
    rules = [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)]
    res = _scan(db, seeded, rules)
    assert res.matched_count == len(res.matched)


def test_no_snapshot_rows_matches_nothing(db):
    # Universe resolves but nothing is warmed yet → empty, not an error.
    svc = SignalSnapshotService()
    rules = [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)]
    res = scan(db, "symbols", rules, symbols=["AAPL", "MSFT"], snapshot_svc=svc)
    assert res.matched == []
    assert res.universe_size == 2


def test_scan_returns_the_value_each_symbol_scored(seeded, db):
    """The screen has to show HOW MUCH, not just whether.

    Jimmy's reference renders the screened metric as a sortable column per
    condition ("量比 3.00"). The snapshot already holds these; the scan used to
    filter on them and drop them, so the UI could only say a name matched.
    """
    rules = [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)]
    res = _scan(db, seeded, rules)
    assert set(res.matched) == {"AAPL", "TSLA"}
    assert res.values["AAPL"]["rsi"] == 25.0
    assert res.values["TSLA"]["rsi"] == 20.0


def test_values_cover_every_screened_primitive(seeded, db):
    rules = [
        StrategyRule(primitive_id="rsi", operator="lt", threshold=30),
        StrategyRule(primitive_id="sma", operator="gt", threshold=100, logic_with_prior="AND"),
    ]
    res = _scan(db, seeded, rules)
    assert res.matched == ["AAPL"]
    assert res.values["AAPL"] == {"rsi": 25.0, "sma": 150.0}


def test_a_missing_cell_is_omitted_not_sent_as_zero(seeded, db):
    """TSLA has no `sma` row. Sending 0 would render as a real reading and sort
    to the bottom as though it were the lowest value in the set."""
    rules = [
        StrategyRule(primitive_id="rsi", operator="lt", threshold=30),
        StrategyRule(primitive_id="sma", operator="gt", threshold=100, logic_with_prior="OR"),
    ]
    res = _scan(db, seeded, rules)
    assert "TSLA" in res.matched
    assert "sma" not in res.values.get("TSLA", {})
    assert res.values["TSLA"]["rsi"] == 20.0


def test_unmatched_symbols_carry_no_values(seeded, db):
    rules = [StrategyRule(primitive_id="rsi", operator="lt", threshold=30)]
    res = _scan(db, seeded, rules)
    assert "MSFT" not in res.values  # rsi 55 — didn't match
