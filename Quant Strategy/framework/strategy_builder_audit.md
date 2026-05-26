# Livermore Strategy Builder — Code Audit & Module Gap Analysis

> **What this doc is**: A read of the current Livermore code to map what's shipped in the strategy-builder flow, paired with the module list needed to fully enable both "Use a Template" and "Custom Build" experiences. Each module is scored: ✅ shipped / 🟡 partial / ❌ missing.
>
> **Sources read** (as of HEAD `61638c1`):
> - Backend: `apps/api/app/schemas/strategy.py`, `services/strategy_parser.py`, `services/strategy_validator.py`, `services/backtester/{engine,signal_provider,metrics}.py`, `services/chat_guardrails.py`, `services/backtest_preflight.py`, `services/chat_tools/*`, `api/routes/{backtest,strategy,strategy_storage}.py`
> - Frontend: `apps/web/src/components/strategy-builder/{strategy-builder-modal,summary-step,strategy-brief-card}.tsx`, `wizard/{strategy-wizard,strategy-wizard-data,strategy-wizard-recommend}.{tsx,ts}`, `app/templates/{page,[slug]/page}.tsx`, `lib/strategy-picker/risk-presets.ts`, `lib/contracts.ts`

---

## 1. Executive summary

The current strategy-builder is in remarkably good shape. The **"Use a Template" flow is ~85% complete** — gallery, detail page, wizard recommendation, 4-block summary, risk preset → engine parameters, and the full backtest pipeline all work end to end. The **"Custom Build" flow is ~50% complete** — the scaffold is in place but the signal-composition layer is missing: WHEN IN and WHEN OUT are read-only template-baked copy, not editable building blocks.

The biggest single gap to unlock a real custom builder is a **signal primitive library and composition UI** (the "checkboxes with AND/OR" pattern from the prior conversation). Everything underneath it — the StrategyJSON schema, signal providers, engine branches — is already shipped.

---

## 2. The two flows side by side

```
                   ┌─────────────────────────────────────────────────┐
                   │       StrategyBuilderModal (orchestrator)        │
                   └──────────────────────┬──────────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  │                                               │
        ┌─────────▼──────────┐                       ┌────────────▼────────────┐
        │  USE A TEMPLATE    │                       │     CUSTOM BUILD        │
        │  (Browse-first)    │                       │     (Idea-first)        │
        └─────────┬──────────┘                       └────────────┬────────────┘
                  │                                               │
                  ▼                                               ▼
        ┌─────────────────────┐                       ┌──────────────────────┐
        │ /templates gallery  │                       │ StrategyWizard       │
        │ filter by category, │                       │ (5 questions)        │
        │ evidence, capacity, │                       │ → top-3 recs         │
        │ horizon             │                       │ → pick one → custom  │
        └────────┬────────────┘                       └──────────┬───────────┘
                 │                                               │
                 ▼                                               ▼
        ┌─────────────────────┐                       ┌──────────────────────┐
        │ template-brief      │                       │ custom-1..custom-5   │
        │ (per-template page) │                       │  (legacy form steps) │
        └────────┬────────────┘                       └──────────┬───────────┘
                 │                                               │
                 └──────────────────────┬────────────────────────┘
                                        │
                                        ▼
                          ┌──────────────────────────────┐
                          │  SummaryStep (4-block model) │
                          │  WHAT │ WHEN IN │ HOW MUCH │ WHEN OUT │
                          └──────────────┬───────────────┘
                                         │  applyRiskLevel(preset)
                                         ▼
                          ┌──────────────────────────────┐
                          │  POST /api/backtest/run      │
                          │  - preflight (universe+data) │
                          │  - data quality gate          │
                          │  - engine.run()              │
                          │  - credibility warnings      │
                          └──────────────────────────────┘
```

Both flows converge on the same `SummaryStep` and the same backtest endpoint. The difference is upstream: template path starts from a chosen template; custom path starts from the wizard's recommendation (or a free-form idea via chat).

---

## 3. Module inventory

### 3.1 Shared infrastructure (used by both flows)

