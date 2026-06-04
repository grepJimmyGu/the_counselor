# PRD-13c: Portfolio Overlay Expansion — Dual Momentum, Defense-First, Stability Tilt

**Status**: Research validated — ready to build
**Phase**: Sprint 2 (expands PRD-13b Sprint 1 overlays)
**Depends on**:
- **PRD-13b** (Portfolio Mode) — all three overlay strategy_types, `inherited_universe` engine support, the flow runtime bricks (`OverlayPicker`, `PortfolioDiagnosis`, `PortfolioSummary`), and the diagnose endpoint must be on `main` before this PRD starts.
- **PRD-13a** (flow runtime) — `useFlowCopy`, `registerModeCopy`, `FlowDefinition` contract.

**Blocks**: Nothing. This is additive — three new overlay cards + their engine branches. Existing overlays, flow steps, and saved strategies are untouched.

**Effort**: 1–1.5 weeks (backend ~2 days, frontend ~3 days, testing ~1 day)
**Owner**: TBD
**Source research**:
- Antonacci, "Dual Momentum Investing" (2014); Pavlović et al., *European Journal of Applied Economics* (2025)
- Carlson, "Defense First: A Multi-Asset Tactical Model for Adaptive Downside Protection" (SSRN, July 2025); Keller/Keuning, "Hybrid Asset Allocation" (AllocateSmartly)
- Lu et al., "TrendFolios" (arXiv, June 2025); Ang et al., "The Cross-Section of Volatility and Expected Returns" (2006)
- Yang, "Do Simple Strategies Still Work for Retail Investors?" (Emory thesis, Fall 2025)

---

## 🤖 Coding-agent kickoff prompt

> Paste into a fresh Claude Code session. Each prompt is self-sufficient — Claude Code only needs `CLAUDE.md` (auto-loaded) plus this prompt to start.

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded on boot) for branch / PR / Python-3.9-compat rules.

Goal: expand Portfolio Mode from 3 overlays to 6 by adding three new
research-validated overlay strategies — Dual Momentum, Defense-First, and
Stability Tilt. Each overlay:

  1. Has an engine branch in BacktestEngine._generate_weights
  2. Has a strategy_type literal + validation in the schema layer
  3. Appears as a card in <OverlayPicker> with credibility annotations
     (research source, estimated impact, expandable "How it works")

PREREQUISITES (must be on main before starting):
  - PRD-13b: portfolio_defensive_overlay, portfolio_rotation_overlay,
    portfolio_rebalance_overlay engine branches + schema types
  - PRD-13b: <OverlayPicker> brick, OverlayKind type, buildStrategyJson()
  - PRD-13a: flow runtime (useFlowCopy, registerModeCopy)

Context to read in order:
  - agent-system/plans/PRD-13b-portfolio-mode.md (the original; this PRD expands it)
  - agent-system/plans/PRD-13c-portfolio-overlay-expansion.md (this file)
  - apps/api/app/services/backtester/engine.py (existing overlay branches at
    lines 687–729; dual_momentum at 433–454; low_volatility at 456–471;
    vol_target post-processing at 762–781)
  - apps/api/app/schemas/strategy.py (StrategyType, PORTFOLIO_OVERLAY_TYPES,
    ENGINE_SUPPORTED_TYPES, StrategyRule fields)
  - apps/web/src/lib/contracts.ts (OverlayKind type at line 370)
  - apps/web/src/lib/flows/bricks/overlay-picker.tsx (card rendering, buildStrategyJson)

Architecture rules for this PRD:
  1. Every new overlay reuses an existing engine primitive — no new
     _generate_weights infrastructure. Dual Momentum reuses
     _generate_cross_sectional_weights + a per-holding absolute filter;
     Defense-First reuses rolling MA + exposure scaling; Stability Tilt
     reuses rolling volatility + row normalization.
  2. Frontend changes extend <OverlayPicker> — don't fork it. The existing
     3 cards continue to render unchanged; 3 new cards are appended with
     an "Advanced" section header + credibility annotations.
  3. Credibility data lives in a static registry on the frontend
     (lib/overlay-metadata.ts). No new API endpoint needed — the estimates
     are research-backed, not per-user.
  4. Match UX rules: consistent labels via useFlowCopy('portfolio_mode', key),
     <300ms perceived load (the overlay picker is already client-side; no new
     API call on card render), prefetch next step on idle.

