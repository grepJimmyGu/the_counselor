# PRD-08a: Fundamental Analysis Module — Financial Check + Structured Company Data

**Status:** Ready to build (requires PRD-06 FMP integration first)  
**Date:** 2026-05-11  
**Depends on:** PRD-06 (FMP client + symbol seed), PRD-07 (stock screener page — provides `/stocks` nav)  
**Followed by:** PRD-08b (Business Map full + Market Position full — gated on 10-K/10-Q extraction model)

---

## Scope

Build the company deep-dive page at `/stocks/[ticker]` with three sections:

1. **Business Map** — populated from structured APIs only. Fields that require analytical intelligence are left blank and reserved for PRD-08b / 10-K model.
2. **Market Position** — sector, industry, and FMP peers from structured APIs. All other fields blank.
3. **Financial Check** — fully deterministic from FMP financial statements + Alpha Vantage OVERVIEW. This is the complete section for PRD-08a.

Scoring in PRD-08a: only `financial_validation_score` and `valuation_risk_score` are computed. `business_map_score` and `market_position_score` are null until PRD-08b.

---

## Design Principles

- Business story first, financials validate — even with partial data, show Business Map and Market Position at the top
- Blank is honest — do not invent data. Show `—` or "Data pending" for fields requiring 10-K/10-Q
- Visual-first — each section uses cards and mini-charts, not prose paragraphs
- No buy/sell recommendations — use: research candidate, watchlist candidate, financial validation signal, valuation risk
- Disclaimer visible on every fundamental page

**Disclaimer text:**
> "This tool provides research candidates, not financial advice. Market size estimates, competitive position, and financial data may be incomplete, delayed, or uncertain. Always verify with primary sources."

---

## Data Sources per Field

### Business Map — what each field pulls from

| Field | Source | Notes |
|---|---|---|
| `one_line_summary` | FMP `/profile/{symbol}` description (first 2 sentences) | Fallback: Alpha Vantage OVERVIEW `Description` |
| `primary_value_chain_role` | Rule-based inference from `sector` + `industry` (see lookup table below) | Deterministic, no LLM |
| `secondary_value_chain_roles` | Empty array | Reserved PRD-08b |
| `customer_types` | **Blank** | Reserved for 10-K/10-Q model |
| `revenue_model` | **Blank** | Reserved for 10-K/10-Q model |
| `margin_implication` | Rule-based from gross margin vs sector median (see logic below) | Derived from Financial Check data |
| `cyclicality_implication` | Rule-based from sector (Technology/Healthcare = low, Materials/Energy = high, etc.) | Deterministic |
| `pricing_power_implication` | **Blank** | Reserved for 10-K/10-Q model |
| `confidence` | `"partial"` always in PRD-08a | Full confidence in PRD-08b |
| `source_notes` | List which API fields were used | e.g. `["FMP /profile", "sector-to-value-chain mapping v1"]` |

### Value chain role — sector + industry lookup table

