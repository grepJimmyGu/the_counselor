# PRD-01: Research Templates Page

**Status:** Ready to build
**Phase:** 1
**Depends on:** None

---

## Problem

Users have no structured starting point for research. The demo picker shows the product working but does not teach users how to apply a framework to their own hypothesis. Templates bridge the gap between "I saw a demo" and "I know what to test."

---

## Goals

- Surface 5 research frameworks on a dedicated `/templates` page
- Let users load a pre-built example OR build their own version using the framework as context
- Communicate data availability gaps honestly before users click
- Pre-seed the workspace with the right ticker(s) and chat prompt so users start creating immediately

## Non-Goals

- Running a backtest directly from the templates page
- Personalised or recommended templates
- Community-submitted templates
- Editing template definitions (templates are product-defined, not user-editable)

---

## User Stories

1. As a user, I want to browse available research frameworks so I can find one that matches my hypothesis.
2. As a user, I want to load a pre-built example so I can see the framework in action before customising it.
3. As a user, I want to build my own version of a framework so I can test my specific hypothesis without starting from scratch.
4. As a user, I want to know upfront which templates I can run today and which require data that is not yet available.
5. As a user, I want to pick my ticker(s) on the template card so the workspace opens ready to go.

---

## Template Definitions

### Schema — add to `contracts.ts`

```ts
export type TemplateAvailability = "ready" | "unavailable" | "proxy";

export interface ResearchTemplate {
  id: string;
  name: string;
  category: "Momentum" | "Rotation" | "Factor" | "Carry";
  description: string;           // one-line card subtitle
  whatItTests: string;           // 2–3 sentences shown in card body
  dataRequirement: string;       // e.g. "Price data only"
  universe: string;              // plain English, e.g. "Any equity or ETF"
  defaultTickers: string[];      // pre-filled in the ticker input
  multiTicker: boolean;          // true for Template 2 (requires universe)
  availability: TemplateAvailability;
  dataGapReason?: string;        // shown on card when availability !== "ready"
  etfProxyCaveat?: string;       // shown in workspace when availability === "proxy"
  strategy: StrategyJson;        // pre-built strategy for "Load Example"
  chatSeed: string;              // {ticker} or {tickers} placeholder replaced at click time
}
```

Add `fiveYearsAgo` date constant alongside existing date constants:
```ts
const fiveYearsAgo = new Date(Date.now() - 5 * 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
```

---

### Drafted Strategy JSON — all 5 templates

**Template 1 — Trend Following**

Maps to `breakout` strategy type. Entry: 20-day high breakout. Exit: 10-day low. Stop loss: 8%.
Default universe: single equity (user picks). Default: AAPL.

```ts
{
  strategy_name: "Trend Following — 20-Day Breakout",
  strategy_type: "breakout",
  universe: ["AAPL"],           // replaced by user-selected ticker at load time
  benchmark: "SPY",
  start_date: fiveYearsAgo,
  end_date: today,
  initial_capital: 10000,
  rebalance_frequency: "daily",
  transaction_cost_bps: 10,
  slippage_bps: 5,
  rules: [{ entry_window: 20, exit_window: 10 }],
  position_sizing: { method: "equal_weight", max_positions: 1 },
  risk_management: { stop_loss_pct: 0.08 },
  cash_management: { hold_cash_when_no_signal: true, cash_yield_bps: 0 },
}
```

chatSeed: `"I want to build a trend following strategy for {ticker}. Tell me your rules — breakout window, exit window, or stop type."`

---

**Template 2 — Cross-Sectional Momentum**

Maps to `momentum_rotation`. Ranks universe by 6-month return, holds top 2.
Default universe: AAPL, MSFT, GOOGL, NVDA, META. User picks their own universe (multi-ticker).

```ts
{
  strategy_name: "Cross-Sectional Momentum — Top 2 of 5",
  strategy_type: "momentum_rotation",
  universe: ["AAPL", "MSFT", "GOOGL", "NVDA", "META"],  // replaced by user's universe
  benchmark: "SPY",
  start_date: fiveYearsAgo,
  end_date: today,
  initial_capital: 10000,
  rebalance_frequency: "monthly",
  transaction_cost_bps: 10,
  slippage_bps: 5,
  rules: [{ top_n: 2, ranking_measure: "total_return", ranking_lookback_days: 126 }],
  position_sizing: { method: "equal_weight", max_positions: 2 },
  risk_management: {},
  cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
}
```

chatSeed: `"I want to build a cross-sectional momentum strategy. My universe is {tickers}. Tell me: how many top performers to hold, and what lookback period to rank by."`

---

**Template 3 — ETF Rotation**

Maps to `momentum_rotation`. Rotates into top 1 asset class ETF by 3-month return.
Default universe: SPY, QQQ, IEF, GLD, DBC. Single ticker input on card (benchmark ETF the user wants to compare against).

