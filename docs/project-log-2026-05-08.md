# Project Log — 2026-05-08

## Session Summary

Full-day session covering UI/UX agent system, navigation infrastructure, and the complete Research & Strategy Layer (PRDs 01–03).

---

## Areas Completed

### Area 9: UI/UX Expert Agent

**Backend**
- `POST /api/uiux/review` — structured 10-section UX review endpoint
- `app/schemas/uiux.py` — UXReviewRequest, UXIssue, MissingStates, DesignBrief, UXReviewResponse
- `app/services/uiux_service.py` — system prompt embedding full investment product spec, design identity, anti-goals, severity definitions
- `app/api/routes/uiux.py` — route registered in main.py

**Frontend**
- `apps/web/src/app/uiux/page.tsx` — review form pre-filled with Livermore workspace description; displays all 10 sections (verdict, confusion/trust risks, top issues, layout/copy changes, missing states, mobile concerns, design brief, what not to change)

**Agent system documents**
- `agent-system/skills/investment-uiux-agent.md` — full product-specific skill spec (role, design identity, 13 review focus areas, 10 anti-goals, severity definitions, review rules, I/O format)
- `agent-system/style/investment-design-style-guide.md` — color tokens, typography, component patterns, trust patterns, state patterns, anti-patterns
- `agent-system/examples/good-bad-investment-ui.md` — 14 concrete good/bad examples across all major UI areas

---

### Area 10: Navigation Header

**Branch:** `feature/navigation-header` → merged to main

- `apps/web/src/components/nav-header.tsx` — sticky persistent header: Livermore product name (links to `/`), Workspace · Research Templates nav links with active state, LanguageSwitcher moved here from workspace header
- `apps/web/src/app/layout.tsx` — NavHeader added to root layout inside LocaleProvider
- `apps/web/src/app/templates/page.tsx` — stub created to satisfy Next.js typed routes
- `apps/web/src/lib/i18n.ts` — demo picker subtitle updated: "Select an example to load a pre-built strategy, or describe your own in the chat below" (EN + ZH)
- Workspace: LanguageSwitcher import removed (moved to NavHeader)

---

### Area 11: Research Templates Page — PRD-01

**Branch:** `feature/research-templates` → merged to main

**Design process**
- UI/UX agent review run on template surfacing options (A/B/C/D) — approved Option B (dedicated /templates page) with conditions
- Full design proposal covering template card layout, two-CTA pattern, ticker input, load/build flows, data availability communication
- Combined UI/UX Feature Plan saved to `agent-system/plans/research-strategy-design-plan.md`
- Three PRDs written and saved to `agent-system/plans/`

**Contracts**
- `ResearchTemplate` interface + `TemplateAvailability` type added to `contracts.ts`
- `fiveYearsAgo` date constant added
- `researchTemplates` array: 5 templates with full strategy JSON, chatSeed, data requirement, ETF proxy caveat

**Strategy JSON drafted for all 5 templates**

| Template | Type | Default Universe | Key Rule |
|---|---|---|---|
| Trend Following | breakout | AAPL | 20-day entry / 10-day exit / 8% stop |
| Cross-Sectional Momentum | momentum_rotation | AAPL, MSFT, GOOGL, NVDA, META | Top 2 by 6-month return |
| ETF Rotation | momentum_rotation | SPY, QQQ, IEF, GLD, DBC | Top 1 by 3-month return |
| Value + Momentum | placeholder | — | Unavailable (needs fundamentals) |
| Commodity Carry | momentum_rotation | GLD, SLV, USO, UNG, DBA | Top 2 by 1-month return (carry proxy) |

**New components**
- `UniverseInput` — comma-separated multi-ticker input with min-count validation (Templates 2 + 5)

**`/templates/page.tsx`**
- Two sections: Available Now (3 cards) + Requires Additional Data (2 cards)
- Each card: category badge, name, description, what-it-tests, data requirement, ticker input, CTAs
- Template 4: data gap text only, no CTA
- Template 5: "Load with ETF Proxy" label