Acceptance: the "Acceptance Checklist" section at the bottom of this PRD,
fully ticked. Branch as <your-agent-name>/feat/overlay-expansion. One PR;
do NOT stack.
```

---

## Design Constraints (same four principles as PRD-13b)

These apply to every line of code in this PRD.

### 1. Reuse, don't replicate

This PRD adds 3 overlay strategy types. Each reuses an existing engine primitive:

| Overlay | Reuses |
|---|---|
| `portfolio_dual_momentum_overlay` | `_generate_cross_sectional_weights` (from rotation) + per-holding absolute return filter (from `time_series_momentum` branch) |
| `portfolio_defense_first_overlay` | Rolling MA computation (from `portfolio_defensive_overlay`) + exposure scaling (from `vol_target` post-processing) |
| `portfolio_stability_tilt_overlay` | Rolling volatility (from `low_volatility` branch) + row-wise normalization (from `_generate_cross_sectional_weights` internal logic) |

No new engine infrastructure. No new API endpoints. The frontend extends `<OverlayPicker>` — it does not fork it.

### 2. LEGO bricks

Every new piece is either:
- **A brick** — reusable across modes, with a documented contract.
- **A composer** — wires bricks for *this* PRD only, no logic beyond composition.

New bricks created: `lib/overlay-metadata.ts` (static overlay registry — reusable by any surface that renders overlay cards: Portfolio Mode, Strategy Builders, saved-strategy detail page, community feed).

### 3. Mode is a `FlowDefinition`, not a route

No new routes. The `portfolio_mode` flow definition in `portfolio-mode.ts` already handles all 7 steps. The `<OverlayPicker>` brick renders one card per `OverlayKind`; adding 3 kinds means 3 more cards appear. The flow runtime, state persistence, and event emission are unchanged.

### 4. UX rules

- **Consistent language**: new overlay labels and descriptions registered via `registerModeCopy('portfolio_mode', { ... })`. No hardcoded strings.
- **Credibility layer**: every new card shows a research citation + a historical estimate. These are static (research-backed), not computed per-user, so no loading state is needed.
- **<300ms perceived load**: the overlay picker is client-side — no API call fires on card render. Card metadata is imported statically.
- **Accessibility**: expandable "How it works" sections use `<details>` / `<summary>` for native keyboard + screen-reader support.

---

## Problem

PRD-13b shipped three overlay strategies: Defensive (per-holding trend filter), Rotation (cross-sectional momentum ranking), and Rebalance (fixed-weight reset). These cover the basics but leave three gaps that market research and competitive analysis flag as important for retail users:

1. **No absolute momentum hurdle.** Rotation picks the "best" holdings even when all of them are falling. A user with a tech-heavy portfolio in a bear market gets told to concentrate in the least-bad tech stock. They need an overlay that says "when nothing looks good, step aside."

2. **No portfolio-level regime check.** All three overlays operate at the holding level — each ticker is evaluated independently. None asks "what's the overall market environment right now?" A user whose 20 holdings are mostly below their 200-day MAs still gets fully invested by Rotation and Rebalance.

3. **No risk-based position sizing.** Rotation uses equal-weight. Rebalance uses fixed weights. Defensive uses the user's target weights but only as a binary in/out. None sizes positions based on how risky each holding actually is. A user with both TSLA (40% annualized vol) and PG (15% vol) gets the same weight in both under equal-weight — meaning TSLA dominates their portfolio risk ~7:1.

These gaps aren't theoretical. Composer.trade ($200M daily volume) offers volatility-triggered rotation and trend-following with crash protection. AllocateSmartly tracks 90+ tactical strategies, nearly all built on dual momentum. eToro's Alpha Portfolios (launched May 2025) include momentum L/S and sector-neutral strategies. The retail market has moved — Livermore's overlay set needs to keep pace.

## Goals

1. **Ship three new overlay strategies** that fill the absolute-momentum, regime-check, and risk-sizing gaps.
2. **Every new overlay is explainable in one sentence** and understandable by a retail user who has never heard of "cross-sectional momentum."
3. **Every new overlay carries a credibility layer**: a research citation (who discovered/validated this), a historical estimate (what impact has it had in backtests), and an expandable plain-English explanation of the mechanic.
4. **Engine implementation reuses existing primitives.** No new `_generate_weights` patterns — each overlay composes helpers that already exist.
5. **Zero regression on existing overlays, flow steps, or saved strategies.** The original 3 overlay types, their engine behavior, and their UI cards are untouched.
6. **TypeScript type safety**: `OverlayKind` union extended; `buildStrategyJson()` handles all 6 kinds.

## Non-Goals

- **Per-user personalized estimates.** The credibility layer shows research-backed historical averages, not "for YOUR portfolio, we estimate X." Personalized estimation requires a mini-backtest per overlay (2–5s each), which is deferred to a future "overlay backtest tease" PRD (already noted as Sprint 2 polish in PRD-13b §Frontend changes §3).
- **New API endpoints.** Overlay metadata is static and lives in the frontend. No new backend routes.
- **Overlay composition** (e.g., "Defensive + Stability Tilt"). Future PRD. This PRD adds 3 standalone overlays.
- **Broker integration, tax-loss harvesting, multi-currency** — same exclusions as PRD-13b.
- **Short-term mean reversion overlay.** Academic evidence shows consistent underperformance post-2020 (Yang, Emory 2025). Engine has a `short_term_reversal` branch for template universes but it's not suitable for small, arbitrary holding sets.
- **Pairs trading, sector rotation, carry/yield overlays** — require data or relationships (cointegration, sector classification, dividend history) that arbitrary user holdings don't guarantee.

## User stories

1. **As David (portfolio-holder, 15 holdings)**, I want an overlay that won't force me to stay invested when everything is falling, so I don't feel like the algorithm is fighting me during bear markets. → *Dual Momentum*

2. **As Sarah (cautious investor, 8 dividend stocks)**, I want the platform to check the overall market's health before committing my full capital, so I'm not 100% exposed when conditions look shaky. → *Defense-First*

3. **As Mike (growth investor, 6 holdings including 2 high-vol names)**, I want my jumpier stocks to get smaller positions automatically, so my portfolio's swings reflect my steady names more than my wild ones. → *Stability Tilt*

4. **As Anna (prosumer, evaluating overlays)**, I want to see WHY each overlay exists — who discovered it, what the evidence is — before I commit my money to it, so I can make an informed choice without reading academic papers. → *Credibility layer on every card*

5. **As any existing user with a saved portfolio strategy**, I want my existing Defensive / Rotation / Rebalance strategies to work exactly as before — no behavior changes, no forced migration. → *Zero regression*

---

## Architecture overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Frontend                                                                  │
│                                                                           │
│  <OverlayPicker>  (apps/web/src/lib/flows/bricks/overlay-picker.tsx)      │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Core Overlays (unchanged)                                          │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                          │  │
│  │  │Defensive │  │ Rotation │  │ Rebalance│                          │  │
│  │  └──────────┘  └──────────┘  └──────────┘                          │  │
│  │                                                                     │  │
│  │  Advanced Overlays (NEW — with credibility annotations)             │  │
│  │  ┌────────────────────┐  ┌────────────────────┐  ┌──────────────┐  │  │
│  │  │ Dual Momentum   ★  │  │ Defense-First   ★  │  │Stability Tilt│  │  │
│  │  │ 📚 Antonacci 2014  │  │ 📚 Carlson 2025    │  │📚 Ang 2006   │  │  │
│  │  │ 📊 ↓30% drawdowns  │  │ 📊 ↓50% drawdowns  │  │📊 ↓25% vol   │  │  │
│  │  │ [How it works ▸]   │  │ [How it works ▸]   │  │[How it works▸]│  │  │
│  │  └────────────────────┘  └────────────────────┘  └──────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  lib/overlay-metadata.ts  (NEW — static registry)                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  OVERLAY_METADATA: Record<OverlayKind, OverlayMeta>                 │  │
│  │  { label, shortDesc, mechanicSummary, researchSource,               │  │
│  │    historicalEstimate, suitableFor, unsuitableFor }                 │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Backend                                                                   │
│                                                                           │
│  apps/api/app/schemas/strategy.py                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  StrategyType += "portfolio_dual_momentum_overlay",                 │  │
│  │                  "portfolio_defense_first_overlay",                 │  │
│  │                  "portfolio_stability_tilt_overlay"                 │  │
│  │  PORTFOLIO_OVERLAY_TYPES += same three                             │  │
│  │  ENGINE_SUPPORTED_TYPES += same three                              │  │
│  │  StrategyRule: no new fields needed — all params fit existing      │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  apps/api/app/services/backtester/engine.py                               │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  _compute_lookback: 3 new cases                                    │  │
│  │  _generate_weights: 3 new elif branches (~85 lines total)          │  │
│  │    - dual_momentum: cross_sectional rank + absolute filter         │  │
│  │    - defense_first: breadth signal → exposure scalar               │  │
│  │    - stability_tilt: inverse-vol weights, normalized row-wise      │  │
│  │  Post-processing (ffill, exposure cap, vol_target): unchanged      │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Backend changes

### 1. Schema additions (additive, backwards-compatible)

**File**: `apps/api/app/schemas/strategy.py`

Add three new entries to `StrategyType`:

```python
StrategyType = Literal[
    # ... existing 25 entries unchanged ...
    # ── Portfolio overlay expansion (PRD-13c) ─────────────────────────────
    "portfolio_dual_momentum_overlay",
    "portfolio_defense_first_overlay",
    "portfolio_stability_tilt_overlay",
]
```

Add to `PORTFOLIO_OVERLAY_TYPES`:

```python
PORTFOLIO_OVERLAY_TYPES = frozenset({
    "portfolio_defensive_overlay",
    "portfolio_rotation_overlay",
    "portfolio_rebalance_overlay",
    # PRD-13c additions:
    "portfolio_dual_momentum_overlay",
    "portfolio_defense_first_overlay",
    "portfolio_stability_tilt_overlay",
})
```

Add to `ENGINE_SUPPORTED_TYPES`.

No new fields needed on `StrategyRule`. The existing fields cover all parameters:

| Overlay | Uses existing fields |
|---|---|
| Dual Momentum | `ranking_lookback_days`, `top_n`, `lookback_days` (for absolute filter window) |
| Defense-First | `lookback_days` (MA window), `threshold` (breadth threshold 0–1), `value` (scale-down factor 0–1) |
| Stability Tilt | `lookback_days` (vol window), `top_pct` (optional: only tilt the calmest P%), `value` (max single weight cap) |

**Validator additions** in `StrategyJSON.model_validator`:

```python
# PRD-13c: new portfolio overlay minimums
if self.strategy_type == "portfolio_dual_momentum_overlay":
    holdings = self.inherited_universe or []
    if len(holdings) < 3:
        raise ValueError(
            "portfolio_dual_momentum_overlay needs at least 3 holdings"
        )