```ts
{
  strategy_name: "ETF Rotation — Asset Class Momentum",
  strategy_type: "momentum_rotation",
  universe: ["SPY", "QQQ", "IEF", "GLD", "DBC"],
  benchmark: "SPY",
  start_date: fiveYearsAgo,
  end_date: today,
  initial_capital: 10000,
  rebalance_frequency: "monthly",
  transaction_cost_bps: 10,
  slippage_bps: 5,
  rules: [{ top_n: 1, ranking_measure: "total_return", ranking_lookback_days: 63 }],
  position_sizing: { method: "equal_weight", max_positions: 1 },
  risk_management: {},
  cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
}
```

chatSeed: `"I want to build an ETF rotation strategy. My benchmark is {ticker}. Tell me: which ETFs to rotate across, what lookback period to rank by, and how many to hold at once."`

Note: Template 3 card TickerSearch asks for the benchmark ETF, not the universe (the universe is fixed). Label: "Which benchmark do you want to compare against?"

---

**Template 4 — Value + Momentum**

Not runnable. `availability: "unavailable"`. Strategy JSON is a placeholder only — never sent to the backend.

```ts
{
  strategy_name: "Value + Momentum",
  strategy_type: "momentum_rotation",   // placeholder
  universe: ["AAPL"],
  benchmark: "SPY",
  start_date: fiveYearsAgo,
  end_date: today,
  initial_capital: 10000,
  rebalance_frequency: "monthly",
  transaction_cost_bps: 10,
  slippage_bps: 5,
  rules: [],
  position_sizing: { method: "equal_weight", max_positions: 1 },
  risk_management: {},
  cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
}
```

dataGapReason: `"Requires fundamental data (P/E, earnings) — not yet available in this tool. Shown here so you can plan your research."`

---

**Template 5 — Commodity Carry (ETF Proxy)**

Maps to `momentum_rotation`. Uses 1-month return as carry proxy. Holds top 2 commodity ETFs.

```ts
{
  strategy_name: "Commodity Carry — ETF Proxy",
  strategy_type: "momentum_rotation",
  universe: ["GLD", "SLV", "USO", "UNG", "DBA"],   // replaced by user's tickers
  benchmark: "DBC",
  start_date: fiveYearsAgo,
  end_date: today,
  initial_capital: 10000,
  rebalance_frequency: "monthly",
  transaction_cost_bps: 10,
  slippage_bps: 5,
  rules: [{ top_n: 2, ranking_measure: "total_return", ranking_lookback_days: 21 }],
  position_sizing: { method: "equal_weight", max_positions: 2 },
  risk_management: {},
  cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
}
```

etfProxyCaveat: `"This template uses an ETF proxy for futures curve data. The approximation may differ materially from actual roll yield. Treat results as directional, not precise."`

chatSeed: `"I want to build a commodity carry strategy using ETF proxies. My universe is {tickers}. Tell me: which commodity ETFs to include and how to rank them."`

---

## Ticker Input — Per Template

| Template | Input type | Label | Default |
|---|---|---|---|
| 1 — Trend Following | Single `TickerSearch` | "Which ticker do you want to test this on?" | AAPL |
| 2 — Cross-Sectional Momentum | Multi-ticker (comma-separated, min 3) | "Enter your universe (min 3 tickers, comma-separated)" | AAPL, MSFT, GOOGL, NVDA, META |
| 3 — ETF Rotation | Single `TickerSearch` | "Which benchmark do you want to compare against?" | SPY |
| 4 — Value + Momentum | None | — | — |
| 5 — Commodity Carry | Multi-ticker (comma-separated, min 2) | "Enter your commodity universe (comma-separated)" | GLD, SLV, USO, UNG, DBA |

### Multi-ticker input component (Templates 2 and 5)

New component: `UniverseInput` — a comma-separated text input with:
- Placeholder: `"AAPL, MSFT, GOOGL, NVDA, META"`
- On blur: splits by comma, trims whitespace, deduplicates
- Validation: minimum ticker count (3 for Template 2, 2 for Template 5)
- Error state: `"Enter at least {min} tickers separated by commas"`
- Does not validate tickers against the API (too expensive per keystroke) — validation happens in the workspace after load

---

## Navigation — URL Params

Both CTAs navigate to `/` and pass state via URL search params.
The workspace reads params on mount.

| CTA | URL format |
|---|---|
| Load Example (single ticker) | `/?templateId=trend-following&path=load&ticker=AAPL` |
| Load Example (multi-ticker) | `/?templateId=cross-sectional-momentum&path=load&tickers=AAPL,MSFT,GOOGL,NVDA,META` |
| Build my own (single ticker) | `/?templateId=trend-following&path=build&ticker=NVDA` |
| Build my own (multi-ticker) | `/?templateId=cross-sectional-momentum&path=build&tickers=AAPL,MSFT,NVDA` |

