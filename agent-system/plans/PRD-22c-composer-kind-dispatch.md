# PRD-22c: Composer Rule-Builder Kind-Dispatch + Six New Widgets

**Status**: Ready to build
**Phase**: Custom Mode v2 (Signal Library upgrade)
**Depends on**:
- **PRD-22a (hard)** — needs `output_kind` field on every primitive.
- **PRD-22b (soft)** — can ship with v1 catalog only; new primitives light up the widgets once 22b lands.
**Blocks**: —
**Effort**: ~1.5 weeks, single owner
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/signal_catalog_v2_spec.html`](../../Quant%20Strategy/framework/signal_catalog_v2_spec.html) — §2 (semantics → widget mapping), §5 (composer dispatch)

---

## 0. Scope addendum (2026-06-16) — finishing 22c so it actually works + feeds PRD-23

Three adjustments from the 2026-06-16 design session (Jimmy). This mode is the foundation
the Market Screener (PRD-23) reuses, so "finished" must mean *functional end-to-end*, not just
rendered.

1. **The engine operator-dispatch is IN SCOPE here — it was wrongly punted.** §3.3 says the
   new-operator dispatch is "a PRD-22b concern." PRD-22b shipped content-only and never added
   it. Ground truth: `StrategyRule.operator` is `Literal["gt","gte","lt","lte","crosses_above",
   "crosses_below"]` and `engine._apply_rule_threshold` **raises for anything but gt/gte/lt/lte**
   (even `crosses_above` is unimplemented in custom_build). So the new widgets currently
   serialize to operators the backtester rejects. Finishing 22c therefore includes a small
   additive **backend foundation slice**: widen `StrategyRule.operator` (+ `fires`, `is_true`,
   `crosses_up`, `crosses_down`, `in_range`, `equals`, `divergence_bullish/bearish`), widen
   `threshold` (`float → Union[float, dict, str]` for ranges + regime values), extend
   `_apply_rule_threshold`, and add `parameter_overrides` (§3.5). This is also the prerequisite
   for PRD-23, whose scan filter + rank backtest evaluate these same rules.

2. **The reading layer folds in here** (was tentatively PRD-23b). Two additive catalog fields —
   `reading` (plain-English "what a trader reads when this fires") and `intent_group` (the chip
   it lives under) — ship as part of 22c, backfilled across the ~72 primitives, same additive
   pattern as PRD-22a. The intent chips + per-kind widgets are the intent-first composer that
   PRD-23's `<ReadingComposer>` reuses wholesale.

3. **Catalog frozen at ~72.** No net-new primitive families during 22c. Existing non-VALUE
   primitives already exercise every widget except DIVERGENCE: `ma_crossover` (CROSS),
   `donchian_breakout` (EVENT), `vol_regime` (REGIME), the 52-week family (DISTANCE/EVENT/LEVEL),
   RVOL/Chandelier/TTM (EVENT/REGIME). MACD's 3 cross/event children remain optional demo
   sugar, not a blocker.

**Real file targets** (the §3 paths are aspirational): the composer is
`apps/web/src/lib/flows/bricks/custom-build-rule-composer.tsx` + `custom-build-rule-card.tsx`
(the refactor target, currently VALUE-only with a hardcoded binary special-case); the browser is
`apps/web/src/components/signal-library/signal-catalog-browser.tsx`; rule types in
`apps/web/src/lib/contracts.ts` + `custom-build-mode-context.tsx`.

**Build order**: (a) backend operator-dispatch foundation → (b) reading layer (catalog fields +
backfill + types) → (c) frontend kind-dispatch shell + 6 widgets + ValueRule refactor → (d)
catalog kind-filter + `composes` drawer + per-kind e2e. Each its own PR.

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded). Then read agent-system/plans/HANDOFF-livermore-signal-catalog-v2.md.

Goal: upgrade the Custom Build composer's rule-builder to dispatch on each
primitive's output_kind. The shipped <RuleBuilder> renders one widget shape
(value vs threshold). v2 routes to a kind-specific sub-component:

  - VALUE      → <ValueRule>      (existing UI, refactored)
  - EVENT      → <EventRule>      (no threshold input; "When [primitive] fires")
  - LEVEL      → <LevelRule>      (no threshold input; "While [primitive] is true")
  - CROSS      → <CrossRule>      (direction picker: above | below)
  - REGIME     → <RegimeRule>     (single-select chip: trending | ranging | …)
  - DISTANCE   → <DistanceRule>   (range slider: between [min%] and [max%])
  - DIVERGENCE → <DivergenceRule> (lookback bars + bull/bear picker)

Three deliverables:

  1. Refactor <RuleBuilder> into a kind-dispatch shell that picks the right
     sub-component based on the selected primitive's output_kind.

  2. Six new kind-specific rule sub-components.

  3. Update <SignalCatalogBrowser> with an output_kind filter chip-row so users
     can find primitives by "show me only EVENT primitives" etc.

PREREQUISITES (must be on main):
  - PRD-22a — output_kind on every primitive.

NICE-TO-HAVE on main but not blocking:
  - PRD-22b — gives you the ~65 new primitives. Without it, only v1 primitives
    with non-VALUE kinds (ma_crossover, donchian_breakout, vol_regime) exercise
    the new widgets. Still shippable; just lower demo value.

OUT OF SCOPE for this PRD:
  - Backend changes (PRD-22a/b own everything backend).
  - Composer's WHEN IN / WHEN OUT block structure — unchanged.
  - Backtest engine changes — engine already consumes whatever the
    SignalProvider emits; new rule shapes serialize to the same StrategyRule
    schema.

Context to read in order:
  - /Quant Strategy/framework/signal_catalog_v2_spec.html §2 + §5
  - apps/web/src/components/composer/RuleBuilder.tsx (existing — refactor target)
  - apps/web/src/components/signal-library/signal-catalog-browser.tsx (PRD-16a)
  - apps/web/src/lib/contracts.ts (SignalPrimitive types from PRD-22a)

DEFINITION OF DONE:
  - <RuleBuilder> dispatches on output_kind
  - 6 new sub-components + refactored ValueRule
  - <SignalCatalogBrowser> has output_kind filter
  - Storybook stories for each new widget
  - Vitest tests for kind-dispatch + each widget's serialization to StrategyRule
  - Composer end-to-end test passes for at least one rule of each kind
```

