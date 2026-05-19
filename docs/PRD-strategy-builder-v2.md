# PRD: Strategy Builder V2 — Chat-Based Guided Experience

**Status:** Confirmed, ready for execution  
**Date:** 2026-05-18  
**Scope:** Strategy Builder entry point, guided chat modal, workspace research report redesign

---

## 1. Background & Motivation

The current Strategy Builder (at `/workspace`) is a power-user tool: a freeform text prompt + JSON editor + backtest runner. It is not accessible to most users and has no guided onboarding path. The Quant Strategy Framework document (Stefanini-derived) defines a tiered UX — Starter / Builder / Pro — where users are guided through the 8-Layer Strategy Framework in a structured, progressive way.

The three confirmed main pillars of the platform are now:
1. **Market Pulse** — `/stocks`
2. **Community** — `/community`
3. **Strategy Builder** — `/templates` (entry) + `/workspace` (results)

This PRD defines the V2 Strategy Builder experience: a chat-based guided modal that replaces the raw text-prompt entry, combined with a research-report–style workspace.

---

## 2. Goals

- Lower time-to-first-backtest for new users from "describe strategy in freeform text" to "pick a template, enter a ticker, run"
- Surface the 8-Layer Strategy Framework as the mental model for all strategy building
- Boost template credibility with academic evidence, performance context, and structural rationale
- Replace the cluttered workspace with a clean research report that puts results first
- Provide a compelling loading experience instead of a blank spinner

---

## 3. Entry Points

| Trigger | Action |
|---|---|
| Homepage → "Open Strategy Builder" button | Opens Strategy Builder Modal directly (no page navigation) |
| `/templates` → click any template card | Opens Modal in Template mode, pre-selecting that template |
| `/templates` → "Build Custom" button | Opens Modal in Custom mode |
| Nav → "Strategy Builder" | Navigates to `/templates` (gallery + both launch paths) |

**Key decision:** "Open Strategy Builder" from the homepage fires a **full-screen chat modal overlay** over the current page. The homepage does not navigate away.

---

## 4. Strategy Builder Modal

### 4.1 Modal Shell

- Full-screen overlay (`fixed inset-0 z-50 bg-background`)
- Close button top-right (×)
- Back button per step (← returns to prior step, not close)
- Step indicator (dots or numbered breadcrumb) for Custom mode
- State preserved on back — no reset when editing

**Opening state:** Two-option launcher
```
Hi — let's build a strategy. Where do you want to start?

[ Use a Template ]     [ Describe my own idea ]
```

---

### 4.2 Path A — Template Mode

#### Step A1: Template Picker

- Shows the existing template gallery (same grid as `/templates`) inside the modal
- Category filter pills at top
- Clicking a card advances to Step A2
- Coming-soon templates are shown greyed out / locked

#### Step A2: Strategy Brief Card

The core credibility-building screen. System displays a structured fact-sheet card (see §6 for visual spec).

Contents:
- **Header:** Strategy name + Evidence tier badge (A/B/C, color-coded emerald/amber/orange)
- **Quick stats strip (3 columns):**
  - Typical annual return range (e.g. "+8% to +16%")
  - Risk-adjusted return (e.g. "Sharpe ~1.0 – 1.5")
  - Worst stretch historically (e.g. "−22% to −35%")
- **8-layer breakdown** (numbered circles ①–⑧, plain language labels):
  1. What it trades (universe)
  2. The core idea (thesis)
  3. How it decides (signal)
  4. How it trades (execution)
  5. How it protects positions (risk)
  6. Typical hold time (liquidity)
  7. How we test it (backtest config)
  8. What to review after (attribution)
- **Credibility footer:**
  - Citation (e.g. "Jegadeesh & Titman (1993) · AQR Capital")
  - One-sentence structural rationale (e.g. "One of the most robust factors in finance — 30+ years of evidence across geographies.")

Chat bubble above the card:
> "Here's how **Cross-Sectional Momentum** works. It's been documented across 30+ years and multiple markets."

"Looks good → " button advances to Step A3.

#### Step A3: Universe / Ticker Input

Context-aware question based on template type:

