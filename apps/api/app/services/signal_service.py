"""Signal helpers (Stage 8 v0 — Phase A foundation + Phase B compute).

Phase A shipped the pure helpers (`signals_equal`, `classify_change`).
Phase B adds `compute_current_signal()` — the cron-side wrapper that turns
a strategy JSON + as-of date into a signal payload using the backtest engine.

The signal payload shapes are dictated by spec §4.1 and keyed off
`strategy_type`:

  - Single-asset (MA filter, MA crossover, RSI mean rev, breakout):
      {"position": "long", "ticker": "NVDA"}   or   {"position": "cash"}
  - Rotation-style (momentum_rotation, dual_momentum, sector_rotation,
    time_series_momentum, cross_sectional_momentum, low_vol):
      {"holdings": [{"ticker": "GLD", "weight": 0.5}, ...]}
  - Static allocation:
      {"target_weights": [{"ticker": "SPY", "weight": 0.6}, ...]}
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.schemas.strategy import StrategyJSON

# Strategy types that produce a single long/cash position.
_SINGLE_ASSET_TYPES = frozenset({
    "moving_average_filter",
    "moving_average_crossover",
    "rsi_mean_reversion",
    "breakout",
    "bollinger_mean_reversion",
})

# Strategy types that produce a multi-ticker basket of holdings.
_ROTATION_TYPES = frozenset({
    "momentum_rotation",
    "dual_momentum",
    "sector_rotation",
    "time_series_momentum",
    "cross_sectional_momentum",
    "low_vol",
})

# Strategy types that produce a fixed target-weight basket.
_STATIC_ALLOC_TYPES = frozenset({"static_allocation"})


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


def _build_signal_payload(strategy_type: str, weights: dict) -> dict:
    """Map (strategy_type, non-zero weights dict) → spec §4.1 signal payload.

    `weights` is the engine's end-of-period non-zero ticker → weight dict.
    Returns the canonical signal shape — the same shape that
    `SavedStrategySignalState.current_signal` stores and that the email
    template + frontend panel render.
    """
    if not weights:
        return {"position": "cash"}

    if strategy_type in _SINGLE_ASSET_TYPES:
        # Engine occasionally returns multiple non-zero tickers for these (e.g.,
        # a multi-universe MA filter); pick the largest position as primary.
        ticker = max(weights, key=lambda k: abs(weights[k]))
        return {"position": "long", "ticker": ticker}

    if strategy_type in _ROTATION_TYPES:
        holdings = [
            {"ticker": t, "weight": round(float(w), 4)}
            for t, w in sorted(weights.items(), key=lambda kv: -abs(kv[1]))
        ]
        return {"holdings": holdings}

    if strategy_type in _STATIC_ALLOC_TYPES:
        target_weights = [
            {"ticker": t, "weight": round(float(w), 4)}
            for t, w in sorted(weights.items(), key=lambda kv: -abs(kv[1]))
        ]
        return {"target_weights": target_weights}

    # Catch-all for strategy types not classified above (e.g. pairs_trading,
    # quality_piotroski). Render as a generic basket so the row never crashes;
    # downstream classify_change treats it as `basket`.
    holdings = [
        {"ticker": t, "weight": round(float(w), 4)}
        for t, w in sorted(weights.items(), key=lambda kv: -abs(kv[1]))
    ]
    return {"holdings": holdings}


def _render_display(strategy_type: str, weights: dict) -> str:
    """Pre-render a human-readable status string for the signal.

    Stored in `SavedStrategySignalState.current_signal_display` so the UI +
    email can show it without re-deriving from the JSON payload. Capped at
    280 chars (matches the column).
    """
    if not weights:
        return "In cash"

    if strategy_type in _SINGLE_ASSET_TYPES:
        ticker = max(weights, key=lambda k: abs(weights[k]))
        return f"Hold {ticker}"

    sorted_items = sorted(weights.items(), key=lambda kv: -abs(kv[1]))

    if strategy_type in _STATIC_ALLOC_TYPES:
        parts = [f"{t} ({round(float(w) * 100)}%)" for t, w in sorted_items]
        display = "Static: " + ", ".join(parts)
    else:
        # Rotation / catch-all baskets.
        n = len(sorted_items)
        parts = [f"{t} ({round(float(w) * 100)}%)" for t, w in sorted_items]
        display = f"Top {n}: " + ", ".join(parts)

    return display[:280]


def compute_current_signal(
    db: Session,
    strategy_json: StrategyJSON,
    as_of: date,
) -> dict:
    """Compute "what does this strategy say to do as of `as_of`?"

    Returns a dict with three keys:
      - "signal":  dict matching spec §4.1 shape for the strategy_type
      - "display": pre-rendered string for `current_signal_display` column
      - "prices":  dict[str, float] — close prices on the actual market-data
        date that drove the computation (rounded to 4 decimals)

    Raises:
      NotImplementedError — for fundamental strategy types (v0 limitation,
        propagated from `BacktestEngine.compute_current_position`).
      ValueError — when no price data is available (e.g. delisted ticker).

    Called from the daily recompute cron (per-strategy try/except handles
    raised exceptions and continues with the rest of the population).
    """
    # Local import: BacktestEngine pulls heavy deps (pandas, numpy) and
    # importing at module load slows route registration. Cron path only.
    from app.services.backtester.engine import BacktestEngine

    # Override end_date so the engine returns positions through `as_of`,
    # not the strategy's original end_date (which may be a year stale).
    strategy = strategy_json.model_copy(update={"end_date": as_of})

    engine = BacktestEngine()
    result = asyncio.run(engine.compute_current_position(db, strategy))

    return {
        "signal": _build_signal_payload(strategy.strategy_type, result["weights"]),
        "display": _render_display(strategy.strategy_type, result["weights"]),
        "prices": result["prices"],
    }