```python
# apps/api/app/services/value_chain_classifier.py
SECTOR_INDUSTRY_TO_ROLE = {
    # Technology
    ("Technology", "Semiconductors"): "Component Supplier",
    ("Technology", "Semiconductor Equipment & Materials"): "Infrastructure Provider",
    ("Technology", "Software—Application"): "Software Layer",
    ("Technology", "Software—Infrastructure"): "Infrastructure Provider",
    ("Technology", "Consumer Electronics"): "Manufacturer / Producer",
    ("Technology", "Electronic Components"): "Component Supplier",
    ("Technology", "Information Technology Services"): "Service Provider",
    ("Technology", "Internet Content & Information"): "Platform Provider",
    # Communication Services
    ("Communication Services", "Internet Content & Information"): "Platform Provider",
    ("Communication Services", "Telecom Services"): "Infrastructure Provider",
    ("Communication Services", "Entertainment"): "End-Market Brand",
    # Healthcare
    ("Healthcare", "Biotechnology"): "Value-Added Technology Provider",
    ("Healthcare", "Drug Manufacturers—General"): "Manufacturer / Producer",
    ("Healthcare", "Medical Devices"): "Component Supplier",
    ("Healthcare", "Health Information Services"): "Software Layer",
    ("Healthcare", "Healthcare Plans"): "Financial Intermediary",
    # Financials
    ("Financials", "Banks—Diversified"): "Financial Intermediary",
    ("Financials", "Insurance—Diversified"): "Financial Intermediary",
    ("Financials", "Asset Management"): "Financial Intermediary",
    ("Financials", "Capital Markets"): "Financial Intermediary",
    # Consumer
    ("Consumer Cyclical", "Specialty Retail"): "Retailer",
    ("Consumer Cyclical", "Auto Manufacturers"): "Manufacturer / Producer",
    ("Consumer Defensive", "Beverages—Non-Alcoholic"): "End-Market Brand",
    ("Consumer Defensive", "Grocery Stores"): "Retailer",
    ("Consumer Defensive", "Household & Personal Products"): "End-Market Brand",
    # Energy
    ("Energy", "Oil & Gas E&P"): "Raw Material Provider",
    ("Energy", "Oil & Gas Refining & Marketing"): "Manufacturer / Producer",
    ("Energy", "Oil & Gas Integrated"): "Raw Material Provider",
    # Industrials
    ("Industrials", "Aerospace & Defense"): "Manufacturer / Producer",
    ("Industrials", "Railroads"): "Distributor",
    ("Industrials", "Trucking"): "Distributor",
    ("Industrials", "Specialty Industrial Machinery"): "Infrastructure Provider",
    # Materials
    ("Basic Materials", "Agricultural Inputs"): "Raw Material Provider",
    ("Basic Materials", "Chemicals"): "Raw Material Provider",
    ("Basic Materials", "Steel"): "Raw Material Provider",
    # Utilities
    ("Utilities", "Utilities—Regulated Electric"): "Infrastructure Provider",
    ("Utilities", "Utilities—Renewable"): "Infrastructure Provider",
}
# Fallback: sector-level default
SECTOR_FALLBACK_ROLE = {
    "Technology": "Software Layer",
    "Healthcare": "Value-Added Technology Provider",
    "Financials": "Financial Intermediary",
    "Consumer Cyclical": "Retailer",
    "Consumer Defensive": "End-Market Brand",
    "Industrials": "Manufacturer / Producer",
    "Energy": "Raw Material Provider",
    "Basic Materials": "Raw Material Provider",
    "Real Estate": "Service Provider",
    "Utilities": "Infrastructure Provider",
    "Communication Services": "Platform Provider",
}
```

### Market Position — what each field pulls from

| Field | Source | Notes |
|---|---|---|
| `market_category` | FinanceDatabase sector + industry + market cap category | e.g. "Large-Cap Technology — Semiconductors" |
| `market_size_estimate` | **Blank** (`"estimate unavailable"`) | Reserved for 10-K/10-Q model |
| `market_growth_label` | **Blank** | Reserved for 10-K/10-Q model |
| `competitive_position_label` | **Blank** | Reserved for 10-K/10-Q model |
| `market_share_notes` | **Blank** | Reserved for 10-K/10-Q model |
| `key_competitors` | FMP `/stock/peers/{symbol}` when available, otherwise **empty array** | No fallback invented |
| `key_growth_drivers` | **Blank** | Reserved for 10-K/10-Q model |
| `key_risks` | **Blank** | Reserved for 10-K/10-Q model |
| `confidence` | `"partial"` always in PRD-08a | |
| `source_notes` | `["FMP /stock/peers", "FinanceDatabase sector mapping"]` | |

### Financial Check — fully deterministic

**Primary source:** FMP endpoints  
**Supplementary:** Alpha Vantage OVERVIEW (for cross-check of P/E, EPS)

| Metric group | FMP endpoint | Fields |
|---|---|---|
| Growth | `/income-statement/{symbol}?limit=5` | Revenue YoY, Revenue 3Y CAGR, EPS YoY, Operating income growth |
| Profitability | `/income-statement` + computed | Gross margin, operating margin, net margin |
| ROE / ROA | `/key-metrics/{symbol}` | ROE, ROA, ROIC |
| Cash flow | `/cash-flow-statement/{symbol}?limit=5` | Operating CF, CapEx, FCF, FCF margin, FCF conversion |
| Balance sheet | `/balance-sheet-statement/{symbol}?limit=3` | Cash, debt, net debt, D/E ratio, current ratio |
| Valuation | `/key-metrics` + price | P/E, P/S, P/B, PEG (if EPS growth > 0), FCF yield, dividend yield |