| Template type | Question asked |
|---|---|
| Cross-sectional (momentum, low-vol, value, quality) | "Which group of stocks should we run this on?" → chips: S&P 500 / Nasdaq 100 / Russell 1000 / Custom tickers |
| Single-asset (bollinger, short-term reversal) | "Which stock or ETF do you want to test? (e.g. AAPL, QQQ)" |
| Pairs | "Which two stocks do you want to pair up? (e.g. COST and WMT)" |
| Sector rotation | "Which sector ETFs? (defaults to all 11 SPDR sector ETFs)" |

Follow-up (collapsible):
> "How far back should we test?" → [3Y] [5Y ✓] [10Y] [Custom]

"Preview Strategy →" advances to Step A4.

#### Step A4: Strategy Preview Popup

Bottom-sheet modal (slides up from bottom, sits over the brief card). Contains:
- Auto-generated strategy name (editable inline with pencil icon)
- 8-layer plain-English summary (compact, 1-line per layer)
- Two buttons: **← Edit** (scrolls back to relevant step) | **Run Backtest →** (navigates to `/workspace`)

---

### 4.3 Path B — Custom Mode

5 guided steps. Each shows a system recommendation; numbers are editable inline. Step indicator at top shows progress.

#### Step B1 — What are you trading? *(skippable)*

> "What kind of assets do you want to include? Skip to use S&P 500 stocks by default."

Chips: `S&P 500 Stocks` · `Nasdaq 100` · `Commodities` · `Specific tickers…` · `Skip`

#### Step B2 — What's your idea? *(Thesis + Signal combined)*

> "Describe your trading idea in plain language — one or two sentences is enough."

- User types free text
- System parses and maps to nearest strategy type
- Shows 3 candidate cards with plain-language labels (no jargon)
- User picks one
- Key numbers appear with defaults, all editable:
  - How far back to look: **[252 days]**
  - How many stocks to hold: **[20]**
  - How often to rebalance: **[Monthly]**

#### Step B3 — How do you want to manage positions? *(Execution + Risk combined)*

> "We'll pre-fill sensible defaults. Change anything that doesn't feel right."

- Max % of portfolio per stock: **[5%]**
- Cut a position if it drops: **[No stop-loss]** (toggle to enable, then set %)
- Direction: **[Long only ▾]** / Long & Short

#### Step B4 — How long will you hold each position?

Chips: `Days (1–5)` · `Weeks (1–4)` · `1–3 Months ✓` · `3–6 Months`

Minimum daily trading volume: **[$5,000,000]** (editable)

#### Step B5 — Time period & starting capital

> "How far back should the backtest go?"  
[3Y] [5Y ✓] [10Y] [Custom]

Starting with: **[$100,000]** (editable)  
Transaction cost estimate: **[5 bps per trade]** (collapsible)

"Preview Strategy →" → same Preview Popup as Path A Step 4.

---

## 5. Loading Animation (Backtest Running State)

Displayed in `/workspace` while `isRunning === true`. Replaces the current skeleton placeholder.

### Top Layer — Progress Tracker

Horizontal flow showing 5 stages. Each transitions: pending → spinner → ✓ checkmark.

```
[ Fetching prices ] ──✓── [ Building signal ] ──✓── [ Simulating trades ] ──⟳── [ Metrics ] ── [ Report ]
      AAPL 5Y                  Momentum rank             2,847 trades…
```

- Active stage pulses with `animate-pulse` on label
- Each stage shows a small descriptor line (e.g. "2,847 trades processed")
- `transition-all duration-500` between states

### Bottom Layer — Rotating Context Cards

3 card types, cycling every 5 seconds with fade transition:

**Card A — Strategy context** (always shown first):
- Title: "Why this strategy has an edge"
- 2–3 sentences on the structural rationale
- Source attribution (paper or practitioner)

**Card B — Ticker news** (shown if specific ticker was entered):
- Title: "Recent signals for [TICKER]"
- 3 latest headlines from sentiment pipeline with catalyst badge + date

**Card C — What to look for** (shown last, primes user for results):
- Title: "When your results load, focus on these first:"
- ① Sharpe ratio — anything above 0.8 is worth studying
- ② Max drawdown — this is what you'd live through
- ③ Whether returns beat the S&P 500 benchmark

---

## 6. Strategy Brief Card — Visual Design Spec

Component: `StrategyBriefCard`  
Used in: Modal Step A2, `/templates` gallery detail view

