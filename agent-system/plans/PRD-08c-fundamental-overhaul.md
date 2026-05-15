# PRD-08c/d/e: Fundamental Analysis Overhaul

**Status:** ✅ SHIPPED — 2026-05-13 to 2026-05-15
**Scope:** Full restructure of `/stocks/[ticker]` Overview tab
**Depends on:** PRD-08a ✅, PRD-08b ✅ (10-K extraction live)

---

## What Was Built

### PRD-08c — Financial Health Check
**Original plan:** Piotroski F-Score (9-signal) + Altman Z-Score + QSV insight paragraphs + industry percentile via S&P 500 prewarm.

**What shipped:** Piotroski/Altman Z were fully implemented but subsequently replaced by the 3-question Evaluation Dashboard (see below). The redundant pipeline was removed to eliminate 3 duplicate FMP API calls per page load.

**What remains from PRD-08c:**
- `EV/EBITDA` sourced from `FMP /key-metrics-ttm` → `FinancialCheckSection.ev_ebitda`
- `pe_ratio`, `peg_ratio`, `fcf_yield` in `FinancialCheckSection` — used by Evaluation Dashboard
- `MetricLabel` component (`CircleHelp` icon + shadcn Tooltip) — reused across the app

---

### PRD-08c (revised) — Asset Evaluation Dashboard ✅

Three-question framework replacing the Piotroski/Altman display:

```
[Health scorecard]   [Valuation scorecard]   [Trend scorecard]
     0–100                 0–100                   0–100
  Plain-English         Plain-English           Plain-English
     answer               answer                  answer
  3 top metrics        3 top metrics           3 top metrics
    Warning              Warning                 Warning

[Health detail panel — expandable]
[Valuation detail panel — expandable]
[Trend detail panel — expandable]

[Final Analyst Summary]
  Overall score + label (Attractive / Moderately Positive / Neutral / Caution / Avoid)
  Analyst paragraph | Bull case | Bear case
  Key metrics to watch | Contradiction warning
```

**Scoring weights:**

| Dimension | Weight | Components |
|---|---|---|
| Health | Revenue growth 20%, Margin quality 20%, FCF quality 20%, ROE/capital efficiency 20%, Balance sheet 20% |
| Valuation | FCF yield 28%, EV/EBITDA 27%, P/E 22%, PEG 17%, DCF placeholder 6% |
| Trend | Momentum 35%, MA50/MA200 position 30%, RS vs SPY 20%, Volume + EPS revisions 15% |
| **Final** | Health 40%, Valuation 30%, Trend 30% |

**Data sources:**
- Health + Valuation: `financial_check` fields (FMP income/cashflow/balance + key-metrics-ttm)
- Trend: Alpha Vantage `price_bars` via `/api/company/{symbol}/trend` (lazy fetch, skeleton while loading)

**Files:**
- `apps/web/src/lib/evaluation/types.ts` — StockMetricsInput, CommodityMetricsInput, QuestionScore, EvaluationResult
- `apps/web/src/lib/evaluation/scoring.ts` — all score functions
- `apps/web/src/lib/evaluation/interpretation.ts` — rule-based text generation
- `apps/web/src/lib/evaluation/mock-data.ts` — AAPL, NVDA, XOM, JPM mocks
- `apps/web/src/app/stocks/[ticker]/_evaluation-dashboard.tsx` — main component

---

### PRD-08d — Business Model Section ✅

**Revenue Segment Charts:**
- Data: FMP `/stable/revenue-product-segmentation` + `/revenue-geographic-segmentation`
- Cache: `revenue_segments` table, 24h TTL
- Parser handles both FMP flat and nested dict formats
- Charts: Recharts stacked `BarChart` (5yr product segments) + `PieChart` donut (geographic mix, latest year)
- Fallback: "Segment breakdown not disclosed" if no data

**Business Characteristics Row:**
- Compact pill chips: Revenue model · Customers · Cyclicality · Pricing power
- Source: 10-K LLM extraction (rule-based sector mapping as fallback)

**Key files:** `revenue_segment_service.py`, `_business-model-section.tsx`

---

### PRD-08e — Market Position Section ✅ (partial)

**Supply Chain Flow:**
- Extended 10-K LLM prompt to extract `upstream_suppliers` + `downstream_customers` (max 6 each)
- `_match_names_to_symbols()` fuzzy-matches names against `symbols` table → clickable badges for public companies
- Visual: `[Suppliers] ← SYMBOL → [Customers]` Tailwind badge layout
- Data refreshes on next 10-K re-extraction (90-day cache)

