# PRD-02: Strategy Storage & Shareable URLs

**Status:** Ready to build
**Phase:** 2
**Depends on:** PRD-01 (templates page) not required, but workspace must have a completed backtest to save

---

## Problem

Strategies and backtest results exist only in browser memory. Once a user closes the tab or refreshes, everything is lost. Users cannot share a result with someone else or return to a previous backtest. There is no record of research done.

---

## Goals

- Let users save a completed backtest as a permanent named record
- Generate a shareable URL for every saved strategy
- Make saved strategies publicly viewable (read-only) via that URL
- Require no login or account — the URL is the access key

## Non-Goals

- User accounts or authentication
- Editing a saved strategy after saving
- Running a backtest from the saved strategy page (read-only)
- Deleting saved strategies (MVP — no delete)
- Private strategies (all saved strategies are public via URL)
- Listing all strategies (no browse/search page — that is Phase 3+)

---

## User Stories

1. As a user, I want to save a backtest result so I can return to it later without losing my work.
2. As a user, I want to share a strategy result with someone else by sending them a link.
3. As a viewer, I want to open a shared strategy link and see the full rules, result, explanation, and sandbox review so I understand exactly what was tested.
4. As a viewer, I want a clear disclaimer that the saved strategy is a user-created historical backtest, not a product recommendation.

---

## Backend

### Schema changes — `BacktestRecord`

Add three nullable columns:

```python
slug: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)
name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

Migration: add columns with `ALTER TABLE` — nullable, no backfill needed.

### Slug generation

```python
def generate_slug(name: str, year: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{base}-{year}"
```

On collision: append `-2`, `-3`, etc. until unique.

### New endpoints

**`POST /api/strategies/save`**

Request:
```json
{ "backtest_id": 42, "name": "NVDA Trend Following" }
```

Response:
```json
{ "slug": "nvda-trend-following-2024", "url": "/strategies/nvda-trend-following-2024" }
```

Logic:
1. Look up `BacktestRecord` by `backtest_id`
2. Return 404 if not found
3. Return 400 if already saved (slug already set)
4. Generate slug from name + current year, check uniqueness, increment suffix on collision
5. Set `slug`, `name`, `is_public=True`, commit
6. Return slug and relative URL

**`GET /api/strategies/{slug}`**

Response: full `BacktestRecord` as JSON including:
- `name`, `slug`, `saved_at`
- `strategy_json` (the exact rules that were tested)
- `metrics` (all backtest metrics)
- `equity_curve` (list of `{date, value}` points)
- `explanation` (nullable — may not have been generated)
- `sandbox_review` (nullable — may not have been generated)
- `warnings` (credibility warnings list)

Return 404 if slug not found or `is_public=False`.

---

## Frontend

### Workspace — Save button

Show Save button when `backtestResult !== null` and strategy has not yet been saved.

```
[ Run Again ]  [ Save Strategy ]  [ Compare ]
```

On click — inline save dialog (not a modal, inline below the button row):

```
Name your strategy
[ NVDA Trend Following          ]
[ Save ]  [ Cancel ]
```

After successful save:

```
Strategy saved.
livermore.app/strategies/nvda-trend-following-2024
[ Copy link ]
```

State management:
- `savedSlug: string | null` — set after successful save
- When `savedSlug` is set: replace Save button with "Saved · Copy link"
- Prevent duplicate saves: once saved, the Save button is gone

### `/strategies/[slug]/page.tsx`

Read-only page. Fetches `GET /api/strategies/{slug}` on load.

**Layout:**

```
Header
  Strategy name (h1)
  Saved date · Ticker · Date range · Benchmark

Disclaimer banner (prominent, above results)
  "This strategy was created and saved by a user of this tool.
   It is a historical backtest result, not a recommendation or validation."

Strategy Rules card
  All rules from strategy_json displayed in plain English

Backtest Results card
  Equity curve chart
  Key metrics: total return, benchmark return, max drawdown,
               Sharpe ratio, win rate, number of trades
  Transaction cost assumption
  Credibility warnings (if any)

AI Explanation card (if present)
  Labeled: "AI Explanation · AI-generated · Not investment advice"

Sandbox Review card (if present)
  Labeled: "Sandbox Review · Skeptical second opinion"

Footer
  "Historical analysis only. Does not predict future returns."
```

**States:**
- Loading: spinner with "Loading strategy…"
- Not found: "This strategy link is invalid or has been removed."
- Explanation/sandbox absent: sections hidden, no empty state shown (not all backtests generate these)

---

## Acceptance Criteria

- ☐ Save button appears in workspace after backtest completes
- ☐ Save button is absent if no backtest has run or strategy already saved
- ☐ Save dialog accepts a name (required, max 80 chars)
- ☐ After saving: slug returned, full URL shown, copy link button works
- ☐ Save button replaced with "Saved · Copy link" after saving
- ☐ `GET /api/strategies/{slug}` returns 404 for unknown slugs
- ☐ `/strategies/[slug]` shows strategy rules, metrics, equity curve, disclaimer
- ☐ Explanation and sandbox sections hidden if not present (not shown as empty)
- ☐ Disclaimer banner is prominent — above results, not in footer
- ☐ No "run this" or "load this" CTA on the saved strategy page
- ☐ Page title is the strategy name (for sharing previews)

---

## Risks

- **Explanation and sandbox may not exist** for a saved backtest (user ran backtest but never clicked Explain or Review). The `/strategies/{slug}` response must handle these as nullable — the frontend must hide those sections cleanly, not show empty cards.
- **Equity curve data size**: equity curves for long backtests can be hundreds of rows. Confirm the existing `BacktestRecord` stores the full curve, or add a separate `equity_curve` column.
- **Slug collisions on common names**: names like "AAPL Momentum" will collide quickly. The suffix approach (`-2`, `-3`) works but may produce ugly URLs. Consider appending a short random suffix instead (e.g. `aapl-momentum-a3f2`).
- **No delete**: if a user saves a bad result, there is no way to remove it. Acceptable for MVP but should be noted.