**Workspace changes**
- `useSearchParams` + `Suspense` wrapper on `app/page.tsx`
- `handleLoadTemplate` — loads strategy, shows review callout, scrolls Strategy Preview into view, replaces universe with user tickers
- `handleBuildFromTemplate` — pre-seeds Chat Builder with framework-aware prompt containing ticker(s)
- Review callout + ETF proxy caveat shown conditionally
- Guided empty state in dashboard tab when template loaded but no backtest run
- URL params cleared via `router.replace` after load

---

### Area 12: Strategy Storage — PRD-02

**Branch:** `feature/strategy-storage` → merged to main

**Backend**
- `BacktestRecord` extended: `slug` (VARCHAR 128), `name` (VARCHAR 255), `is_public` (BOOLEAN), `saved_at` (TIMESTAMP)
- Migration: ALTER TABLE backtests for new columns + partial unique index on slug
- `POST /api/strategies/save` — takes backtest_id + name, generates slug with 4-char random suffix, returns shareable URL
- `GET /api/strategies/{slug}` — public read endpoint, returns full result payload

**Frontend**
- `SavedStrategy` type in `contracts.ts`
- `saveStrategy()` + `getSavedStrategy()` in `lib/api.ts`
- Workspace: Save Strategy button after backtest completes → inline name dialog → "Saved · Copy link" state
- Save state resets on each new backtest run
- `/strategies/[slug]/page.tsx` — read-only page: strategy rules, prominent disclaimer, 8 metrics, equity curve, drawdown chart

---

### Area 13: Personal Strategy Library — PRD-03

**Branch:** `feature/strategy-library` → merged to main

**Library persistence**
- `LibraryEntry` type + `LIBRARY_KEY` constant
- `savedLibrary` state loaded from `localStorage["livermore_saved_strategies"]` on mount (max 20 entries)
- Written on successful save; stale slugs pruned silently on 404

**Comparison tab extension**
- "Compare against" dropdown: Previous run + My Saved Strategies optgroup (up to 5 entries)
- `buildSavedComparison()` helper for saved strategy metrics
- `handleSelectCompare()` fetches saved strategy via `getSavedStrategy()`
- Context row showing ticker + date range for both strategies
- Yellow context note when tickers or date ranges differ
- Dynamic column header (saved strategy name)
- Loading spinner during fetch

---

## Architecture Decisions

- **No auth for strategy storage** — URL is the identity. Slug = shareable access key. All saved strategies are public via URL.
- **Slug format** — `name-a3f2` (4-char random suffix) to avoid collisions without sequential numbering
- **Library is browser-local** — localStorage only, not server-side. Cross-device sync deferred to Phase 4 (requires auth).
- **Community strategies deferred** — Phase 4. Requires curation model, attribution, and user accounts to avoid misleading leaderboard.
- **Template multi-ticker** — new `UniverseInput` component for Templates 2 and 5; single `TickerSearch` for Templates 1 and 3; no input for Template 4.
- **Template 3 ticker input** — asks for benchmark ETF (not universe), which is fixed at SPY/QQQ/IEF/GLD/DBC.

---

## Documents Created

| File | Purpose |
|---|---|
| `agent-system/skills/investment-uiux-agent.md` | UX agent skill spec |
| `agent-system/style/investment-design-style-guide.md` | Design system reference |
| `agent-system/examples/good-bad-investment-ui.md` | 14 good/bad UI examples |
| `agent-system/plans/research-strategy-design-plan.md` | Combined UX feature plan |
| `agent-system/plans/PRD-01-research-templates.md` | Templates page PRD |
| `agent-system/plans/PRD-02-strategy-storage.md` | Storage PRD |
| `agent-system/plans/PRD-03-strategy-library.md` | Library + comparison PRD |

---

## Pending

- **Phase 4: Community strategies** — requires auth, curation model, attribution design
- **`/uiux` server restart** — uiux_router was added but server needs restart to register (already committed, will pick up on Railway deploy)
- **Template strategy JSON validation** — template strategies haven't been backtest-tested end-to-end; verify each template loads and runs cleanly
