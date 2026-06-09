# PRD-16a: Signal Primitive Library + Categorized Catalog + KB Lookup

**Status**: Ready to build
**Phase**: Custom Mode foundation
**Depends on**:
- **None hard.** Can ship in parallel with PRD-19.
- **Soft dep on Module 2 (PR #97/#106)** — reuses the `PriceDataService` cache pattern.

**Blocks**: PRD-16b (consumes the catalog + KB lookup); PRD-16c (extends with intraday primitives).
**Effort**: ~2 weeks, single owner
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/livermore_product_flow_v2.html`](../../Quant%20Strategy/framework/livermore_product_flow_v2.html) — §2 Mode 4 + signal-library research from chat 2026-06-08

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded). Then read agent-system/plans/HANDOFF-livermore-product-flow-v2.md.

Goal: build the signal primitive library — the foundation Custom Mode (Mode 4)
will compose strategies from. Three deliverables:

  1. A unified SignalProvider protocol extension wiring ~40 Alpha Vantage
     technical indicators + existing template signals into one catalog of
     ~55 categorized primitives.

  2. A GET /api/signal-primitives catalog endpoint exposing each primitive's
     metadata (category, parameters, defaults, asset compatibility, evidence,
     plain-English description).

  3. A POST /api/signal-combos/match-templates endpoint — the knowledge-base
     lookup. Given a set of primitive_ids, returns top-3 matching templates
     from the existing library with their suggested entry/exit thresholds.

PREREQUISITES (must be on main):
  - Existing SignalProvider abstraction (shipped Phase A)
  - Existing strategy template catalog (researchTemplates in contracts.ts)
  - Module 2 (PR #97/#106) — reuses PriceDataService cache

OUT OF SCOPE for this PRD:
  - The composer UI itself (drag-and-drop) — PRD-16b
  - Engine multi-rule fold — PRD-16b
  - Intraday primitives (the catalog includes daily-resolution wiring only) — PRD-16c
  - User-saved custom signal primitives (e.g. user-supplied Python) — far future

Context to read in order:
  - /Quant Strategy/framework/livermore_product_flow_v2.html §2 Mode 4
  - /Quant Strategy/framework/strategy_builder_audit.md (existing primitives)
  - /Quant Strategy/framework/Livermore_Strategy_Library_v2.html §3 (template signals)
  - apps/api/app/services/backtester/signal_provider.py (existing protocol)
  - apps/web/src/lib/contracts.ts (existing template catalog)

Architecture rules (the four principles, see HANDOFF §2):
  1. Reuse — extend SignalProvider protocol; don't fork.
  2. LEGO bricks — every primitive is a brick; categorization is metadata.
  3. FlowDefinition — not applicable to this PRD (catalog is content, not a flow).
  4. UX rules — useFlowCopy('signal_library', key); skeleton on catalog load;
     <300ms perceived load via aggressive caching of the catalog itself.

Acceptance: see "Acceptance Checklist" at the bottom. Branch as
`<your-agent-name>/feat/signal-library-catalog`. Open one PR; base=main.
```

---

## Design Constraints (the four principles)

Same four principles as the product flow v2 packet and the notification packet. Re-stated for the agent.

### 1. Reuse, don't replicate

The codebase already has:
- `SignalProvider` protocol with 4 concrete implementations (Fundamental, Sentiment, EarningsEvent, Insider) — extend this; don't fork.
- `PriceDataService` cache pattern — use it for all Alpha Vantage indicator pulls.
- `researchTemplates` catalog in `apps/web/src/lib/contracts.ts` — read template metadata from here for the KB lookup; don't duplicate.
- The 4-block summary step in strategy builder — eventually consumes this catalog (PRD-16b); don't fork.

Novel work: ~40 new Alpha Vantage indicator wirings, categorization metadata layer, catalog endpoint, KB lookup endpoint, frontend catalog browser brick.

### 2. LEGO bricks

Each signal primitive is a brick. `SignalPrimitiveCard` (frontend) renders any primitive uniformly. `SignalProvider` impls share the same interface. The KB lookup is a brick PRD-16b consumes verbatim.

Brick inventory at end of doc; future PRD-16c will add intraday primitives that extend (not fork) this catalog.

### 3. FlowDefinition (where applicable)

Not applicable. The catalog browser is a content surface, not a multi-step flow. PRD-16b will define `custom_build_mode.ts` as a `FlowDefinition` that consumes this PRD's catalog.

### 4. UX consistency + sub-300ms perceived load

- **Centralized labels** via `useFlowCopy('signal_library', key)`.
- **Aggressive catalog caching** — the catalog metadata changes only on deploy; cache it in localStorage with a version stamp; revalidate on app load.
- **Skeleton** during initial catalog fetch.
- **Optimistic UI** on user clicks (e.g., clicking a category filter doesn't wait for re-render).
- **Plain-English everywhere** — each primitive carries a 1-sentence description that the catalog browser shows; no Greek-letter jargon by default (RSI is "Relative Strength Index — measures overbought/oversold extremes," not "RSI(14) > 70 = sell signal").

---

## Problem

Livermore's Custom Mode (Mode 4) ships in v2 as "fork a template and edit its 4 blocks." That's useful but constrained — the user can't actually build a strategy from scratch, because the WHEN IN and WHEN OUT signals are template-baked.

To enable real custom strategies, users need:
1. A **library of signal primitives** to choose from (not just whatever a template happens to use).
2. **Categorization** so they can find what they need without reading 55 entries.
3. A **guided starting point** — when they pick {RSI, Bollinger, Volume}, the system should recognize this as a mean-reversion setup and suggest defaults rather than make them invent thresholds from scratch.

This PRD ships the **content + lookup** layer. PRD-16b ships the composer UI that consumes it.

## Goals

1. **~55 categorized signal primitives** wired and queryable, spanning all 8 categories.
2. **`GET /api/signal-primitives`** endpoint returns full catalog with metadata.
3. **`GET /api/signal-primitives/{id}/preview`** returns sample values on a chosen symbol — for the catalog browser's "show me what this looks like" UX.
4. **`POST /api/signal-combos/match-templates`** — takes `{primitive_ids: [...]}`, returns top-3 matching templates with their suggested WHEN IN/OUT thresholds.
5. **Frontend `<SignalCatalogBrowser>`** — searchable, filterable, category-grouped UI.
6. **Frontend `<SignalPrimitiveCard>`** — uniform brick for rendering any primitive.
7. **Frontend `<TemplateMatchSuggestion>`** — renders KB lookup results.
8. **Cache layer** for catalog metadata (server-side ETag + client-side localStorage with version).
9. **Compliance**: every primitive description is descriptive (what it measures), not prescriptive (when to buy).

## Non-Goals

- **No composer UI** — PRD-16b.
- **No engine changes** — PRD-16b (multi-rule fold).
- **No intraday primitives** — PRD-16c (catalog ships daily-resolution wiring only).
- **No user-supplied signals** — far-future Pro feature.
- **No NLP-based primitive recommendation** — deterministic category-overlap match only.
- **No LLM-generated descriptions** — descriptions are hand-authored in code; PR review is the editorial gate.
- **No live preview against user portfolio** — preview uses a default symbol (SPY); the personalized preview lands when PRD-16b's composer integrates it.
- **No ML-based template matching** — Jaccard similarity on category-sets is enough.

## User stories

1. **As a prosumer building a custom strategy**, I want to browse ~55 signal primitives organized by 8 categories so I can pick the ones that match my thesis without scrolling a giant flat list.
2. **As any user**, I want each primitive to come with a 1-sentence plain-English description so I don't have to look up what "Aroon" means.
3. **As any user**, when I select {RSI, Bollinger, Volume}, I want the system to say "this looks like a mean-reversion setup — try these thresholds" so I don't have to invent values from scratch.
4. **As any user**, I want to see what a primitive looks like on a chart before committing — a preview chart of RSI on SPY would help me understand it.
5. **As a returning user**, I want the catalog to load instantly because it doesn't change often; only revalidate when a new version ships.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│  CATALOG METADATA (apps/api/app/data/signal_primitives.py)             │
│   Hand-authored Python data structure — ~55 entries:                   │
│     [SignalPrimitive(                                                  │
│        id="rsi_14",                                                    │
│        category=SignalCategory.MEAN_REVERSION,                         │
│        family="RSI",                                                    │
│        name="RSI (14)",                                                │
│        description="Measures overbought/oversold extremes...",          │
│        parameters=[Parameter(name="period", default=14, ...)],         │
│        default_thresholds={"upper": 70, "lower": 30},                  │
│        asset_compat=["equity", "etf", "commodity"],                    │
│        evidence_tier="B",                                              │
│        provider_impl="RsiSignalProvider",                              │
│      ), ... ]                                                          │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ SIGNAL PROVIDERS (apps/api/app/services/backtester/signal_provider.py) │
│   Extended with ~40 new concrete implementations:                      │
│     - RsiSignalProvider, MacdSignalProvider, BBandsSignalProvider...   │
│   All inherit existing protocol; existing Fundamental/Sentiment/etc.   │
│   impls unchanged.                                                     │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ROUTES (apps/api/app/api/routes/signal_primitives.py)                  │
│   GET /api/signal-primitives                                           │
│     → returns full catalog metadata with ETag                          │
│   GET /api/signal-primitives/{id}/preview?symbol=SPY                   │
│     → returns ~252 days of computed primitive values                   │
│   POST /api/signal-combos/match-templates                              │
│     → body: {primitive_ids: [...]} → returns top-3 template matches    │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ FRONTEND BRICKS (apps/web/src/components/signal-library/)              │
│   <SignalCatalogBrowser /> — searchable, filterable grid               │
│   <SignalPrimitiveCard /> — uniform card for any primitive             │
│   <SignalPreviewChart /> — mini chart of primitive on SPY              │
│   <TemplateMatchSuggestion /> — top-3 recommended templates            │
│                                                                        │
│   Catalog cached in localStorage; revalidated via ETag on app load.    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Backend changes

### 1. Categorization schema

`apps/api/app/schemas/signal_primitive.py` (new file)

```python
class SignalCategory(str, Enum):
    TREND = "trend"                          # SMA, EMA, MACD, MA crossover, ADX, AROON...
    MEAN_REVERSION = "mean_reversion"        # RSI, Bollinger, Stochastic, CCI, WILLR...
    MOMENTUM = "momentum"                    # ROC, MOM, breakout (Donchian), 12-1 momentum...
    VOLUME = "volume"                        # OBV, AD, VWAP, avg dollar volume...
    VOLATILITY = "volatility"                # ATR, NATR, realized vol, vol regime...
    FUNDAMENTAL = "fundamental"              # FCF yield, P/B, Piotroski, buyback yield...
    SENTIMENT = "sentiment"                  # News sentiment (FinBERT), insider buying...
    CROSS_SECTIONAL = "cross_sectional"      # Rank by N-month return, sector rotation...


class Parameter(BaseModel):
    name: str
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str                          # plain-English


class SignalPrimitive(BaseModel):
    id: str                                  # unique slug e.g. "rsi_14"
    category: SignalCategory
    family: str                              # e.g. "RSI" (for grouping families like RSI / STOCHRSI)
    name: str                                # display name
    description: str                         # 1-sentence plain-English
    long_description: Optional[str] = None   # optional 1-paragraph deeper explanation
    parameters: list[Parameter]
    default_thresholds: dict[str, float]     # e.g. {"upper": 70, "lower": 30}
    asset_compat: list[str]                  # ["equity", "etf", "commodity", "fx", "crypto"]
    evidence_tier: Literal["A", "B", "C"]    # from existing template evidence framework
    provider_impl: str                       # name of SignalProvider class
    data_source: Literal["price", "fundamental", "sentiment", "event"]
    resolution: list[Literal["daily", "intraday"]]  # which data resolutions support this; intraday will be added in PRD-16c
    is_ranking: bool = False                 # cross-sectional primitives flag this
```

### 2. Catalog content

`apps/api/app/data/signal_primitives.py` (new file)

Hand-authored Python data structure. ~55 entries. Sample:

```python
SIGNAL_PRIMITIVES: list[SignalPrimitive] = [
    # ── Trend ────────────────────────────────────────────────────────
    SignalPrimitive(
        id="sma",
        category=SignalCategory.TREND,
        family="MA",
        name="Simple Moving Average",
        description="Average closing price over N days — the classic trend line.",
        parameters=[
            Parameter(name="period", default=200, min_value=2, max_value=500,
                      description="Number of days to average")
        ],
        default_thresholds={"price_above_ma": 1.0},  # binary signal
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="SmaSignalProvider",
        data_source="price",
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="ema",
        category=SignalCategory.TREND,
        family="MA",
        name="Exponential Moving Average",
        description="Weighted moving average that reacts faster to recent prices than SMA.",
        parameters=[Parameter(name="period", default=50, min_value=2, max_value=500, description="Smoothing period")],
        # ... continued
    ),
    SignalPrimitive(
        id="macd",
        category=SignalCategory.TREND,
        family="MACD",
        name="MACD (Moving Average Convergence Divergence)",
        description="Difference between fast and slow EMAs; signal line is a smoothed version. Crossovers signal trend changes.",
        parameters=[
            Parameter(name="fast_period", default=12, min_value=2, max_value=100, description="Fast EMA length"),
            Parameter(name="slow_period", default=26, min_value=2, max_value=200, description="Slow EMA length"),
            Parameter(name="signal_period", default=9, min_value=2, max_value=50, description="Signal-line smoothing length"),
        ],
        # ...
    ),

    # ── Mean Reversion ───────────────────────────────────────────────
    SignalPrimitive(
        id="rsi_14",
        category=SignalCategory.MEAN_REVERSION,
        family="RSI",
        name="RSI (Relative Strength Index)",
        description="Measures overbought (>70) and oversold (<30) extremes from recent gains vs losses.",
        parameters=[Parameter(name="period", default=14, min_value=2, max_value=100, description="Look-back window")],
        default_thresholds={"upper": 70, "lower": 30},
        # ...
    ),

    # ── ~50 more entries spanning all 8 categories ──
]
```

The complete inventory:
- **Trend** (~12 entries): SMA, EMA, WMA, DEMA, TEMA, TRIMA, KAMA, MAMA, T3, MACD, SAR, HT_TRENDLINE, HT_TRENDMODE
- **Mean Reversion** (~9 entries): RSI, STOCH, STOCHF, STOCHRSI, WILLR, CCI, CMO, BBANDS, MFI
- **Momentum** (~10 entries): ADX, ADXR, AROON, AROONOSC, MOM, ROC, ROCR, APO, PPO, ULTOSC, TRIX, BOP, Donchian breakout, 12-1 cross-sectional
- **Volume** (~5 entries): OBV, AD, ADOSC, VWAP, avg dollar volume filter
- **Volatility** (~5 entries): ATR, NATR, TRANGE, realized vol (rolling stdev), vol regime classifier
- **Fundamental** (~7 entries): FCF yield, P/B, EV/EBITDA, P/E, Piotroski F-score, buyback yield, estimate revisions
- **Sentiment** (~3 entries): news sentiment (FinBERT), insider buying cluster, analyst rating change
- **Cross-Sectional** (~4 entries): N-month return rank, composite-score rank, sector rotation rank, pair spread z-score

### 3. SignalProvider extensions

`apps/api/app/services/backtester/signal_provider.py` (extend existing)

For each of the ~40 new Alpha Vantage indicators, add a concrete `SignalProvider` implementation. Pattern (sketch):

```python
class RsiSignalProvider(SignalProvider):
    """Computes RSI series for a symbol over a date range."""

    def __init__(self, period: int = 14):
        self.period = period

    async def compute(
        self,
        db: Session,
        symbol: str,
        start: date,
        end: date,
        resolution: str = "daily",
    ) -> pd.Series:
        # 1. Pull cached price history via PriceDataService
        prices = await price_data_service.get_close_series(db, symbol, start, end)
        # 2. Compute RSI
        delta = prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(self.period).mean()
        avg_loss = loss.rolling(self.period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
```

Some primitives are pure pandas computations (RSI, SMA, MACD). Others would benefit from Alpha Vantage's pre-computed endpoint (avoids re-computing; saves CPU on Railway). Decision per-primitive:

- **Use AV pre-computed**: indicators requiring expensive math (Hilbert Transform family, MAMA, KAMA). Cheap to fetch, expensive to compute.
- **Compute locally with pandas**: simple indicators (SMA, EMA, RSI, MACD, Bollinger). No AV call needed; saves API budget.

Document the per-primitive choice in the catalog metadata as `compute_strategy: "local" | "av_endpoint"`.

### 4. Catalog endpoint

`apps/api/app/api/routes/signal_primitives.py` (new file)

```python
@router.get("/signal-primitives")
async def get_catalog() -> SignalPrimitivesResponse:
    """Return the full primitive catalog with metadata.

    Heavily cached: ETag is the catalog content hash; frontend reuses
    cached payload if ETag matches.
    """
    return SignalPrimitivesResponse(
        primitives=SIGNAL_PRIMITIVES,
        categories=[c for c in SignalCategory],
        version_hash=_compute_catalog_hash(),
    )

@router.get("/signal-primitives/{primitive_id}/preview")
async def preview(
    primitive_id: str,
    symbol: str = "SPY",
    parameter_overrides: Optional[dict] = None,
    db: Session = Depends(get_db),
) -> PreviewResponse:
    """Return ~252 days of primitive values on the requested symbol.

    Used by the catalog browser to show "this is what RSI looks like on SPY."
    """
    primitive = _find_primitive(primitive_id)
    provider = _instantiate_provider(primitive, parameter_overrides)
    series = await provider.compute(db, symbol, date.today() - timedelta(days=365), date.today())
    return PreviewResponse(symbol=symbol, primitive_id=primitive_id, series=series.to_dict())
```

### 5. KB lookup endpoint — the load-bearing piece

`POST /api/signal-combos/match-templates`

```python
@router.post("/signal-combos/match-templates")
async def match_templates(payload: MatchTemplatesRequest) -> MatchTemplatesResponse:
    """Given a list of primitive ids, return top-3 matching templates with
    suggested entry/exit thresholds.

    Algorithm:
      1. Compute category set of user's combo: {SignalCategory.MEAN_REVERSION, SignalCategory.VOLUME, ...}
      2. For each template in researchTemplates catalog:
         - Compute template's category set
         - Compute Jaccard similarity: |user ∩ template| / |user ∪ template|
      3. Sort by similarity; return top-3 with their existing rule structure as suggestions.
      4. For each template match, ALSO emit specific suggested thresholds for
         the user's primitives based on what that template uses for its own
         (e.g. if user picked RSI and the matching template is "RSI Mean
         Reversion," suggest RSI < 30 / RSI > 60 from that template).
    """
```

Suggested-threshold derivation: each template in the catalog has a `metadata.signal_thresholds` map authored alongside the template definition. PRD-16a is responsible for **populating this map for existing templates** as part of the catalog work — the data structure already supports it; we just need to fill it in.

### 6. Test plan

`apps/api/tests/`

- `test_signal_catalog.py` — every primitive in SIGNAL_PRIMITIVES has all required fields; descriptions are ≥ 30 chars; no duplicate ids.
- `test_signal_provider_extensions.py` — each new `SignalProvider` impl produces correct output on synthetic price series (test ~5 representative impls: RSI, MACD, BBANDS, ATR, Aroon).
- `test_catalog_endpoint.py` — GET /signal-primitives returns full catalog; ETag matches.
- `test_preview_endpoint.py` — preview returns ≥ 200 data points on SPY for a representative primitive.
- `test_kb_lookup.py` — synthetic combos return expected templates ({RSI, Bollinger} → RSI Mean Reversion top match; {MA, momentum} → Trend Following top match).

---

## Frontend changes

### 1. New bricks

`apps/web/src/components/signal-library/signal-catalog-browser.tsx`

```tsx
export function SignalCatalogBrowser({ onPick }: { onPick: (id: string) => void }) {
  // Fetches GET /api/signal-primitives (cached in localStorage with version stamp)
  // Renders:
  //   - Category sidebar (8 entries)
  //   - Search bar (filters by name + description)
  //   - Asset-class filter (equity / ETF / commodity)
  //   - Grid of <SignalPrimitiveCard>
  //   - Skeleton state on initial load
  // Clicking a card calls onPick(primitive.id) — composer will consume this in PRD-16b
}
```

`apps/web/src/components/signal-library/signal-primitive-card.tsx`

```tsx
export function SignalPrimitiveCard({ primitive, onClick }: Props) {
  // Uniform card: name + 1-line description + category badge + evidence tier badge
  // Optional: thumbnail preview of <SignalPreviewChart> on hover (lazy-loaded)
}
```

`apps/web/src/components/signal-library/signal-preview-chart.tsx`

```tsx
export function SignalPreviewChart({ primitiveId, symbol = "SPY" }: Props) {
  // Lazy-loads GET /api/signal-primitives/{id}/preview
  // Renders simple line chart with skeleton while loading
}
```

`apps/web/src/components/signal-library/template-match-suggestion.tsx`

```tsx
export function TemplateMatchSuggestion({ primitiveIds }: { primitiveIds: string[] }) {
  // Fetches POST /api/signal-combos/match-templates
  // Renders top-3 matches with:
  //   - Template name + thesis
  //   - Suggested thresholds (e.g. "RSI < 30 to enter, RSI > 60 to exit")
  //   - "Use these defaults" button
  // PRD-16b's composer will consume the suggested-defaults output via callback
}
```

### 2. Standalone catalog page (optional)

`apps/web/src/app/signal-library/page.tsx` (new file, optional)

A standalone "browse the signal library" page for users who want to explore primitives without committing to a strategy. Useful for the marketing surface and SEO; also useful for users learning what's available.

If this turns out to add unwarranted scope, defer to a follow-up PRD. The catalog browser brick lives in `components/signal-library/` regardless and can be reused by PRD-16b.

### 3. Test plan

- `__tests__/signal-catalog-browser.test.tsx` — renders categories, filters, search.
- `__tests__/signal-primitive-card.test.tsx` — renders all fields; click fires callback.
- `__tests__/template-match-suggestion.test.tsx` — fetches and renders top-3.

---

## Reusable LEGO bricks created by this PRD

### Backend

| Brick | Path | Used by |
|---|---|---|
| `SignalPrimitive` Pydantic model | `schemas/signal_primitive.py` | All consumers; PRD-16b's composer |
| `SIGNAL_PRIMITIVES` catalog | `data/signal_primitives.py` | PRD-16b; PRD-16c extends with intraday entries |
| `SignalCategory` enum | `schemas/signal_primitive.py` | All consumers |
| ~40 new `SignalProvider` impls | `services/backtester/signal_provider.py` (extended) | PRD-16b composer + PRD-16c intraday |
| `GET /api/signal-primitives` catalog endpoint | `routes/signal_primitives.py` | PRD-16b; standalone catalog page |
| `GET /api/signal-primitives/{id}/preview` | Same | Catalog browser preview chart |
| `POST /api/signal-combos/match-templates` | Same | PRD-16b's recommendation panel |
| Per-template signal_thresholds metadata | `lib/contracts.ts` (extended) | KB lookup endpoint |

### Frontend

| Brick | Path | Used by |
|---|---|---|
| `<SignalCatalogBrowser>` | `components/signal-library/` | PRD-16b composer; standalone library page |
| `<SignalPrimitiveCard>` | Same | Catalog browser; PRD-16b composer canvas |
| `<SignalPreviewChart>` | Same | Catalog browser; PRD-16b composer hover preview |
| `<TemplateMatchSuggestion>` | Same | PRD-16b's recommendation panel |
| Catalog localStorage cache | `lib/signal-library/catalog-cache.ts` | All catalog consumers; version-stamped invalidation |

---

## Acceptance checklist

A PR is accepted when **all of the following are true**.

### Backend

- [ ] `SignalPrimitive` Pydantic model defined; `SignalCategory` enum with 8 values.
- [ ] `SIGNAL_PRIMITIVES` populated with ≥ 50 entries spanning all 8 categories.
- [ ] Every primitive has: `description` ≥ 30 chars, ≥ 1 parameter, `asset_compat` ≥ 1 entry, `evidence_tier`, `provider_impl`, `data_source`, `resolution = ["daily"]`.
- [ ] ~40 new `SignalProvider` impls implemented; each has at least one test on a synthetic price series.
- [ ] `GET /api/signal-primitives` endpoint returns catalog with ETag header.
- [ ] `GET /api/signal-primitives/{id}/preview` returns ≥ 200 data points on SPY.
- [ ] `POST /api/signal-combos/match-templates` returns ≥ 1 match for representative combos.
- [ ] All existing templates in `researchTemplates` have a `signal_thresholds` map populated.
- [ ] No `X | None` syntax (Python 3.9 compat).
- [ ] All 5 new backend tests pass.
- [ ] Full backend suite passes: `cd apps/api && python3 -m pytest -q`.

### Frontend

- [ ] `<SignalCatalogBrowser>` brick renders all 8 categories, filters, search; uses cached catalog via localStorage.
- [ ] `<SignalPrimitiveCard>` brick renders uniformly across primitives.
- [ ] `<SignalPreviewChart>` brick lazy-loads + renders simple line chart.
- [ ] `<TemplateMatchSuggestion>` brick fetches + renders top-3 matches.
- [ ] (Optional) Standalone catalog page at `/signal-library`.
- [ ] All 3 frontend unit tests pass.
- [ ] `cd apps/web && npm run build` clean.
- [ ] `cd apps/web && npm run test` green.

### Quality

- [ ] Every primitive description is plain English (no Greek letters in default text); long descriptions optional.
- [ ] No prescriptive language in descriptions — "measures X" not "use this to buy when Y."
- [ ] Catalog loads in < 300ms perceived on warm cache; < 1s on cold.
- [ ] Preview chart loads in < 1s perceived.

### Telemetry

- [ ] PostHog events: `signal_catalog_opened`, `signal_primitive_previewed` (with `primitive_id`), `template_match_lookup` (with category set), `template_match_selected`.

### Documentation

- [ ] Update HANDOFF-livermore-product-flow-v2.md §6 Brick inventory: mark PRD-16a bricks as ✅.
- [ ] PR title: `feat(signal-library): primitive catalog + KB lookup (PRD-16a)`.

---

## Out of scope (do not build in this PRD)

- **Composer UI** — PRD-16b.
- **Engine multi-rule fold** — PRD-16b.
- **Intraday primitives** — PRD-16c.
- **User-supplied custom primitives** (e.g. Python sandboxed code) — far-future Pro feature.
- **LLM-generated descriptions** — descriptions are hand-authored.
- **Real-time preview against user portfolio** — preview uses SPY as default; personalized preview lands when PRD-16b's composer integrates.
- **Marketplace / community-contributed primitives** — separate future product.
- **Mark-as-Executed for primitive picks** — irrelevant; primitives are inputs to strategies, not actions.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §2 Mode 4
- Source research: chat 2026-06-08 (Alpha Vantage indicator coverage + template signal taxonomy)
- Master handoff: `agent-system/plans/HANDOFF-livermore-product-flow-v2.md`
- Soft dep: Module 2 (PR #97/#106) — reuses `PriceDataService`
- Blocks: `PRD-16b-custom-build-composer.md`, `PRD-16c-intraday-active-execution.md`
- Existing SignalProvider: `apps/api/app/services/backtester/signal_provider.py`
- Existing template catalog: `apps/web/src/lib/contracts.ts:researchTemplates`
- Repo conventions: `CLAUDE.md` (auto-loaded), `agent-system/PARALLEL_WORK.md`

---

*Drafted 2026-06-08. Catalog content; no UI for assembling strategies (that's PRD-16b) and no intraday (PRD-16c). Ships in parallel with PRD-19.*
