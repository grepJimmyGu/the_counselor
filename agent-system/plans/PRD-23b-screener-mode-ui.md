# PRD-23b: Market Screener — Mode + UI (screen_mode flow + universe selector + reading composer + results)

**Status**: Ready to build (pending Jimmy's review of the packet)
**Phase**: Market Screener mode (PRD-23 packet) — phase 2 of 3
**Depends on** (on `main`): PRD-23a (scan/count + rank endpoints), PRD-13a (flow runtime), PRD-16b (composer canvas + rule cards). **Soft:** PRD-22c widgets + reading layer — the intent-first composer renders them; 23b can ship VALUE-only first and light up when 22c's remaining slices land.
**Blocks**: PRD-23c (soft — save handoff).
**Effort**: ~1.5 weeks, single owner.
**Owner**: TBD
**Read first**: `HANDOFF-livermore-market-screener.md`.

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/web). Read CLAUDE.md + apps/web/AGENTS.md
(auto-loaded — "this is NOT the Next.js you know"; read node_modules/next/dist/docs/
before writing components), then HANDOFF-livermore-market-screener.md.

Goal: ship the "Screen the market" mode UI on top of PRD-23a's backend. Four bricks:

  1. screen_mode FlowDefinition (register it; the universal /flow shell renders it)
     steps: pick-universe -> compose-reading -> results
  2. <UniverseSelector> — the few default universes (sp500 default, sector,
     watchlist, portfolio), tier-gated. REPLACES the "backtest symbol" input.
  3. <ReadingComposer> — extends PRD-16b's <CustomBuildRuleComposer>: intent chips
     + the per-output_kind widgets (PRD-22c) + a LIVE MATCH COUNT wired to
     POST /api/screen/count that updates as rules change.
  4. <ScreenResults> — the progressive ranked basket: ticker + satisfied readings
     + streamed backtest metric + "as of <date>"; click -> the existing
     single-asset backtest detail (drill-in, reused). A "Save + track" CTA -> 23c.

Types-first: add the scan/count/result types to contracts.ts BEFORE the components.

PREREQUISITES (on main): PRD-23a. Soft: PRD-22c widgets (else VALUE-only composer).

OUT OF SCOPE: backend (PRD-23a owns it), save/track (PRD-23c), intraday (PRD-23c).

