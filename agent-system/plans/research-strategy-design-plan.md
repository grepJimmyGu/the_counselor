# Combined UI/UX Feature Plan — Research & Strategy Layer

Reviewed and approved by the Investment Analytics UI/UX Agent.
Date: 2026-05-08

---

## Area A: Research Templates Page (`/templates`)

**What it is:** A dedicated page presenting 5 research frameworks. Distinct from demo strategies — demos show how the product works, templates are starting points for the user's own research hypothesis.

**Page header copy:**
> Research Templates
> Use a structured investment framework as the starting point for your own hypothesis. Each template defines a strategy type, required data, and testable rules. Review the rules before running a backtest.
> `3 templates available now · 2 require additional data`

**Template card design:**
```
┌─────────────────────────────────────────────────────┐
│  MOMENTUM                          ← category badge │
│                                                     │
│  Trend Following                   ← template name  │
│  Price momentum with ATR-based trailing stops       │
│                                                     │
│  What it tests                                      │
│  Buy when price breaks above a rolling high.        │
│  Exit using an ATR-based trailing stop.             │
│                                                     │
│  Data: Price data only  ·  Universe: Any equity     │
│                                                     │
│  Which ticker do you want to test this on?          │
│  [ AAPL                              🔍 ]           │
│                                                     │
│  [ Load Example ]   [ Build my own version → ]      │
└─────────────────────────────────────────────────────┘
```

**Two sections on the page:**

Section 1 — Available Now (Templates 1–3):

| Template | Category | Description |
|---|---|---|
| Trend Following | Momentum | Price momentum with ATR-based trailing stops |
| Cross-Sectional Momentum | Momentum | Rank a universe by return, rotate into top performers |
| ETF Rotation | Rotation | Rotate across asset class ETFs by relative momentum |

Section 2 — Requires Additional Data (Templates 4–5):

| Template | Category | Gap |
|---|---|---|
| Value + Momentum | Factor | Requires P/E and earnings data — not yet available |
| Commodity Carry | Carry | Requires futures curve data. ETF proxy available as approximation |

Template 4: no CTA — data gap shown on card, not discovered after clicking.
Template 5: "Load with ETF Proxy" CTA — loads with a yellow caveat callout in workspace.

**Data gap copy (not "coming soon"):**
> Requires fundamental data (P/E, earnings) — not yet available in this tool. Shown here so you can plan your research.

---

## Area B: Template-to-Workspace Flow (Workspace Changes)

**Two paths from a template card:**

**Path 1 — Load Example**
- Loads the pre-built strategy rules into Strategy Preview
- Scrolls and highlights Strategy Preview so the user's eye goes there
- Shows yellow review callout above Strategy Preview:
  > *"Template loaded with default parameters. Review the rules and universe before running a backtest."*
- Right panel shows guided empty state (not generic "no results"):
  > *"Strategy loaded. Review the rules on the left, adjust the universe and date range for your hypothesis, then run the backtest."*

**Path 2 — Build my own version →**
- Ticker selected on the card is pre-loaded into the workspace
- Chat Builder is focused and pre-seeded with a framework-aware prompt:
  > *"I want to build a trend following strategy for NVDA. Tell me your specific rules — lookback period, stop type, or anything else."*
- Each template has its own `chatSeed` string in `contracts.ts`
- User answers in plain English → AI parses → Strategy Preview populates → user runs backtest

**Feature 1: Ticker Customization in the Chat Seed**
- Inline `TickerSearch` component on each template card, above the CTAs
- Ticker selected on card pre-loads into the workspace on both paths
- For "Build my own version": ticker is embedded in the chat seed string so the user does not retype it
- Uses the existing `TickerSearch` component — no new component needed

**Template 5 special case:**
- "Load with ETF Proxy" loads the strategy but adds an additional yellow caveat:
  > *"This template uses an ETF proxy for futures curve data. The approximation may differ from actual roll yield. Treat results as directional, not precise."*

---

## Area C: Strategy Storage (Phase 1)

**What it is:** After a backtest runs, the user can save the strategy as a permanent record with a shareable URL. No login required — the URL is the identity.