```
┌──────────────────────────────────────────────────────────────┐
│  [Evidence A ●]              Cross-Sectional Momentum        │
│  Systematic · Equity · Monthly · Retail-scale capacity       │
├──────────────┬───────────────┬──────────────────────────────┤
│  Typical     │  Risk-adj     │  Worst stretch               │
│  return      │  return       │  historically                │
│  +8% – +16%  │  Sharpe ~1.2  │  −22% to −35%               │
├──────────────┴───────────────┴──────────────────────────────┤
│                                                              │
│  ①  Trades        S&P 500 or Nasdaq 100 stocks              │
│  ②  Core idea     Stocks that outperformed over the past    │
│                   year tend to keep outperforming            │
│  ③  How it picks  Ranks every stock by 12-month return,     │
│                   buys the top 10% each month               │
│  ④  Execution     Equal dollar per stock · monthly swap     │
│  ⑤  Protection    Max 5% per stock · 25% per sector        │
│  ⑥  Hold period   ~30 days average per position            │
│  ⑦  How we test   Up to 10 years · 5bps/trade estimate     │
│  ⑧  After results  Which sectors drove your returns        │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  📑  Jegadeesh & Titman (1993) · AQR Capital (live 2009+)   │
│  "One of the most robust and widely documented factors in    │
│   finance — 30 years of evidence across geographies."        │
└──────────────────────────────────────────────────────────────┘
```

Tailwind treatment:
- Card: `bg-card border border-border rounded-2xl overflow-hidden`
- Evidence badge: pill using existing `EVIDENCE_CONFIG` colors (emerald/amber/orange)
- Stats strip: 3-col grid, `border-b border-border`, numbers `text-2xl font-bold font-mono`, labels `text-xs text-muted-foreground`
- Layer rows: `①` in `h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center`, label `font-medium text-sm`, description `text-muted-foreground text-sm`
- Credibility footer: `bg-muted/40 rounded-b-2xl px-5 py-4`

New fields required in `ResearchTemplate` (contracts.ts):
```typescript
academicRef?: {
  citation: string;   // "Jegadeesh & Titman (1993) · AQR Capital"
  note: string;       // "One of the most robust factors..."
};
perfContext?: {
  returnRange: string;   // "+8% to +16% annual alpha"
  sharpeRange: string;   // "Sharpe ~1.0 – 1.5"
  worstStretch: string;  // "−22% to −35% in bear markets"
};
```

---

## 7. Workspace Research Report Redesign

### 7.1 Remove

- Strategy Doc panel (markdown upload + parse)
- Demo picker section (equity/commodity demo strategies)
- Validation State panel
- CapabilityGlossary compact sidebar
- "Example Strategies" (demo picker serves this purpose — removed entirely)
- Strategy Preview editable form (replaced by read-only header strip)

### 7.2 New Layout

```
┌─────────────────────────────────────────────────────────────┐
│  [Strategy name]  ·  Type badge  ·  Run date  ·  Universe   │
│  [Modify Strategy]                                    [Save] │
├────────────┬────────────┬────────────┬──────────────────────┤
│  CAGR      │  Sharpe    │  Max DD    │  Win Rate  Turnover   │
│  14.2%     │  1.31      │  −18.4%    │  58%       6.4×/yr   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  EQUITY CURVE  ─────────────────── (full-width)            │
│  Strategy vs Benchmark overlay, date range selector        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  TRADE LOG  (scrollable table, collapsible with Show more)  │
│  Date · Ticker · Entry · Exit · Return · Hold days          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  [Detailed Metrics] [Review] [Robustness] [History]  ← tabs │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Detailed Metrics (default tab):                           │
│    Monthly return heatmap                                   │
│    Drawdown chart                                           │
│    Annual returns table                                     │
│    Rolling Sharpe (12M)                                     │
│                                                             │
│  Review tab:                                               │
│    AI explanation (strengths / weaknesses / regime notes)  │
│    AI sandbox review (trust score, overfit risk, concerns) │
│                                                             │
│  Robustness tab:                                           │
│    Parameter sensitivity table                             │
│    Subperiod splits table                                   │
│    Transaction cost sensitivity                            │
│    Benchmark comparison                                     │
│                                                             │
│  History tab:                                              │
│    All previous runs with metrics + restore button         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Strategy Navigation into Workspace

Strategy JSON is passed from modal to workspace via `sessionStorage`:
```typescript
// In modal "Run Backtest" handler:
sessionStorage.setItem('pendingStrategy', JSON.stringify(strategyJson));
router.push('/workspace?fromBuilder=true&autorun=true');

