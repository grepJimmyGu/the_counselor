"""Unified signal card schema (PRD-25 — Minimal presentation layer).

A *signal card* is a uniform re-presentation of the existing per-strategy
signal state (`SavedStrategySignalState`) so every ticker surface can render
the same brick at progressive depth:

    L0 glance chip → L1 card + reason → L2 fired-primitive logic → L3 backtest

It introduces **no new signal computation**. `state` is derived from the
existing `current_signal` position (long / cash / basket) via
`signal_service._position`; `fired_primitives` is read off the strategy's own
rules; `backtest_id` links the existing most-recent run.

Minimal scope (redesign decision, 2026-07-28): the six-state market-driven
machine from the v3.1 spec (`entry_zone` / `in_position` / `target_hit` /
`stop_hit`) is intentionally NOT modelled here. Those states require a
user-declared entry price and belong to a later position-driven pass. This
card carries only what today's data supports, in descriptive tool framing —
never advice.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class SignalCardState(str, Enum):
    """The reduced, market-fill-free state set (see module docstring)."""

    IN_SIGNAL = "in_signal"  # strategy currently holds a single-name long
    BASKET = "basket"        # strategy currently holds a multi-name basket
    FLAT = "flat"            # strategy currently in cash / no position
    PENDING = "pending"      # signal not yet computed for this strategy


class SignalCard(BaseModel):
    saved_strategy_id: str
    strategy_title: Optional[str] = None
    strategy_type: Optional[str] = None
    # The named ticker for a single-name long; None for basket / flat / pending.
    symbol: Optional[str] = None
    state: SignalCardState
    # Backend display string, e.g. "LONG NVDA" / "CASH" / "AAPL, MSFT, …".
    display: str
    # Plain-English, non-prescriptive one-liner (never "buy" / "sell").
    reason: str
    # L2 "logic" — the strategy's own rules, humanized. May be empty for
    # classic strategy_types that carry no explicit rule list.
    fired_primitives: List[str] = []
    # L3 — the strategy's most-recent backtest run, if any.
    backtest_id: Optional[str] = None
    as_of: Optional[str] = None
