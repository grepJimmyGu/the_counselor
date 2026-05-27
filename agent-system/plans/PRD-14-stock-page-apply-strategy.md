# PRD-14: Stock Page "Apply a Strategy" CTA + Fingerprint Surface

**Status**: Ready to build (once Module 2 / PR #106 is confirmed on `main`)
**Phase**: Sprint 1
**Depends on**:
- **Module 2** (`PRD-12-asset-behavior-reconciliation.md`) — uses `getAssetBehavior(symbol)` helper + `<AssetBehaviorFingerprintCard>` component, both shipped in PR #97/#106.
- **NOT dependent on PRD-13a or PRD-13b.** The Apply CTA is just a Next.js `<Link>` to the existing strategy-builder route with the ticker pre-loaded. Sprint 2 will refactor Mode 1 to use `startFlow('one_asset_mode', …)` and this CTA will be updated then.

**Blocks**: nothing.

**Effort**: ~1 day, single owner (frontend)
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/livermore_product_flow_v2.html`](../../Quant%20Strategy/framework/livermore_product_flow_v2.html) — §5 Surface 2 "Stock detail page", §2 Mode 1 secondary trigger

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/web). Read CLAUDE.md first
(auto-loaded). Then read agent-system/plans/HANDOFF-livermore-product-flow-v2.md.

Goal: add the Mode 1 secondary trigger to every stock detail page
(/stocks/[ticker]). Two visible changes:

  1. Below the existing stock-page sections, render the existing
     <AssetBehaviorFingerprintCard symbol={ticker} /> from Module 2.
  2. Add a prominent "⚡ Apply a strategy" CTA button next to the
     ticker header (or below the fingerprint card — pick whichever
     reads better given the existing layout). Clicking the button
     navigates to /strategies/new?ticker=<ticker>&from=stock_page
     (existing route in the strategy-builder modal — pre-loads ticker).

PREREQUISITES (must be on main):
  - Module 2 / PR #106: ab255e5 must be on main. Verify with:
      ls apps/api/app/services/asset_behavior_service.py
      ls apps/web/src/components/strategy-picker/AssetBehaviorFingerprintCard.tsx
    If either is missing, STOP — see PRD-12-asset-behavior-reconciliation.md
    §"open administrative item" before proceeding.

OUT OF SCOPE for this PRD:
  - Mode 1 refactor to FlowDefinition (Sprint 2). The Apply CTA is just
    a <Link> for now.
  - New backend endpoints. Module 2's endpoint is reused as-is.
  - Behavior card redesign. <AssetBehaviorFingerprintCard> is used as-is.
  - Mobile-specific layout. Use existing responsive breakpoints.

Context to read in order:
  - /Quant Strategy/framework/livermore_product_flow_v2.html §5 Surface 2
  - agent-system/plans/PRD-12-asset-behavior-reconciliation.md (what
    Module 2 ships — your only dependency)
  - apps/web/src/app/stocks/[ticker]/page.tsx (the existing stock page)

Architecture rules for this PRD (the four principles, see HANDOFF §2):
  1. Reuse the existing <AssetBehaviorFingerprintCard> as-is. Don't fork it.
  2. The "Apply a strategy" CTA is a brick (<ApplyStrategyCTA>) so the
     same component can be reused on other surfaces (commodity page,
     screener result rows, etc.).
  3. No flow runtime usage. CTA is a <Link>; Sprint 2 refactors to
     startFlow('one_asset_mode', …).
  4. Match UX rules: SSR-fetch the fingerprint (already supported by the
     card), so the page renders fully on first paint — no skeleton needed.

Acceptance: see "Acceptance Checklist" at the bottom. Branch as
`<your-agent-name>/feat/stock-page-apply-cta`. Open one PR; base=main.
```

---

## Design Constraints (the four principles)

### 1. Reuse, don't replicate

Module 2 ships `<AssetBehaviorFingerprintCard symbol={ticker} />` as a self-fetching component. Use it directly. Do not fork it. Do not re-style it. If layout changes are needed, do them via wrapper CSS, not by copying the component.

Module 2 also ships `getAssetBehavior(symbol)` for SSR/server-component fetches. Use it on the stock page to pre-fetch the fingerprint and pass to the card as `fingerprint={preFetched}` — that avoids a client-side flash.

### 2. LEGO bricks

The new `<ApplyStrategyCTA ticker={ticker} from={"stock_page"} />` is a reusable button component. It will be reused on:

- The commodity page (`/commodities/[symbol]`)
- Screener result rows (future PRD)
- Watchlist items (future PRD)
- Per-holding rows in portfolio diagnosis (PRD-13b's `<PortfolioDiagnosis>` will use it)

Put it under `lib/flows/bricks/apply-strategy-cta.tsx` so future modes can pick it off the shelf.

### 3. Mode = FlowDefinition (deferred to Sprint 2)

This PRD does NOT define `one_asset_mode` as a `FlowDefinition`. The CTA navigates via `<Link>` to the existing strategy-builder modal route. When Sprint 2's PRD refactors Mode 1 to a `FlowDefinition`, this CTA's `<Link>` will be replaced with `startFlow('one_asset_mode', { initialContext: { fromTrigger: 'stock_page/apply_strategy', ticker } })` — a one-line change.

### 4. UX rules

- **SSR-pre-fetch** the fingerprint on the stock page (the page is a Server Component anyway). No client-side loading state needed — the card renders fully populated on first paint.
- **Centralized labels** via `useFlowCopy('apply_cta', 'button_label')`. Lexicon registered in the brick.
- **Optimistic state** for the CTA on click: navigate immediately, don't wait for confirmation.

---

## Problem

Today, when a user lands on a stock detail page (e.g., `/stocks/NVDA`), the page shows business model, sentiment, fundamentals, and evaluation sections — but there's no path to "apply a strategy to this ticker." The user has to:

1. Navigate away to `/builders` or `/strategies/new`
2. Re-enter the ticker
3. Pick a template

This is friction for the most common retail starting state ("I want to trade NVDA"). The v2 product flow §2 Mode 1 calls for a secondary trigger on every stock detail page: a single "Apply a strategy" button that pre-loads the ticker and routes into the strategy picker.

Module 2 also already ships the Asset Behavior Fingerprint card but it's not yet placed on the stock page. Placing it there closes the "is this template appropriate for this asset?" loop right at the moment the user is deciding.

## Goals

1. **`<AssetBehaviorFingerprintCard symbol={ticker} />` rendered** on `/stocks/[ticker]` between the existing sections and the footer.
2. **"⚡ Apply a strategy" CTA button** placed prominently on the stock page (next to the ticker header — see UI mockup in source spec).
3. **CTA click** → navigates to existing strategy-builder route with ticker pre-loaded + `from=stock_page` analytics param.
4. **PostHog event** on CTA click: `stock_page_apply_strategy_clicked`.
5. **SSR pre-fetch** so no client-side skeleton needed.
6. **No regression** on existing stock-page sections.

## Non-Goals

- No backend changes. Module 2's endpoint and existing strategy-builder route handle everything.
- No `<AssetBehaviorFingerprintCard>` design changes. Use as-is.
- No Mode 1 refactor to `FlowDefinition`. CTA is a `<Link>`; Sprint 2 refactor will swap to `startFlow`.
- No commodity-page changes in this PRD. A follow-up PRD applies the same pattern to `/commodities/[symbol]` (and other surfaces) using the same `<ApplyStrategyCTA>` brick.
- No mobile redesign. Existing responsive breakpoints carry through.

## User stories

1. **As a user who landed on `/stocks/NVDA`** (via Market Pulse or search), I want to see "Apply a strategy" within the first viewport so I can go from "looking at NVDA" to "building a strategy for NVDA" without context switching.
2. **As a user comparing two stocks**, I want to see each one's behavior fingerprint (trending pct, vol, drawdown) on the stock page so I can compare them side-by-side via two tabs.
3. **As any user**, I want the fingerprint to load without a flash — the stock page renders all at once on first paint.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│  /stocks/[ticker]/page.tsx (Server Component)                          │
│                                                                        │
│  Existing nav + breadcrumbs                                            │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  Ticker header (existing)                                       │    │
│  │  NVDA · NVIDIA Corp · $485 · +1.2%       ┌────────────────────┐│    │
│  │                                            │ ⚡ Apply a strategy ││    │
│  │                                            └────────────────────┘│    │
│  └─────────────────────────────────────────────────────────┬──────┘    │
│                                                            │ ← NEW CTA  │
│                                                            │            │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  Existing sections:                                            │    │
│  │   - Evaluation dashboard                                       │    │
│  │   - Business model                                             │    │
│  │   - Market position                                            │    │
│  │   - Sentiment tab                                              │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  <AssetBehaviorFingerprintCard symbol={ticker}                │    │
│  │                                fingerprint={preFetched} />    │    │ ← NEW
│  │  (Module 2 component — used as-is)                            │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  Existing footer                                                       │
└────────────────────────────────────────────────────────────────────────┘

CTA navigation:
  router.push(`/strategies/new?ticker=${ticker}&from=stock_page`)
  // Sprint 2: replace with startFlow('one_asset_mode', …)
```

---

## Backend changes

**None.**

This PRD reuses:
- Module 2's `GET /api/assets/{symbol}/behavior` endpoint (already shipped)
- The existing `/strategies/new?ticker=…` route on the strategy builder (already accepts a `ticker` query param to pre-load)

If the existing strategy-builder route does NOT accept `?ticker=…` as a pre-load query param, the PRD adds it (1-line change in `apps/web/src/app/strategies/new/page.tsx` or equivalent). Check first — likely already supported.

---

## Frontend changes

### 1. New brick: `<ApplyStrategyCTA>`

`apps/web/src/lib/flows/bricks/apply-strategy-cta.tsx`

```tsx
"use client";

import Link from "next/link";
import { useFlowCopy, registerModeCopy } from "@/lib/flows/copy";
import { Button } from "@/components/ui/button";

registerModeCopy("apply_cta", {
  button_label: "⚡ Apply a strategy →",
  button_label_short: "Apply strategy",  // for tight layouts
});

interface Props {
  ticker: string;
  from: string;                    // e.g. "stock_page", "commodity_page", "screener_row"
  variant?: "primary" | "secondary";
  compact?: boolean;
  onClick?: () => void;            // optional analytics hook
}

export function ApplyStrategyCTA({
  ticker, from, variant = "primary", compact = false, onClick,
}: Props) {
  const label = useFlowCopy("apply_cta", compact ? "button_label_short" : "button_label");
  const href = `/strategies/new?ticker=${encodeURIComponent(ticker)}&from=${from}`;

  return (
    <Link href={href} onClick={onClick}>
      <Button variant={variant === "primary" ? "default" : "outline"}>
        {label}
      </Button>
    </Link>
  );
}
```

The brick is intentionally small. Sprint 2 will swap the `<Link>` for a `startFlow('one_asset_mode', …)` call without changing the component's interface.

### 2. Stock page surgery

`apps/web/src/app/stocks/[ticker]/page.tsx`

This file is a Server Component. Two changes:

```tsx
// existing imports + …
import { AssetBehaviorFingerprintCard } from "@/components/strategy-picker/AssetBehaviorFingerprintCard";
import { getAssetBehavior } from "@/lib/api";
import { ApplyStrategyCTA } from "@/lib/flows/bricks/apply-strategy-cta";

export default async function StockPage({ params }: { params: { ticker: string } }) {
  const ticker = params.ticker.toUpperCase();

  // SSR pre-fetch the fingerprint so the card renders fully on first paint.
  // If the fetch fails (unknown ticker, transient backend error), pass `null`
  // and the card renders its insufficient-data state.
  let fingerprint = null;
  try {
    fingerprint = await getAssetBehavior(ticker);
  } catch (err) {
    // Don't fail the whole page over a fingerprint error.
    console.warn(`stock-page: fingerprint fetch failed for ${ticker}`, err);
  }

  return (
    <main>
      <Nav />                                              {/* existing */}

      <header className="ticker-header">
        <div>
          <h1>{ticker} · {/* company name + price (existing) */}</h1>
        </div>
        <ApplyStrategyCTA ticker={ticker} from="stock_page" />   {/* NEW */}
      </header>

      <EvaluationDashboard ticker={ticker} />              {/* existing */}
      <BusinessModelSection ticker={ticker} />             {/* existing */}
      <MarketPositionSection ticker={ticker} />            {/* existing */}
      <SentimentTab ticker={ticker} />                     {/* existing */}

      <AssetBehaviorFingerprintCard                        {/* NEW */}
        symbol={ticker}
        fingerprint={fingerprint}
      />

      <Footer />                                           {/* existing */}
    </main>
  );
}
```

Notes:
- The CTA button is placed **inside the ticker header**, right of the company name and price. If existing layout doesn't have room, place it just below the header (still above-fold).
- The behavior card is placed **at the bottom of the existing sections**, above the footer. This keeps existing content order intact.
- The `try/catch` around `getAssetBehavior` ensures a fingerprint API failure doesn't 500 the whole page.

### 3. PostHog wiring

```tsx
// In ApplyStrategyCTA, when used on the stock page:
<ApplyStrategyCTA
  ticker={ticker}
  from="stock_page"
  onClick={() => posthog.capture('stock_page_apply_strategy_clicked', { ticker })}
/>
```

The brick takes an optional `onClick` so the analytics call lives at the use-site (not inside the brick). Future consumers (commodity page, screener row) pass their own events.

### 4. Test plan

`apps/web/src/lib/flows/bricks/__tests__/`

- `apply-strategy-cta.test.tsx` — renders the link with correct `href`; clicking calls `onClick` if provided; respects `compact` and `variant` props.

`apps/web/src/app/stocks/[ticker]/__tests__/`

- `stock-page-fingerprint.test.tsx` — render the page with mocked `getAssetBehavior`; assert the fingerprint card is present; CTA renders with `?ticker=NVDA&from=stock_page` href.
- `stock-page-fingerprint-failure.test.tsx` — when `getAssetBehavior` throws, page still renders (fingerprint card receives `null` and shows insufficient-data state).

E2E (Playwright):

- `e2e/stock-page-apply-cta.spec.ts` — visit `/stocks/NVDA`, see "Apply a strategy" button, click it, assert URL is `/strategies/new?ticker=NVDA&from=stock_page`.

---

## Reusable LEGO bricks created by this PRD

### Frontend bricks

| Brick | Location | Used by |
|---|---|---|
| `<ApplyStrategyCTA>` | `lib/flows/bricks/apply-strategy-cta.tsx` | Stock page (this PRD); future commodity page; screener rows; per-holding rows in PRD-13b's diagnosis view |
| `apply_cta` copy lexicon | `lib/flows/copy.ts` registered on module load | Same as above |

### Backend bricks

**None added by this PRD.** Consumes Module 2's endpoint + the existing strategy-builder route.

---

## Acceptance checklist

A PR is accepted when **all of the following are true**.

### Prerequisites

- [ ] Module 2 (PR #97/#106) confirmed on `main`: `ls apps/api/app/services/asset_behavior_service.py` succeeds.
- [ ] Module 2 frontend confirmed: `ls apps/web/src/components/strategy-picker/AssetBehaviorFingerprintCard.tsx` succeeds.

### Code

- [ ] `apps/web/src/lib/flows/bricks/apply-strategy-cta.tsx` exists; uses `useFlowCopy('apply_cta', key)`; exports `ApplyStrategyCTA` with the props in §1.
- [ ] `apps/web/src/app/stocks/[ticker]/page.tsx` updated:
  - SSR pre-fetches `getAssetBehavior(ticker)` inside a try/catch.
  - `<ApplyStrategyCTA ticker={ticker} from="stock_page" onClick={…} />` rendered in the ticker header (or just below if layout requires).
  - `<AssetBehaviorFingerprintCard symbol={ticker} fingerprint={preFetched} />` rendered after existing sections, before footer.
- [ ] No `<AssetBehaviorFingerprintCard>` modifications — used as-is from Module 2.
- [ ] No new backend endpoints. If `/strategies/new?ticker=…` doesn't already accept `ticker` query param, add it (1-line change).

### Behavior

- [ ] On `/stocks/NVDA`, the CTA button is visible above the fold.
- [ ] Clicking CTA navigates to `/strategies/new?ticker=NVDA&from=stock_page`.
- [ ] The strategy-builder modal opens with NVDA pre-loaded.
- [ ] Fingerprint card renders fully on first paint (no client-side skeleton flash).
- [ ] If `getAssetBehavior(ticker)` fails (e.g., unknown ticker), the page still renders; the card shows its insufficient-data state.
- [ ] No regression on existing stock-page sections (evaluation, business model, market position, sentiment).

### Tests

- [ ] 3 unit/component tests pass: apply-strategy-cta, stock-page-fingerprint, stock-page-fingerprint-failure.
- [ ] 1 Playwright E2E test passes: stock-page-apply-cta navigation.
- [ ] `cd apps/web && npm run build` clean.
- [ ] `cd apps/web && npm run test` green.

### Telemetry

- [ ] PostHog event `stock_page_apply_strategy_clicked` fires on CTA click with `ticker` property.

### Documentation

- [ ] Update HANDOFF §6 Brick inventory: mark `<ApplyStrategyCTA>` as ✅.
- [ ] PR title: `feat(stocks): apply-strategy CTA + behavior card (PRD-14)`.

---

## Out of scope (do not build in this PRD)

- Mode 1 refactor to use `FlowDefinition`. Sprint 2 will swap the `<Link>` in `<ApplyStrategyCTA>` for `startFlow('one_asset_mode', …)`.
- Applying this pattern to `/commodities/[symbol]`. Follow-up PRD; uses the same `<ApplyStrategyCTA>` brick.
- Applying this pattern to screener result rows. Follow-up PRD.
- Behavior card design tweaks. Use Module 2's component as-is.
- Mobile-specific layout polish.
- Per-section deep-link anchors (`#evaluation`, `#sentiment`, etc.). Separate PRD.
- Personalized CTA copy variants (e.g., "Apply YOUR favorite strategy"). Separate experimentation PRD.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §5 Surface 2 "Stock detail page"
- Master handoff: `agent-system/plans/HANDOFF-livermore-product-flow-v2.md`
- Hard dep: `PRD-12-asset-behavior-reconciliation.md` (Module 2 = the only dependency)
- Related (not consumed): `PRD-13b-portfolio-mode.md` (per-holding rows in its diagnosis view will reuse `<ApplyStrategyCTA>`)
- Repo conventions: `CLAUDE.md` (auto-loaded), `agent-system/PARALLEL_WORK.md`

---

*Drafted 2026-05-26. PRD-14 is the smallest Sprint 1 PRD (~1 day). Its only dependency is Module 2 being on `main`. The `<ApplyStrategyCTA>` brick it creates is intentionally minimal so it can be reused across surfaces in Sprint 2+.*