**Save flow in workspace:**
```
After backtest completes:
[ Run Again ]  [ Save Strategy ]  [ Compare ]

On clicking Save Strategy:
  Name your strategy: [ NVDA Trend Following          ]
  [ Save ]

After saving:
  Strategy saved.
  livermore.app/strategies/nvda-trend-following-2024
  [ Copy link ]
```

**Saved strategy page (`/strategies/[slug]`):**
- Strategy name + saved date
- Strategy rules (exact rules tested — deterministic, not AI-generated)
- Ticker, date range, benchmark, assumptions
- Equity curve + full metrics
- AI Explanation
- Sandbox Review
- Disclaimer (prominent, not footer):
  > *"This strategy was created and saved by a user of this tool. It is a historical backtest result, not a recommendation or validation."*
- Read-only — no "run this" button for other users

**Backend additions:**
- `BacktestRecord` extended: `slug`, `name`, `is_public` fields
- `POST /api/strategies/save` — takes backtest ID + name, returns slug
- `GET /api/strategies/{slug}` — public read endpoint

---

## Area D: Personal Strategy Library + Comparison (Phase 2)

**What it is:** Saved strategies appear in a personal library accessible from the Comparison tab. User can compare any two saved strategies side by side.

**Comparison tab extension:**
```
Compare:  Current strategy  vs.  [ Select saved strategy ▾ ]
                                  My Strategies
                                  — NVDA Trend Following (May 8)
                                  — SPY RSI Mean Reversion (May 6)
                                  — AAPL Momentum (May 3)
```

Comparison table always shows both strategies' full context — ticker, date range, benchmark, assumptions — not just metrics. Consistent with the style guide rule: comparison views surface trade-offs, not winners.

**Community strategies — deferred to Phase 3.** Requires curation model, attribution, and user accounts before it can be built without creating a misleading leaderboard.

---

## What Not to Build Yet

- Community strategy browsing — needs auth + curation decisions first
- "Top strategies" ranking — leaderboard sorted by return creates false confidence
- Strategy forking ("copy this community strategy") — needs auth

---

## Phased Build Order

| Phase | Feature | New pages | Backend changes | Workspace changes |
|---|---|---|---|---|
| 1 | Templates page + card design | `/templates` full build | `contracts.ts` — 5 template defs with `chatSeed` | Template load flow, review callout, guided empty state |
| 2 | Strategy save + shareable URL | `/strategies/[slug]` | `BacktestRecord` extension, `POST /api/strategies/save`, `GET /api/strategies/{slug}` | Save button after backtest, copy link |
| 3 | Personal library + Comparison extension | None | `GET /api/strategies/mine` | Comparison tab dropdown |
| 4 | Community strategies | To be designed | Requires auth | To be designed |

---

## Full Acceptance Criteria

**Templates page:**
- ☐ 5 template cards in two sections (Available Now / Requires Additional Data)
- ☐ Each card: category badge, name, description, what it tests, data requirement, universe
- ☐ Inline `TickerSearch` on each card above CTAs
- ☐ Ticker selected on card pre-loads into workspace on both paths
- ☐ Templates 1–3: "Load Example" + "Build my own version" CTAs
- ☐ Template 4: no CTA, data gap explanation on card
- ☐ Template 5: "Load with ETF Proxy" CTA + caveat callout on load

**Template-to-workspace flow:**
- ☐ Load Example scrolls to Strategy Preview and shows review callout
- ☐ Right panel shows guided empty state after template load (not generic)
- ☐ Build my own version pre-loads ticker + pre-seeds chat with framework-aware prompt embedding the selected ticker
- ☐ Template 5 ETF proxy caveat shown in workspace after load

**Strategy storage:**
- ☐ Save button appears after backtest completes
- ☐ User can name the strategy before saving
- ☐ Saved strategy gets a permanent shareable URL
- ☐ Strategy page is read-only with full rules, results, explanation, sandbox review, disclaimer

**Comparison extension:**
- ☐ Comparison tab dropdown shows user's saved strategies
- ☐ Both strategies show full context (ticker, date range, benchmark, assumptions) not just metrics