| Module | Path | Status | Notes |
|---|---|---|---|
| `StrategyJSON` schema (22 strategy_types) | `apps/api/app/schemas/strategy.py` | ✅ | Includes `target_vol_annual`, `signal_weighted` sizing, all v2/v3 strategy types. |
| `BacktestEngine` (cross-sectional helper, vol-target overlay) | `apps/api/app/services/backtester/engine.py` | ✅ | `vol_target` overlay implemented at line 702; `_generate_cross_sectional_weights` is the shared rank-and-select helper. |
| `SignalProvider` abstraction (4 concrete providers) | `apps/api/app/services/backtester/signal_provider.py` | ✅ | `FundamentalSignalProvider`, `SentimentSignalProvider`, `EarningsEventSignalProvider`, `InsiderSignalProvider`. Disclosure-date lag enforced. |
| `backtest_preflight` (universe + data) | `apps/api/app/services/backtest_preflight.py` | ✅ | `validate_universe` + `ensure_data_available` shared by `/api/backtest/run` and anonymous endpoint. |
| `DataQualityService` (blocks bad backtests) | `apps/api/app/services/data_quality_service.py` | ✅ | Pre-engine gate that returns `blocked` / `warning` / `ok`. |
| `_credibility_warnings` (post-engine reality check) | `apps/api/app/api/routes/backtest.py:31` | ✅ | Flags Sharpe > 2.0, win rate > 80% with ≥10 trades, total return > 100% in < 1 yr. |
| `chat_guardrails` (refusal classification, citation enforcement) | `apps/api/app/services/chat_guardrails.py` | ✅ | LLM response auditor for the chat builder path. |
| `applyRiskLevel(preset)` (frontend) | `apps/web/src/lib/strategy-picker/risk-presets.ts` | ✅ | Maps low/medium/high → `target_vol_annual`, `max_drawdown_stop`, `stop_loss_pct`. PR-D shipped. |
| Entitlement-based caps (universe size, history) | `apps/api/app/api/routes/backtest.py:_enforce_custom_caps` | ✅ | Tier-gated; shadow-mode logging when `GATING_ENABLED=false`. |
| PostHog telemetry on backtest start/complete | `apps/api/app/api/routes/backtest.py` | ✅ | `backtest_started`, `backtest_completed` events. |
| `template_usage_events` table (for quarterly cycle telemetry) | — | ❌ | Spec'd in `/Quant Strategy/framework/sql-schema.sql` but not yet in `apps/api/app/models/`. |

### 3.2 "Use Template" modules

| Module | Path | Status | Notes |
|---|---|---|---|
| Template catalog | `apps/web/src/lib/contracts.ts:researchTemplates` | ✅ | 25 templates with full metadata (category, evidence, capacity, horizon). |
| Template catalog mirror for chat | `apps/api/app/services/chat_tools/template_search.py` | 🟡 | Drift risk: manual mirror of frontend catalog. Noted in source as a backlog candidate. |
| Gallery page (filter/search) | `apps/web/src/app/templates/page.tsx` | ✅ | Category, evidence, capacity, horizon badges + filtering. |
| Per-template detail page | `apps/web/src/app/templates/[slug]/page.tsx` | ✅ | Read-only details for a single template. |
| `StrategyBuilderModal` template path | `strategy-builder-modal.tsx` | ✅ | Step machine: `launch → template-pick → template-brief → template-universe → summary → preview`. |
| Universe input (basket builder) | `components/universe-input.tsx` | ✅ | |
| `SummaryStep` 4-block UI | `components/strategy-builder/summary-step.tsx` | ✅ | WHAT (read-only universe), WHEN IN (read-only signal copy), HOW MUCH (editable: risk preset + weights + capital + costs), WHEN OUT (read-only signal copy). |
| Risk preset → StrategyJSON | `lib/strategy-picker/risk-presets.ts` | ✅ | `applyRiskLevel()` shipped. |
| Backtest endpoint (`POST /api/backtest/run`) | `apps/api/app/api/routes/backtest.py` | ✅ | |
| Backtest result viewer (workspace) | `components/workspace/research-workspace.tsx` | ✅ | Equity curve, drawdown, monthly heatmap, trade log. |
| **Asset behavior fingerprint** ("This stock has trended 70% of the time") | — | ❌ | Not implemented. Would compare the user's chosen ticker to the template's "ideal fit profile". |
| **Soft mismatch warnings** ("RSI on trending asset") | — | ❌ | Backend has `credibility_warnings` for post-hoc; no pre-hoc check that the template-asset combination is well-fitted. |
| **Per-template usage telemetry** | — | ❌ | `template_usage_events` table not wired; PostHog has the events but they're not normalized into the analytics DB for the quarterly cycle. |
| Chat tool: `template_search` | `services/chat_tools/template_search.py` | ✅ | Chat-driven template discovery. |

**"Use Template" flow score: 12/15 modules shipped, 1 partial, 2 missing.**

### 3.3 "Custom Build" modules