DEFINITION OF DONE: see §6.
```

---

## 1. The problem

PRD-23a can scan + rank, but there's no way for a user to drive it. Today the composer asks for a symbol; the screener needs the *inverse* entry: pick a universe, compose a reading, watch it narrow the market, drill into the ranked survivors. This PRD is the market-out entry mode.

---

## 2. Design constraints

1. **Mode = FlowDefinition** (Principle 3). `screen_mode` registers via `registerFlow` and renders through `/flow/[flowId]`. No bespoke route. Triggered from the Home entry picker (PRD-11) via `startFlow("screen_mode", …)`.
2. **Reuse the composer** (Principle 1). `<ReadingComposer>` extends `<CustomBuildRuleComposer>` — same rule cards, same AND/OR fold, same StrategyJSON conversion. The new bits are the intent chips, the kind-widgets (PRD-22c), and the live count.
3. **The live match-count funnel is first-class** (Principle 4). Every rule change re-queries `POST /api/screen/count` (debounced) and updates the count. This is the discovery loop — treat it as the centerpiece, not a stat.
4. **Never a blank page** (Principle 4). `<ScreenResults>` renders the matched basket immediately (proxy-ordered), then streams the backtest-return metrics row-by-row and re-sorts (the PRD-I staged-loading pattern). Date-stamp "as of <close>".
5. **Drill-in reuses the existing backtest detail.** Clicking a result opens the shipped single-asset backtest view — no new results surface.
6. **Types-first + Next.js 16.** Add scan/count/result types to `contracts.ts` first; read `node_modules/next/dist/docs/` before components.

---

## 3. Implementation

### 3.1 `screen_mode` FlowDefinition — `apps/web/src/lib/flows/modes/screen-mode.tsx`

Steps: `pick-universe → compose-reading → results`. Saves flow state to `sessionStorage` (`livermore_flow_screen_mode`) like every mode; registered in `registry.ts`; copy in `copy.ts` (no hardcoded labels).

### 3.2 `<UniverseSelector>` — `apps/web/src/lib/flows/bricks/screener-universe-selector.tsx`

The default universes (from PRD-23a `universe_resolver`) as cards/chips: `S&P 500` (default) · `Sector` (sub-picker) · `My watchlist` · `My portfolio`. Tier-gated (Scout → capped; a `<SoftPaywall>` on the locked ones). This is the brick that replaces the "backtest symbol" input.

### 3.3 `<ReadingComposer>` — extends `<CustomBuildRuleComposer>`

- **Intent chips** at the top (the `intent_group` taxonomy from the reading layer) → picking one surfaces the handful of primitives under it.
- **Per-`output_kind` widgets** (PRD-22c): VALUE threshold · CROSS direction picker · EVENT "fires" · LEVEL "while" · REGIME chip · DISTANCE range · DIVERGENCE lookback+direction. (If 22c isn't merged yet, fall back to the VALUE widget — degraded but functional.)
- **Live match count**: a `useEffect` (debounced ~250 ms) on the composed rule-set POSTs to `/api/screen/count` and renders "N of <universe size> match today". Reads `backendToken` off `useSession()` (trap #19) and waits for `sessionStatus !== "loading"`.

### 3.4 `<ScreenResults>` — `apps/web/src/lib/flows/bricks/screener-results.tsx`

Calls `POST /api/screen/scan` then the rank stream. Renders the basket immediately (ticker · satisfied-readings chips · skeleton metric · sparkline), fills CAGR/return progressively + re-sorts. "as of <date>" byline (date-visibility invariant). Row click → existing backtest detail. Footer CTA "Save + track this screen" → PRD-23c handoff.

### 3.5 `contracts.ts` types (first)

```ts
export interface ScreenScanRequest { universe_id: string; rules: StrategyRule[]; }
export interface ScreenMatch { symbol: string; satisfied_readings: string[]; }
export interface ScreenRankedMatch extends ScreenMatch { total_return: number | null; cagr: number | null; }
export interface ScreenScanResponse { matches: ScreenMatch[]; as_of_date: string; universe_size: number; }
```

---

## 4. Testing (vitest + jsdom)

- `screen_mode` registers + renders via the `/flow` shell (mock-flow fixture pattern).
- `<UniverseSelector>`: default = sp500; tier-locked universes show the paywall.
- `<ReadingComposer>` live count: debounces, POSTs `/count`, renders the count; passes `backendToken`; waits for session resolve.
- `<ScreenResults>`: renders the basket before metrics arrive, then re-sorts when they land (progressive); "as of <date>" present; row click routes to backtest detail.
- Types-first: `npm run build` clean.

---

## 5. Pre-merge checklist

1. `cd apps/web && npm run build` — clean (types compile).
2. `cd apps/web && npm test -- screener` — green.
3. Backend untouched (`pytest -q` still green).
4. Accessibility pass on the composer + results (no new violations).
5. Branch follows `claude/feat/prd-23b-screener-mode-ui`.

---

## 6. Definition of done

- [ ] `screen_mode` FlowDefinition registered + rendered via `/flow`; Home entry-picker trigger
- [ ] `<UniverseSelector>` (default sp500 + tier gate) replaces the symbol input
- [ ] `<ReadingComposer>` with intent chips + kind-widgets + the live match-count funnel
- [ ] `<ScreenResults>` progressive ranked basket + "as of <date>" + drill-in to backtest detail
- [ ] `contracts.ts` types-first; `npm run build` clean; vitest green
- [ ] PR merged to `main` with green CI; brick inventory (HANDOFF §5) updated

---

## 7. Hand-off to PRD-23c

The "Save + track this screen" CTA hands the composed rule + `universe_id` to PRD-23c, which persists it as a `SavedStrategy` and wires the cron to notify on new basket entrants.

---

*PRD drafted 2026-06-16. Part of the Market Screener packet (`HANDOFF-livermore-market-screener.md`). Supersedes §3.6 of the single-doc draft.*