---

## 1. The problem

The shipped composer renders one rule shape: `[primitive selector] [< | > | =] [number input]`. This works for VALUE primitives (`rsi`, `atr`, `fcf_yield`) but is wrong for the other six kinds:

- **EVENT** primitives like `bb_squeeze_fire` have no threshold — they're either firing this bar or not. The current widget asks "fire is < what?", which makes no sense.
- **CROSS** primitives need a direction picker, not a threshold. "MACD signal cross above" vs "below" is the canonical choice; the current widget forces users to pick a numeric threshold for a binary event.
- **DISTANCE** primitives like `distance_to_52w_high` are consumed as a *range* ("between 2% and 25% below high"), not a threshold. The current widget can only express `> -2` OR `< -25`, neither of which is what the user wants.

This PRD fixes the dispatch — the composer becomes the front door to every primitive shape PRD-22b ships.

---

## 2. Design constraints

1. **Backward-compatible serialization.** Every kind-specific widget serializes to the existing `StrategyRule` schema. The backtest engine doesn't need to know about output kinds — it consumes whatever the `SignalProvider` returns. The new widgets are UX shells over the existing rule shape.

2. **VALUE primitives unchanged.** The current widget IS the `<ValueRule>` post-refactor. The dispatch shell picks it for VALUE; users see no difference.

3. **All widgets share a common shell.** Same border, same hover state, same focus ring, same height (~80px collapsed, ~140px expanded). Only the inner inputs differ. Consistency matters — the canvas can show 5+ rules and they should visually compose.

4. **Composer end-to-end test for each kind.** PRD-22b's primitive set provides at least one example per kind. End-to-end test = drop primitive → configure → save strategy → backtest → result reflects the rule.

5. **Catalog browser kind-filter is a chip row, not a select.** Users want to see multiple kinds at once ("show CROSS + EVENT"). Multi-select chips, not a dropdown.

6. **The `composes` field powers parameter inheritance.** `macd_signal_cross` (composes `["macd"]`) inherits MACD's `fast_period`, `slow_period`, `signal_period` knobs in the rule UI. Users tune MACD-style parameters in one place per rule, not duplicated.

7. **No new icons.** Reuse `lucide-react` icons that exist in `node_modules`. Suggested: `ArrowRightLeft` (CROSS), `Zap` (EVENT), `CheckSquare` (LEVEL), `Layers` (REGIME), `Ruler` (DISTANCE), `Split` (DIVERGENCE).

---

## 3. Implementation