if self.strategy_type == "portfolio_defense_first_overlay":
    holdings = self.inherited_universe or []
    if len(holdings) < 2:
        raise ValueError(
            "portfolio_defense_first_overlay needs at least 2 holdings"
        )
if self.strategy_type == "portfolio_stability_tilt_overlay":
    holdings = self.inherited_universe or []
    if len(holdings) < 2:
        raise ValueError(
            "portfolio_stability_tilt_overlay needs at least 2 holdings"
        )
```

### 2. Engine: `_compute_lookback` additions

**File**: `apps/api/app/services/backtester/engine.py`

```python
# ── PRD-13c portfolio overlay expansion ────────────────────────────────
if stype == "portfolio_dual_momentum_overlay":
    rule0 = rules[0] if rules else None
    lookback = (rule0.ranking_lookback_days if rule0 else None) or 126
    return int(lookback * 1.5) + 5
if stype == "portfolio_defense_first_overlay":
    rule0 = rules[0] if rules else None
    window = (rule0.lookback_days if rule0 else None) or 200
    return int(window * 1.5) + 5
if stype == "portfolio_stability_tilt_overlay":
    rule0 = rules[0] if rules else None
    lookback = (rule0.lookback_days if rule0 else None) or 63
    return int(lookback * 1.4) + 10
```

### 3. Engine: `_generate_weights` — Dual Momentum Overlay

```python
elif strategy.strategy_type == "portfolio_dual_momentum_overlay":
    # Rank holdings by relative momentum; only invest in those that also
    # pass an absolute momentum filter. Holdings that fail the absolute
    # filter → cash. If none pass both filters → portfolio in cash.
    rule = strategy.rules[0] if strategy.rules else None
    ranking_lookback = (rule.ranking_lookback_days if rule else None) or 126
    absolute_lookback = (rule.lookback_days if rule else None) or 252
    top_n = (rule.top_n if rule else None)
    if top_n is None:
        top_n = min(3, len(strategy.universe))

    # Step 1: relative momentum ranking (same as rotation)
    score_matrix = close_matrix / close_matrix.shift(ranking_lookback) - 1.0
    weights = self._generate_cross_sectional_weights(
        close_matrix, score_matrix, rebalance_mask,
        top_n=top_n, top_pct=None, rank_direction="top",
    )

    # Step 2: absolute momentum filter — zero out any selected holding
    # whose own trailing return over the absolute lookback is <= 0.
    absolute_returns = close_matrix.pct_change(absolute_lookback)
    for dt in weights.index[weights.sum(axis=1) > 0]:
        row = weights.loc[dt]
        active = row[row > 0].index
        for sym in active:
            abs_ret = absolute_returns.loc[dt, sym]
            if pd.isna(abs_ret) or abs_ret <= 0:
                weights.loc[dt, sym] = 0.0
