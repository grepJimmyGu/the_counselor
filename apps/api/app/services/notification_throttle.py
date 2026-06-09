"""Notification throttle — PRD-19 (Phase B re-shape).

Pure functions. No DB dependency. Used by the signal recompute cron and
every ChannelDispatcher. The throttle rules are the load-bearing piece
of the framework: over-firing causes unsubscribes.

Rules:
  - Per-strategy daily cap: max 1 signal-change email per strategy per day
  - Per-user daily cap (all channels): 3. If exceeded → collapse into digest
  - Silent-day skip: if no strategies changed overnight + user opted for
    "only when there's news", return True
"""
from __future__ import annotations

from datetime import date


def throttle_strategy_daily(today_count: int) -> bool:
    """Return True if this strategy's daily cap is hit (should NOT fire)."""
    return today_count >= 1


def throttle_user_daily(today_count: int) -> bool:
    """Return True if the user's cross-strategy daily cap is hit.
    Per HANDOFF §6A: max 3 per user per day across all triggers.
    If exceeded, the caller should collapse into a single digest."""
    return today_count >= 3


def should_skip_digest(changed_count: int, silent_days_enabled: bool) -> bool:
    """Return True if the daily digest should be skipped.
    skips when (a) no strategies changed AND (b) user set silent-days."""
    if not silent_days_enabled:
        return False
    return changed_count == 0


def throttle_key(strategy_id: str, d: date) -> str:
    """Return the tracking key for per-strategy daily throttle.
    Format: '{strategy_id}:{iso_date}' — reset by date rollover."""
    return f"{strategy_id}:{d.isoformat()}"


def user_throttle_key(user_id: str, d: date) -> str:
    """Return the tracking key for per-user daily throttle."""
    return f"{user_id}:{d.isoformat()}"


# ── PRD-16c-3b: per-position throttle ───────────────────────────────────────
#
# Active-execution strategies fire per-symbol per-tier events: a stop on AAPL
# is distinct from a TP1 on AAPL is distinct from a stop on NVDA. The
# (strategy_id, date) keying that signal_change uses would batch all of them
# under one cap and drop legitimate events.
#
# The position throttle is keyed by (strategy_id, symbol, trigger_type, date)
# — one cap per ladder rung per symbol per day. Same TP1 hit on the same
# symbol on the same day is still noise; a stop on a different symbol is not.


def position_throttle_key(
    strategy_id: str, symbol: str, trigger_type: str, d: date
) -> str:
    """Return the per-position daily throttle key.

    `trigger_type` is one of 'stop_hit' | 'tp1_hit' | 'tp2_hit' | ... —
    the position-event names the monitor cron emits.
    """
    return f"{strategy_id}:{symbol}:{trigger_type}:{d.isoformat()}"


def throttle_position_daily(today_count: int) -> bool:
    """Return True if this position+tier's daily cap is hit.

    Same shape as `throttle_strategy_daily`: 1 per day per
    (strategy, symbol, trigger_type). Caller branches on this before
    dispatching the email / banner."""
    return today_count >= 1