| Module | Path | Status | Notes |
|---|---|---|---|
| `StrategyWizard` (5 questions, scoring, recs) | `components/strategy-builder/wizard/strategy-wizard.tsx` | ✅ | One-question-at-a-time flow with animations. Asset at Q1. |
| Wizard scoring engine | `wizard/strategy-wizard-recommend.ts` | ✅ | Direct port from `Retail_Strategy_Picker_Framework.html`. Unit-tested. |
| Wizard strategy profiles (20 strategies) | `wizard/strategy-wizard-data.ts` | ✅ | Per-strategy `asset/behavior/goal/cadence/drawdown` profiles. |
| Chat-based strategy parser (free-form input) | `services/strategy_parser.py` | ✅ | LLM + deterministic parser fallback. Supports `previous_strategy_json` for multi-turn. |
| Chat tool: `strategy_builder_iterate` | `services/chat_tools/strategy_builder_iterate.py` | ✅ | Wraps parser for LLM tool-calling. |
| `SummaryStep` HOW MUCH editor (sizing, weights, capital, costs) | `summary-step.tsx` | ✅ | Editable. |
| **Signal primitive library** (the "atoms" — MA filter, RSI band, etc.) | — | ❌ | Each primitive exists as a `StrategyRule.signal_source` value, but there's no UI dropdown/picker exposing them to users for assembly. |
| **WHEN IN / WHEN OUT signal composer** (checkbox-AND/OR primitive picker) | `summary-step.tsx` whenIn/whenOut blocks | ❌ | Currently read-only template-baked copy (`template.whenInCopy ?? deriveWhenIn(...)`). User cannot pick primitives. |
| **Signal composition operator** (`logic_with_prior` field) | `apps/api/app/schemas/strategy.py:StrategyRule` | ❌ | Schema doesn't yet carry the AND/OR-with-prior-rule flag. |
| **Cross-block consistency validator** (entry trend + exit MR = warn) | `services/strategy_validator.py` | 🟡 | Validator exists but only does a few warnings (`pairs_trading expects 2 symbols`, `vol_target without target`). No entry/exit semantic check. |
| **Turnover-vs-cost reality check** | — | ❌ | No pre-backtest warning that `daily rebalance + 5-bps slippage = unprofitable`. |
| **Asset behavior fingerprint** (compute trending % from price history) | — | ❌ | Same gap as in template flow. |
| **Per-primitive fire-rate report** (signal introspection) | — | ❌ | Backtest result doesn't yet show "primitive A fired 200 times; primitive B fired 12 times". |
| **Contribution attribution** ("which primitive was the deciding factor") | — | ❌ | Same — needs engine to track per-primitive truth values per bar. |
| **Save / fork / share custom strategy** | `services/saved_strategy_service.py` | ✅ | `saved_strategies` table + endpoints work. |

**"Custom Build" flow score: 7/15 modules shipped, 1 partial, 7 missing.**

---

## 4. Gap analysis: what's actually needed to ship a real custom builder

The seven missing custom-build modules cluster into three workstreams. Each can ship independently.

### Workstream A — Signal composition (biggest unlock)

Five modules, all interdependent:

1. **Schema: add `logic_with_prior` to `StrategyRule`** (1 PR, ~30 min)
   - Additive `Optional[Literal["AND","OR"]]` field.
   - Backwards-compatible; existing templates ignore it.

2. **Engine: read multi-rule strategies with composition** (1 PR, ~3 hours)
   - For per-asset boolean strategies (`bollinger_mean_reversion`, `rsi_mean_reversion`, etc.), if multiple rules exist, evaluate each into a Series, then fold with the `logic_with_prior` operator.
   - For cross-sectional strategies, this becomes a multi-factor score combine (already implemented for `multi_factor_composite`).