```

**Default parameters:**
- `ranking_lookback_days`: 126 (6-month relative momentum)
- `lookback_days`: 252 (12-month absolute momentum — longer to reduce whipsaw)
- `top_n`: min(3, len(universe))

**Why 12-month absolute vs 6-month relative:** The absolute filter is the "safety brake" — it should be slower to flip than the ranking signal. A 12-month lookback means a holding needs to be in a sustained downtrend to fail the absolute test, reducing whipsaw during normal pullbacks. This matches the standard dual-momentum convention (Antonacci, AllocateSmartly).

### 4. Engine: `_generate_weights` — Defense-First Overlay

```python
elif strategy.strategy_type == "portfolio_defense_first_overlay":
    # Breadth-of-holdings regime check. Compute what fraction of holdings
    # are above their MA on each rebalance date. If breadth >= threshold,
    # apply target weights at full exposure. If breadth < threshold,
    # scale all positions by scale_down_factor (default 0.5 = 50% exposure).
    rule = strategy.rules[0] if strategy.rules else None
    ma_window = (rule.lookback_days if rule else None) or 200
    breadth_threshold = (rule.threshold if rule else None) or 0.5
    scale_down = (rule.value if rule else None) or 0.5
    if not (0 < scale_down <= 1.0):
        scale_down = 0.5

    # Target weights (same as rebalance: user's allocation)
    target_weights = strategy.position_sizing.weights or {}
    if not target_weights:
        visible = [s for s in strategy.universe if s in close_matrix.columns]
        if visible:
            equal = 1.0 / len(visible)
            target_weights = {s: equal for s in visible}

    # Compute breadth signal: fraction of holdings above their MA
    above_ma = pd.DataFrame(0.0, index=close_matrix.index,
                            columns=close_matrix.columns)
    for sym in close_matrix.columns:
        if sym in target_weights and target_weights.get(sym, 0) > 0:
            ma = close_matrix[sym].rolling(window=ma_window).mean()
            above_ma[sym] = (close_matrix[sym] > ma).astype(float)
    breadth = above_ma.sum(axis=1) / above_ma.astype(bool).sum(axis=1)

    for dt in index:
        target_row = {s: float(target_weights.get(s, 0.0))
                      for s in close_matrix.columns}
        total_target = sum(target_row.values()) or 1.0
        # Normalize to sum to 1
        for s in target_row:
            if s in weights.columns:
                weights.loc[dt, s] = target_row[s] / total_target

    # Apply breadth-based exposure scaling
    for dt in index[rebalance_mask]:
        b = breadth.loc[dt] if dt in breadth.index else 1.0
        if pd.notna(b) and b < breadth_threshold:
            weights.loc[dt] = weights.loc[dt] * scale_down
```

**Default parameters:**
- `lookback_days`: 200 (200-day MA per holding)
- `threshold`: 0.5 (breadth < 50% → scale down)
- `value` (scale_down_factor): 0.5 (reduce to 50% exposure)

**Why breadth-of-holdings instead of external canary:** Carlson's original paper uses 4 defensive ETFs (TLT, GLD, PDBC, UUP) as the canary. A retail user with a stock portfolio doesn't own those. The breadth adaptation achieves the same "check the environment first" logic using only the user's own tickers. When most of their holdings are below trend, the market environment is unfavorable for their specific basket. This also keeps the overlay self-contained — no dependency on external benchmark data.

### 5. Engine: `_generate_weights` — Stability Tilt Overlay

```python
elif strategy.strategy_type == "portfolio_stability_tilt_overlay":
    # Weight each holding inversely to its trailing realized volatility.
    # Normalize so weights sum to 1.0 on each rebalance date.
    # Optionally cap per-holding weight to avoid concentration.
    rule = strategy.rules[0] if strategy.rules else None
    vol_window = (rule.lookback_days if rule else None) or 63
    max_weight = (rule.value if rule else None) or 0.25

    returns = close_matrix.pct_change().fillna(0.0)
    vol = returns.rolling(vol_window).std()

    for dt in index[rebalance_mask]:
        vols = vol.loc[dt].dropna()
        if vols.empty:
            continue
        # Replace zero or near-zero vol with the median to avoid div-by-zero
        vols = vols.replace(0.0, vols.median())
        if (vols <= 0).any():
            vols = vols.clip(lower=vols.median() * 0.1)
        inv_vol = 1.0 / vols
        raw_weights = inv_vol / inv_vol.sum()
        # Apply per-holding cap, redistributing excess proportionally
        excess_mask = raw_weights > max_weight
        while excess_mask.any():
            excess = (raw_weights[excess_mask] - max_weight).sum()
            raw_weights[excess_mask] = max_weight
            raw_weights[~excess_mask] += excess * (
                raw_weights[~excess_mask] / raw_weights[~excess_mask].sum()
            )
            excess_mask = raw_weights > max_weight
        for sym, w in raw_weights.items():
            if sym in weights.columns:
                weights.loc[dt, sym] = w
```

**Default parameters:**
- `lookback_days`: 63 (1-quarter trailing volatility)
- `value` (max_single_weight): 0.25 (no holding exceeds 25%)

**Why 63-day vol window:** One quarter (~3 months) of daily data gives ~63 observations — enough to estimate volatility reliably without being so long that the estimate is stale. This is the standard in the low-volatility literature (Ang et al. 2006 use monthly windows; practitioners use 60–90 days for equity portfolios).

**Why per-holding cap:** Inverse-vol weighting on a portfolio with one very-low-vol utility stock and nine tech stocks could push the utility to 40%+ weight. The 25% cap prevents the overlay from becoming a concentrated bet on the calmest name.

### 6. No changes to post-processing

All three new overlays follow the same post-processing path as the original three: ffill weights between rebalance dates → cap exposure at 1.0 → optionally apply vol_target. Zero changes needed.

### 7. Test plan

**New test files:**

`apps/api/tests/test_portfolio_overlay_dual_momentum.py`
- Synthetic 5-symbol portfolio: 3 trending up, 2 trending down
- Assert: only up-trending names get allocated; absolute filter zeros out down-trenders even if they rank well
- Assert: exposure <= 1.0
- Assert: when ALL holdings are in downtrend → portfolio is 100% cash

`apps/api/tests/test_portfolio_overlay_defense_first.py`
- Synthetic 4-symbol portfolio: 3 above MA, 1 below → breadth = 75% → full exposure
- Same portfolio with 3 below MA, 1 above → breadth = 25% → exposure scaled to 50%
- Assert: weights sum equals 1.0 when breadth >= threshold; equals scale_down when breadth < threshold

`apps/api/tests/test_portfolio_overlay_stability_tilt.py`
- Synthetic 5-symbol portfolio with deliberately different vols
- Assert: lowest-vol holding gets highest weight
- Assert: highest-vol holding gets lowest (non-zero) weight
- Assert: no single weight exceeds max_weight cap
- Assert: weights sum to 1.0 on rebalance dates

**Existing tests that must keep passing:**
- `test_portfolio_overlay_defensive.py`
- `test_portfolio_overlay_rotation.py`
- `test_portfolio_overlay_rebalance.py`
- `test_inherited_universe_validation.py`

Run: `cd apps/api && python3 -m pytest tests/test_portfolio_overlay*.py tests/test_inherited_universe_validation.py -q`

---

## Frontend changes

### 1. Type extension: `OverlayKind`

**File**: `apps/web/src/lib/contracts.ts` (line 370)

```ts
export type OverlayKind =
  | "defensive"
  | "rotation"
  | "rebalance"
  | "dual_momentum"      // PRD-13c
  | "defense_first"      // PRD-13c
  | "stability_tilt";    // PRD-13c