### 3.1 Dispatch shell

```tsx
// apps/web/src/components/composer/RuleBuilder.tsx — REFACTORED

import { SignalPrimitive, SignalOutputKind } from "@/lib/contracts";
import { ValueRule } from "./rules/ValueRule";
import { EventRule } from "./rules/EventRule";
import { LevelRule } from "./rules/LevelRule";
import { CrossRule } from "./rules/CrossRule";
import { RegimeRule } from "./rules/RegimeRule";
import { DistanceRule } from "./rules/DistanceRule";
import { DivergenceRule } from "./rules/DivergenceRule";

const KIND_TO_COMPONENT: Record<SignalOutputKind, React.FC<RuleProps>> = {
  value:      ValueRule,
  event:      EventRule,
  level:      LevelRule,
  cross:      CrossRule,
  regime:     RegimeRule,
  distance:   DistanceRule,
  divergence: DivergenceRule,
};

export function RuleBuilder({ primitive, rule, onChange }: RuleBuilderProps) {
  const RuleComponent = KIND_TO_COMPONENT[primitive.output_kind] ?? ValueRule;
  return (
    <RuleShell primitive={primitive} kind={primitive.output_kind}>
      <RuleComponent primitive={primitive} rule={rule} onChange={onChange} />
    </RuleShell>
  );
}
```

The `<RuleShell>` provides the common chrome: the primitive name + category badge in the header, the output-kind chip, the remove button, the parameter-knobs drawer if `composes` is non-empty.

### 3.2 Six new widgets

Each widget exports the same `RuleProps` interface and serializes to `StrategyRule`. Pseudo-implementations:

**`<EventRule>`** — no threshold input.
```tsx
<div className="flex items-center gap-2 px-3 py-2">
  <Zap className="w-4 h-4 text-violet-400" />
  <span>When <strong>{primitive.name}</strong> fires</span>
</div>
```
Serialized: `{ primitive_id, operator: "fires", threshold: null }`.

**`<LevelRule>`** — no threshold input.
```tsx
<div className="flex items-center gap-2 px-3 py-2">
  <CheckSquare className="w-4 h-4 text-amber-400" />
  <span>While <strong>{primitive.name}</strong> is true</span>
</div>
```
Serialized: `{ primitive_id, operator: "is_true", threshold: null }`.

**`<CrossRule>`** — direction picker.
```tsx
<div className="flex items-center gap-2 px-3 py-2">
  <ArrowRightLeft className="w-4 h-4 text-violet-400" />
  <span>When <strong>{primitive.name}</strong> crosses</span>
  <Segment value={direction} onChange={onDirChange}
           options={[{value: "up", label: "Up"}, {value: "down", label: "Down"}]} />
</div>
```
Serialized: `{ primitive_id, operator: "crosses_up" | "crosses_down", threshold: null }`.

**`<RegimeRule>`** — chip row of valid regime values from `primitive.default_thresholds`.
```tsx
<div className="flex items-center gap-2 px-3 py-2 flex-wrap">
  <Layers className="w-4 h-4 text-green-400" />
  <span>When regime is</span>
  {regimeOptions.map(opt => (
    <Chip key={opt} selected={selected === opt} onClick={() => onChange(opt)}>
      {opt}
    </Chip>
  ))}
</div>
```
Serialized: `{ primitive_id, operator: "equals", threshold: "<regime_value>" }`.

**`<DistanceRule>`** — range slider.
```tsx
<div className="flex items-center gap-3 px-3 py-2">
  <Ruler className="w-4 h-4 text-red-400" />
  <span><strong>{primitive.name}</strong> is between</span>
  <NumberInput value={minPct} onChange={setMin} suffix="%" />
  <span>and</span>
  <NumberInput value={maxPct} onChange={setMax} suffix="%" />
</div>
```
Serialized: `{ primitive_id, operator: "in_range", threshold: { min, max } }`.

**`<DivergenceRule>`** — lookback + bull/bear picker.
```tsx
<div className="flex items-center gap-2 px-3 py-2">
  <Split className="w-4 h-4 text-blue-400" />
  <span>When</span>
  <Segment value={direction} options={[{value:"bullish",...},{value:"bearish",...}]} />
  <span>divergence detected over</span>
  <NumberInput value={lookback} onChange={setLookback} />
  <span>bars</span>
</div>
```
Serialized: `{ primitive_id, operator: "divergence_<dir>", threshold: { lookback } }`.