**Margin implication logic (rule-based, links Business Map to Financial Check):**
```python
def derive_margin_implication(gross_margin: float, value_chain_role: str) -> str:
    ROLE_EXPECTED_MARGINS = {
        "Software Layer": (0.60, 0.85),
        "Platform Provider": (0.55, 0.90),
        "Component Supplier": (0.30, 0.55),
        "Manufacturer / Producer": (0.20, 0.45),
        "Raw Material Provider": (0.15, 0.40),
        "Retailer": (0.20, 0.40),
        "Financial Intermediary": (0.30, 0.70),
        "Service Provider": (0.25, 0.55),
        "Infrastructure Provider": (0.30, 0.60),
    }
    low, high = ROLE_EXPECTED_MARGINS.get(value_chain_role, (0.20, 0.60))
    if gross_margin >= high:
        return f"Above-average for {value_chain_role} — suggests pricing power or premium positioning"
    elif gross_margin < low:
        return f"Below-average for {value_chain_role} — margin pressure or commoditisation risk"
    else:
        return f"In-line with typical {value_chain_role} margins"
```

---

## Scoring (PRD-08a scope)

Only two scores computed in PRD-08a:

### `financial_validation_score` (0–100)

| Dimension | Weight | How scored |
|---|---|---|
| Revenue growth (YoY) | 20% | >20% → 100, 10–20% → 75, 0–10% → 50, negative → 20 |
| Gross margin vs sector norm | 15% | Above norm → 100, at norm → 70, below → 30 |
| Operating margin | 15% | >20% → 100, 10–20% → 75, 0–10% → 40, negative → 0 |
| FCF conversion (FCF/Net income) | 20% | >100% → 100, 75–100% → 80, 50–75% → 50, <50% → 20 |
| Balance sheet (net debt/EBITDA) | 15% | <1x → 100, 1–2x → 75, 2–3x → 50, >3x → 20 |
| EPS growth consistency | 15% | 3+ years growth → 100, 1–2 years → 60, declining → 20 |

### `valuation_risk_score` (0–100, higher = MORE risk)

| Dimension | Weight | How scored |
|---|---|---|
| P/E vs sector median | 35% | >3x sector median → 100 risk, 2x → 70, 1.5x → 40, at or below → 0 |
| P/S ratio | 25% | >20x → 100 risk, 10–20x → 70, 5–10x → 40, <5x → 10 |
| FCF yield | 25% | <1% → 100 risk, 1–2% → 70, 2–4% → 40, >4% → 0 |
| PEG ratio | 15% | >3 → 100 risk, 2–3 → 70, 1–2 → 30, <1 → 0 |

### Overall score (PRD-08a partial)
```
overall_fundamental_score_partial = (
    financial_validation_score × 0.70
    - valuation_risk_score × 0.30
)
```
Capped 0–100. Labelled "(financial only — business analysis pending)".

### `financial_validation_label` mapping
| Score | Label |
|---|---|
| 80–100 | Financials Strongly Support Story |
| 60–79 | Financials Mostly Support Story |
| 40–59 | Mixed Financial Validation |
| 20–39 | Financials Do Not Yet Support Story |
| 0–19 | Weak Financial Support |

+ Overlay warnings:
- If `valuation_risk_score > 70` → append "Valuation Risk High"
- If net debt/EBITDA > 3x → append "Balance Sheet Risk High"
- If FCF conversion < 50% → append "Cash Flow Quality Weak"

---

## Database Schema

Four new tables — all with Alembic migration, reviewed by `safe-migration` skill before merge.

