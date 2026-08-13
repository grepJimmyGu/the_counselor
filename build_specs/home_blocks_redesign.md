# Home blocks redesign — Hot Market Picks · Quant Rules · Traders Ask · Catalysts

**Status:** specification, not yet built. Authored 2026-08-13, revised after
Jimmy's answers on the three open questions.
**Scope:** the home below-fold blocks. **No backend changes.**

---

## Why

Four blocks sit in a 2×2 grid at ~568px each. Two problems Jimmy named:

1. **They don't reuse the good work.** The starting-point cards, the template
   gallery and the overlay picker all have designed, shipped surfaces elsewhere.
   The home versions are thinner re-inventions of the same content.
2. **They're loose.** "Traders ask" is mostly whitespace, and the blocks read as
   lists rather than as things worth clicking.

The design target from `ui-ux-pro-max` for this product type is **Data-Dense
Dashboard** — "minimal padding, grid layout, space-efficient, maximum data
visibility" — whose named anti-pattern is *ornate design*. That is the standard
the blocks are held to below.

---

## The registry this all hangs on

`lib/recommended-templates.ts` — `RECOMMENDED_TEMPLATES`, the ten starting
points already built for **Screen the Market** (`/flow/custom_build_mode`).
It splits cleanly in two, and that split drives the whole redesign:

| kind | count | carries | routes to |
|---|---|---|---|
| `composer` | 5 | **real `rules`** (`primitive_id` conditions, verified present in the daily snapshot vocabulary) | a scan → a stock list |
| `sentiment` | 5 | `toolkit_id` | `/sentiment?toolkit=…` |

```
composer   best_momentum        Best Momentum Pick      momentum
composer   breakout             Breakout to Highs       event
composer   oversold_bounce      Oversold in Uptrend     event
composer   volatility_squeeze   Coiled Spring           event
composer   steady_uptrend       Trend Leader            momentum

sentiment  positive_catalyst    Positive Catalyst       catalyst
sentiment  rising_attention     Rising Attention        catalyst
sentiment  news_community_…     Mainstream Buyers       catalyst
sentiment  sentiment_reversal   Sentiment Reversal      catalyst
sentiment  community_hype       Community Hype          catalyst
```

**Adding a starting point stays one entry in that file.** Nothing below
introduces a second registry.

---

## 1. "Special list" → **Hot Market Picks**

**File:** `components/home/home-curated-screens.tsx`

### Source: the composer starting points, recycled

The five `kind: "composer"` entries — the same cards, the same copy, the same
category chips as screen 1. Not the nine `/api/screener/presets`; those stay
where they are on `/stocks`.

### Card design

Extract the card from `recommended-templates-gallery.tsx` so both surfaces
render the same component:

```
components/screen/starting-point-card.tsx   ← new, single source
  used by: recommended-templates-gallery.tsx  (Screen the Market)
           home-curated-screens.tsx           (Hot Market Picks)
```

Structure, unchanged from screen 1: category chip (Lucide icon in a tinted
rounded square + uppercase label) → title → one-line trader's reading →
`Screen this →`. The home instance takes `density="compact"`: tighter padding,
description clamped to two lines.

### Results destination — the search-query landing, unchanged

A card lands **directly on the filtered stock list**, on the exact surface a
typed search produces (`/screen`, `components/screen/query-results.tsx`). Not
`/stocks`, not an intermediate page. Reference: the `?q=above the 50 day`
landing — every affordance on it already exists and must survive.

| Element on that landing | Source for a template |
|---|---|
| Search box, still editable | unchanged — the user refines from here |
| Universe pill (`S&P 500`) | `template.universe_id`, carried in the URL |
| **Selected filters** chips, each with a live count `(352)` | one chip **per rule** — a 6-rule template shows 6 chips. `screenCount` already fetches per-chip counts |
| `+ Add condition` · `+ Additional metrics` · `+ Filter by metric` · `+ Add ticker` | unchanged |
| `352 match of 525` + `AS OF <date>` | `screenScan` result, unchanged |
| Prose line — *"Screened the S&P 500 on price above the 50-day average."* | **needs a source.** A typed query uses `parsed.note`; a template has no parse. Compose from the template: *"Screened the S&P 500 on Best Momentum Pick — top-quintile 6-month momentum in a leading sector."* |
| Truncation notice ("first 300 of 352 matches") | unchanged |
| Table — Symbol · Name · Price · Change % · Market cap · Volume + per-condition value column | unchanged |