3. **Signal primitive catalog (frontend)** (1 PR, ~2 hours)
   - A typed catalog `signal_primitives.ts` that lists every primitive the engine supports (~13 entries from the prior conversation's Layer 1 table) with: id, family, user-facing label, parameters with sane defaults and ranges, asset compatibility.

4. **WHEN IN / WHEN OUT block UI** (1 PR, ~4 hours)
   - In `summary-step.tsx`, replace the read-only `whenIn`/`whenOut` blocks with an editable picker: checkbox list of primitives + an AND/OR toggle + per-primitive parameter editors (sliders for thresholds, dropdowns for windows).
   - "Use template defaults" button restores the read-only template copy.

5. **Frontend wiring: composer → StrategyJSON** (1 PR, ~2 hours)
   - When user submits, serialize the picked primitives into the existing `rules` array shape with `logic_with_prior`.

### Workstream B — Pre-backtest guardrails

Three modules:

6. **Asset behavior fingerprint service** (1 PR, ~3 hours)
   - Backend: `services/asset_behavior_service.py:classify(ticker) → {trending_pct, mean_reverting_pct, realized_vol, max_drawdown_5y, sample_size_years}`. Pure price-history computation; no new data sources.
   - Surface in `/api/strategy/preview` so the summary step can show "This asset has trended 65% of the time" next to the strategy's "Works best on trending assets" copy.

7. **Cross-block consistency validator** (1 PR, ~1 hour)
   - Extend `strategy_validator.validate_strategy` to flag semantic mismatches:
     - entry uses trend-family primitive + exit uses mean-reversion primitive → warn
     - entry uses fundamental ranking + exit uses price stop → fine (no warning)
   - Returns warnings, not errors. User can override.

8. **Turnover-vs-cost preflight** (1 PR, ~1 hour)
   - Compute `expected_turnover × (transaction_cost_bps + slippage_bps)` and compare to a typical 8–10% annual return. If costs > 50% of expected return, return a warning.
   - Cheap heuristic — no engine run needed.

### Workstream C — Backtest introspection

Two modules that polish the result UX:

9. **Per-primitive fire-rate reporter** (1 PR, ~3 hours)
   - Engine: while evaluating multi-rule strategies, count how often each primitive returned true, store on the result.
   - Frontend: render in the result viewer as a small panel: "RSI < 30 fired 23 times. Price > MA fired 412 times."

10. **Contribution attribution** (1 PR, ~5 hours)
    - For each entry, log which primitive flipped from false → true on that bar (the "deciding" one for AND composition; the "first true" for OR).
    - Frontend: hover any trade in the trade log to see which primitive triggered it.

---

## 5. Recommended build queue

Ordered by user impact ÷ effort. Ship A1+A2+A3+A4+A5 together as one "signal composer" release; the rest can stage independently.

| # | Workstream | Module | Effort | Why this order |
|---|---|---|---|---|
| 1 | A | Schema `logic_with_prior` + Engine multi-rule fold | ~3h | Foundation; everything above needs it. |
| 2 | A | Signal primitive catalog (frontend) | ~2h | Data structure for the UI. |
| 3 | A | WHEN IN / WHEN OUT composer UI | ~4h | The visible deliverable. |
| 4 | A | Composer → StrategyJSON wiring | ~2h | Closes the loop. |
| 5 | B | Asset behavior fingerprint | ~3h | Cheap; high educational value; both flows benefit. |
| 6 | B | Cross-block consistency validator | ~1h | One-hour win; catches a real misuse. |
| 7 | B | Turnover-vs-cost preflight | ~1h | Same — small but valuable. |
| 8 | C | Per-primitive fire-rate report | ~3h | First introspection feature; teaches users about their strategy. |
| 9 | C | Contribution attribution | ~5h | Bigger; defer to after #1-8 land. |
| 10 | shared | `template_usage_events` table + wiring | ~2h | Feeds the quarterly iteration cycle's Step 1 telemetry. |

**Workstream A as one shipping unit: ~11 hours of focused engineering.** That's the meaningful unlock — once #1–4 land, Livermore has a real, retail-readable custom strategy builder with composable signals, not just a template gallery with editable risk knobs.

---

## 6. Things you've already shipped that surprised me (in a good way)

- **22 strategy types in the engine**, including the fundamental + sentiment + multi-factor branches. I expected to see 6–8 still in `partial`.
- **SignalProvider abstraction with disclosure-date lag**. The point-in-time guarantee is baked into the fundamental provider — that prevents the single biggest backtest bug (lookahead bias) at the architectural level.
- **`chat_guardrails`** doing refusal classification AND uncited-numeric detection with reprompt loop. That's prod-grade. Most apps would have neither.
- **`applyRiskLevel` shipped, exactly as specced in `risk_control_prompt.md`**. Round-trip from doc → code worked.
- **`DataQualityService` pre-engine gate** + **`_credibility_warnings` post-engine** — both belts and braces. The "Sharpe > 2.0" warning will save many users from trusting a survivorship-biased backtest.
- **Two-path orchestrator (`StrategyBuilderModal`)** is clean — template path and custom path converge on `SummaryStep`, which is the right architecture.

---

## 7. Things that aren't broken but are worth a future refactor

- **`template_search.py` mirrors `contracts.ts`** as a hand-maintained list. Drift is inevitable. Move the catalog to backend; have frontend fetch via API. (Already noted in the source as a backlog candidate.)
- **`strategy-wizard-data.ts`** has 20 strategy profiles; `contracts.ts` has 25 research templates; the mapping between them is partial. Worth consolidating into one source of truth (probably `contracts.ts`).
- **`custom-1` through `custom-5` steps in the modal** look like a legacy form-driven flow from before the wizard. May be dead code or rarely used; check usage before deleting.
- **No `SignalProvider` for price-based primitives**. They're computed inline in `engine._generate_weights`. If you ever want truly composable primitives (Workstream A above), promote price primitives to providers too — same protocol, different implementation.

---

## 8. Cross-references

- Iteration framework: `framework/Livermore_Library_Iteration_Framework.html`
- Quarterly runbook: `framework/quarterly-runbook.md`
- Risk-level adjustment spec: `framework/risk_control_prompt.md`
- Retail picker framework (interactive): `framework/Retail_Strategy_Picker_Framework.html`
- Strategy Library v2 (catalog + integration prompts): `Quant Strategy building/Livermore_Strategy_Library_v2.html`

---

*Audit performed against `main` branch HEAD `61638c1` on 2026-05-25.*