```sql
-- company_business_maps
CREATE TABLE company_business_maps (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    as_of_date DATE NOT NULL,
    one_line_summary TEXT,
    primary_value_chain_role VARCHAR(60),
    secondary_value_chain_roles JSONB DEFAULT '[]',
    customer_types JSONB DEFAULT '[]',          -- blank in PRD-08a
    revenue_model TEXT,                          -- blank in PRD-08a
    margin_implication TEXT,
    cyclicality_implication TEXT,
    pricing_power_implication TEXT,              -- blank in PRD-08a
    raw_json JSONB,
    source_notes JSONB DEFAULT '[]',
    confidence VARCHAR(20) DEFAULT 'partial',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, as_of_date)
);

-- company_market_positions
CREATE TABLE company_market_positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    as_of_date DATE NOT NULL,
    market_category TEXT,
    market_size_estimate TEXT DEFAULT 'estimate unavailable',
    market_growth_label VARCHAR(40) DEFAULT NULL,
    competitive_position_label VARCHAR(40) DEFAULT NULL,
    market_share_notes TEXT DEFAULT NULL,
    key_competitors JSONB DEFAULT '[]',
    key_growth_drivers JSONB DEFAULT '[]',      -- blank in PRD-08a
    key_risks JSONB DEFAULT '[]',               -- blank in PRD-08a
    raw_json JSONB,
    source_notes JSONB DEFAULT '[]',
    confidence VARCHAR(20) DEFAULT 'partial',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, as_of_date)
);

-- company_financial_validations
CREATE TABLE company_financial_validations (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    as_of_date DATE NOT NULL,
    financial_validation_label VARCHAR(60),
    growth_summary TEXT,
    profitability_summary TEXT,
    cash_flow_summary TEXT,
    balance_sheet_summary TEXT,
    valuation_summary TEXT,
    supporting_evidence JSONB DEFAULT '[]',
    contradicting_evidence JSONB DEFAULT '[]',
    metrics_json JSONB,                         -- full raw metrics dict
    confidence VARCHAR(20) DEFAULT 'high',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, as_of_date)
);

-- company_fundamental_scores
CREATE TABLE company_fundamental_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    as_of_date DATE NOT NULL,
    business_map_score SMALLINT DEFAULT NULL,       -- null until PRD-08b
    market_position_score SMALLINT DEFAULT NULL,    -- null until PRD-08b
    financial_validation_score SMALLINT,
    valuation_risk_score SMALLINT,
    overall_fundamental_score SMALLINT,
    overall_label VARCHAR(60),
    score_explanation_json JSONB,
    warnings_json JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, as_of_date)
);
```

**Cache TTLs:**
- `company_financial_validations`: refresh daily (FMP data changes)
- `company_business_maps` + `company_market_positions`: refresh weekly (structural company data changes slowly)
- `company_fundamental_scores`: recomputed when financial validation refreshes

---

## Backend Services

```
apps/api/app/services/
├── value_chain_classifier.py      # sector+industry → value chain role (deterministic lookup)
├── company_business_map_service.py  # assembles Business Map from FMP profile + classifier
├── market_position_service.py     # assembles Market Position from FMP peers + FinanceDatabase
├── financial_validation_service.py  # computes all Financial Check metrics from FMP statements
├── fundamental_scoring_service.py   # computes financial_validation_score + valuation_risk_score
└── fundamental_summary_builder.py  # aggregates all three sections + scores into summary response
```

**PRD-08b adds:**
```
├── fundamental_explainer.py        # LLM or 10-K-model fills blank fields in Business Map + Market Position
├── fundamental_sandbox_reviewer.py # challenges the full three-section analysis
```

---

## API Endpoints

```
GET  /api/fundamentals/{symbol}/summary          # all three sections + scores + labels + warnings
GET  /api/fundamentals/{symbol}/business-map     # Business Map section only
GET  /api/fundamentals/{symbol}/market-position  # Market Position section only
GET  /api/fundamentals/{symbol}/financial-check  # Financial Check section only (most complete in 08a)
POST /api/fundamentals/analyze                   # bulk: list of symbols → ranked fundamental candidates
POST /api/fundamentals/review                    # sandbox review (PRD-08b)
```

