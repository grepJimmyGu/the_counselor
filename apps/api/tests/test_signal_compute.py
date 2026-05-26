"""Stage 8 v0 Phase A — signal_service pure helpers.

Tests `signals_equal` (with float-noise tolerance) and `classify_change`.
The full backtest-engine-driven `compute_current_signal` lands in Phase B
alongside the daily recompute cron.
"""
from __future__ import annotations

from app.services.signal_service import classify_change, signals_equal


# ── signals_equal ────────────────────────────────────────────────────────────


def test_signals_equal_returns_true_for_identical_long_position() -> None:
    a = {"position": "long", "ticker": "NVDA"}
    b = {"position": "long", "ticker": "NVDA"}
    assert signals_equal(a, b) is True


def test_signals_equal_returns_false_when_ticker_changes() -> None:
    a = {"position": "long", "ticker": "NVDA"}
    b = {"position": "long", "ticker": "AAPL"}
    assert signals_equal(a, b) is False


def test_signals_equal_handles_float_rounding() -> None:
    """Spec §13 — float-derived signals must not false-flip on noise. The two
    payloads describe the same RSI signal; their `trigger_rsi` values differ
    only in the 12th decimal place after independent recomputation."""
    a = {"position": "long", "ticker": "AAPL", "trigger_rsi": 28.4000000001}
    b = {"position": "long", "ticker": "AAPL", "trigger_rsi": 28.4000000009}
    assert signals_equal(a, b) is True


def test_signals_equal_detects_real_basket_weight_change() -> None:
    """4-decimal normalization must NOT mask a real rebalance — 50.0% vs 50.1%
    is a legitimate weight change that should propagate as a rebalance event."""
    a = {"holdings": [{"ticker": "GLD", "weight": 0.5000}, {"ticker": "SLV", "weight": 0.5000}]}
    b = {"holdings": [{"ticker": "GLD", "weight": 0.5010}, {"ticker": "SLV", "weight": 0.4990}]}
    assert signals_equal(a, b) is False


def test_signals_equal_treats_both_none_as_equal() -> None:
    assert signals_equal(None, None) is True


def test_signals_equal_treats_one_none_as_unequal() -> None:
    assert signals_equal(None, {"position": "cash"}) is False


# ── classify_change ──────────────────────────────────────────────────────────


def test_classify_change_long_to_cash_is_flip_to_cash() -> None:
    prev = {"position": "long", "ticker": "NVDA"}
    new = {"position": "cash"}
    assert classify_change(prev, new) == "flip_to_cash"


def test_classify_change_cash_to_long_is_flip_to_long() -> None:
    prev = {"position": "cash"}
    new = {"position": "long", "ticker": "NVDA"}
    assert classify_change(prev, new) == "flip_to_long"


def test_classify_change_no_prior_state_to_long_is_flip_to_long() -> None:
    """First-ever recompute with no prior state is treated as cash → long.
    Phase B cron should normally suppress this (first compute = silent), but
    the classifier should still bucket it sensibly if called."""
    assert classify_change(None, {"position": "long", "ticker": "QQQ"}) == "flip_to_long"


def test_classify_change_basket_holdings_change_is_rotation() -> None:
    prev = {"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "SLV", "weight": 0.5}]}
    new = {"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "PLAT", "weight": 0.5}]}
    assert classify_change(prev, new) == "rotation"


def test_classify_change_basket_weights_change_is_rebalance() -> None:
    prev = {"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "SLV", "weight": 0.5}]}
    new = {"holdings": [{"ticker": "GLD", "weight": 0.7}, {"ticker": "SLV", "weight": 0.3}]}
    assert classify_change(prev, new) == "rebalance"
