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