Composer templates carry `rules` directly, so there is **nothing to parse**:

```
/screen?template=<id>&universe=<template.universe_id>
```

`query-results.tsx` gains a `templateId` path — when present it hydrates `rules`
from `RECOMMENDED_TEMPLATES` and calls `screenScan` with them, skipping
`parseSearch`. Chips, counts, table, sort, add-ticker and share are reused
as-is; the only new code is the hydration and the note.

**The landing must be indistinguishable from a typed search**, because from
there the user's next move is the same — edit a chip, add a condition, add a
ticker. A template is just a faster way to arrive at it.

> This is why recycling the starting points mattered. The earlier draft routed
> through `/screen?q=<phrase>`, which required every phrase to be verified
> against `/api/search/parse` — and a card could silently return a different set
> than it promised. The composer rules are already the scan's own vocabulary, so
> that risk class disappears.

The **Market cap** column on that landing reads `SymbolCache.market_cap`, which
sat at 1.8% coverage across the Russell 3000 before the 2026-08-13 backfill.
Confirm it is populated before judging this block — a table of blanks would look
like a layout bug and isn't one.

### Unchanged

A card whose scan returns zero names is hidden rather than shown as "0" — a
zero-count card on the home page reads as a broken product.

---

## 2. "Quant strategies" → **Quant Rules**

**File:** `components/home/home-quant-strategies.tsx`

Renamed, cut to **exactly three sections**.

### Section A — Templates (one row)

Four entries at `sm:grid-cols-4`:

| Entry | Action |
|---|---|
| **Try a Template** | `startFlow("one_asset_mode")` — the entry currently at `home-focus-sections.tsx:152` |
| 3 × template card | top 3 of `researchTemplates` where `availability !== "unavailable"` |

Cards keep `evidenceTier` (A/B/C) and **must not** show performance numbers —
`perfContext` reads like backtested returns but is hand-written prose, and there
is no per-template performance store. That constraint is load-bearing.

Below 640px the row becomes 2×2 with "Try a Template" first.

### Section B — Overlays (two entries)

| Entry | Action |
|---|---|
| **Overlay overview** | the six-overlay illustration, read-only |
| **Upload Portfolio** | `startFlow("portfolio_mode", { fromTrigger: "home/upload_portfolio" })` — currently at `home-focus-sections.tsx:160` |