**`<ValueRule>`** (refactored from existing — unchanged behavior):
```tsx
<div className="flex items-center gap-2 px-3 py-2">
  <span><strong>{primitive.name}</strong></span>
  <Segment value={op} options={[{value:">",label:">"}, {value:"<",label:"<"}, {value:"=",label:"="}]} />
  <NumberInput value={threshold} onChange={setThreshold} />
</div>
```
Serialized: `{ primitive_id, operator: "gt" | "lt" | "eq", threshold: number }`.

### 3.3 StrategyRule schema accommodation

`StrategyRule` already allows `operator: string` and `threshold: Any`. No backend schema change is needed — the new operators (`fires`, `is_true`, `crosses_up`, `crosses_down`, `in_range`, `divergence_bullish`, `divergence_bearish`, `equals`) are strings the existing schema accepts. The backtest engine reads `operator` to dispatch to the right consumer per primitive.

**The backtest engine dispatch is a PRD-22b concern** — engine consumes the primitive's `output_kind` and routes to the correct boolean reducer. Sketch:

```python
def evaluate_rule(rule: StrategyRule, primitive_series: pd.Series) -> pd.Series:
    if rule.operator == "fires":         return primitive_series != 0
    if rule.operator == "is_true":       return primitive_series.astype(bool)
    if rule.operator == "crosses_up":    return primitive_series == 1
    if rule.operator == "crosses_down":  return primitive_series == -1
    if rule.operator == "in_range":      return primitive_series.between(
                                              rule.threshold["min"], rule.threshold["max"])
    # ... existing >, <, = operators unchanged for VALUE
```

The engine change is small and additive. Document it in PRD-22b § handoff.

### 3.4 Catalog browser kind-filter

`<SignalCatalogBrowser>` gets a chip row above the category sidebar:

```tsx
<div className="flex flex-wrap gap-1.5 mb-3">
  {ALL_KINDS.map(kind => (
    <KindChip
      key={kind}
      kind={kind}
      selected={activeKinds.has(kind)}
      onClick={() => toggleKind(kind)}
    />
  ))}
</div>
```

`activeKinds` is a `Set<SignalOutputKind>`; empty set = show all (default). Multi-select. The filter intersects with the existing category filter.

### 3.5 Parameter inheritance via `composes`

When a primitive has `composes=["macd"]`, the rule UI also surfaces MACD's parameter knobs (in a collapsible "Tune underlying" drawer below the rule). Editing them is per-rule (not global) — saved into the rule's `parameter_overrides` field on `StrategyRule`. This requires one additive field on `StrategyRule`:

```python
class StrategyRule(BaseModel):
    # ... existing ...
    parameter_overrides: Optional[Dict[str, Any]] = None
```