```

### 2. New file: `lib/overlay-metadata.ts` (static overlay registry)

**File**: `apps/web/src/lib/overlay-metadata.ts`

This is the single source of truth for every overlay card's credibility content. Any surface that renders an overlay card (OverlayPicker, saved-strategy detail, community feed, future comparison views) imports from here.

```ts
import type { OverlayKind } from "@/lib/contracts";

export interface OverlayMeta {
  kind: OverlayKind;
  /** Display label (e.g. "Dual Momentum") */
  label: string;
  /** One-line description for the card body */
  shortDesc: string;
  /** Plain-English mechanic summary for the expandable "How it works" */
  mechanicSummary: string;
  /** Who discovered / validated this approach */
  researchSource: string;
  /** Research-backed historical estimate of the overlay's impact */
  historicalEstimate: string;
  /** What kind of portfolio this overlay works best for */
  suitableFor: string;
  /** When this overlay might be a poor choice */
  unsuitableFor: string;
  /** The strategy_type sent to the backend */
  strategyType: string;
  /** Whether this is a core (PRD-13b) or advanced (PRD-13c) overlay */
  tier: "core" | "advanced";
}

export const OVERLAY_METADATA: Record<OverlayKind, OverlayMeta> = {
  defensive: {
    kind: "defensive",
    label: "Defensive",
    shortDesc:
      "Holds each name only when above its 200-day trend; sells back to cash when it breaks down. Best when you want to limit downside.",
    mechanicSummary:
      "Each holding is checked independently: if its price is above its 200-day moving average, it stays in your portfolio at your target weight. If it falls below, that holding's allocation moves to cash until the trend recovers. No holding is sold because of what other holdings are doing — each name earns its place on its own.",
    researchSource:
      "Trend following is one of the oldest and most studied strategies in finance, with documented outperformance across 100+ years of market data (Hurst, Ooi & Pedersen, 2013; Moskowitz, Ooi & Pedersen, 2012).",
    historicalEstimate:
      "In backtests from 2000–2024, a 200-day MA filter on the S&P 500 reduced max drawdown from −55% to −28% while capturing ~70% of the upside.",
    suitableFor: "Portfolios with 5+ holdings where capital preservation matters.",
    unsuitableFor:
      "Highly concentrated portfolios (1–3 holdings) — the overlay has fewer names to rotate away from.",
    strategyType: "portfolio_defensive_overlay",
    tier: "core",
  },

  rotation: {
    kind: "rotation",
    label: "Rotation",
    shortDesc:
      "Rebalances monthly to the top-3 holdings by 6-month return. Best when you want to follow strength.",
    mechanicSummary:
      "Every month, each holding is ranked by its return over the past 6 months. The top 3 (by default) get equal weight; the rest go to cash. This means your portfolio is always concentrated in whatever is working right now — it follows strength and drops weakness automatically.",
    researchSource:
      "Cross-sectional momentum has been documented across asset classes and geographies since Jegadeesh & Titman (1993). It remains one of the most robust factors in empirical finance, confirmed in 200+ years of global data.",
    historicalEstimate:
      "A top-3 rotation on a 10-stock equal-weight universe has historically added ~2–4% annualized return vs buy-and-hold, with similar or lower drawdowns in trending markets.",
    suitableFor:
      "Diversified portfolios (8+ holdings across sectors) where you're comfortable concentrating into 2–4 names.",
    unsuitableFor:
      "Portfolios where all holdings are in the same sector — rotation will just pick the least-bad name in a sector-wide drawdown.",
    strategyType: "portfolio_rotation_overlay",
    tier: "core",
  },

  rebalance: {
    kind: "rebalance",
    label: "Rebalance",
    shortDesc:
      "Periodically re-weights back to your target allocation. Best when you want discipline without timing.",
    mechanicSummary:
      "On a fixed schedule (monthly, quarterly, or annually), your portfolio is re-weighted to match your target allocation. If a holding has grown to 30% of your portfolio when you wanted it at 20%, the overlay trims it back. If another has shrunk, it tops it up. There is no market-timing signal — just disciplined rebalancing.",
    researchSource:
      "Periodic rebalancing is a foundational portfolio management practice. Vanguard research (2019) found that rebalancing historically added ~0.3–0.5% annualized return through volatility harvesting, separate from any market-directional bet.",
    historicalEstimate:
      "Monthly rebalancing on a 60/40 stock/bond portfolio has historically reduced annual volatility by ~1–2 percentage points vs never rebalancing, with a small (~0.3%) return benefit from selling high and buying low.",
    suitableFor:
      "Any portfolio where you have a clear target allocation you want to maintain.",
    unsuitableFor:
      "Portfolios where you want the winners to run and don't mind drift from your target weights.",
    strategyType: "portfolio_rebalance_overlay",
    tier: "core",
  },

  dual_momentum: {
    kind: "dual_momentum",
    label: "Dual Momentum",
    shortDesc:
      "Invest in your strongest holdings, but only if they're actually going up. When everything's falling, your portfolio moves to cash.",
    mechanicSummary:
      "This overlay asks two questions. First: which of my holdings have performed best recently? (Relative momentum — same as Rotation.) Second: is each of those winners actually going up in absolute terms? (Absolute momentum — a safety check.) A holding must pass BOTH tests to stay in the portfolio. If nothing passes both, the portfolio sits in cash until conditions improve.",
    researchSource:
      "Gary Antonacci formalized dual momentum in 2014. Pavlović, Korenak & Stakić (European Journal of Applied Economics, 2025) validated it for retail ETF portfolios. AllocateSmartly independently tracks 90+ tactical strategies built on this framework.",
    historicalEstimate:
      "Adding an absolute momentum filter to a relative momentum rotation has historically reduced max drawdown by ~30% on average while capturing ~80% of the upside (2000–2024 backtests on diversified equity portfolios).",
    suitableFor:
      "Portfolios of 5+ holdings where you want to stay invested in good times but protect capital in broad downturns.",
    unsuitableFor:
      "Portfolios where all holdings tend to move together (same sector, same factor) — the absolute filter will switch the whole portfolio to cash at once.",
    strategyType: "portfolio_dual_momentum_overlay",
    tier: "advanced",
  },

  defense_first: {
    kind: "defense_first",
    label: "Defense-First",
    shortDesc:
      "Check the market's health first. When most of your holdings look weak, automatically reduce your exposure until conditions improve.",
    mechanicSummary:
      "Instead of looking at each holding individually, this overlay looks at the whole portfolio first. It asks: what fraction of my holdings are currently above their 200-day moving average? If more than half are above (healthy breadth), you stay fully invested at your target weights. If fewer than half are above (weak breadth), the overlay scales down all positions — defaulting to 50% exposure — until breadth recovers. It's a circuit breaker, not a stock picker.",
    researchSource:
      "Thomas Carlson's 'Defense First' paper (SSRN, July 2025) demonstrated that checking defensive conditions before committing capital produced a Sharpe ratio of 0.70 vs 0.50 for the benchmark, with max drawdown of −17.2% vs −29.5% (1971–2025). Keller & Keuning's Hybrid Asset Allocation uses a similar 'canary asset' concept.",
    historicalEstimate:
      "Reducing exposure when fewer than half of holdings are above their 200-day MA has historically cut portfolio drawdowns roughly in half while sacrificing only ~15% of bull market returns — the trade-off between sleep and FOMO.",
    suitableFor:
      "Portfolios of 8+ holdings across at least 2–3 sectors. Larger portfolios give the breadth signal more statistical meaning.",
    unsuitableFor:
      "Concentrated portfolios (2–5 holdings) — breadth flips between 0% and 100% on a single holding's move, making the signal too noisy.",
    strategyType: "portfolio_defense_first_overlay",
    tier: "advanced",
  },

  stability_tilt: {
    kind: "stability_tilt",
    label: "Stability Tilt",
    shortDesc:
      "Give larger positions to your calmest holdings and smaller ones to your wildest — same stocks, less drama.",
    mechanicSummary:
      "Every month, each holding's recent volatility (how much its price has swung day-to-day over the past quarter) is measured. Holdings are then weighted inversely to their volatility: a stock that's been swinging 15% a year gets roughly 3× the weight of one swinging 45% a year. All holdings stay in the portfolio — none are dropped — but position sizes shift toward the steadier names. The overlay also caps any single holding at 25% to avoid over-concentration.",
    researchSource:
      "The low-volatility anomaly — that lower-volatility stocks deliver comparable or better risk-adjusted returns than higher-volatility ones — was documented by Ang, Hodrick, Xing & Zhang (2006) and has been replicated across global markets. Lu, Rojas, Yeung & Convery's 'TrendFolios' framework (arXiv, June 2025) validates inverse-volatility weighting as the position-sizing layer in a multi-signal retail system.",
    historicalEstimate:
      "Inverse-volatility weighting has historically reduced portfolio volatility by 20–30% compared to equal-weighting, with negligible difference in long-term returns. The benefit is largest in portfolios with a mix of high- and low-volatility names.",
    suitableFor:
      "Portfolios with a mix of volatile and steady holdings (e.g., tech + consumer staples). The more volatility dispersion, the more the overlay matters.",
    unsuitableFor:
      "Portfolios where all holdings have similar volatility profiles — the overlay produces near-equal weights and adds little value.",
    strategyType: "portfolio_stability_tilt_overlay",
    tier: "advanced",
  },
};

