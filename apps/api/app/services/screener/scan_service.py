"""Market Screener — scan service (PRD-23a §3.5).

Evaluate a composed reading (a list of custom_build `StrategyRule`s) as a
boolean filter over the pre-warmed `signal_snapshot`, returning the matched
basket + the per-symbol "why it matched" readings + the snapshot freshness
stamp. Pure read over the snapshot — NO backtest (the rank step, slice 5,
backtests only this matched subset).

Fidelity: each rule's mask is computed with the SAME evaluator the backtest
uses — `BacktestEngine._apply_rule_threshold` — applied to the snapshot's
column for that primitive. A *null cell* (the symbol has no value for the
primitive) is excluded from the rule (never treated as a real value — this
matters for shape ops like `fires`, where `NaN != 0` would otherwise be True).
Rules fold left-to-right via `logic_with_prior` (AND/OR), exactly as the
engine folds them.

The byte-identical guarantee holds for the operator/threshold and for
default-param rules. It does NOT cover an indicator-*period* override: the
snapshot is warmed at catalog-default params, so a rule with a non-default
`primitive_params` is scanned against the default-param value — an
approximation. Those primitives are surfaced as `default_param_primitives`
(and logged), never silently divergent; the sign-in-gated rank step
re-backtests with the real params.

A rule whose primitive isn't in the daily snapshot coverage (e.g. a
fundamental) can never match here; rather than fail silently, the result
surfaces those `unsupported_primitives` and logs them (no-silent-cap).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

import pandas as pd

from app.schemas.strategy import StrategyRule
from app.services.screener.signal_snapshot_service import (
    SignalSnapshotService,
    snapshot_primitive_ids,
)
from app.services.screener.universe_resolver import (
    SectorMembershipFn,
    resolve_universe,
)

logger = logging.getLogger("livermore.screener.scan")


@dataclass
class ScanResult:
    matched: List[str]
    # symbol -> the satisfied rule readings (the "why this matched" copy).
    readings: Dict[str, List[str]]
    as_of_date: Optional[date]
    universe_size: int
    matched_count: int
    # Rule primitives not covered by the daily snapshot (can't match) —
    # surfaced so the UI can tell the user, never a silent always-false.
    unsupported_primitives: List[str] = field(default_factory=list)
    # Covered primitives whose rule sets a non-default `primitive_params`
    # (e.g. RSI period=7 vs the cataloged 14). The daily snapshot is warmed at
    # catalog-default params only, so the scan evaluates these against the
    # DEFAULT-param value — an APPROXIMATION, not byte-identical to the
    # backtest. Surfaced (never silent) so the UI can flag "screened at default
    # periods"; the sign-in-gated rank step re-backtests with the real params.
    default_param_primitives: List[str] = field(default_factory=list)


def _reading_for(rule: StrategyRule, catalog_by_id: dict) -> str:
    """The short headline shown for a satisfied rule. Falls back to the
    primitive name / id when the catalog has no `reading`."""
    primitive = catalog_by_id.get(rule.primitive_id)
    if primitive is None:
        return rule.primitive_id or "rule"
    return primitive.reading or primitive.name or primitive.id


def scan(
    db,
    universe_id: str,
    rules: Sequence[StrategyRule],
    *,
    symbols: Optional[Sequence[str]] = None,
    sector_membership: Optional[SectorMembershipFn] = None,
    resolution: str = "daily",
    snapshot_svc: Optional[SignalSnapshotService] = None,
) -> ScanResult:
    """Filter `universe_id` to the symbols whose snapshot satisfies `rules`."""
    from app.data.signal_primitives import SIGNAL_PRIMITIVES
    from app.services.backtester.engine import BacktestEngine

    syms = resolve_universe(
        universe_id, symbols=symbols, sector_membership=sector_membership
    )
    svc = snapshot_svc or SignalSnapshotService()
    snap = svc.get_snapshot(db, syms, resolution=resolution)
    frame = snap.frame

    catalog_by_id = {p.id: p for p in SIGNAL_PRIMITIVES}
    covered = set(snapshot_primitive_ids())
    engine = BacktestEngine()

    unsupported = sorted(
        {r.primitive_id for r in rules if r.primitive_id not in covered if r.primitive_id}
    )
    if unsupported:
        logger.info(
            "screener scan: %d rule primitive(s) not in the daily snapshot — "
            "they cannot match: %s",
            len(unsupported),
            unsupported,
        )

    # Covered primitives with a non-default param override: the snapshot holds
    # only the default-param value, so the scan is an APPROXIMATION for these
    # (not byte-identical). Conservative — flags any non-empty primitive_params
    # (may over-flag a set that happens to equal defaults; never under-flags).
    default_param = sorted(
        {
            r.primitive_id
            for r in rules
            if r.primitive_id in covered and r.primitive_params
        }
    )
    if default_param:
        logger.info(
            "screener scan: %d rule(s) override indicator params but the snapshot "
            "is default-param — scanned at default periods (rank re-backtests "
            "with the real params): %s",
            len(default_param),
            default_param,
        )

    if not syms or frame.empty or not rules:
        return ScanResult(
            matched=[],
            readings={},
            as_of_date=snap.as_of_date,
            universe_size=len(syms),
            matched_count=0,
            unsupported_primitives=unsupported,
            default_param_primitives=default_param,
        )

    accumulator: Optional[pd.Series] = None
    per_rule_masks: List[tuple] = []  # (rule, mask) for the readings breakdown

    for i, rule in enumerate(rules):
        pid = rule.primitive_id
        if pid in frame.columns:
            col = frame[pid]
        else:
            # Primitive absent from the snapshot → all-null column → no matches.
            col = pd.Series(float("nan"), index=frame.index, dtype=float)

        mask = engine._apply_rule_threshold(rule, col)
        # Exclude null cells: a symbol only satisfies a rule if it has a real
        # value for that primitive (guards `fires` on NaN, etc.).
        mask = (mask & col.notna()).fillna(False)
        per_rule_masks.append((rule, mask))

        if accumulator is None:
            accumulator = mask
        elif rule.logic_with_prior == "AND":
            accumulator = accumulator & mask
        elif rule.logic_with_prior == "OR":
            accumulator = accumulator | mask
        else:
            raise ValueError(
                f"screener scan: rule {i} missing logic_with_prior (AND/OR)"
            )

    matched = [str(sym) for sym, ok in accumulator.items() if bool(ok)]
    readings: Dict[str, List[str]] = {}
    for sym in matched:
        readings[sym] = [
            _reading_for(rule, catalog_by_id)
            for rule, mask in per_rule_masks
            if bool(mask.get(sym, False))
        ]

    return ScanResult(
        matched=matched,
        readings=readings,
        as_of_date=snap.as_of_date,
        universe_size=len(syms),
        matched_count=len(matched),
        unsupported_primitives=unsupported,
        default_param_primitives=default_param,
    )
