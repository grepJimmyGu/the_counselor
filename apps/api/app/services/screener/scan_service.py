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
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from app.schemas.strategy import StrategyRule
from app.services.screener.signal_snapshot_service import (
    SignalSnapshotService,
    snapshot_primitive_ids,
)
from app.services.screener.universe_resolver import (
    SectorMembershipFn,
    is_standing_id,
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
    # symbol -> {primitive_id: value} for the primitives the rules screened on.
    # The snapshot frame already holds these; the scan filters on them and then
    # dropped them, so the UI could say WHICH conditions a name matched but
    # never BY HOW MUCH. Jimmy's reference shows the numbers as sortable
    # columns ("量比 3.00"), which is the difference between a list of tickers
    # and a screen you can actually read.
    values: Dict[str, Dict[str, float]] = field(default_factory=dict)
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
    primitive name / id when the catalog has no `reading`.

    Catalog-level only — the copy is keyed on `primitive_id` alone, so two
    rules on the same primitive share it. `readings_for_rules` is what the
    scan actually renders; it disambiguates the collisions.
    """
    primitive = catalog_by_id.get(rule.primitive_id)
    if primitive is None:
        return rule.primitive_id or "rule"
    return primitive.reading or primitive.name or primitive.id


# Params that name a plain day-window. The base reading already says what the
# window is measuring ("Price above its moving average"), so the suffix only
# has to carry the number: "200-day".
_DAY_WINDOW_PARAMS = frozenset(
    {
        "period", "lookback", "lookback_days", "window_days", "trading_days",
        "anchor_lookback", "lag_days", "consecutive",
    }
)

# Suffix -> unit for qualified windows (`fast_period` -> "fast 12-day").
_QUALIFIED_WINDOW_SUFFIXES = (("_period", "day"), ("_days", "day"), ("_months", "month"))


def _fmt_param_value(value: Any) -> str:
    """`200.0` and `200` must render identically — they're the same window,
    and a spurious difference would suffix rules that don't actually differ."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _fmt_param(name: str, value: Any) -> str:
    """One param as user-facing copy: `("period", 200)` -> `"200-day"`."""
    rendered = _fmt_param_value(value)
    if name in _DAY_WINDOW_PARAMS:
        return f"{rendered}-day"
    for suffix, unit in _QUALIFIED_WINDOW_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            qualifier = name[: -len(suffix)].replace("_", " ")
            return f"{qualifier} {rendered}-{unit}"
    return f"{name.replace('_', ' ')} {rendered}"


def _effective_params(rule: StrategyRule, primitive) -> Dict[str, Any]:
    """What the rule actually evaluates: catalog defaults overlaid with the
    rule's overrides.

    Resolving the defaults (rather than reading `primitive_params` raw) is what
    lets an implicit-default rule label correctly next to an explicit one — a
    bare `price_above_ma` and a `{"period": 50}` one differ by 200 vs 50, not
    by "no params" vs "50".
    """
    params: Dict[str, Any] = {}
    if primitive is not None:
        params = {p.name: p.default for p in (primitive.parameters or [])}
    params.update(rule.primitive_params or {})
    return params


def readings_for_rules(
    rules: Sequence[StrategyRule], catalog_by_id: dict
) -> List[str]:
    """One headline per rule, index-aligned with `rules`.

    The catalog's `reading` is keyed on `primitive_id` alone, so any two rules
    on the same primitive collapse to the same string — a 50-day and a 200-day
    `price_above_ma` both render "Price above its moving average", which the
    user reads as a duplicated chip rather than two distinct conditions.

    So when a reading is claimed by more than one rule, each of those rules is
    suffixed with the effective param(s) that actually DIFFER within the group
    ("… · 200-day" / "… · 50-day"), matching the `pill · value` chip form the
    home condition builder uses. Rules that don't collide are returned
    untouched — no suffix noise on the common single-rule case.

    Rules that collide with identical effective params are genuinely the same
    condition; there is nothing to disambiguate, so they keep the base copy.
    """
    base = [_reading_for(rule, catalog_by_id) for rule in rules]

    # Key on the primitive too, so a group is always same-primitive even if two
    # catalog entries ever share a reading string — diffing params across
    # different primitives would be meaningless.
    groups: Dict[tuple, List[int]] = {}
    for i, (rule, label) in enumerate(zip(rules, base)):
        groups.setdefault((rule.primitive_id, label), []).append(i)

    out = list(base)
    for (primitive_id, label), idxs in groups.items():
        if len(idxs) < 2:
            continue
        primitive = catalog_by_id.get(primitive_id)
        params = [_effective_params(rules[i], primitive) for i in idxs]
        names = sorted({name for p in params for name in p})
        differing = [
            name
            for name in names
            if len({_fmt_param_value(p.get(name)) for p in params}) > 1
        ]
        if not differing:
            continue
        for i, p in zip(idxs, params):
            suffix = ", ".join(
                _fmt_param(name, p[name]) for name in differing if name in p
            )
            if suffix:
                out[i] = f"{label} · {suffix}"
    return out


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

    if not rules and syms and not is_standing_id(universe_id):
        # A caller-supplied population with nothing left to filter by.
        #
        # This is the whole fundamental-only path. "p/e under 15" is not a
        # snapshot primitive (`condition-groups.ts` sets `rule: null` for it),
        # so `/api/search/parse` resolves it itself and returns
        # `universe_id="symbols"` with the 564 names that match — plus the note
        # "Matched 564 names on P/E under 15." The results page handed those
        # 564 straight back here with an empty rule list, `not rules` returned
        # `matched: []`, and the user saw an empty screen under a note claiming
        # 564 matches. The answer had been computed and was thrown away.
        #
        # An empty conjunction is vacuously true: "no constraints" is not
        # "nothing qualifies". Scoped to the client-supplied tiers, because
        # `resolve_universe` ignores `symbols` for a standing id — there the
        # population is the whole index and returning it for an empty query
        # would be a worse bug than the one being fixed.
        return ScanResult(
            matched=list(syms),
            readings={},
            as_of_date=snap.as_of_date,
            universe_size=len(syms),
            matched_count=len(syms),
            unsupported_primitives=unsupported,
            default_param_primitives=default_param,
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
    # Resolved once for the whole rule set (not per symbol): the labels are
    # rule-set-dependent — same-primitive rules disambiguate against each other.
    rule_readings = readings_for_rules([rule for rule, _ in per_rule_masks], catalog_by_id)
    readings: Dict[str, List[str]] = {}
    for sym in matched:
        readings[sym] = [
            rule_readings[i]
            for i, (_, mask) in enumerate(per_rule_masks)
            if bool(mask.get(sym, False))
        ]

    # Values for the screened primitives, matched symbols only. Floats that
    # aren't finite (NaN for a missing cell) are omitted rather than sent as
    # null — the column then renders "—" instead of a misleading 0.
    screened_ids = [r.primitive_id for r in rules if r.primitive_id]
    values: Dict[str, Dict[str, float]] = {}
    for sym in matched:
        row: Dict[str, float] = {}
        for pid in screened_ids:
            if pid in frame.columns:
                raw = frame.at[sym, pid] if sym in frame.index else None
                try:
                    v = float(raw)
                except (TypeError, ValueError):
                    continue
                if v == v and v not in (float("inf"), float("-inf")):
                    row[pid] = v
        if row:
            values[sym] = row

    return ScanResult(
        matched=matched,
        readings=readings,
        values=values,
        as_of_date=snap.as_of_date,
        universe_size=len(syms),
        matched_count=len(matched),
        unsupported_primitives=unsupported,
        default_param_primitives=default_param,
    )