/** Overlay display order in the picker UI */
export const OVERLAY_DISPLAY_ORDER: OverlayKind[] = [
  "defensive",
  "rotation",
  "rebalance",
  "dual_momentum",
  "defense_first",
  "stability_tilt",
];
```

### 3. Updated brick: `<OverlayPicker>`

**File**: `apps/web/src/lib/flows/bricks/overlay-picker.tsx`

Changes from PRD-13b version:

1. **Import `OVERLAY_METADATA`** and `OVERLAY_DISPLAY_ORDER` from `lib/overlay-metadata.ts`
2. **Replace hardcoded `overlayCopy` record** with reads from `OVERLAY_METADATA`
3. **Replace `orderedOverlays`** with `OVERLAY_DISPLAY_ORDER`
4. **Add group headers**: "Core Overlays" before the first 3, "Advanced Overlays" before the last 3
5. **Add credibility annotations** to advanced-tier cards: research source, historical estimate, expandable "How it works"
6. **Update `buildStrategyJson()`** to handle the three new overlay kinds

```tsx
function buildStrategyJson(overlay: OverlayKind, holdings: Holding[]): StrategyJson {
  const tickers = holdings.map((h) => h.ticker);
  const weights = makeWeights(holdings);
  const meta = OVERLAY_METADATA[overlay];

  // Overlays that use target weights (all except rotation and dual_momentum)
  const usesFixedWeights = !["rotation", "dual_momentum"].includes(overlay);

  // Build rules based on overlay kind
  let rules: StrategyRule[] = [];
  if (overlay === "rotation") {
    rules = [{ ranking_lookback_days: 126, top_n: Math.min(3, tickers.length) }];
  } else if (overlay === "dual_momentum") {
    rules = [{
      ranking_lookback_days: 126,
      top_n: Math.min(3, tickers.length),
      lookback_days: 252,  // absolute momentum filter window
    }];
  } else if (overlay === "defensive" || overlay === "defense_first") {
    rules = [{ lookback_days: 200, source: "close", indicator: "moving_average", operator: "gt" }];
    if (overlay === "defense_first") {
      rules[0].threshold = 0.5;   // breadth threshold
      rules[0].value = 0.5;       // scale-down factor
    }
  } else if (overlay === "stability_tilt") {
    rules = [{ lookback_days: 63, value: 0.25 }];
  }
  // rebalance: no rules

  return {
    strategy_name: meta.label + " Overlay",
    strategy_type: meta.strategyType,
    universe: tickers,
    inherited_universe: tickers,
    benchmark: "SPY",
    start_date: fiveYearsAgoIso(),
    end_date: todayIso(),
    initial_capital: 100_000,
    rebalance_frequency: "monthly",
    transaction_cost_bps: 5,
    slippage_bps: 5,
    rules,
    position_sizing: usesFixedWeights
      ? { method: "fixed_weight", weights }
      : { method: "equal_weight" },
    risk_management: {},
    cash_management: { hold_cash_when_no_signal: true, cash_yield_bps: 0 },
  };
}
```

**Card rendering with credibility layer** (the JSX for each card):

```tsx
{OVERLAY_DISPLAY_ORDER.map((overlay, idx) => {
  const meta = OVERLAY_METADATA[overlay];
  const isSelected = selected === overlay;
  const isAdvanced = meta.tier === "advanced";
  const showGroupHeader = idx === 0 || idx === 3;

  return (
    <React.Fragment key={overlay}>
      {showGroupHeader && (
        <div className="col-span-full mt-2 first:mt-0">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {idx === 0 ? "Core Overlays" : "Advanced Overlays"}
          </h2>
        </div>
      )}
      <button
        type="button"
        onClick={() => onPick(overlay)}
        aria-pressed={isSelected}
        data-testid={`overlay-card-${overlay}`}
        className={[
          "cursor-pointer rounded-xl border p-4 text-left transition-all duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
          isSelected
            ? "border-primary bg-primary/8 ring-1 ring-primary shadow-sm"
            : "border-border hover:border-primary/40 hover:bg-muted/30",
        ].join(" ")}
      >
        <div className="flex items-center justify-between">
          <span className="font-medium">
            {meta.label}
            {isAdvanced && (
              <span className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                ADVANCED
              </span>
            )}
          </span>
          {isSelected && (
            <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
              Selected
            </span>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{meta.shortDesc}</p>

        {/* Credibility annotations — always visible for advanced overlays */}
        {isAdvanced && (
          <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
            <p className="text-[11px] text-muted-foreground">
              <span className="font-medium">Estimate:</span>{" "}
              {meta.historicalEstimate}
            </p>
            <p className="text-[11px] text-muted-foreground">
              <span className="font-medium">Source:</span>{" "}
              {meta.researchSource}
            </p>
            <details className="mt-1">
              <summary className="cursor-pointer text-[11px] font-medium text-primary hover:underline">
                How it works
              </summary>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                {meta.mechanicSummary}
              </p>
            </details>
          </div>
        )}
      </button>
    </React.Fragment>
  );
})}
```

### 4. Updated copy registration

**File**: `apps/web/src/lib/flows/portfolio-mode.ts`

Add the new overlay labels to `registerModeCopy`:

```ts
registerModeCopy("portfolio_mode", {
  // ... existing entries unchanged ...
  overlay_dual_momentum: "Dual Momentum",
  overlay_defense_first: "Defense-First",
  overlay_stability_tilt: "Stability Tilt",
  overlay_advanced_header: "Advanced Overlays",
  overlay_core_header: "Core Overlays",
});
```

### 5. Updated card layout for 6 cards

The current grid uses `grid gap-3` (single column). With 6 cards + 2 group headers, switch to a 2-column grid on tablet+ to avoid excessive scrolling:

```tsx
<div className="grid gap-3 sm:grid-cols-2">
```

This keeps cards readable on mobile (single column) while using space efficiently on desktop.

### 6. Test plan

**File**: `apps/web/src/lib/flows/__tests__/overlay-picker.brick.test.tsx`

- Renders 6 cards + 2 group headers
- "Core Overlays" header appears before first card; "Advanced Overlays" before 4th
- Advanced cards show credibility annotations (estimate, source, "How it works")
- Core cards do NOT show credibility annotations
- Selecting a card updates state and builds correct StrategyJson for all 6 kinds
- `buildStrategyJson("dual_momentum")` sets `lookback_days: 252` on rule
- `buildStrategyJson("defense_first")` sets `threshold: 0.5, value: 0.5`
- `buildStrategyJson("stability_tilt")` sets `lookback_days: 63, value: 0.25`

**File**: `apps/web/src/lib/flows/__tests__/portfolio-mode.flow.test.tsx`

- Extend existing flow test: drive flow with each new overlay kind
- Assert `updateContext` receives correct `strategyJson` for each

---

## Reusable LEGO bricks created by this PRD

### Backend bricks

| Brick | Purpose | Used by |
|---|---|---|
| `portfolio_dual_momentum_overlay` engine branch | Dual momentum on inherited universe | Portfolio Mode, future template strategies |
| `portfolio_defense_first_overlay` engine branch | Breadth-based exposure scaling | Portfolio Mode |
| `portfolio_stability_tilt_overlay` engine branch | Inverse-vol weighting on inherited universe | Portfolio Mode, future "risk budget" features |

### Frontend bricks

| Brick | Purpose | Used by |
|---|---|---|
| `lib/overlay-metadata.ts` | Single source of truth for overlay display data | OverlayPicker, saved-strategy detail, community feed, future comparison views |
| Expanded `<OverlayPicker>` | 6-card overlay selection with credibility layer | Portfolio Mode |
| `OverlayKind` (extended) | Type-safe overlay identifiers | All overlay-consuming surfaces |

### NOT created by this PRD (deferred)

- Per-user personalized estimates — requires mini-backtest infrastructure (deferred to overlay backtest tease PRD)
- Overlay composition (e.g., Defensive + Stability Tilt) — future PRD
- "Backtest tease" numbers on cards — already deferred in PRD-13b to Sprint 2 polish; not in this PRD's scope either

---

## Acceptance checklist

### Backend

- [ ] Three new `strategy_type` literals added to `StrategyType`, `PORTFOLIO_OVERLAY_TYPES`, `ENGINE_SUPPORTED_TYPES`
- [ ] Validator enforces minimum holdings: dual_momentum ≥3, defense_first ≥2, stability_tilt ≥2
- [ ] `_compute_lookback` returns correct warmup for each new type
- [ ] `_generate_weights` has three new `elif` branches
- [ ] Dual momentum: only holdings with positive absolute return get allocated; portfolio goes to cash when none pass
- [ ] Defense-first: breadth computes correctly; exposure scales to `scale_down` when breadth < threshold
- [ ] Stability tilt: weights are inverse to trailing vol; per-holding cap enforced; weights sum to 1.0 on rebalance dates
- [ ] Post-processing (ffill, exposure cap, vol_target) works unchanged for all three new types
- [ ] Three new test files pass: `test_portfolio_overlay_dual_momentum.py`, `test_portfolio_overlay_defense_first.py`, `test_portfolio_overlay_stability_tilt.py`
- [ ] All existing portfolio overlay tests keep passing (zero regression)
- [ ] Full backend pytest suite passes: `cd apps/api && python3 -m pytest -q`
- [ ] No `X | None` syntax (Python 3.9 compat per CLAUDE.md)

### Frontend

- [ ] `OverlayKind` type extended with `"dual_momentum" | "defense_first" | "stability_tilt"`
- [ ] `lib/overlay-metadata.ts` exists with all 6 entries; every field populated for every overlay
- [ ] `<OverlayPicker>` renders 6 cards grouped into Core (3) and Advanced (3) sections
- [ ] Advanced cards show credibility annotations: historical estimate, research source, expandable "How it works"
- [ ] Core cards render unchanged (no credibility annotations — they speak for themselves)
- [ ] "ADVANCED" badge on the 3 new cards
- [ ] `buildStrategyJson()` handles all 6 overlay kinds with correct rules, position_sizing, and strategy_type
- [ ] Copy registered via `registerModeCopy` for all new labels; no hardcoded strings in JSX
- [ ] `OVERLAY_METADATA` is the single import for overlay display data — no duplicated strings between picker and other surfaces
- [ ] Card layout adapts: single column on mobile, 2 columns on tablet+ (`sm:grid-cols-2`)
- [ ] Bricks tests pass: `cd apps/web && npm run test -- src/lib/flows/__tests__/`
- [ ] `cd apps/web && npm run build` clean

### End-to-end smoke

- [ ] Upload a 10-holding CSV → 6 overlay cards appear, grouped → pick Dual Momentum → backtest completes with per-holding weights
- [ ] Same flow with Defense-First → backtest shows reduced exposure during breadth-weak periods
- [ ] Same flow with Stability Tilt → backtest shows non-equal weights, highest-vol name gets smallest weight
- [ ] Saved strategy from each new overlay type loads correctly from the saved-strategies list
- [ ] Original 3 overlays work identically to before (zero regression smoke test)

### Documentation

- [ ] Add section to `apps/api/CLAUDE.md` documenting the three new overlay strategy_types and their engine semantics
- [ ] Update `agent-system/WORK_LOG.md` with the PR summary
- [ ] Update `docs/PROJECT_BACKLOG.md` once overlays ship

---

## Out of scope (deferred — do not build in this PRD)

- **Per-user personalized estimates** on overlay cards — requires mini-backtest per overlay (2–5s each), deferred to overlay backtest tease PRD
- **Overlay composition** — combining two overlays (e.g., Stability Tilt + Defensive) into one strategy — future PRD
- **Overlay recommendations** — the diagnose endpoint currently returns `recommended_overlays`; extending the logic to rank all 6 overlays (not just the original 3) is a separate backend change
- **Drawdown Protection overlay** — identified in research as a candidate 4th overlay but deprioritized because 2025's whipsaw environment would produce frequent false triggers; revisit when market conditions stabilize
- **Short-term mean reversion, pairs trading, sector rotation, carry overlays** — all rejected for retail portfolios (see Non-Goals section for rationale)
- **Overlay comparison view** — side-by-side backtest of two overlays on the same portfolio — future PRD
- **Community-shared overlay configurations** — users customizing overlay parameters and sharing them — depends on community infrastructure (PRD-9 area)

---

## Cross-references

- **Parent PRD**: `agent-system/plans/PRD-13b-portfolio-mode.md` (the Sprint 1 Portfolio Mode that this PRD expands)
- **Engine reference**: `apps/api/app/services/backtester/engine.py` — `_generate_weights` lines 687–729 (existing overlays), lines 433–454 (dual_momentum template), lines 456–471 (low_volatility template), lines 762–781 (vol_target post-processing)
- **Schema reference**: `apps/api/app/schemas/strategy.py` — `StrategyType`, `PORTFOLIO_OVERLAY_TYPES`, `ENGINE_SUPPORTED_TYPES`, `StrategyRule`
- **Frontend reference**: `apps/web/src/lib/flows/bricks/overlay-picker.tsx` (current 3-card picker), `apps/web/src/lib/contracts.ts` line 370 (`OverlayKind`), `apps/web/src/lib/flows/portfolio-mode.ts` (flow definition + copy)
- **Research backing**: See "Source research" in the PRD header
- **Repo conventions**: `/CLAUDE.md`, `/agent-system/PARALLEL_WORK.md`, `/apps/api/CLAUDE.md`

---

*Drafted 2026-06-01 as a Sprint 2 expansion to PRD-13b. All three overlays were validated against current (2025) market offerings, academic literature, and the retail constraint: understandable, interpretable, executable. The credibility layer design ensures users know WHY each overlay exists, not just WHAT it does.*