**Overlay overview** uses the existing `Pick an overlay` design (screen 2,
`lib/flows/bricks/overlay-picker.tsx`): Basic (Defensive · Rotation · Rebalance)
and Advanced (Dual Momentum · Defense-First · Stability Tilt), each with its
one-line thesis and outcome line ("Cuts crash damage in half — worst loss −28%
vs −55%").

**Read-only, confirmed.** The picker selects an overlay *for a portfolio you
have already uploaded*; selecting one here with no holdings dead-ends. Cards
inform; the CTA underneath is **Upload Portfolio**. Keep the `Needs 3+ holdings`
/ `Needs 2+ holdings` badges — they set expectations before the upload.

Extract `components/overlays/overlay-card.tsx` with a `readOnly` prop so the
picker and the overview cannot drift.

### Section C — Build your own

One entry into the composer. Behaviour unchanged.

### Removed

The `<dt>` definition list explaining the three sections, which sits directly
above the three sections.

---

## 3. **Traders Ask** — redesign

**File:** `components/home/home-example-queries.tsx`

Current layout: tab row, then a 2-column grid of full-width buttons each holding
one short question, then a caption, then the news ticker. Each button is ~40px
tall holding ~30 characters, so most of the block is empty background.

- **Query chips, not rows.** `inline-flex`, `rounded-full`, `px-3 py-1.5`, sized
  to their text and wrapping. Roughly doubles the questions visible in the same
  height.
- **Tabs become a segmented control** on the heading line, reclaiming a row.
- **Caption merges into the heading row** as muted helper text.
- **The news ticker moves out** — see block 4.

**Unchanged:** clicking a query writes into the search box and submits rather
than navigating, so the user watches their question appear as a typed query and
learns to type their own. Every string must still parse —
`tests/test_home_example_queries.py` runs each through the real extractors.

---

## 4. **Catalysts** — new block (the ticker's new home)

**File:** `components/home/market-catalysts.tsx` (new; absorbs
`market-news-ticker.tsx`)

Per Jimmy: the ticker becomes its own box, with the catalyst entries leading
into it. This is where the **five `kind: "sentiment"` starting points** belong —
they cannot produce a stock list from a scan, which is exactly why they don't
fit Hot Market Picks.

Layout:

1. **Catalyst entries** — the five sentiment templates as compact chips or
   two-line cards, reusing `starting-point-card.tsx` at its smallest density.
   Each routes to `/sentiment?toolkit=<toolkit_id>&autorun=1`, the deep link the
   hub already honours (#239). CTA reads `View in News & Sentiment →`, matching
   screen 1.
2. **The live ticker** below them, unchanged in behaviour.

The pairing is the point: the headline tells you something happened, the
catalyst entry is how you act on it.

### Grid

Five blocks no longer fit a 2×2. Options, in preference order:

1. **2×2 + full-width strip.** Market Pulse · Hot Market Picks / Quant Rules ·
   Traders Ask, then Catalysts full width beneath. The ticker is horizontal by
   nature and reads better at full width; nothing else has to move.
2. 3-column at `xl`, 2-column at `lg`. More disruption, no clear gain.

Take option 1 unless it looks wrong at 1024px.

---

## Cross-cutting

### Density

`p-5` → `p-4`; inner gaps `gap-2` → `gap-1.5`; card padding `py-2` → `py-1.5`.
Type scale unchanged — these blocks sit in a ~568px column beside siblings, and
anything larger shouts.

### Consistency

Three card idioms today → two after, both extracted and shared:

- `starting-point-card.tsx` — Screen the Market · Hot Market Picks · Catalysts
- `overlay-card.tsx` — the picker · Overlay overview

### Accessibility — from the skill's checklist, non-negotiable

- `cursor-pointer` on every clickable card (several lack it today)
- Visible focus rings; tab order matching visual order
- `aria-label` on icon-only controls; `aria-pressed` on segmented tabs
- Contrast ≥ 4.5:1 — muted text at `slate-600` minimum, never `slate-400`
- Hover feedback via **color/opacity only**; no scale transforms, which shift
  layout in a dense grid
- Transitions 150–300ms; respect `prefers-reduced-motion`
- Verify at 375 / 768 / 1024 / 1440px, no horizontal scroll

### Out of scope

- No backend changes. Every source exists: `RECOMMENDED_TEMPLATES`,
  `researchTemplates`, `POST /api/screen/scan`, `/sentiment?toolkit=`.
- No new performance claims.
- `HomeMarketPulseBlock` untouched.

---

## Build order

1. Extract `starting-point-card.tsx`; repoint the Screen the Market gallery at
   it. **No visual change** — that is the proof the extraction is faithful.
2. `query-results.tsx` gains the `?template=` path (hydrate rules → scan).
   Verify each of the five composer templates returns a non-empty list.
3. Hot Market Picks: rename, adopt the card, route to `/screen?template=`.
4. Extract `overlay-card.tsx` with `readOnly`; repoint `overlay-picker.tsx`.
5. Quant Rules: rename, three sections, absorb the two entries from
   `home-focus-sections.tsx`.
6. Catalysts: new block, move the ticker, add the five sentiment entries,
   regrid to 2×2 + strip.
7. Traders Ask: chips, segmented tabs.
8. Density and a11y pass; screenshot at four widths.

Steps 1 and 4 land first and alone: an extraction that changes no pixels is easy
to review, and it makes 3, 5 and 6 small.

## Testing

- `home-below-fold.test.tsx` covers these blocks and **mocks `@/lib/api`
  wholesale** — any new API import must be added to that mock or the entire
  block fails to render. This has already broken once.
- Step 2 needs a test that each composer template's rules produce a non-empty
  scan against the seeded snapshot fixture.
- Snapshot the blocks at 375 and 1024px.