Defaults to None (use primitive's default parameters). Backend engine reads it as override map when computing the primitive's series.

---

## 4. Testing

### 4.1 Dispatch tests

```ts
// apps/web/src/components/composer/__tests__/rule-builder.test.tsx

test("dispatches to ValueRule for VALUE primitives", () => {
  const { container } = render(<RuleBuilder primitive={mkPrim("rsi", "value")} />);
  expect(container.querySelector("[data-testid='value-rule']")).toBeTruthy();
});

test("dispatches to CrossRule for CROSS primitives", () => {
  const { container } = render(<RuleBuilder primitive={mkPrim("macd_signal_cross", "cross")} />);
  expect(container.querySelector("[data-testid='cross-rule']")).toBeTruthy();
});

test("dispatches to DistanceRule for DISTANCE primitives", () => {
  const { container } = render(<RuleBuilder primitive={mkPrim("distance_to_52w_high", "distance")} />);
  expect(container.querySelector("[data-testid='distance-rule']")).toBeTruthy();
});
```

### 4.2 Serialization tests

```ts
test("EventRule serializes to { operator: 'fires', threshold: null }", () => {
  const onChange = vi.fn();
  render(<EventRule primitive={mkPrim("bb_squeeze_fire", "event")} onChange={onChange} />);
  // Auto-fires on mount — no input needed
  expect(onChange).toHaveBeenCalledWith({
    primitive_id: "bb_squeeze_fire",
    operator: "fires",
    threshold: null,
  });
});

test("DistanceRule serializes range with min and max", () => {
  const onChange = vi.fn();
  const { getByLabelText } = render(
    <DistanceRule primitive={mkPrim("distance_to_52w_high", "distance")} onChange={onChange} />
  );
  fireEvent.change(getByLabelText("min"), { target: { value: "-25" } });
  fireEvent.change(getByLabelText("max"), { target: { value: "-2" } });
  expect(onChange).toHaveBeenLastCalledWith({
    primitive_id: "distance_to_52w_high",
    operator: "in_range",
    threshold: { min: -25, max: -2 },
  });
});
```

### 4.3 Catalog filter test

```ts
test("kind filter chip shows only selected-kind primitives", () => {
  const { getByText, queryByText } = render(<SignalCatalogBrowser />);
  fireEvent.click(getByText("EVENT"));  // toggle EVENT chip
  expect(getByText("bb_squeeze_fire")).toBeTruthy();
  expect(queryByText("rsi")).toBeFalsy();  // VALUE — filtered out
});
```

### 4.4 End-to-end composer test

```ts
test("user composes a CROSS + EVENT rule, saves, backtests", async () => {
  // Drag macd_signal_cross + rvol_surge onto canvas
  // Configure each
  // Click Backtest
  // Result reflects the rule (verified via mocked backtest service)
});
```

One e2e test per output kind. PRD-22b's primitive set guarantees at least one primitive per kind exists once both PRDs are merged.

---

## 5. Pre-merge checklist

1. ✅ `cd apps/web && npm run build` — clean.
2. ✅ `cd apps/web && npm test -- composer` — all green, including kind-dispatch.
3. ✅ Storybook builds; stories for each new widget present.
4. ✅ `cd apps/api && python3 -m pytest -q` — backend untouched, still green.
5. ✅ End-to-end composer test green for at least one rule of each kind.
6. ✅ Lighthouse / accessibility scan on composer page — no new violations.
7. ✅ Branch follows `<agent>/feat/prd-22c-composer-kind-dispatch` convention.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| New rule operators (`fires`, `crosses_up`, etc.) not recognized by backtest engine | Engine dispatch sketch in §3.3 — coordinate with PRD-22b owner to land both together |
| `parameter_overrides` field on StrategyRule breaks saved strategies | Additive (`Optional[Dict] = None`); existing rules unaffected |
| Mobile composer canvas becomes cramped with 7 widget types | Tablet+ is the supported breakpoint for composer; mobile shows read-only summary |
| Users confused by 7 different rule shapes | Onboarding: each widget has a (?) tooltip explaining the kind on first hover |
| Storybook bundle bloat from 6 new components | Code-split stories; ~50KB each is acceptable |

---

## 7. Definition of done

- [ ] `<RuleBuilder>` refactored as kind-dispatch shell
- [ ] 6 new rule sub-components + refactored `<ValueRule>`
- [ ] `<RuleShell>` common chrome shared across all 7
- [ ] `<SignalCatalogBrowser>` has multi-select kind chip filter
- [ ] `composes`-based parameter inheritance drawer working
- [ ] `parameter_overrides` field added to `StrategyRule` (additive)
- [ ] Vitest tests for dispatch + each widget's serialization
- [ ] Storybook stories for each widget
- [ ] One end-to-end composer test per output kind
- [ ] PR merged to `main` with green CI
- [ ] Brick inventory updated in `HANDOFF-livermore-signal-catalog-v2.md` §5

---

## 8. Hand-off after PRD-22c

PRD-22c is the last PRD in the packet. Once merged:

- The signal catalog v2 loop is complete — users can compose strategies using any of the 7 semantic kinds with kind-appropriate UI.
- Retention metrics from the HANDOFF §7 should be instrumented to confirm the upgrade is used:
  - Kind-specific rule adoption — % of saved strategies with at least one non-VALUE rule
  - 52-week-extrema family use rate — addresses the originally-flagged gap
- Follow-up PRDs likely:
  - Intraday extension of v2 primitives (flip `resolution=["daily"]` → `["daily", "intraday"]` for eligible primitives; reuses PRD-16c machinery).
  - Cross-asset / macro signals (VIX term structure, put/call ratio, HY-IG spread) — needs new `data_source` wiring; separate PRD.
  - User-supplied custom Python signals — far-future Pro feature, not in scope for any v2 PRD.

---

*PRD drafted 2026-06-12. Cross-references: v2 spec at `/Quant Strategy/framework/signal_catalog_v2_spec.html` §2+§5, parent HANDOFF at `agent-system/plans/HANDOFF-livermore-signal-catalog-v2.md`, depends on PRD-22a + PRD-22b.*
