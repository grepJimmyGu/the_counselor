"""Build unified SignalCards from the existing per-strategy signal state.

PRD-25 (Minimal). No new computation: reads `SavedStrategySignalState` +
`SavedStrategy.strategy_json` and maps them to the uniform `SignalCard`
shape. The batch path is two queries total (strategies + states) so a list
surface is one cached call — the spec's "batch < 300ms, no live AV/FMP
fetch" goal.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.schemas.signal_card import SignalCard, SignalCardState
from app.services.signal_service import _basket_tickers, _position

_MAX_FIRED = 8
_MAX_BATCH = 100


def _humanize_rules(strategy_json: dict) -> List[str]:
    """Render a strategy's rules as short, non-prescriptive reading strings.

    Reads each rule's `primitive_id` (custom-build) or `indicator` (classic),
    plus `operator` + `threshold` when present. Best-effort: classic
    strategy_types that carry no explicit `rules` list yield an empty list.
    """
    rules = strategy_json.get("rules") if isinstance(strategy_json, dict) else None
    if not isinstance(rules, list):
        return []
    out: List[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        name = rule.get("primitive_id") or rule.get("indicator")
        if not name:
            continue
        label = str(name).replace("_", " ")
        operator = rule.get("operator")
        threshold = rule.get("threshold")
        if operator and threshold is not None and not isinstance(threshold, (dict, list)):
            out.append(f"{label} {operator} {threshold}")
        else:
            out.append(label)
        if len(out) >= _MAX_FIRED:
            break
    return out


def card_from_state(
    strategy: SavedStrategy,
    state: Optional[SavedStrategySignalState],
) -> SignalCard:
    """Map one strategy (+ its cached signal state, if any) to a SignalCard."""
    sj = strategy.strategy_json if isinstance(strategy.strategy_json, dict) else {}
    strategy_type = sj.get("strategy_type")
    fired = _humanize_rules(sj)
    title = strategy.title

    # No state row yet (cron hasn't run) or an empty payload → pending.
    if state is None or not state.current_signal:
        return SignalCard(
            saved_strategy_id=strategy.id,
            strategy_title=title,
            strategy_type=strategy_type,
            symbol=None,
            state=SignalCardState.PENDING,
            display="Signal pending",
            reason="This strategy's signal hasn't been computed yet.",
            fired_primitives=fired,
            backtest_id=strategy.backtest_record_id,
            as_of=None,
        )

    signal = state.current_signal
    position = _position(signal)
    if position == "long":
        card_state = SignalCardState.IN_SIGNAL
        symbol = signal.get("ticker") or None
        reason = f"“{title}” is currently in signal" + (
            f" on {symbol}." if symbol else "."
        )
    elif position == "basket":
        card_state = SignalCardState.BASKET
        symbol = None
        count = len(_basket_tickers(signal))
        reason = f"“{title}” currently holds {count} name{'' if count == 1 else 's'}."
    else:  # cash
        card_state = SignalCardState.FLAT
        symbol = None
        reason = f"“{title}” is currently flat — no position."

    return SignalCard(
        saved_strategy_id=strategy.id,
        strategy_title=title,
        strategy_type=strategy_type,
        symbol=symbol,
        state=card_state,
        display=state.current_signal_display or "—",
        reason=reason,
        fired_primitives=fired,
        backtest_id=strategy.backtest_record_id,
        as_of=state.as_of_date.isoformat() if state.as_of_date else None,
    )


def evaluate_cards(
    db: Session,
    saved_strategy_ids: List[str],
    user_id: str,
) -> List[SignalCard]:
    """Return SignalCards for the caller's own strategies, in request order.

    Non-owned / unknown ids are silently skipped so we never leak the
    existence of another user's strategy. Two queries total regardless of
    list length; the input is de-duplicated and capped at `_MAX_BATCH`.
    """
    ids = list(dict.fromkeys(saved_strategy_ids))[:_MAX_BATCH]
    if not ids:
        return []

    strategies = {
        s.id: s
        for s in db.query(SavedStrategy)
        .filter(SavedStrategy.id.in_(ids), SavedStrategy.user_id == user_id)
        .all()
    }
    if not strategies:
        return []

    states = {
        st.saved_strategy_id: st
        for st in db.query(SavedStrategySignalState)
        .filter(
            SavedStrategySignalState.saved_strategy_id.in_(list(strategies.keys()))
        )
        .all()
    }

    return [
        card_from_state(strategies[sid], states.get(sid))
        for sid in ids
        if sid in strategies
    ]
