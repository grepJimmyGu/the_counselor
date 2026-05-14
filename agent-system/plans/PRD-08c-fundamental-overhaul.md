# PRD-08c: Fundamental Analysis Overhaul

**Status:** Pending discussion — calculation decisions needed before implementation  
**Date:** 2026-05-13  
**Scope:** Full restructure of `/stocks/[ticker]` Overview tab  
**Depends on:** PRD-08a ✅, PRD-08b ✅ (10-K extraction already live)  
**Skills to activate:** `us-stock-analysis`, `safe-migration`

---

## Overview

Three sections are being overhauled. All use FMP Starter plan data — confirmed available.

```
Current structure:           New structure:
─────────────────────        ─────────────────────────────────
Business Map (partial)   →   1. Financial Health Check   ★ redesigned
Market Position (partial) →   2. Business Model           ★ new
Financial Check           →   3. Market Position          ★ new
Valuation scores          →   (removed — embedded in #1)
```

---

## Section 1 — Financial Health Check

### 1a. Score redesign: replace three scores with two IB-standard scores

**Current scores (being replaced):**
- `financial_validation_score` (0–100) — 6 weighted dimensions
- `valuation_risk_score` (0–100) — 4 valuation dimensions
- `overall_score` (0–100) — weighted combo

**Proposed replacement:**

#### Score A — Piotroski F-Score (0–9)
The standard hedge fund quality screen. 9 binary signals, 1 point each.

| Signal | Source field | Condition |
|---|---|---|
| ROA positive | `returnOnAssets` | > 0 |
| CFO positive | `operatingCashFlow / totalAssets` | > 0 |
| ΔROA improving | vs prior year `returnOnAssets` | current > prior |
| Accruals low | CFO > Net Income (cash quality) | `operatingCashFlow > netIncome` |
| Δ Leverage down | vs prior year `debtToEquityRatio` | current < prior |
| Δ Liquidity up | vs prior year `currentRatio` | current > prior |
| No dilution | shares outstanding | `sharesOutstanding` ≤ prior year |
| Δ Gross margin up | vs prior year `grossProfitMargin` | current > prior |
| Δ Asset turnover up | vs prior year `assetTurnover` | current > prior |

**Interpretation:**
- 7–9 → Strong (green) — financially healthy, improving
- 4–6 → Average (amber) — mixed signals
- 0–3 → Weak (red) — deteriorating fundamentals

**Data sources:** `ratios` (annual, limit=2), `income-statement` (annual, limit=2), `cash-flow-statement` (annual, limit=2)

---

#### Score B — Altman Z-Score (financial distress)
Classic bankruptcy predictor used by credit analysts.

```
Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5

X1 = (Current Assets − Current Liabilities) / Total Assets
     → workingCapital / totalAssets
X2 = Retained Earnings / Total Assets
     → retainedEarnings / totalAssets
X3 = EBIT / Total Assets
     → operatingIncome / totalAssets
X4 = Market Cap / Total Liabilities
     → marketCap / totalLiabilities
X5 = Revenue / Total Assets
     → revenue / totalAssets
```

**Interpretation:**
- Z > 2.99 → Safe Zone (green) — low distress risk
- 1.81–2.99 → Grey Zone (amber) — monitor closely
- Z < 1.81 → Distress Zone (red) — elevated risk

**Important caveat:** Z-Score is calibrated for manufacturing companies. For financials/banks, use Altman's Z'-Score variant (adapted). For the MVP, apply to all non-financial companies and flag financial sector companies with a disclaimer.

**Data sources:** `balance-sheet-statement` + `income-statement` + FMP `profile` (for `marketCap`)

---

### 1b. Industry percentile positioning — lightweight approach

**Goal:** Show where a company ranks vs its sector peers (e.g., "Top 23% in Technology")

**Lightweight calculation:**
- Do NOT compute all 14k+ companies on page load
- Instead: maintain a `sector_percentile_cache` table, updated lazily
- On company page load:
  1. Query `SELECT piotroski, altman_z FROM symbol_fundamentals WHERE sector = :sector AND piotroski IS NOT NULL`
  2. Count how many have lower score → percentile
  3. Only compares against companies already cached (companies that have been viewed)
  4. Cache the percentile result for 24h
- As more companies are viewed, the percentile becomes more accurate over time
- Show count: "Top 23% among 84 Technology companies tracked"

**Deferred to Phase 2:** Pre-warming top 500 companies to make percentiles meaningful at launch.

---

### 1c. Three Key Investment Insights — deterministic synthesis

Replace the verbose financial check cards with 3 clear IB-style verdicts:

```
┌──────────────────────────────────────────────────────────────┐
│  Q  Quality    Is the business getting healthier?             │
│     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 7/9 Strong       │
│     Revenue growing. Margins stable. Cash earnings high.      │
├──────────────────────────────────────────────────────────────┤
│  S  Safety     Can it survive a downturn?                     │
│     Safe Zone ●━━━━━━━━━━━━━━━━━━━━━○ Z=3.8               │
│     Net cash. Coverage ratio 18×. No dilution in 3 years.    │
├──────────────────────────────────────────────────────────────┤
│  V  Value      Is it attractively priced?                     │
│     EV/EBITDA 27× — Top 15% most expensive in Technology     │
│     FCF yield 2.6%. PEG 2.4 — growth priced in.             │
└──────────────────────────────────────────────────────────────┘
```

