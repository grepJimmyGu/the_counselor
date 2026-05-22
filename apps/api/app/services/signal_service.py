"""Signal helpers (Stage 8 v0 — Phase A).

Two pure functions used by the signals route layer today, and by the daily
recompute cron landing in Phase B.

Deliberately omitted in Phase A: `compute_current_signal(db, strategy_json, as_of)`.
That helper lives next to the cron (Phase B) — running it eagerly from the GET
endpoint would warm an empty cache for the entire saved-strategy population on
first read post-deploy, which is the opposite of the spec's "lazy on cron"
contract (§4.1 + §6).
"""
from __future__ import annotations

from typing import Any, Optional


def _round_floats(value: Any, ndigits: int = 4) -> Any:
    """Recursively round floats inside a signal payload.

    Prevents false flips when the same underlying position is re-computed and a
    cached value differs in the 12th decimal place. Spec §13 ("Float-noise false
    flips"): normalize to 4 decimal places before equality comparison.
    """
    if isinstance(value, float):
        return round(value, ndigits)
    if isinstance(value, dict):
        return {k: _round_floats(v, ndigits) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_floats(v, ndigits) for v in value]
    return value


def signals_equal(a: Optional[dict], b: Optional[dict]) -> bool:
    """True when two signal payloads describe the same position.

    Treats `None` as cash on both sides. Float values are rounded to 4 decimals
    before comparison so noise in re-computation doesn't trigger spurious flips.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return _round_floats(a) == _round_floats(b)


def _position(signal: dict) -> str:
    """Bucket a signal payload into one of {"cash", "long", "basket"}.

    Used only by classify_change — the route layer never calls this directly.
    """
    if "position" in signal:
        return "cash" if signal["position"] == "cash" else "long"
    if "holdings" in signal or "target_weights" in signal:
        return "basket"
    # Unknown payload shape — treat as basket so we never silently call it a flip.
    return "basket"


def classify_change(previous: Optional[dict], new: dict) -> str:
    """Return the change_type literal for a SignalEvent row.

    Buckets:
      - "flip_to_cash"  — previously held a long position, now cash
      - "flip_to_long"  — previously cash (or no prior state), now long
      - "rotation"      — basket strategies whose holdings changed
      - "rebalance"     — basket strategies whose weights changed but holdings unchanged
    """
    prev_pos = _position(previous) if previous else "cash"
    new_pos = _position(new)

    if prev_pos in {"cash", "long"} and new_pos == "cash":
        return "flip_to_cash"
    if prev_pos == "cash" and new_pos == "long":
        return "flip_to_long"
    if new_pos == "basket":
        # Compare ticker sets to distinguish rotation from rebalance.
        prev_tickers = _basket_tickers(previous) if previous else set()
        new_tickers = _basket_tickers(new)
        if prev_tickers != new_tickers:
            return "rotation"
        return "rebalance"
    # Long-to-long with same ticker shouldn't trigger an event upstream
    # (signals_equal would have returned True), but if it does, treat as rebalance.
    return "rebalance"


def _basket_tickers(signal: dict) -> set:
    """Extract the ticker set from a basket-style signal payload."""
    holdings = signal.get("holdings") or signal.get("target_weights") or []
    return {h["ticker"] for h in holdings if "ticker" in h}