---

## Workspace Changes (`research-workspace.tsx`)

**Requires `useSearchParams` wrapped in `Suspense`** — Next.js App Router requirement.
Wrap the workspace page in a Suspense boundary in `app/page.tsx`.

On mount, read URL params:

```ts
const searchParams = useSearchParams();
const templateId = searchParams.get("templateId");
const path = searchParams.get("path");        // "load" | "build"
const ticker = searchParams.get("ticker");    // single ticker
const tickers = searchParams.get("tickers"); // comma-separated
```

**If `path === "load"`:**
1. Find template in `researchTemplates` by `templateId`
2. Replace `template.strategy.universe` with user's ticker(s)
3. Call `handleLoadDemo`-equivalent with the modified strategy
4. Set `templateReviewCallout = true`
5. If `template.availability === "proxy"`, set `showEtfProxyCaveat = true`
6. Scroll Strategy Preview into view after load

**If `path === "build"`:**
1. Find template by `templateId`
2. Pre-load ticker(s) into workspace ticker/universe state
3. Resolve chatSeed: replace `{ticker}` or `{tickers}` with the user's input
4. Set pre-seeded chat message in Chat Builder input
5. Focus Chat Builder

**New UI states to add:**

```tsx
// Review callout — shown after template load
{templateReviewCallout && (
  <div className="rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-2.5 text-sm text-yellow-300/80">
    Template loaded with default parameters.
    Review the rules and universe before running a backtest.
  </div>
)}

// ETF proxy caveat
{showEtfProxyCaveat && (
  <div className="rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-2.5 text-sm text-yellow-300/80">
    {template.etfProxyCaveat}
  </div>
)}

// Guided right-panel empty state — replaces generic empty state when template loaded
{strategy && !backtestResult && templateReviewCallout && (
  <div className="flex flex-col items-center justify-center py-16 text-center space-y-2">
    <p className="text-sm text-muted-foreground">Strategy loaded.</p>
    <p className="text-xs text-muted-foreground/70">
      Review the rules on the left, adjust the universe and date range
      for your hypothesis, then run the backtest.
    </p>
  </div>
)}
```

---

## `/templates/page.tsx` Layout

```
NavHeader (from root layout)

Page header
  Breadcrumb: Research Templates
  h1: Research Templates
  p: Use a structured investment framework as the starting point for
     your own hypothesis. Review the rules before running a backtest.
  Stat badge: "3 available now · 2 require additional data"

Section: Available Now
  Grid of 3 cards (Templates 1, 2, 3)

Section: Requires Additional Data
  Grid of 2 cards (Templates 4, 5)
```

Card grid: `grid gap-6 md:grid-cols-2 lg:grid-cols-3` for Available Now.
Template 4-5: `grid gap-6 md:grid-cols-2` (max 2 columns).

---

## Acceptance Criteria

**Templates page:**
- ☐ 5 cards in two clearly labelled sections
- ☐ Each card: category badge, name, description, what it tests, data requirement, universe
- ☐ Template 1, 3: single `TickerSearch`, correct label per template
- ☐ Template 2, 5: `UniverseInput` (comma-separated), correct min ticker validation
- ☐ Template 4: data gap text, no input, no CTA
- ☐ Template 5: "Load with ETF Proxy" CTA label
- ☐ CTAs disabled until valid ticker input

**Workspace flow:**
- ☐ Load Example: strategy loads, review callout shown, Strategy Preview scrolled into view
- ☐ Load Example: universe replaced with user's ticker(s) before loading
- ☐ Build my own: ticker(s) pre-loaded, chat seeded with framework prompt containing ticker(s)
- ☐ Template 5 load: ETF proxy caveat shown
- ☐ Right panel guided empty state shown when strategy loaded, no backtest run yet
- ☐ Workspace page wrapped in Suspense boundary for `useSearchParams`

**Mobile:**
- ☐ Cards stack to single column on mobile
- ☐ CTAs full-width on mobile
- ☐ `UniverseInput` readable and usable on small screens

---

## Risks and Decisions Made

| Risk | Decision |
|---|---|
| Template 2 needs multi-ticker input | New `UniverseInput` component — comma-separated, min-count validated |
| Template 3 ticker input asks for benchmark, not universe | Label changed: "Which benchmark do you want to compare against?" |
| URL params lost on workspace refresh | Acceptable for MVP — user navigates back to /templates |
| Template 4 strategy JSON is a placeholder | Never sent to backend — `availability: "unavailable"` cards have no CTA |
| `useSearchParams` requires Suspense | Wrap `app/page.tsx` children in `<Suspense>` |
| Multi-ticker not validated against API | Validation happens in workspace after load, not on the card |