**Q — Quality** (Piotroski-derived):
- Driven by: F-Score + 3-year revenue CAGR + gross margin trend
- One sentence: "{Revenue direction}, {margin direction}, {cash quality note}"

**S — Safety** (Altman Z + coverage):
- Driven by: Altman Z-Score + interest coverage ratio + net debt/EBITDA
- One sentence: "{balance sheet posture}, {coverage}, {dilution note}"

**V — Value** (valuation multiples vs sector):
- Driven by: EV/EBITDA percentile within sector + FCF yield + PEG
- One sentence: "EV/EBITDA {Nx} — {percentile description}. FCF yield {%}."

All three are **purely deterministic** — no LLM calls, computed from FMP data.

---

### 1d. Existing financial metrics — keep, reorganise

The raw metrics (revenue growth %, margins, FCF, balance sheet ratios, valuation multiples) stay — just reorganised under the three insight panels as expandable drill-down detail. No data is removed.

---

## Section 2 — Business Model (new section, replaces Business Map)

### 2a. Business description
- One-paragraph summary (already pulled from FMP `/profile` description)
- Supplement with LLM-extracted detail from 10-K Item 1 (PRD-08b already provides this)

### 2b. Revenue breakdown chart — 5 years, by segment

**Data source:** `revenue-product-segmentation` — confirmed available for AAPL, MSFT, etc.

**Chart:** Stacked bar chart (Recharts `BarChart` with `Bar` per segment), 5 years on X-axis

```
Revenue Breakdown ($B) — AAPL
400 │         ████████████████████████
    │       ████████████████████████████
300 │     ██████████████████████████████
    │   ████████████████████████████████
200 │ ████████████████████████████████
    │
    └─────────────────────────────────
      2021   2022   2023   2024   2025
      ■ iPhone  ■ Services  ■ Mac  ■ iPad  ■ Wearables
```

**Fallback:** If no product segmentation data → show total revenue trend (line chart) with note "Segment data not disclosed"

### 2c. Geographic revenue breakdown
**Data source:** `revenue-geographic-segmentation` — confirmed available

**Chart:** Donut/pie for most recent year + table showing 3-year trend by region

### 2d. Revenue model + customer types + cyclicality + pricing power (combined)
These four currently scattered fields go into one compact "Business characteristics" row:
- Revenue model (from 10-K LLM extraction)
- Primary customers (B2B / B2C / Government)
- Cyclicality label
- Pricing power assessment

---

## Section 3 — Market Position (new section, replaces Market Position)

### 3a. What the company does — core business summary
80–100 words (LLM-extracted from 10-K Item 1, already available via PRD-08b):
- Core products/services
- How it makes money
- Primary revenue segments with % mix

### 3b. Competitive standing — moat analysis
60–80 words (LLM-extracted from 10-K):
- Market share estimate
- Key competitors named
- Moat type identified: brand / scale / network effects / switching costs / IP

### 3c. Supply chain flowchart
**Source:** LLM extraction from 10-K Item 1 (PRD-08b text already parsed)
**Implementation:** Simple horizontal flow using Tailwind/shadcn — no React-Flow dependency needed

```
[Key Suppliers]  →  [AAPL]  →  [Key Customers]
TSMC               ↕              Apple Retail
Samsung          Products         Enterprise
Foxconn                          Carriers / Telcos
```

Clickable tags: each company/segment is a badge; clicking goes to `/stocks/[SYMBOL]` if it's a publicly traded peer.

**Limitation:** Supplier extraction accuracy depends on 10-K quality. Always show source note.

### 3d. Geographic and customer mix
- Reuse geographic breakdown from Section 2
- Customer concentration: top customer % if disclosed in 10-K
- End-market exposure (consumer / enterprise / government / industrial)

### 3e. Competitor group + market sizing

**Competitor group mapping:**

For each public peer in FMP `/stock-peers`:
1. Fetch their revenue (from `/income-statement`)
2. Sum peer revenues → proxy "addressable market pool"
3. Rank by revenue share within peer group:
   - Dominant Player: >50% of peer group revenue
   - Market Leader: 25–50%
   - Major Participant: 10–25%
   - Niche Player: <10%

**5-year trend:** Plot each peer's revenue share change over 5 years using `revenue-product-segmentation` or `income-statement`.

**Honest disclaimer:** "Market share estimate based on public peer group revenue. Actual TAM is larger. This is a relative competitive position indicator, not an absolute market share figure."

**Multi-industry companies:** If a company spans multiple sectors (e.g., GE, Amazon), split by segment revenue and calculate position per segment independently.

---

## Data Sources Required