**Competitor Groups:**
- `CompetitorGroupService`: one LLM call filters FMP peers by segment relevance → stored in `competitor_groups` table
- Fetches 5yr income statements for all peers (parallel, 10s timeout per peer)
- Revenue share = peer_rev / sum(group_revs) → Dominant (>50%) / Leader (25–50%) / Major (10–25%) / Niche (<10%)
- 7-day cache in `competitor_revenue_cache`
- Per-segment tab UI with revenue/share/position dot/5yr sparkline

**DB tables added:** `revenue_segments`, `competitor_groups`, `competitor_revenue_cache`
**Columns added to:** `company_business_intelligence` (upstream_suppliers, downstream_customers)

**Key files:** `competitor_group_service.py`, `_market-position-section.tsx`

---

### Commodity Evaluation Framework ✅

**Page:** `/commodities/[symbol]` — Gold, WTI, Copper, Wheat

**Physical Market Health scoring:**
- Inventory percentile 30% + Supply-demand 25% + Spare capacity 15% + Cost curve support 15% + Disruption risk 15%

**Commodity Valuation scoring:**
- Spot vs marginal cost 25% + 10yr price percentile 20% + Futures curve 25% + Inventory-adjusted 20% + Related ratio 10%

**Commodity Trend scoring:**
- Momentum 25% + Futures curve 20% + CFTC positioning 20% + ETF flows 15% + Macro (dollar/yields/China PMI) 20%

**Data sources:**
- Physical market (inventory, CFTC, futures curve): **mock/estimated** — noted clearly in UI
- Price trend, performance, MAs: **real Alpha Vantage** via ETF proxies (GLD, USO, COPX, WEAT)

**New backend endpoints:**
- `GET /api/commodities/{commodity}/trend` — maps GOLD→GLD, WTI→USO, COPPER→COPX, WHEAT→WEAT
- `POST /api/admin/warmup-commodity-etfs` — load ETF price bars

**Files:** `commodity-interpretation.ts`, `_commodity-evaluation-dashboard.tsx`, `commodities/[symbol]/page.tsx`, `apps/api/app/api/routes/commodities.py`

---

## Page Structure (as shipped)

```
/stocks/[ticker] Overview tab
│
├── TIER 1 (~100ms): Company header + live price (FMP /stable/quote, always fresh)
│
├── TIER 2 (~300ms): Asset Evaluation Dashboard
│   ├── Health / Valuation / Trend scorecards
│   │   └── Trend: skeleton → lazy Alpha Vantage fetch
│   ├── Expandable detail panels per dimension
│   └── Final analyst summary + contradiction warning
│
├── TIER 3 (~1-2s): Business Model
│   ├── Revenue segment stacked bar (FMP, 5yr, 24h cache)
│   ├── Geographic donut (FMP, latest year)
│   └── Business characteristics chips (10-K LLM extraction)
│
└── TIER 4 (~3-5s): Market Position
    ├── Growth drivers + Key risks (10-K LLM extraction)
    ├── Peers (FMP /stock-peers, live per request, filtered to universe)
    ├── Supply chain badges (10-K LLM extraction, 90d cache)
    └── Competitor segment tabs (LLM + FMP revenues, 7d cache)
```

---

## Removed / Not Built

| Item | Decision |
|---|---|
| Piotroski F-Score display | Removed — replaced by Evaluation Dashboard Health score |
| Altman Z-Score display | Removed — not meaningful for mega-cap tech; removed from pipeline |
| QSV insight paragraphs (Q/S/V) | Removed — replaced by rule-based Evaluation Dashboard interpretation |
| Industry percentile (S&P 500 prewarm) | Removed — prewarm loop removed; percentile not shown |
| `symbol_health_scores` table writes | Removed — `HealthScoreService` no longer called per page load |
| `HealthScoreSection` in API response | Removed — `financial_check` now carries all valuation fields |

---

## Outstanding / Future Work

| Item | Notes |
|---|---|
| Commodity physical market data | EIA (oil inventories), CFTC COT data, World Gold Council — not yet integrated |
| EPS revision trend (Trend scorecard) | Requires analyst consensus data (FMP `/analyst-estimates` or Zacks) — placeholder in UI |
| Short interest (Trend scorecard) | Not in current FMP plan |
| ROIC | Computable from existing data — not yet added to `FinancialCheckSection` |
| Capital return yield | Computable from shares + dividends — not yet surfaced |
| Competitor segment tabs for multi-segment companies | Works but requires full segment + peer data to be cached first |
