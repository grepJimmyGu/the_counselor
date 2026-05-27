# PRD-11: Home Page Entry Picker

**Status**: Ready to build (once PRD-13a is on `main`)
**Phase**: Sprint 1
**Depends on**:
- **PRD-13a** (flow runtime) — for the future `startFlow('portfolio_mode', …)` call from the Upload Portfolio CTA. Hard dependency: this PRD cannot ship its Upload Portfolio CTA without the runtime existing.
- **NOT dependent on PRD-13b**. PRD-11 wires the Upload CTA optimistically; if `portfolio_mode` isn't yet registered (PRD-13b hasn't landed), the runtime gracefully shows a "coming soon" state (`getFlow('portfolio_mode')` returns undefined).
- **NOT dependent on Module 2** (PR #97/#106). PRD-11 doesn't render the asset fingerprint inline — it routes users into the existing search/picker flows that already render the fingerprint themselves.

**Blocks**: nothing immediately downstream in Sprint 1. Sprint 2's Mode 3 (Thesis) chat CTA wiring will modify this same Home page.

**Effort**: ~3 days, single owner (frontend)
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/livermore_product_flow_v2.html`](../../Quant%20Strategy/framework/livermore_product_flow_v2.html) — §4 Surface 1 "Home page", §5 Surface 1 (mockup)

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/web). Read CLAUDE.md first
(auto-loaded). Then read agent-system/plans/HANDOFF-livermore-product-flow-v2.md.

Goal: Replace the existing "Describe Your Strategy, We Handle the Rest"
section on the Home page with a 3-CTA entry-mode picker:

  1. "Pick an asset"    → routes to existing ticker search (Mode 1)
  2. "Upload portfolio" → startFlow('portfolio_mode')      (Mode 2)
  3. "Chat builder"     → opens existing chat widget       (Mode 3 / 5)

Plus: above the picker, for signed-in users, an "Your saved strategies"
tile that lists up to 3 most-recent saved strategies with their current
signal status. Anonymous users see a "Sign in to access your strategies"
prompt instead.

PREREQUISITES (must be on main before starting):
  - PRD-13a: lib/flows/ runtime infrastructure (types, runtime, registry,
    copy). The Upload Portfolio CTA calls startFlow() from this runtime.

OUT OF SCOPE for this PRD:
  - Mode 1 ("Pick an asset") refactor to use the FlowDefinition. For Sprint 1,
    this button routes to the existing ticker search / strategy picker via
    a Next.js <Link>. Sprint 2 will refactor Mode 1 to use startFlow.
  - Chat builder UI changes — uses the existing chat widget; this PRD just
    opens it.
  - PRD-13b's "Upload portfolio" handler. This PRD wires the button to
    startFlow('portfolio_mode', …) optimistically. If portfolio_mode isn't
    yet registered (PRD-13b not merged), the runtime shows a "Coming soon"
    state. When PRD-13b lands, the button starts working automatically.

Context to read in order:
  - /Quant Strategy/framework/livermore_product_flow_v2.html §5 Surface 1
  - agent-system/plans/HANDOFF-livermore-product-flow-v2.md (sprint plan)
  - agent-system/plans/PRD-13a-flow-runtime-infra.md (the runtime you use)
  - apps/web/src/app/page.tsx (the existing Home page)

Architecture rules for this PRD (the four principles, see HANDOFF §2):
  1. Reuse existing Home page chrome. Replace only the "Describe Your
     Strategy" section, not the whole page.
  2. Build the EntryModePicker as a brick under lib/flows/bricks/ so it
     can be reused for re-engagement modals later.
  3. The Upload Portfolio CTA calls startFlow() — no inline flow logic.
  4. Match UX rules: consistent labels via useFlowCopy('home_picker', key),
     <300ms perceived load (skeleton for saved-strategies tile if signed in),
     optimistic CTA states for unknown-flow case ("Coming soon" overlay).

Acceptance: see "Acceptance Checklist" at the bottom. Branch as
`<your-agent-name>/feat/home-entry-picker`. Open one PR; base=main.
```

---

## Design Constraints (the four principles)

### 1. Reuse, don't replicate

The Home page (`apps/web/src/app/page.tsx`) has existing chrome — nav, hero, market pulse teaser, ticker bar, footer. This PRD replaces **only one section** ("Describe Your Strategy, We Handle the Rest") with the new entry picker. Don't touch anything else.

For the saved-strategies tile (signed-in users), reuse the existing `getSavedStrategies()` / `listUserStrategies()` endpoint from `apps/web/src/lib/api.ts`. No new backend.

For the Chat builder CTA: reuse the existing `ChatWidget` component (`apps/web/src/components/ChatWidget.tsx`) — this PRD just provides an entry point that opens it.

### 2. LEGO bricks

This PRD creates two reusable bricks:

- **`<EntryModePicker>`** — the 3-CTA grid. Reusable in re-engagement modals (e.g., when a user abandons a flow halfway). Lives under `lib/flows/bricks/entry-mode-picker.tsx`.
- **`<SavedStrategiesTile>`** — compact list of N most-recent saved strategies with signal status. Reusable in `My Strategies`-style surfaces later.

The CTAs themselves are pure composers — no business logic beyond routing.

### 3. Mode = FlowDefinition

This PRD does NOT define a new flow. It triggers existing flows:

- Upload Portfolio → `startFlow('portfolio_mode', { initialContext: { fromTrigger: 'home/upload_portfolio' } })` (flow registered by PRD-13b)
- Pick an Asset → `<Link href="/strategies/new?from=home/pick_asset">` (Sprint-1 placeholder; Sprint 2 refactors to `startFlow('one_asset_mode', …)`)
- Chat Builder → opens the `ChatWidget` (no flow runtime; existing surface)

### 4. UX rules

- **Centralized labels**: `useFlowCopy('home_picker', 'cta_asset')`, `useFlowCopy('home_picker', 'cta_portfolio')`, `useFlowCopy('home_picker', 'cta_chat')`. The lexicon is loaded via `registerModeCopy('home_picker', { … })` in `entry-mode-picker.tsx`.
- **Sub-300ms perceived load**: the saved-strategies tile shows a skeleton (3 placeholder rows) while loading. If load > 800ms, show a "Still loading…" caption to confirm the page hasn't stalled.
- **Optimistic state for unknown flows**: if `startFlow('portfolio_mode', …)` is called but `portfolio_mode` isn't registered (PRD-13b not merged), the runtime catches the error and shows a "Coming soon" overlay rather than crashing. The CTA button stays clickable; the failure is graceful.
- **Anonymous fallback**: signed-out users see "Sign in to access your strategies" in place of the saved-strategies tile.

---

## Problem

The Home page currently has a section titled "Describe Your Strategy, We Handle the Rest" that funnels every user into the same chat-builder path. This works for users who already have an investment thesis or trading idea — but is friction for the two largest retail user states identified in the v2 product flow:

- **"I have one asset"** — the user knows their ticker; the chat builder asks them to describe a strategy they don't yet have.
- **"I have a portfolio"** — the user has existing holdings; the chat builder doesn't accept holdings as input.

The v2 product flow (§4 Navigation IA) calls for the Home page to be a contextual entry-mode picker: three CTAs that route the user into the flow that matches what they brought. The chat builder remains one of the three options — for users with a thesis or idea — not the default for everyone.

## Goals

1. **Three CTAs replace the existing "Describe Your Strategy" block**: Pick an asset · Upload portfolio · Chat builder.
2. **The Upload Portfolio CTA is wired to `startFlow('portfolio_mode')`** — uses the PRD-13a runtime; graceful "coming soon" if PRD-13b hasn't registered the flow.
3. **The Pick-an-Asset CTA routes to existing ticker search** via `<Link>` (Sprint 1 placeholder).
4. **The Chat builder CTA opens the existing chat widget** (no behavior change).
5. **Above the picker, signed-in users see their saved strategies tile** (up to 3 most-recent, with current signal status).
6. **No regression**: existing Home page sections (nav, market pulse, ticker bar, footer) unchanged.

## Non-Goals

- No new chat UI. The Chat builder CTA opens the existing `ChatWidget`.
- No backend changes. All Home page enhancements compose existing endpoints.
- No Mode 1 refactor to `FlowDefinition`. Sprint 2's Mode 1 refactor will replace the `<Link>` placeholder with `startFlow('one_asset_mode', …)`.
- No Discovery / Market Pulse changes. Those live in their own tabs.
- No A/B testing infrastructure for the picker copy. Add PostHog events but don't gate on flags in this PRD.

## User stories

1. **As a new visitor with one stock in mind**, I want to click "Pick an asset" and type my ticker, so I get to a strategy picker without writing a description.
2. **As a portfolio-holder**, I want to click "Upload portfolio" and drop a CSV, so I get a portfolio diagnosis and overlay recommendation.
3. **As a thesis-driven user**, I want to click "Chat builder" and type my thesis, so the LLM parses it into a strategy.
4. **As a returning user with saved strategies**, I want to see my saves above the entry picker so I can jump straight to monitoring without re-picking an entry mode.
5. **As an anonymous user**, I want a clear sign-in prompt where saved strategies would be, so I know what I'm missing.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│ Home page (apps/web/src/app/page.tsx)                                  │
│                                                                        │
│  Existing nav (Home / Market Pulse / Community / Strategy Builders)    │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  Hero (existing — unchanged)                                   │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  [SIGNED-IN ONLY] <SavedStrategiesTile />                     │    │
│  │  Top 3 saved strategies with signal status.                    │    │
│  │  Skeleton while loading. "Sign in" prompt for anonymous.       │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  <EntryModePicker />     ← REPLACES "Describe Your Strategy"   │    │
│  │                                                                │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │    │
│  │  │ Pick an  │  │ Upload   │  │ Chat     │                      │    │
│  │  │ asset    │  │ portfolio│  │ builder  │                      │    │
│  │  │ → Link   │  │ → Flow   │  │ → Widget │                      │    │
│  │  └──────────┘  └──────────┘  └──────────┘                      │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  Existing market pulse teaser, ticker bar, footer (unchanged)          │
└────────────────────────────────────────────────────────────────────────┘

CTA click handlers:
  Pick an asset       → router.push('/strategies/new?from=home/pick_asset')
  Upload portfolio    → startFlow('portfolio_mode', { initialContext:
                          { fromTrigger: 'home/upload_portfolio' } })
                        // if portfolio_mode not registered, runtime
                        // shows "Coming soon" overlay
  Chat builder        → openChatWidget({ source: 'home/chat_builder' })
```

---

## Backend changes

**None.** This PRD is frontend-only.

The saved-strategies tile composes the existing `GET /api/saved-strategies` endpoint (from PR #82 et al.). The Pick-an-Asset CTA routes to an existing page. The Upload Portfolio CTA calls the PRD-13a runtime. The Chat builder CTA opens an existing component.

If during implementation the existing `GET /api/saved-strategies` doesn't support a `limit` query param, add it (1-line addition). That's the only backend touch — and only if it doesn't already exist.

---

## Frontend changes

### 1. New bricks (LEGO)

`apps/web/src/lib/flows/bricks/entry-mode-picker.tsx`

```tsx
"use client";

import { useRouter } from "next/navigation";
import { startFlow } from "@/lib/flows/runtime";
import { useFlowCopy, registerModeCopy } from "@/lib/flows/copy";
import { openChatWidget } from "@/lib/chat-widget-event-bus"; // existing

// Register home-picker copy on module load
registerModeCopy("home_picker", {
  section_title: "What are you starting with?",
  section_sub: "Three ways into the product. Pick the one closest to where you are.",
  cta_asset_label: "🎯 Pick an asset",
  cta_asset_sub: "I want to trade NVDA / gold / SPY",
  cta_portfolio_label: "📊 Upload portfolio",
  cta_portfolio_sub: "I already own a basket — find me an overlay",
  cta_chat_label: "💬 Chat builder",
  cta_chat_sub: "I have a thesis or trading idea",
});

export function EntryModePicker() {
  const router = useRouter();

  const onPickAsset = () => {
    // Sprint 1: <Link>-style nav to existing strategy picker.
    // Sprint 2: replace with startFlow('one_asset_mode', …).
    router.push("/strategies/new?from=home/pick_asset");
  };

  const onUploadPortfolio = () => {
    startFlow("portfolio_mode", {
      initialContext: { fromTrigger: "home/upload_portfolio" },
    });
  };

  const onChatBuilder = () => {
    openChatWidget({ source: "home/chat_builder" });
  };

  return (
    <section className="entry-picker">
      <h2>{useFlowCopy("home_picker", "section_title")}</h2>
      <p>{useFlowCopy("home_picker", "section_sub")}</p>
      <div className="cta-grid">
        <CtaTile
          label={useFlowCopy("home_picker", "cta_asset_label")}
          sub={useFlowCopy("home_picker", "cta_asset_sub")}
          onClick={onPickAsset}
        />
        <CtaTile
          label={useFlowCopy("home_picker", "cta_portfolio_label")}
          sub={useFlowCopy("home_picker", "cta_portfolio_sub")}
          onClick={onUploadPortfolio}
        />
        <CtaTile
          label={useFlowCopy("home_picker", "cta_chat_label")}
          sub={useFlowCopy("home_picker", "cta_chat_sub")}
          onClick={onChatBuilder}
        />
      </div>
    </section>
  );
}
```

`apps/web/src/lib/flows/bricks/saved-strategies-tile.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";
import { listUserStrategies } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";

interface Props {
  limit?: number; // default 3
}

export function SavedStrategiesTile({ limit = 3 }: Props) {
  const [strategies, setStrategies] = useState<SavedStrategy[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listUserStrategies({ limit })
      .then(setStrategies)
      .catch((err) => setError(err.message));
  }, [limit]);

  if (error === "unauthenticated") {
    return <SignInPromptTile />;
  }

  if (strategies === null) {
    return (
      <div className="saved-strategies-tile">
        <Skeleton className="h-4 w-32 mb-3" />
        <Skeleton className="h-16 w-full mb-2" />
        <Skeleton className="h-16 w-full mb-2" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (strategies.length === 0) {
    return null; // signed in but no saves — hide the tile entirely
  }

  return (
    <div className="saved-strategies-tile">
      <h3>Your saved strategies</h3>
      {strategies.map((s) => (
        <Link key={s.slug} href={`/strategies/${s.slug}`}>
          <SavedStrategyRow strategy={s} />
        </Link>
      ))}
      <Link href="/builders" className="view-all">View all →</Link>
    </div>
  );
}

function SignInPromptTile() { /* ... */ }
function SavedStrategyRow({ strategy }: { strategy: SavedStrategy }) { /* ... */ }
```

### 2. Home page surgery

`apps/web/src/app/page.tsx`

Locate the existing "Describe Your Strategy" section and replace with:

```tsx
import { EntryModePicker } from "@/lib/flows/bricks/entry-mode-picker";
import { SavedStrategiesTile } from "@/lib/flows/bricks/saved-strategies-tile";

// ... existing imports and code ...

export default async function HomePage() {
  return (
    <main>
      <Hero />                                  {/* existing */}
      <SavedStrategiesTile />                   {/* NEW */}
      <EntryModePicker />                       {/* NEW — replaces "Describe Your Strategy" */}
      <MarketPulseTeaser />                     {/* existing */}
      <LiveTickerBar />                         {/* existing */}
      <Footer />                                {/* existing */}
    </main>
  );
}
```

The "Describe Your Strategy, We Handle the Rest" section (identified by its heading text in the current `page.tsx`) is deleted in this PR. The corresponding component / sub-tree is removed; if it was a separate file (e.g., `components/home/strategy-teaser.tsx`), the file is deleted and the import removed.

### 3. Existing-flow-not-registered fallback

The `<EntryModePicker>` calls `startFlow('portfolio_mode', …)` optimistically. If PRD-13b hasn't merged yet, `startFlow` (per PRD-13a §runtime.ts) will detect the missing flow and either:

- Show a toast "Portfolio mode coming soon — for now, try a template" with a CTA linking to Strategy Builders
- OR navigate to `/builders?notice=portfolio_coming_soon` which renders the message inline

Pick the toast approach — less disruptive, lets the user pick another CTA without leaving Home. The runtime's `startFlow` returns a `Promise<{ ok: boolean; reason?: string }>`; the EntryModePicker shows the toast when `ok === false`.

This means the PR can ship and pass acceptance even if PRD-13b is still in flight. When PRD-13b merges, the Upload Portfolio CTA works automatically — no changes needed in this PRD.

### 4. Test plan

`apps/web/src/lib/flows/bricks/__tests__/`

- `entry-mode-picker.test.tsx` — renders three CTAs; clicking each fires the right handler (mock router, mock startFlow, mock chat widget event bus).
- `entry-mode-picker.fallback.test.tsx` — when `startFlow('portfolio_mode')` returns `{ ok: false }`, toast appears with "Coming soon" message.
- `saved-strategies-tile.test.tsx` — skeleton state, empty state, error state (unauthenticated → sign-in prompt), populated state (3 rows, "View all" link).

E2E (Playwright):

- `e2e/home-entry-picker.spec.ts` — visit `/`, see three CTAs; clicking "Pick an asset" navigates to `/strategies/new?from=home/pick_asset`; clicking "Chat builder" opens the chat widget (assert widget visibility).

---

## Reusable LEGO bricks created by this PRD

### Frontend bricks

| Brick | Location | Used by |
|---|---|---|
| `<EntryModePicker>` | `lib/flows/bricks/entry-mode-picker.tsx` | Home page; future re-engagement modals; abandonment recovery |
| `<SavedStrategiesTile>` | `lib/flows/bricks/saved-strategies-tile.tsx` | Home page; future `/builders` saved-strategies hub |
| `home_picker` copy lexicon | `lib/flows/copy.ts` registered on module load | This PRD only |

### Backend bricks

**None added by this PRD.** Consumes existing `GET /api/saved-strategies` (with new `limit` query param if not already present).

---

## Acceptance checklist

A PR is accepted when **all of the following are true**.

### Code

- [ ] `apps/web/src/lib/flows/bricks/entry-mode-picker.tsx` exists; uses `useFlowCopy('home_picker', key)`.
- [ ] `apps/web/src/lib/flows/bricks/saved-strategies-tile.tsx` exists with skeleton / empty / error / populated states.
- [ ] `apps/web/src/app/page.tsx` rewired: `<EntryModePicker>` replaces the "Describe Your Strategy" section; `<SavedStrategiesTile>` placed above it.
- [ ] No backend changes (or single 1-line addition to `GET /api/saved-strategies` for `limit` query param if absent).
- [ ] PRD-13a's `startFlow`, `useFlowCopy`, `registerModeCopy` imported correctly.

### Behavior

- [ ] "Pick an asset" CTA → navigates to `/strategies/new?from=home/pick_asset` (Sprint 1 placeholder route).
- [ ] "Upload portfolio" CTA → calls `startFlow('portfolio_mode', { initialContext: { fromTrigger: 'home/upload_portfolio' } })`.
- [ ] "Chat builder" CTA → calls `openChatWidget({ source: 'home/chat_builder' })`.
- [ ] If `portfolio_mode` is not yet registered (PRD-13b not merged), Upload CTA shows a "Coming soon" toast; no crash.
- [ ] Signed-in users see saved-strategies tile (skeleton while loading, max 3 entries, "View all" link).
- [ ] Anonymous users see "Sign in to access your strategies" prompt.
- [ ] Signed-in users with zero saves see the entry picker without the tile (tile hidden, not empty-state).
- [ ] No regression: nav, hero, market pulse teaser, ticker bar, footer unchanged.

### Tests

- [ ] 3 unit tests pass: entry-picker-CTAs, entry-picker-fallback, saved-strategies-tile-states.
- [ ] 1 Playwright E2E test passes: home-entry-picker navigation.
- [ ] `cd apps/web && npm run build` clean.
- [ ] `cd apps/web && npm run test` green.

### Telemetry

- [ ] PostHog events fire on each CTA click: `home_pick_asset_clicked`, `home_upload_portfolio_clicked`, `home_chat_builder_clicked`.
- [ ] PostHog event `home_saved_strategy_clicked` fires when user clicks a saved-strategy row.

### Documentation

- [ ] Update HANDOFF §6 Brick inventory: mark `<EntryModePicker>` and `<SavedStrategiesTile>` as ✅.
- [ ] PR title: `feat(home): entry mode picker (PRD-11)`.

---

## Out of scope (do not build in this PRD)

- Mode 1 ("Pick an asset") refactor to use a `FlowDefinition`. Sprint 2.
- Chat widget redesign. Existing widget opens; no changes.
- A/B testing of CTA copy variants. Add events; build flag-gated variants in a separate PRD.
- Personalized re-engagement (e.g., "You haven't visited in 30 days — here's a strategy update"). Future PRD.
- Marketing landing page sections (testimonials, "as seen in" logos). Out of product scope for Sprint 1.
- Mobile-specific layout polish. Use existing responsive breakpoints; mobile-first redesign of Home is a separate effort.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §5 Surface 1 mockup
- Master handoff: `agent-system/plans/HANDOFF-livermore-product-flow-v2.md`
- Hard dep: `PRD-13a-flow-runtime-infra.md` (the runtime you import from)
- Soft dep: `PRD-13b-portfolio-mode.md` (registers `portfolio_mode`; until it merges, Upload CTA shows "Coming soon")
- Related: Module 2 reconciliation memo `PRD-12-asset-behavior-reconciliation.md` (not consumed by this PRD; for awareness)
- Repo conventions: `CLAUDE.md` (auto-loaded), `agent-system/PARALLEL_WORK.md`

---

*Drafted 2026-05-26. PRD-11 is the smallest of the Sprint 1 trio (PRD-11, PRD-13a, PRD-13b) and lands once PRD-13a's runtime is on `main`. PRD-13b's merge state determines whether the Upload Portfolio CTA is functional on PR-merge day; the graceful "Coming soon" fallback means PRD-11 ships either way.*