**Response shape for `GET /api/fundamentals/{symbol}/summary`:**
```json
{
  "symbol": "AAPL",
  "as_of_date": "2026-05-11",
  "company_name": "Apple Inc.",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "business_map": {
    "one_line_summary": "Apple designs, manufactures...",
    "primary_value_chain_role": "Manufacturer / Producer",
    "margin_implication": "Above-average for Manufacturer / Producer...",
    "cyclicality_implication": "Low — consumer hardware has some cyclicality...",
    "confidence": "partial",
    "source_notes": ["FMP /profile", "sector-to-value-chain mapping v1"]
  },
  "market_position": {
    "market_category": "Large-Cap Technology — Consumer Electronics",
    "key_competitors": ["MSFT", "GOOGL", "SMSN.KS"],
    "market_size_estimate": "estimate unavailable",
    "market_growth_label": null,
    "competitive_position_label": null,
    "confidence": "partial",
    "source_notes": ["FMP /stock/peers/AAPL", "FinanceDatabase sector mapping"]
  },
  "financial_check": {
    "financial_validation_label": "Financials Strongly Support Story",
    "growth_summary": "Revenue grew 8.1% YoY...",
    "profitability_summary": "Gross margin of 45.2% is above sector norm...",
    "cash_flow_summary": "FCF of $96B, 97% conversion rate...",
    "balance_sheet_summary": "Net cash position of $48B...",
    "valuation_summary": "P/E of 28x is 1.4x sector median...",
    "supporting_evidence": [...],
    "contradicting_evidence": [...],
    "confidence": "high",
    "source_notes": ["FMP /income-statement", "FMP /cash-flow-statement", "FMP /key-metrics"]
  },
  "scores": {
    "financial_validation_score": 82,
    "valuation_risk_score": 38,
    "business_map_score": null,
    "market_position_score": null,
    "overall_fundamental_score": 57,
    "overall_label": "Good Business, Watch Valuation (financial only — business analysis pending)"
  },
  "warnings": ["Valuation Risk High"],
  "disclaimer": "This tool provides research candidates, not financial advice..."
}
```

---

## Frontend — Company Page (`/stocks/[ticker]`)

### Page layout

```
[Company header]
  Ticker | Name | Price | % change | Sector · Industry badge | Market cap badge

[Three sections — stacked vertically]
  1. Business Map card
  2. Market Position card
  3. Financial Check cards (most detailed)

[Scores bar]
  Financial Score: 82/100  |  Valuation Risk: 38/100  |  Overall: 57  |  Label

[Disclaimer]

[Action buttons]
  "Run Backtest on {ticker}" → /workspace?prompt=...
  "Publish to Community" → disabled, tooltip "Coming soon"
  "Add to Watchlist" → disabled, tooltip "Sign in to use — coming soon"
```

### Business Map card (PRD-08a partial view)

```
┌─ Business Map ──────────────────────────────────────────────────┐
│ Value chain position:  [Manufacturer / Producer]                 │
│                                                                  │
│ ── ── ── ── [▶ Manufacturer/Producer] ── ── ── ──               │
│ Raw Mat · Components · [■ Production] · Platform · Distribution  │
│                                                                  │
│ Margin implication: Above-average for this role                  │
│ Cyclicality: Low                                                 │
│                                                                  │
│ ℹ Revenue model, customer types, pricing power:                 │
│   Data pending — available when 10-K/10-Q analysis is added     │
│                                                                  │
│ Confidence: Partial · Source: FMP profile, sector mapping       │
└──────────────────────────────────────────────────────────────────┘
```

### Market Position card (PRD-08a partial view)

```
┌─ Market Position ───────────────────────────────────────────────┐
│ Category: Large-Cap Technology — Consumer Electronics            │
│                                                                  │
│ Peers: [MSFT] [GOOGL] [SMSN]                                    │
│                                                                  │
│ Market size, growth, competitive position, share:               │
│   Data pending — available when 10-K/10-Q analysis is added     │
│                                                                  │
│ Confidence: Partial · Source: FMP /stock/peers, FinanceDatabase │
└──────────────────────────────────────────────────────────────────┘
```

### Financial Check cards (complete in PRD-08a)

Four mini-cards in a 2×2 grid, plus a valuation card:

```
┌─ Growth ─────────────┐  ┌─ Profitability ───────┐
│ Revenue YoY: +8.1%   │  │ Gross margin: 45.2%   │
│ EPS YoY: +10.4%      │  │ Op. margin: 30.1%     │
│ [8-quarter sparkline]│  │ Net margin: 25.3%     │
│                      │  │ [8-quarter sparkline] │
└──────────────────────┘  └───────────────────────┘

┌─ Cash Flow ──────────┐  ┌─ Balance Sheet ───────┐
│ FCF: $96B            │  │ Net cash: +$48B       │
│ FCF margin: 25.1%    │  │ D/E ratio: 1.2x       │
│ FCF conversion: 97%  │  │ Current ratio: 0.99   │
│ [8-quarter sparkline]│  │                       │
└──────────────────────┘  └───────────────────────┘

┌─ Valuation ─────────────────────────────────────┐
│ P/E: 28x  (sector median: 20x)  ⚠ +40% premium │
│ P/S: 7.2x · P/B: 45x · FCF yield: 3.6%        │
│ [Valuation Risk: 38/100 — Moderate]             │
└──────────────────────────────────────────────────┘

┌─ Financial Validation ─────────────────────────────────────────┐
│ ✓ Financials Strongly Support Story  ⚠ Valuation Risk High    │
│                                                                  │
│ Supporting: Strong FCF conversion, net cash, growing margins    │
│ Contradicting: P/E premium vs sector, high P/B                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## Skills to activate during build

| Skill | When |
|---|---|
| `data-quality-checker` | After FMP client is wired — validate response field coverage |
| `safe-migration` | Before merging Alembic migrations for the 4 new tables |
| `us-stock-analysis` | Reference when writing financial summary text generation logic |
| `earnings-calendar` | Wire into Financial Check earnings history section |
| `ui-ux-pro-max` | Company page design — run `--design-system` for fintech dashboard style |

---

## GitHub resources activated

| Resource | Where used |
|---|---|
| `JerBouma/FinanceDatabase` | `pip install financedatabase` — Market Position `market_category` + screener filter options |
| `ranaroussi/yfinance` | `pip install yfinance` — fallback for FMP when rate-limited; supplement earnings history |
| `xang1234/stock-screener` | Reference for company detail column spec and sector filter taxonomy |

---

## Acceptance criteria

- [ ] `GET /api/fundamentals/AAPL/summary` returns all three sections with correct field population
- [ ] Business Map: `one_line_summary`, `primary_value_chain_role`, `margin_implication`, `cyclicality_implication` populated; all other fields null with `confidence: "partial"`
- [ ] Market Position: `market_category` and `key_competitors` populated where FMP data exists; all other fields null
- [ ] Financial Check: all metrics computed for any S&P 500 company; `confidence: "high"`
- [ ] `financial_validation_score` and `valuation_risk_score` computed; `business_map_score` and `market_position_score` are null
- [ ] Overall label appends "(financial only — business analysis pending)"
- [ ] FMP 429 → graceful fallback to yfinance, no 500 error surfaced
- [ ] `safe-migration` skill run confirms no dangerous migration operations
- [ ] Company page `/stocks/AAPL` renders all three section cards
- [ ] "Data pending" message shown clearly in Business Map and Market Position for blank fields
- [ ] "Publish to Community" and "Add to Watchlist" buttons visible but disabled with tooltip
- [ ] Disclaimer text visible on page
- [ ] All new TS types defined in `contracts.ts` before any component written

---

## What PRD-08b adds (gated on 10-K/10-Q model)

When Jimmy's 10-K/10-Q data extraction model is ready, PRD-08b will:
- Fill `customer_types`, `revenue_model`, `pricing_power_implication` in Business Map
- Fill `market_size_estimate`, `market_growth_label`, `competitive_position_label`, `key_growth_drivers`, `key_risks` in Market Position
- Compute `business_map_score` (25%) and `market_position_score` (30%) 
- Add `fundamental_explainer.py` and `fundamental_sandbox_reviewer.py`
- Change `confidence` from `"partial"` to `"full"` when all sections are populated
- Activate "Publish to Community" when PRD-14 ships

PRD-08b is **not scheduled** — it is explicitly waiting on the external data model.
