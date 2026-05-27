# PRD-13b: Portfolio Mode (Entry Mode 2)

**Status**: Ready to build (once PRD-12 and PRD-13a have landed)
**Phase**: Sprint 1
**Depends on**:
- **PRD-12** (asset fingerprint service) — `PortfolioDiagnosisService` composes it.
- **PRD-13a** (flow runtime) — Portfolio Mode is defined as a `FlowDefinition` using the runtime.
- **Phase B signals** (currently paused per PR #107) — out of scope for this PRD; per-holding signal extension is deferred to a separate PRD that lands after Phase B is reshaped.

**Blocks**: PRD-11 frontend (its Home "Upload portfolio" CTA calls `startFlow('portfolio_mode', …)`, so this PRD must register the flow before PRD-11 can wire its trigger).

**Effort**: 1.5–2 weeks (backend + frontend, single owner)
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/livermore_product_flow_v2.html`](../../Quant%20Strategy/framework/livermore_product_flow_v2.html) — §2 Mode 2, §5 Surface 1, Surface 5, §6 Engineering

---

## 🤖 Coding-agent kickoff prompt

> Paste into a fresh Claude Code session. Each prompt is self-sufficient — Claude Code only needs `CLAUDE.md` (auto-loaded) plus this prompt to start.

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded on boot) for branch / PR / Python-3.9-compat rules.

Goal: build "Portfolio Mode" — the entry mode that takes a user's existing
holdings as the universe and applies a chosen overlay rule (defensive,
rotation, or rebalance). Triggered from two UI locations:

  1. Home page "Upload portfolio" CTA  (PRD-11 will wire this; this PRD
     pre-registers the flow so PRD-11 can call startFlow('portfolio_mode'))
  2. Strategy Builders, when user picks a multi-ticker template, the universe
     picker offers "Use my portfolio" (this PRD wires it)

PREREQUISITES (must be on main before starting):
  - PRD-12: AssetFingerprintService + GET /api/stocks/{ticker}/fingerprint
  - PRD-13a: lib/flows/ runtime infrastructure (types, runtime, registry, copy)

OUT OF SCOPE for this PRD:
  - Per-holding signal extension on signal_service / signal_alert.py.
    Phase B is paused (PR #107); per-holding signals will ship in a
    follow-up PRD after Phase B is reshaped.
  - Backtest "tease" numbers on overlay cards. Cards render with neutral
    descriptions; live mini-backtests are 2-5s each and Sprint 1 ships
    without them (Sprint 2 polish PRD will add).

Context to read in order:
  - /Quant Strategy/framework/livermore_product_flow_v2.html §2 Mode 2, §6
  - /Quant Strategy/framework/strategy_builder_audit.md (current state)
  - agent-system/plans/HANDOFF-livermore-product-flow-v2.md (sprint plan)
  - agent-system/plans/PRD-13a-flow-runtime-infra.md (the runtime you'll use)
  - agent-system/plans/PRD-13b-portfolio-mode.md (this file)

Architecture rules for this PRD (the four principles, see HANDOFF §2):
  1. Reuse existing strategy-builder modules — don't fork the wizard.
  2. Build LEGO bricks others can plug.
  3. Define Portfolio Mode as a `FlowDefinition` using the PRD-13a runtime.
  4. Match UX rules: consistent labels via useFlowCopy('portfolio_mode', key),
     <300ms perceived load (skeleton states), prefetch next step on idle.

Acceptance: the "Acceptance Checklist" section at the bottom of this PRD,
fully ticked. Branch as `<your-agent-name>/feat/portfolio-mode`. Open one PR
when all phases land; do NOT split into stacked PRs (CI gotcha — see
CLAUDE.md §"Stacked PRs lose backend CI").
```

---

## Design Constraints (the four principles)

These apply to every line of code in this PRD. Claude Code should re-read these before each phase begins.

### 1. Reuse, don't replicate

This PRD adds Mode 2. It must not add a new wizard, a new backtest pipeline, a new save format, or a new result viewer. All four exist. The novel work is:

- portfolio upload component
- portfolio diagnosis service + UI
- overlay-picker step
- engine extension for `inherited_universe`

Everything else — risk preset, summary step, backtest run, result viewer, save / publish / monitor — **must** reuse what's in `apps/web/src/components/strategy-builder/` and `apps/api/app/services/backtester/`.

### 2. LEGO bricks

Every new component/function in this PRD is either:

- **A brick** — reusable across modes, with a documented contract.
- **A composer** — wires bricks for *this* mode only, no logic beyond composition.

A "Mode 2 portfolio-upload page" that contains business logic is forbidden. The Portfolio Upload **brick** lives in `apps/web/src/lib/flows/bricks/portfolio-upload.tsx`; the Mode 2 **flow** lives in `apps/web/src/lib/flows/portfolio-mode.ts` and is purely declarative.

The bricks created by this PRD are inventoried at the end of this doc; future PRDs (Mode 1 refactor, Mode 3, Mode 4) will compose them.

### 3. Mode is a `FlowDefinition`, not a route

Mode 2 is stored as `apps/web/src/lib/flows/portfolio-mode.ts`. The Home button and the Strategy Builders multi-ticker option **both** call:

```ts
startFlow('portfolio_mode', { initialContext: { tickers?, fromTemplate? } });
```

The flow runtime decides whether to render in a modal (Home trigger) or full-page (Strategy Builders trigger), persists state in `sessionStorage` so a navigation interruption doesn't lose progress, and emits typed events for analytics. New triggers (e.g., a chat command, a deep link, a community CTA) are one line:

```ts
<Button onClick={() => startFlow('portfolio_mode', { initialContext: ctx })} />
```

No duplicated step components, no duplicated state machines, no duplicated tests.

### 4. UX rules

- **Consistent language**: a `useFlowCopy(key)` hook reads from `apps/web/src/lib/flows/copy.ts`. The label for "WHAT" is the same across every mode; same for "WHEN IN", "WHEN OUT", "Backtest", "Save".
- **Sub-300ms perceived load**: every API call that exceeds 300ms must show a skeleton component. Use existing `<Skeleton>` from `components/ui/`. Use `<MockHero>` shapes from `livermore_product_flow_v2.html` mockups as references.
- **Prefetch the next likely step on idle**: when the user lands on the portfolio-diagnosis step, idle-prefetch the backtest engine's `/api/backtest/run` warm-up. When they pick an overlay, idle-prefetch the result viewer's chart libs.
- **Optimistic UI** for save / fork / subscribe. The user clicks → UI updates immediately → API confirms in background → revert + toast on failure (existing pattern in `strategy_storage.ts`).

---

## Problem

The product currently has no entry point for the most common retail starting state: *"I already own these stocks; what should I do with them?"* Today, a portfolio-holder must either:

- Pick a template and manually re-enter their holdings as the universe (high friction, error-prone)
- Build a custom strategy from scratch (only ~5% of users will)

Both are bad. The result is that portfolio-holders bounce after one session.

Backend infrastructure exists to support this (`BacktestEngine`, `SignalProvider`, `signal_service`) but assumes the strategy *defines* its universe. Portfolio Mode inverts this: the **user defines the universe**; the strategy **inherits it** and applies an overlay rule on top.

## Goals

1. **Two trigger paths to Portfolio Mode** — Home upload CTA + Strategy Builders multi-ticker template offer.
2. **Upload friction <60 seconds** from sign-in to portfolio diagnosis dashboard.
3. **Three overlay rules shipped**: defensive (trend filter), rotation (rank by momentum), rebalance (periodic re-weight).
4. **Engine extension**: `inherited_universe` field on `StrategyJSON`; new `strategy_type` values for the three overlays.
5. **Per-holding weights produced by the engine** so the saved `BacktestResult` is correctly shaped. (Per-holding *signal alerts* via cron are deferred — Phase B is paused per PR #107; future PRD.)
6. **Round-trip with save / publish / monitor** — Portfolio Mode strategies reuse the existing lifecycle.

## Non-Goals

- **Broker API integration** (Plaid, Snaptrade, etc.) — CSV upload + manual entry only for v1.
- **Tax-loss harvesting** — out of scope.
- **Multi-currency portfolios** — USD only for v1.
- **Options or short positions in the uploaded portfolio** — long equity / ETF only.
- **Portfolio optimization** (mean-variance, Black-Litterman) — overlay paradigm explicitly avoids this; we apply rules, not solve optimization problems.

## User stories

1. **As David (portfolio-holder, from Home)**, I want to upload my five holdings via CSV and see a diagnosis of my book within 30 seconds, so I can decide which overlay fits.
2. **As David**, I want to pick a "defensive" overlay and see backtested numbers within one minute, so I know whether the overlay would have helped in past drawdowns.
3. **As David**, I want to subscribe to per-holding signal alerts, so I get an email when one of my five positions flips its rule (e.g., MSFT breaks 200-day MA).
4. **As Anna (prosumer, from Strategy Builders)**, I want to pick the Sector Rotation template and apply it to *my* portfolio rather than the SPDR sector ETFs, so I rotate within my own book.
5. **As any user**, if I drop out mid-flow and come back, I want to resume where I left off — not start over.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│ Frontend                                                               │
│  Home page                  Strategy Builders                          │
│   "Upload portfolio" CTA    "Use my portfolio" (in multi-ticker tpl)  │
│           │                          │                                 │
│           └──────────┬───────────────┘                                 │
│                      ▼                                                 │
│         startFlow('portfolio_mode')                                    │
│                      │                                                 │
│  ┌───────────────────┴─────────────────────────────────┐               │
│  │ FlowRuntime (lib/flows/runtime.ts)                   │               │
│  │  - persists step state in sessionStorage             │               │
│  │  - emits step events for analytics                   │               │
│  │  - prefetches next-step assets on idle               │               │
│  └───────────────────┬─────────────────────────────────┘               │
│                      ▼                                                 │
│      portfolio-mode.ts (FlowDefinition)                                │
│      ┌─────────┬──────────┬───────────┬──────────┬─────────┐           │
│      │ upload  │ diagnose │ overlay   │ summary  │ result  │           │
│      │ <Brick> │ <Brick>  │ <Brick>   │ (reused) │ (reused)│           │
│      └─────────┴──────────┴───────────┴──────────┴─────────┘           │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Backend                                                                │
│  POST /api/portfolio/diagnose  →  PortfolioDiagnosisService            │
│                                    (style, factor exposure, behavior)  │
│                                                                        │
│  POST /api/backtest/run        →  BacktestEngine.run(strategy)         │
│   strategy.inherited_universe = [tickers]  ← NEW                       │
│   strategy.strategy_type = "portfolio_*_overlay"  ← NEW (3 types)      │
│                                                                        │
│  Cron: signal_service.compute_current_signal(saved_strategy)           │
│   → emits AGGREGATE signal in v1 (Phase B paused per PR #107).         │
│   → per-holding payload extension DEFERRED to follow-up PRD.           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Backend changes

### 1. Schema additions (additive, backwards-compatible)

`apps/api/app/schemas/strategy.py`

```python
# Add to StrategyType Literal (additive):
"portfolio_defensive_overlay",
"portfolio_rotation_overlay",
"portfolio_rebalance_overlay",

# Add to StrategyJSON model (additive Optional field):
inherited_universe: Optional[list[str]] = None
```

When `inherited_universe` is provided, the engine uses it as the universe instead of any default. When it's None, behavior is unchanged from today (full backwards compatibility for existing templates).

Validator additions in `services/strategy_validator.py`:

- If `strategy_type` starts with `portfolio_`, `inherited_universe` must be non-empty and have ≥1 ticker.
- If `inherited_universe` is set, the strategy's `universe` field is ignored at engine time (warn user).
- Defensive overlay needs ≥1 holding; rotation needs ≥3; rebalance needs ≥2 (with weights set).

### 2. Engine extension

`apps/api/app/services/backtester/engine.py`

Add three new branches in `_generate_weights`:

```python
elif strategy.strategy_type == "portfolio_defensive_overlay":
    # For each holding in inherited_universe:
    #   compute MA filter signal independently
    #   weight = original_weight * signal (0 or 1)
    # When a holding's MA signal is False, that holding's weight goes to cash.

elif strategy.strategy_type == "portfolio_rotation_overlay":
    # Use the existing _generate_cross_sectional_weights helper.
    # Universe = inherited_universe; ranking by N-month return; top-K only.

elif strategy.strategy_type == "portfolio_rebalance_overlay":
    # Apply target weights on each rebalance date.
    # No signal logic; just periodic re-weight.
```

The first one (defensive overlay) is the only genuinely new pattern. Rotation reuses `_generate_cross_sectional_weights`; rebalance is a degenerate case of static allocation with an inherited universe.

Update `_compute_lookback` for the three new types (defensive needs MA-length warmup; rotation needs momentum-lookback warmup; rebalance needs no warmup).

### 3. New service: PortfolioDiagnosisService

`apps/api/app/services/portfolio_diagnosis_service.py`

```python
class PortfolioDiagnosisService:
    def diagnose(
        self, db: Session, holdings: list[Holding]
    ) -> PortfolioDiagnosis: ...
    # Returns:
    #   - style mix (% growth / value / defensive / commodity / macro-sensitive)
    #   - factor exposure (size, value, momentum, quality, low-vol, beta-to-SPY)
    #   - behavior aggregate (% trending, mean-reverting, mixed)
    #   - sector concentration
    #   - realized portfolio vol
    #   - max drawdown over trailing 5y at current weights
```

This service composes existing services — it uses `fundamental_service` (factor exposure), `price_cache_service` (returns history), and the new asset-fingerprint helper from PRD-12.

**Brick property**: `PortfolioDiagnosisService` is reusable by future modes that ingest a list of tickers. Mode 1 ("One Asset") becomes a degenerate case (one holding); the diagnosis output is identical in shape, just with N=1.

### 4. New endpoint: POST /api/portfolio/diagnose

`apps/api/app/api/routes/portfolio.py` (new file)

**Explicit `Holding` model** (write this exactly into `apps/api/app/schemas/portfolio.py`):

```python
class Holding(BaseModel):
    """One position in the user's portfolio.

    The user MUST provide either `weight` or `shares`. If both are present,
    `weight` wins (the user has expressed their intent via target allocation).
    `cost_basis_per_share` is optional and used only for P&L display in the
    diagnosis dashboard — it does NOT affect the backtest.
    """
    ticker: str = Field(..., min_length=1, max_length=10)
    weight: Optional[float] = Field(None, ge=0.0, le=1.0,
        description="Target portfolio weight 0..1. Wins over `shares` if both present.")
    shares: Optional[float] = Field(None, gt=0.0,
        description="Number of shares held. Used only if `weight` is None.")
    cost_basis_per_share: Optional[float] = Field(None, gt=0.0,
        description="USD per share. Optional. Display only — does not affect backtest.")

    @model_validator(mode="after")
    def at_least_one_size_field(self) -> "Holding":
        if self.weight is None and self.shares is None:
            raise ValueError(f"Holding {self.ticker}: must provide weight OR shares")
        return self

class DiagnoseRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=100,
        description="Portfolio holdings. Capped by tier (Scout: 5, Strategist: 25, Quant: 100).")

class DiagnoseResponse(BaseModel):
    diagnosis: PortfolioDiagnosis
    recommended_overlays: list[OverlayRecommendation]
    cache_hit: bool  # for debugging / metrics
```

Endpoint logic:

```python
@router.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose_portfolio(
    payload: DiagnoseRequest,
    auth: tuple = Depends(require_entitlement(needs_run_quota=False)),
    db: Session = Depends(get_db),
) -> DiagnoseResponse:
    user, ent = auth

    # 1. Rate limit (see below)
    enforce_diagnose_rate_limit(db, user, ent)

    # 2. Cache lookup
    cache_key = _make_cache_key(payload.holdings)
    cached = redis_get(cache_key)
    if cached:
        return DiagnoseResponse(**cached, cache_hit=True)

    # 3. Resolve + diagnose
    diag = await service.diagnose(db, payload.holdings)
    recs = service.recommend_overlays(diag)
    response = DiagnoseResponse(diagnosis=diag, recommended_overlays=recs, cache_hit=False)

    # 4. Cache for 60 min
    redis_setex(cache_key, 3600, response.model_dump_json())

    # 5. Increment usage counter
    increment_portfolio_diagnose_run(db, user.id)

    return response
```

**Caching**:

```python
def _make_cache_key(holdings: list[Holding]) -> str:
    # Cache key independent of weight precision noise: sort by ticker,
    # round weights to 4 decimal places.
    parts = sorted(
        f"{h.ticker}:{round(h.weight or 0, 4)}:{round(h.shares or 0, 4)}"
        for h in holdings
    )
    return "portfolio_diag:" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
```

Cache layer: reuse Redis if available (`services/live_quote_service.py` patterns); otherwise fall back to an in-process LRU. TTL: **60 minutes**.

**Rate limits** (tier-gated):

| Tier | Diagnoses per hour |
|---|---|
| Scout | 5 |
| Strategist | 50 |
| Quant | Unlimited (effectively 10,000/hour hard cap) |

Implementation:
1. Add new migration: `weekly_usage.portfolio_diagnose_runs_hourly` INTEGER column with `last_reset_hour` TIMESTAMP.
2. Add `enforce_diagnose_rate_limit(db, user, ent)` helper that checks the count, increments on success, and raises 402 with `code="portfolio_diagnose_rate_limit"` when exceeded.
3. PostHog event: `portfolio_diagnose_rate_limited` on block.

**Why caching matters**: `PortfolioDiagnosisService.diagnose()` reads 5y of price history per ticker (`price_cache_service`) plus fundamentals (`fundamental_service`). For a 10-holding portfolio that's ~2–5 seconds. Without cache, every keystroke on the upload form (if we ever introduce live preview) would re-run this; with a 60-min cache keyed by the holdings hash, re-runs of the same portfolio are instant.

**Why rate-limiting matters**: the endpoint is expensive (~2-5s of CPU per call). Without a tier cap, a single user could DoS the service or run up cost on the LLM-based behavior classifier downstream.

### 5. Per-holding signal extension — DEFERRED (not in this PRD)

Originally scoped here; **removed** because:
- `signal_service.compute_current_signal` and `signal_alert.py` were reverted by PR #101.
- PR #107 marked Phase B as "paused for reshape." Touching either file in this PRD would conflict with the in-progress reshape.

**What this PRD ships instead**: the *engine* produces per-holding weights in the `BacktestResult` (since each overlay strategy_type emits a multi-column weights matrix). The aggregate-level signal cron continues unchanged. When a Portfolio Mode strategy is saved, the cron emits an aggregate signal payload (existing behavior) — the per-holding payload extension is a follow-up PRD.

**When Phase B is reshaped**, a follow-up PRD (PRD-19 or similar) will:
- Extend `signal_service.compute_current_signal` to emit per-holding payloads for `portfolio_*_overlay` strategy types
- Update `signal_alert.py` email template to render the per-holding table

The current PRD's StrategyJSON shape is forward-compatible with that future change — no schema rework needed.

<details>
<summary>Original spec (kept for reference; do NOT implement in this PRD)</summary>

`apps/api/app/services/signal_service.py`

When a `SavedStrategy` has a `portfolio_*_overlay` strategy_type, the cron emits **N signals** (one per holding) rather than one aggregate. Schema:

```python
# Existing: {"position": "long", "ticker": "NVDA"}
# Portfolio overlay (NEW):
{"holdings": [
    {"ticker": "NVDA", "position": "long",  "rule": "above_200ma"},
    {"ticker": "MSFT", "position": "cash",  "rule": "above_200ma"},
    ...
]}
```

`signal_alert.py` email template extended to render the per-holding table.

</details>

### 6. Test plan

`apps/api/tests/`

- `test_portfolio_diagnosis.py` — mock the underlying services; assert style mix sums to 1.0; factor exposures non-null.
- `test_portfolio_overlay_defensive.py` — synthetic 3-symbol portfolio, run defensive overlay, assert per-holding signals.
- `test_portfolio_overlay_rotation.py` — same, with rotation logic.
- `test_portfolio_overlay_rebalance.py` — same, with rebalance.
- `test_inherited_universe_validation.py` — backwards-compat: existing templates without `inherited_universe` still pass; portfolio overlays without it fail validation.
- `test_portfolio_diagnose_cache.py` — second identical request hits cache; cache invalidates after 60 min.
- `test_portfolio_diagnose_rate_limit.py` — Scout tier blocked after 5/hour; Strategist after 50/hour; Quant unlimited.

---

## Frontend changes

> **Prerequisite**: PRD-13a (flow runtime) must be on `main` before any of this frontend work starts. This PRD consumes the runtime API and registers `portfolio_mode` as the first concrete `FlowDefinition`.

### 1. Folder layout (additions to existing `lib/flows/`)

`apps/web/src/lib/flows/`

```
flows/
├── types.ts          ← PRD-13a (already exists)
├── runtime.ts        ← PRD-13a (already exists)
├── registry.ts       ← PRD-13a (already exists)
├── copy.ts           ← PRD-13a (already exists)
├── bricks/           ← ADDED by this PRD
│   ├── portfolio-upload.tsx
│   ├── portfolio-diagnosis.tsx
│   └── overlay-picker.tsx
└── portfolio-mode.ts ← ADDED by this PRD — the FlowDefinition (declarative, no JSX)
```

The Portfolio Mode context type extends `FlowContextBase` from PRD-13a:

```ts
import type { FlowContextBase } from "./types";

export interface PortfolioModeContext extends FlowContextBase {
  holdings?: Holding[];
  diagnosis?: PortfolioDiagnosis;
  selectedOverlay?: 'defensive' | 'rotation' | 'rebalance';
  strategyJson?: StrategyJson;
  /** If launched from a multi-ticker template, this carries the template
   *  id so the OverlayPicker can default to "Rotation" if user picked
   *  Sector Rotation, etc. */
  fromTemplate?: string;
}
```

### 2. The three new bricks

`apps/web/src/lib/flows/bricks/portfolio-upload.tsx`

```tsx
export function PortfolioUpload({ onComplete }: FlowStepProps) {
  // Three input methods:
  //   - CSV drop / file picker
  //   - Manual ticker + weight entry (table)
  //   - Paste from clipboard (CSV format)
  // Validates: all tickers resolve via symbol_service; weights sum to 1.0 (warn, don't block).
}
```

`portfolio-diagnosis.tsx`

```tsx
export function PortfolioDiagnosis({ context, onComplete }: FlowStepProps) {
  // Calls POST /api/portfolio/diagnose
  // Shows: style mix donut, factor exposure bars, behavior aggregate, sector breakdown
  // Skeleton during load; renders in <300ms perceived (skeleton appears <50ms)
  // Idle-prefetches the overlay-picker assets
}
```

`overlay-picker.tsx`

```tsx
export function OverlayPicker({ context, onComplete }: FlowStepProps) {
  // Three cards: Defensive / Rotation / Rebalance
  // Each card shows a one-line NEUTRAL DESCRIPTION (not a backtest tease).
  // Pick → builds StrategyJSON with inherited_universe + portfolio_*_overlay strategy_type
  //   → hands off to existing SummaryStep (HOW MUCH editor)
}
```

**Backtest tease — DEFERRED to Sprint 2 polish PRD.** The original spec called for each card to show a one-line backtest result (e.g. "2022 DD −12% instead of −24%") computed by a "sub-500ms pre-backtest call." On investigation, this is non-trivial:

- A real mini-backtest against the user's portfolio is 2–5 seconds per overlay (not 500ms).
- A precomputed lookup (e.g. "defensive on a 60/40 portfolio in 2022") is fast but not portfolio-specific — risks being misleading.
- A live tease defeats the cache (every card click recomputes for fresh data).

**Sprint 1 ships cards with neutral copy**:
- Defensive: "Holds each name only when above its 200-day trend; sells back to cash when it breaks down. Best when you want to limit downside."
- Rotation: "Rebalances monthly to the top-3 holdings by 6-month return. Best when you want to follow strength."
- Rebalance: "Periodically re-weights back to your target allocation. Best when you want discipline without timing."

After the user picks an overlay, they run the actual backtest in the next step (existing pipeline) and get the real numbers. A Sprint 2 follow-up PRD ("Overlay backtest tease") will pre-compute coarse aggregate stats (e.g. "Defensive overlay on growth-tilted portfolios in 2022: average DD reduction = 8pp") and surface them as benchmarks rather than per-portfolio claims.

### 3. The flow definition

`apps/web/src/lib/flows/portfolio-mode.ts`

```ts
import { PortfolioUpload, PortfolioDiagnosis, OverlayPicker } from './bricks';
import { SummaryStep, BacktestRunner, ResultViewer, SaveStrategy } from '@/components/strategy-builder';
import { registerFlow } from './registry';
import { registerModeCopy } from './copy';

export const PortfolioModeFlow: FlowDefinition<PortfolioModeContext> = {
  id: 'portfolio_mode',
  name: 'Portfolio Overlay',
  triggers: [
    'home/upload_portfolio',
    'builders/multi_ticker_use_my_portfolio',
  ],
  initialStepId: 'upload',
  steps: [
    { id: 'upload',    brick: PortfolioUpload,    next: () => 'diagnose' },
    { id: 'diagnose',  brick: PortfolioDiagnosis, next: () => 'overlay' },
    { id: 'overlay',   brick: OverlayPicker,      next: () => 'summary' },
    { id: 'summary',   brick: SummaryStep,        next: () => 'backtest' },  // REUSED
    { id: 'backtest',  brick: BacktestRunner,     next: () => 'review' },    // REUSED
    { id: 'review',    brick: ResultViewer,       next: () => 'save' },      // REUSED
    { id: 'save',      brick: SaveStrategy,       next: () => null },        // REUSED, terminal
  ],
  onComplete: (ctx) => {
    // navigate to /strategies/[slug] (the saved strategy detail page)
  },
};

// Side-effects on module load — registers this flow and its copy
registerFlow(PortfolioModeFlow);
registerModeCopy('portfolio_mode', {
  upload_title:       "Upload your portfolio",
  upload_csv_label:   "Drop a CSV or pick a file",
  diagnose_title:     "Your portfolio at a glance",
  overlay_title:      "Pick an overlay",
  overlay_defensive:  "Defensive",
  overlay_rotation:   "Rotation",
  overlay_rebalance:  "Rebalance",
  // ... etc.
});
```

This is pure data. Zero business logic. Same structure will be used in PRD-15 (`thesis-mode.ts`), PRD-16 (`custom-build-mode.ts`), and a future refactor of Mode 1.

### 4. Wiring the two triggers

**Home page** (PRD-11 will own the home redesign; it consumes this hook):

```tsx
<Button onClick={() => startFlow('portfolio_mode', {
  initialContext: { fromTrigger: 'home/upload_portfolio' }
})}>Upload portfolio</Button>
```

**Strategy Builders multi-ticker template universe picker**:

```tsx
// In StrategyBuilderModal, when chosen template has min_universe_size > 1:
<UniverseOption onClick={() => startFlow('portfolio_mode', {
  initialContext: {
    fromTrigger: 'builders/multi_ticker_use_my_portfolio',
    fromTemplate: chosenTemplate.id,
  }
})}>Use my portfolio</UniverseOption>
```

Both call the same flow. The `fromTrigger` context value lets the flow customize copy slightly ("Apply Sector Rotation to your portfolio" vs. "Pick an overlay for your portfolio") without code duplication.

### 5. Test plan

`apps/web/src/lib/flows/__tests__/`

- `portfolio-mode.flow.test.ts` — drive the flow through all 7 steps with mocked bricks; assert state transitions and context propagation.
- `portfolio-upload.brick.test.tsx` — CSV parsing, manual entry, validation errors.
- `portfolio-diagnosis.brick.test.tsx` — skeleton shows <50ms; renders diagnosis from mocked API.
- `runtime.test.ts` — sessionStorage persist + resume.

---

## Reusable LEGO bricks created by this PRD

For the next PRD (Mode 3, Mode 4, etc.) authors to know what's already on the shelf:

### Backend bricks (created by this PRD)

| Brick | Purpose | Used by |
|---|---|---|
| `StrategyJSON.inherited_universe` | Decouple universe from strategy_type | Any future mode that ingests user-defined tickers |
| `Holding` Pydantic model | Canonical shape for a portfolio position | Any mode/endpoint ingesting holdings |
| `PortfolioDiagnosisService.diagnose(holdings)` | Style + factor + behavior aggregate | Mode 1 (degenerate N=1 case), future "watchlist diagnosis" |
| `POST /api/portfolio/diagnose` (cached + rate-limited) | Endpoint exposing the above | Any frontend surface |
| `weekly_usage.portfolio_diagnose_runs_hourly` column | Per-tier diagnose rate-limiting | Any future expensive endpoint that needs hourly limits |

### Frontend bricks (created by this PRD; PRD-13a's runtime bricks listed in PRD-13a)

| Brick | Purpose | Used by |
|---|---|---|
| `portfolio-mode.ts` (FlowDefinition) | Portfolio Mode's declarative flow | Triggered by Home upload CTA + Strategy Builders multi-ticker option |
| `<PortfolioUpload>` brick | CSV/manual portfolio entry | Mode 2, future watchlist features |
| `<PortfolioDiagnosis>` brick | Renders the diagnosis output | Mode 2, future portfolio review pages |
| `<OverlayPicker>` brick | Three-card overlay selection (no tease in Sprint 1) | Mode 2 (and any future "rule overlay" patterns) |

### NOT created by this PRD (deferred)

- Per-holding signal payload in `signal_service` — deferred until Phase B reshape (separate PRD).
- Overlay backtest tease — deferred to Sprint 2 polish PRD.

---

## Acceptance checklist

A PR is accepted when **all of the following are true**. Claude Code should self-verify against this list before opening the PR.

### Backend

- [ ] `StrategyJSON.inherited_universe` field added (Optional, defaults to None) — additive change, all existing tests pass.
- [ ] Three new `strategy_type` literals added.
- [ ] Engine `_generate_weights` has three new branches; `_compute_lookback` updated for each.
- [ ] `Holding` Pydantic model implemented at `apps/api/app/schemas/portfolio.py` with the exact field definitions in §4 above.
- [ ] `PortfolioDiagnosisService` implemented; reuses `fundamental_service`, `price_cache_service`, and PRD-12's `AssetFingerprintService`.
- [ ] `POST /api/portfolio/diagnose` endpoint live with **cache (60-min, hash of sorted tickers + weights)** and **per-tier rate limit (5/50/unlimited per hour)**.
- [ ] Migration: `weekly_usage.portfolio_diagnose_runs_hourly` INTEGER + `last_reset_hour` TIMESTAMP columns added.
- [ ] PostHog events captured: `portfolio_diagnosed`, `portfolio_diagnose_rate_limited`.
- [ ] All seven new tests pass (`test_portfolio_diagnosis.py`, `test_portfolio_overlay_{defensive,rotation,rebalance}.py`, `test_inherited_universe_validation.py`, `test_portfolio_diagnose_cache.py`, `test_portfolio_diagnose_rate_limit.py`).
- [ ] **NOT changed**: `signal_service.compute_current_signal` and `signal_alert.py` (deferred until Phase B reshape).
- [ ] Full backend pytest suite passes: `cd apps/api && python3 -m pytest -q`.
- [ ] No `X | None` syntax (Python 3.9 compat per CLAUDE.md).

### Frontend

- [ ] **PRD-13a is merged to main** before any frontend work starts. This PRD assumes `lib/flows/types.ts`, `runtime.ts`, `registry.ts`, `copy.ts` exist.
- [ ] Three bricks shipped under `lib/flows/bricks/`: `portfolio-upload.tsx`, `portfolio-diagnosis.tsx`, `overlay-picker.tsx`.
- [ ] `portfolio-mode.ts` flow definition exists; is pure data (no JSX, no business logic outside the `next()` predicates).
- [ ] `portfolio_mode` registered in the flow registry on module load.
- [ ] Mode-specific copy registered via `registerModeCopy('portfolio_mode', { ... })` on module load.
- [ ] Strategy Builders multi-ticker template option → "Use my portfolio" wired → calls `startFlow('portfolio_mode', { initialContext: { fromTrigger: 'builders/multi_ticker_use_my_portfolio', fromTemplate } })`.
- [ ] Test page at `/test/flows/portfolio` exists for manual smoke testing (Home wiring lands in PRD-11).
- [ ] `useFlowCopy('portfolio_mode', key)` used everywhere; no hardcoded labels in bricks.
- [ ] Overlay picker cards show **neutral copy** (per Frontend §3) — no backtest tease.
- [ ] Skeleton states on all calls > 200ms.
- [ ] sessionStorage resume works (close tab during diagnosis step → reopen `/test/flows/portfolio` → continues from diagnosis with context intact).
- [ ] All four new tests pass.
- [ ] `cd apps/web && npm run build` clean.

### End-to-end smoke

- [ ] Upload a 5-holding CSV → diagnosis appears within 3 seconds (test env) → pick defensive overlay → backtest completes → save → strategy appears in saved-strategies list with per-holding signal payload.
- [ ] Multi-ticker template path: pick Sector Rotation template → universe picker shows "Use my portfolio" → click → flow resumes with portfolio data → same downstream behavior.
- [ ] Interrupt-and-resume: close browser at diagnosis step → reopen `/test/flows/portfolio` → flow resumes with diagnosis already loaded.

### Documentation

- [ ] Add a section to `apps/api/CLAUDE.md` documenting `inherited_universe` semantics + the three overlay strategy_types.
- [ ] Update `agent-system/WORK_LOG.md` with the PR summary.
- [ ] Add note to `docs/PROJECT_BACKLOG.md` once Portfolio Mode is shipped.

---

## Out of scope (deferred — do not build in this PRD)

- **Flow runtime itself** (`lib/flows/types.ts`, `runtime.ts`, `registry.ts`, `copy.ts`) → PRD-13a. This PRD consumes the runtime; it doesn't build it.
- **Per-holding signal payloads** in `signal_service` and `signal_alert.py` → deferred until Phase B reshape (PR #107 paused Phase B). A follow-up PRD will ship this after Phase B is unblocked.
- **Overlay backtest tease** ("DD −12% instead of −24%") on the OverlayPicker cards → deferred to a Sprint 2 polish PRD; live mini-backtests are 2–5s each, not the 500ms originally specced.
- Plaid / Snaptrade broker import → v3.
- Multi-currency portfolios → v3.
- Tax-loss harvesting → never (not in product scope).
- Portfolio optimization (Markowitz, Black-Litterman) → out of philosophy.
- Per-holding asset-fingerprint visualization on the diagnosis dashboard → PRD-12 ships fingerprint service; per-holding visualization happens in a follow-up PRD if usage warrants.
- Mode 1 refactor to use `FlowDefinition` → separate PRD; this PRD only creates the second `FlowDefinition` (Portfolio Mode) on top of PRD-13a's runtime.
- Home page "Upload portfolio" CTA wiring → PRD-11. This PRD pre-registers `portfolio_mode` in the flow registry so PRD-11's wiring is one line.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §2 Mode 2, §6 Engineering
- Current module status: `/Quant Strategy/framework/strategy_builder_audit.md`
- Module visualization: `/Quant Strategy/framework/strategy_builder_status.html`
- Risk-preset implementation reference: `/Quant Strategy/framework/risk_control_prompt.md`
- Repo conventions (auto-loaded): `/CLAUDE.md`, `/agent-system/PARALLEL_WORK.md`
- Related PRDs: PRD-11 (Home redesign, wires the Home trigger), PRD-12 (asset fingerprint, used by diagnosis), PRD-14 (Stock page "Apply a strategy", parallel work)

---

*Drafted 2026-05-26 as Sprint 1 ticket. The four principles in "Design Constraints" should appear at the top of every Sprint 1+ PRD; they're the load-bearing rules for the v2 product-flow rebuild.*
