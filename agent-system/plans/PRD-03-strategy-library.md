# PRD-03: Personal Strategy Library & Comparison Extension

**Status:** Ready to build after PRD-02
**Phase:** 3
**Depends on:** PRD-02 (strategy storage) must ship first — library has nothing to show without saved strategies

---

## Problem

Users can save strategies but have no way to find them again without the URL. The Comparison tab only compares the current strategy against the immediately previous one — there is no way to compare against a strategy from a different session.

---

## Goals

- Give users a personal library of strategies they have saved in this browser
- Let users compare the current backtest against any saved strategy
- Surface trade-offs, not winners — full context always shown alongside metrics

## Non-Goals

- User accounts or server-side identity
- Community strategies or browsing other users' saved strategies (Phase 4)
- Sorting or filtering the library (MVP — chronological only)
- Deleting saved strategies from the library
- Syncing library across devices or browsers

---

## User Stories

1. As a user, I want to see a list of strategies I have saved so I can pick one to compare against my current result.
2. As a user, I want to compare my current backtest against a saved strategy so I can evaluate which approach is stronger.
3. As a user, I want the comparison to show full context (ticker, date range, benchmark, assumptions) not just return numbers, so I can understand the trade-offs.

---

## Identity Without Auth

No user accounts. The library is browser-local.

**Mechanism:** When a strategy is saved (PRD-02), append its slug to a `livermore_saved_strategies` key in `localStorage`:

```ts
// on save success
const existing = JSON.parse(localStorage.getItem("livermore_saved_strategies") ?? "[]");
localStorage.setItem(
  "livermore_saved_strategies",
  JSON.stringify([{ slug, name, savedAt: new Date().toISOString() }, ...existing])
);
```

**Implication:** The library is device- and browser-specific. A user who saves on desktop will not see their library on mobile. This is acceptable for Phase 3. Cross-device sync requires auth (Phase 4).

---

## Backend

**No new endpoints required for the library itself** — the frontend reads slugs from localStorage and fetches each via the existing `GET /api/strategies/{slug}`.

**One new endpoint for Comparison tab use:**

**`GET /api/strategies/batch`**

Request (query param): `?slugs=slug-a,slug-b,slug-c`

Response: array of strategy summaries (not full records — just enough for the dropdown):

```json
[
  { "slug": "nvda-trend-following-2024", "name": "NVDA Trend Following", "ticker": "NVDA", "saved_at": "2026-05-08T10:00:00Z" },
  { "slug": "spy-rsi-2024", "name": "SPY RSI Mean Reversion", "ticker": "SPY", "saved_at": "2026-05-06T14:30:00Z" }
]
```

This avoids fetching full strategy records (including equity curves) just to populate a dropdown.

---

## Frontend

### Comparison Tab Extension

Current behaviour: compares current strategy against the immediately previous backtest run in the same session.

New behaviour: dropdown to select any saved strategy as the comparison target.

**Dropdown:**
```
Compare current strategy vs.
[ Previous run ▾ ]
  ─ This session ─
  Previous run
  ─ Saved strategies ─
  NVDA Trend Following  (May 8)
  SPY RSI Mean Reversion  (May 6)
  AAPL Momentum  (May 3)
```

On selecting a saved strategy:
1. Fetch `GET /api/strategies/{slug}` for the full record
2. Render comparison table using the fetched metrics

**Comparison table — always shows full context:**

```
                       Current              NVDA Trend Following
Ticker                 MSFT                 NVDA
Date range             Jan 2020–Dec 2024    Jan 2019–Dec 2023
Benchmark              SPY                  SPY
Transaction costs      Not included         Not included

Total return           +94.2%               +142.1%
Max drawdown           −28.4%               −38.7%
Sharpe ratio           0.89                 1.14
Win rate               61.0%                61.2%
Trades                 22                   42

Note: Strategies tested on different tickers and date ranges.
Results are not directly comparable. Review assumptions before
drawing conclusions.
```

The "Note" row is auto-generated when tickers or date ranges differ between the two strategies. This is the most important trust protection in the comparison view — users must not assume two strategies are head-to-head comparable when they were tested on different assets or periods.

### Library access point

Add a "My Strategies" link to the Comparison tab header, or a small "Saved (3)" badge that opens the dropdown directly. Do not create a separate `/library` page — the Comparison tab is the natural home for the library in this product.

---

## Acceptance Criteria

- ☐ Saved slugs are written to localStorage on save (PRD-02 save flow)
- ☐ Comparison tab dropdown shows "Previous run" (existing) + saved strategies from localStorage
- ☐ Saved strategies in dropdown show name and saved date
- ☐ Selecting a saved strategy fetches its full record and populates the comparison table
- ☐ Comparison table always shows ticker, date range, benchmark, and assumptions for both strategies
- ☐ Auto-generated note when tickers or date ranges differ between the two strategies
- ☐ If localStorage is empty or `GET /api/strategies/{slug}` returns 404 for a slug, that entry is silently removed from the dropdown
- ☐ Comparison tab still works normally (previous run) when no saved strategies exist

---

## Risks

- **localStorage limits**: browsers allow ~5MB. Each slug entry is tiny (`<100 bytes`). Not a practical concern even with hundreds of saves.
- **Stale slugs**: a slug saved in localStorage may 404 if the backend database is reset (e.g. dev environment wipe). The frontend must handle 404 gracefully — remove the stale slug from localStorage silently.
- **Cross-device gap**: a user who saves on one device and opens the app on another will see an empty library. This is a known limitation, acceptable for Phase 3. Do not attempt to solve it without auth.
- **Comparison across different date ranges**: the auto-generated note partially mitigates the risk of users drawing invalid conclusions from incomparable backtests. Consider whether to add a more prominent warning (e.g. a yellow banner) when date ranges differ by more than 1 year.