| Endpoint | Used for | Availability |
|---|---|---|
| `stable/revenue-product-segmentation` | Section 2 chart | ✅ Confirmed |
| `stable/revenue-geographic-segmentation` | Section 2/3 chart | ✅ Confirmed |
| `stable/key-metrics?limit=5` | ROIC, EV/EBITDA history | ✅ Confirmed |
| `stable/ratios?limit=2` | Piotroski components | ✅ Confirmed |
| `stable/balance-sheet-statement?limit=2` | Altman Z components | ✅ Confirmed |
| `stable/income-statement?limit=5` | Revenue history, EBIT | ✅ Confirmed |
| `stable/stock-peers` | Competitor group | ✅ Confirmed |
| 10-K parsed sections (PRD-08b) | Supply chain, moat, customers | ✅ Already built |

All endpoints are within FMP Starter plan ($14/mo). No new API subscriptions needed.

---

## New DB Columns Required

```sql
-- Add to symbol_fundamentals (new table) OR extend SymbolCache:
piotroski_score        SMALLINT      -- 0-9
altman_z_score         FLOAT         -- raw Z value
altman_z_label         VARCHAR(20)   -- Safe/Grey/Distress
insight_quality        VARCHAR(200)  -- Q insight text
insight_safety         VARCHAR(200)  -- S insight text
insight_value          VARCHAR(200)  -- V insight text
sector_piotroski_pct   FLOAT         -- percentile 0-1
sector_altman_pct      FLOAT         -- percentile 0-1
scores_computed_at     TIMESTAMP     -- 24h TTL

-- New tables:
revenue_segments       -- 5 years of product/geo breakdown (JSONB)
competitor_positions   -- peer group market sizing cache
```

---

## Cache TTL

| Data | TTL | Reason |
|---|---|---|
| Piotroski / Altman Z | 24 hours | Annual data, changes slowly |
| Industry percentile | 24 hours | Depends on how many companies cached |
| Revenue segments | 24 hours | Annual filings |
| Competitor market position | 24 hours | Peer revenue data |
| 3 Key Insights (text) | 24 hours | Derived from above |

---

## Loading time strategy

**Current problem:** Company page loads too many things at once.

**Solution: Progressive loading with priority tiers**

- **Tier 1 (instant, ~100ms):** Company header, price, sector badge
- **Tier 2 (fast, ~300ms):** Piotroski + Altman Z + 3 Key Insights (single DB query if cached)
- **Tier 3 (medium, ~1–2s):** Revenue segment charts, geographic chart (FMP calls)
- **Tier 4 (background, ~3–5s):** Competitor group market sizing, supply chain (heavier FMP + 10-K)

Each tier renders independently. User sees meaningful content in <300ms.

---

## Questions for Jimmy before implementation

### Q1 — Piotroski F-Score vs custom score
Option A: Pure Piotroski (9-point binary, IB standard)
Option B: Hybrid — keep current 6-dimension score + add Piotroski as secondary signal
**Recommendation:** Option A. Cleaner, industry-standard, easier to explain to users.

### Q2 — Altman Z-Score scope
Option A: Apply to all companies with disclaimer for financials/banks
Option B: Apply only to non-financial companies; show "N/A — Banking sector" for financials
**Recommendation:** Option B. Altman Z is unreliable for banks/insurance — showing it would mislead.

### Q3 — Industry percentile bootstrapping
Option A: Show "Top X% among Y companies tracked" — grows over time as companies are viewed
Option B: Pre-warm top 500 S&P companies on deploy (one-time job)
**Recommendation:** Option B for launch quality. The pre-warm is a single script run (~$2 at gpt-4o-mini rates for 500 company Piotroski calculations, mostly deterministic).

### Q4 — Supply chain flowchart
Option A: Simple Tailwind badge flow (left = suppliers, right = customers) — no dependency
Option B: React-Flow interactive diagram — richer but adds a dependency
**Recommendation:** Option A for MVP. Can upgrade to React-Flow in a later iteration.

### Q5 — Market sizing approach
Option A: Peer group revenue share (proxy, described above) — deterministic, fast
Option B: LLM-estimated TAM from 10-K + industry reports — richer, slower, less reliable
**Recommendation:** Option A with clear labeling ("Relative competitive position within public peer group"). Option B can be added to the Sandbox reviewer output later.

### Q6 — Multi-segment companies (Amazon, Google)
When a company has product segments AND geographic segments:
Option A: Show one competitor group based on primary segment only
Option B: Show per-segment competitor groups (complex UI)
**Recommendation:** Option A for MVP. Add multi-segment view in PRD-08d-v2.

---

## Proposed PRD split

| PRD | Scope | Effort |
|---|---|---|
| **PRD-08c** | Financial Health Check (Piotroski + Altman Z + 3 insights + industry percentile) | 3 days |
| **PRD-08d** | Business Model (revenue breakdown chart, geo chart, combined characteristics row) | 2 days |
| **PRD-08e** | Market Position (supply chain flow, competitor group, market sizing) | 4 days |

Total: ~9 engineering days. Can run sequentially (08c → 08d → 08e) or 08c + 08d in parallel.

---

## Unchanged sections

Per scope: everything outside the three sections above stays the same:
- Financial Check raw metrics table (growth, margins, FCF, balance sheet, valuation)
- Score strip at top of page
- Tab navigation (Overview / News & Sentiment)
- Sentiment tab (all of Phase 2)