// In workspace on mount:
const fromBuilder = searchParams.get('fromBuilder');
if (fromBuilder) {
  const pending = sessionStorage.getItem('pendingStrategy');
  if (pending) {
    setStrategy(JSON.parse(pending));
    sessionStorage.removeItem('pendingStrategy');
  }
}
```

Existing `?templateId=...&path=load&tickers=...&autorun=true` param flow is preserved for direct template links.

"Modify Strategy" button in workspace header opens the builder modal pre-populated with current strategy state.

---

## 8. Component File Map

```
apps/web/src/components/strategy-builder/
  index.tsx                     — re-exports, modal open/close hook
  strategy-builder-modal.tsx    — full-screen modal shell + step state machine
  template-picker.tsx           — template grid inside modal (reuses gallery logic)
  strategy-brief-card.tsx       — 8-layer fact-sheet component (§6)
  universe-question.tsx         — context-aware ticker/universe input (Step A3)
  custom-builder.tsx            — 5-step custom wizard (Path B)
  strategy-preview-popup.tsx    — bottom-sheet preview + CTA
  backtest-loading.tsx          — progress tracker + rotating context cards

apps/web/src/components/workspace/
  research-workspace.tsx        — REDESIGNED (§7), remove panels, add report layout
  (existing: charts.tsx, monthly-heatmap.tsx, ticker-search.tsx — keep)
```

---

## 9. contracts.ts Changes

```typescript
// ResearchTemplate additions:
academicRef?: {
  citation: string;
  note: string;
};
perfContext?: {
  returnRange: string;
  sharpeRange: string;
  worstStretch: string;
};
```

Populate for all 8 Phase A templates + legacy templates.

---

## 10. Build Sequence

| # | Deliverable | Key files | Notes |
|---|---|---|---|
| 1 | `ResearchTemplate` field additions | `contracts.ts` | Add `academicRef`, `perfContext` to all 11 ready templates |
| 2 | `StrategyBriefCard` component | `strategy-brief-card.tsx` | Standalone, no external state |
| 3 | `StrategyBuilderModal` — Template path | `strategy-builder-modal.tsx`, `template-picker.tsx`, `universe-question.tsx`, `strategy-preview-popup.tsx` | Path A complete |
| 4 | `StrategyBuilderModal` — Custom path | `custom-builder.tsx` | Path B steps 1–5 + same preview popup |
| 5 | Homepage modal integration | `apps/web/src/app/page.tsx` | Add `builderOpen` state, wire "Open Strategy Builder" |
| 6 | `/templates` page integration | `apps/web/src/app/templates/page.tsx` | Add modal open on template click + "Build Custom" |
| 7 | `BacktestLoadingAnimation` | `backtest-loading.tsx` | Progress tracker + rotating context cards |
| 8 | Workspace research report | `research-workspace.tsx` | Remove 3 panels, new report layout, sessionStorage intake |

---

## 11. Preserved Functionality

The following existing workspace features are **preserved**, not removed:
- Backtest engine API call (`runBacktest`)
- AI Explainer (`explainStrategy`) → surfaces in Review tab
- AI Sandbox Review (`reviewSandbox`) → surfaces in Review tab
- Robustness runner (`runRobustness`) → surfaces in Robustness tab
- Run history (localStorage) → surfaces in History tab
- Save strategy + share link
- Data quality badges per ticker
- `?templateId=...` deep-link param handling

The following are **removed**:
- Strategy Doc markdown upload panel
- Demo picker (equity + commodity demo strategies)
- Validation State panel
- CapabilityGlossary compact in workspace sidebar
- Freeform chat prompt textarea in workspace (building moves to modal)

---

## 12. Out of Scope (Future)

- Pro tier: YAML/DSL editor, Python sandbox, REST API
- Walk-forward / OOS / Monte Carlo robustness (v2)
- Tier gating + billing (Starter/Builder/Pro)
- Paper-trading / live signal webhook
- Factor attribution tab for multi-factor strategies
- `signal_weighted` position sizing (currently `NotImplementedError`)
