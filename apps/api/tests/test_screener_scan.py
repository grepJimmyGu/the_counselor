"""PRD-23a slice 3 — scan service.

The boolean filter over the snapshot. Verifies operator correctness via the
shared evaluator, AND/OR folds, null-cell exclusion (the key correctness
guard for shape ops), unsupported-primitive surfacing, and the per-symbol
satisfied-readings breakdown.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.schemas.strategy import StrategyRule
from app.services.screener.scan_service import scan
from app.services.screener.signal_snapshot_service import SignalSnapshotService

AS_OF = date(2026, 6, 15)


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
