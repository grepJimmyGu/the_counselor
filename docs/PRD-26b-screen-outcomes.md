# PRD-26b — The three things a screen can become

**Status:** Proposal, for review
**Supersedes:** the naming and framing of PRD-26's "Promote to strategy" (kept, renamed)
**Author:** planning session, 2026-09-10
**Prerequisite reading:** [`docs/QUANT_ENGINE_MAP.md`](QUANT_ENGINE_MAP.md) for how this
sits beside the Quant Engine packet; `PROJECT_BACKLOG.md` §4 "One results surface for
both query engines" (#368) for the adjacent scope.

---

## 0. Why this exists

PRD-26 shipped a button labelled **"Promote to strategy"** that does not promote the
screen. It takes one symbol out of the matched basket and builds a single-asset
strategy from it:

```ts
// apps/web/src/lib/flows/promote-to-strategy.ts:171
export async function buildPromoteDraft(context, symbol: string)
// :203
strategy_name: `${symbol} — promoted from screen`
```

You narrow 500 names to 14, press Promote, and the 14 are discarded. What you get is a
single-name backtest that inherits the screen's rules — a genuinely useful thing, and
not the thing the label promises.

Beside it sits **"Save + track this screen"**, which keeps the basket and watches it.
The two buttons are rendered as peers ([`screener-results.tsx:398–452`](../apps/web/src/lib/flows/bricks/screener-results.tsx))
with opposite semantics and no statement of the trade between them.

**A third forcing function arrived with #368.** Once Home's search box routes
*fundamental* queries to the same results surface, half the baskets reaching that
surface will carry **no rules at all** (`strategy_json: null`, `readings: {}`).
"Promote the screen's rules to a strategy" is undefined for "P/E under 15". Whatever
replaces this button has to work for a basket that is only a list of names.

---

## 1. The model

A screen is a standing rule over a universe that produces a **basket that changes over
time**. It has exactly three honest outcomes, and they should be named for what they do.

**Decided 2026-09-10 by Jimmy: there are TWO outcomes, not three.**

| Outcome | Keeps | Produces | Lands on | Status |
|---|---|---|---|---|
| **Save Live Rule** | the **rule**, living — re-run by cron | a saved screen you revisit like a search result | `/screens/{id}` | ✅ ships (PRD-23c) |
| **Create a Portfolio** | the **names**, frozen at today | a portfolio-overlay strategy you backtest | `/account/strategies/{id}` | ⬅ **this PRD** |

Read down the "Keeps" column: that is the whole product decision. One door keeps the
*question* and keeps asking it; the other keeps the *answer* as it stands today. The
user has to be told which. Today neither door says.

**"Study one" is removed** — see §3. It was the third door in the first draft of this
PRD and Jimmy cut it: a screen exists to produce a set, and a door that throws the set
away to build a single-name strategy is a different feature wearing a screen's clothes.

---

## 2. Create a Portfolio — the new outcome

### 2.1 The machinery already exists

`overlay-picker.tsx:109` already turns a list of tickers into a backtestable multi-name
strategy:

```ts
universe: tickers,
inherited_universe: tickers,
strategy_type: meta.strategyType,   // portfolio_*_overlay
```

Six validated overlay types ship (`defensive`, `rotation`, `rebalance`, `dual_momentum`,
`defense_first`, `stability_tilt`), the engine swaps `universe` for `inherited_universe`
at the top of `BacktestEngine.run()`, and `strategy_validator.py` enforces per-overlay
minimums.

**It is wired to the portfolio-upload flow and not to the screen basket** — even though
a screen basket is exactly a list of tickers. This is wiring, not new engine work.

### 2.2 The crux: a frozen basket, and saying so

A screen's basket is dynamic; `inherited_universe` is static, stored in
`strategy_json`. So promoting has to resolve one question.

**Option A — freeze.** Store today's names. Simple, uses the machinery unchanged,
honestly backtestable.

**Option B — live link.** Store a reference to the screen; resolve the universe from
`current_basket` at run time. Matches the user's mental model.

**Option B cannot ship, and the reason is not effort.** A backtest of a living screen
needs to know what the basket was *on every historical date*. We have basket membership
only from the day the screen was saved forward (`rescan_and_diff` seeds, then diffs),
and `signal_snapshot` stores each primitive's **last** value, not a history. Point-in-time
reconstruction across the backtest window does not exist. Option B therefore produces a
strategy that cannot be validated — precisely the thing 43e/43d exist to prevent, and
the same error as shipping a rule that can never reach `tested`.

**Recommendation: Option A, plus a drift notice.** Freeze at promote time, and — because
the screen is still tracked independently — tell the user when the two diverge:

> *Your screen has 3 names this strategy doesn't. Re-promote to pick them up.*

Both datasets already exist (`current_basket(screen_id)` vs `strategy_json.inherited_universe`);
the notice is a set difference. This closes the honesty gap without inventing history,
and it follows the repo's existing date-stamp invariant: state what the number is *as of*.

### 2.3 Which overlays a screen basket can use

| Overlay | Min names | Fits a screen basket? |
|---|---|---|
| `rotation` | 3 | **Default.** "I screened for a quality; hold the best K of them" is the natural reading of a basket |
| `defensive` | 1 | Yes — per-holding MA filter |
| `dual_momentum` / `defense_first` / `stability_tilt` | 3 | Yes |
| `rebalance` | 2 + explicit weights | **Exclude.** It needs weights the user does not have for a screen; equal-weight rebalance is just `defensive` without the filter |

### 2.4 Basket size

A screen can match 200 names; that is not a portfolio. `POST /api/screen/rank` already
returns the basket ordered by return, so the top-K cut is free. Propose **K = 20 default,
user-adjustable**, and refuse below the overlay's minimum with the reason rather than
silently padding.

For a **fundamental** basket (#368's no-rules mode) `rank` is unavailable — there are no
rules to backtest per symbol. Cut by the screen's own ordering and say so.

### 2.5 Reuse, not rebuild

`buildOverlayStrategyJson` is already nearly pure — it takes `tickers` and an overlay
kind. Extract it plus the card grid out of `overlay-picker.tsx` into a brick both
`portfolio_mode` and the screen results surface mount. Do **not** fork a second copy of
the overlay cards; that is how the two screener backends happened.

---

## 3. Study one — removed

**Cut by Jimmy, 2026-09-10.** The earlier draft kept the feature and renamed it. It is
now removed from the results surface entirely.

This is a **deletion of shipped code**, not a hidden button — say so plainly so nobody
"restores" it later:

- `PromoteToStrategyButton` (`components/bridge/promote-to-strategy-button.tsx`)
- `buildPromoteDraft` + the seeded-threshold / ATR-ladder path (`lib/flows/promote-to-strategy.ts`)
- their call site and tests in `screener-results.tsx`

The single-asset path itself is untouched — the composer still builds one-name
strategies, and `one_asset_mode` is unaffected. What goes is the door **from a screen**
into that path. If it turns out users wanted it, it returns as a per-row action on a
ticker, not as a peer of the two outcomes.

---

## 4. Save Live Rule — unchanged, promoted to primary

Today's "Save + track this screen". **No functional change** — it already does exactly
what the name now says: persists the rule as `SavedStrategy(kind="screen")`, wires a
`SignalAlertSubscription` into `monitor_saved_screens`, seeds the basket, and re-runs
on the cron. Revisiting `/screens/{id}` reads like a search result you saved.

Two changes, both outside this outcome's own machinery:

- **Rename** to "Save Live Rule". "Save + track this screen" does not say what is being
  saved, and the whole point of §1 is that the user must know which door keeps what.
- **Surface it under Your Livermore.** `home-your-livermore.tsx` does not mention
  screens today, so a saved rule is currently reachable only by URL. A saved thing the
  user cannot find again is not saved.

---

## 4b. The surface the two doors sit on

*Added 2026-09-10 by the executing session, from Jimmy's UI spec. §§0–4 above are
unchanged; this section is what the two outcomes are rendered on top of, and it
exists because §2 is what finally gives a hand-picked basket somewhere to go.*

Four changes to the results surface. Each is checked against the code below —
what already exists, what is genuinely new, and one that reverses an earlier
decision and should be chosen rather than inherited.

### 4b.1 Conditions on top, editable, with the universe

The reader has to see what they asked for, change it in place, and not be told
a number that means nothing to them.

| Piece | State |
|---|---|
| Condition chips, each with the count it matches ALONE | **Ships** on `/screen` (`query-results.tsx` `ConditionChip`), one `POST /api/screen/count` per chip |
| Edit a condition without leaving the page | **Ships** — the search box is retained at the top and re-pushes `?q=` |
| **Universe selector — S&P 500 / Russell 3000** | **New.** `/screen` reads `?universe=` and never lets you change it; the pair already exists as `UNIVERSES` in `smart-search-box.tsx`. Changing it re-scans |
| **Drop the total-universe size** | **New**, and it is a deletion: `query-results.tsx:672` and `screener-results.tsx:285` both render `of {universe_size}`. "14 of 503" invites the reader to judge the screen by its yield, which is not a quality signal — a screen matching 3 names is not worse than one matching 300 |

Keep the match count itself. It is the one number that says how much work is
left to do.

### 4b.2 The names, not a table of them

Today `/screen` is a dense sortable table: one column per condition carrying its
value, switchable column groups, ranking on any column, 25-row paging. That is
**Jimmy's own 2026-08-07 spec**, shipped across #303 / #304 / #305 / #307.

The proposal here replaces it with a **map of names** — a compact grid holding
many more tickers on one screen, where editing a condition fades tickers in and
out rather than re-paginating a table.

> ✅ **DECIDED 2026-09-10: the map ships.** Jimmy chose it knowing it reverses
> #303–#307. The trade is real and is accepted: the table's columns are what
> justify each match, and a map shows more names and no reasons. **The condition
> values therefore survive behind a toggle rather than being deleted** — "why is
> NVDA here" must stay answerable, which is the condition the decision was made
> under.

The fade is not decoration: it is the only affordance that shows a condition
edit *doing* something to a 200-name basket. A table that re-renders gives no
sense of what changed.

### 4b.3 Clicking a name opens it beside the list

A row click today leaves the page for `/stocks/[ticker]`, which loses the
screen. Instead: open a company profile in a right-hand panel, list still
visible on the left.

`getCompanyOverview(symbol)` already exists and is already used this way — the
company drawer in `smart-search-box.tsx` (`openCompany`). The render is inline
in that component, so the work is **extracting it into a shared panel**, not
building one. Do not fork a second overview renderer.

### 4b.4 Selection, and what it is for

Users pick names — multi-select, drag, or whatever reads best — into a basket.

**This is the point that §2 rescues.** Before **Create a Portfolio** existed, a
hand-picked selection had nowhere to go, and the obvious guesses were both
wrong:

- it is **not** the input to *Save Live Rule*. That door saves the RULE, re-run daily by
  `monitor_saved_screens`; `ScreenSaveRequest` carries `{title, universe_id,
  rules}` and no symbol list. Pinning picks to it means tomorrow's cron
  overwrites them. That is not a missing field, it is what saving *is*;
- *Study one* is gone (§3), so the single-name door it might have fed no longer
  exists.

It is the input to **Create a Portfolio** (§2): the selected names become
`inherited_universe` — the static list Jimmy specified — and §2.4's top-K cut
becomes a default the user can override by hand rather than a number imposed on
them.

So the selection needs one state: **selected** feeds Create-a-Portfolio, and
Save-Live-Rule ignores it entirely — that door keeps the rule, not the names.
If nothing is selected, Create-a-Portfolio falls back to §2.4's ranked top-K — selection is a refinement, never a prerequisite.

### 4b.5 What this does not settle

`/screen` (`query-results.tsx`) and the flow's `screen_results`
(`screener-results.tsx`) are two renderings of "a query landed", and they split
the pieces this section needs: the conditions header lives on the first, the
two doors live on the second. Building 4b.1 and the doors on one screen means choosing one. That choice is `PROJECT_BACKLOG.md` §4 "One results surface for
both query engines" (#368) and is **not decided here** — but it blocks the UI
slices below, and whichever surface wins should be the one with a real URL, so
a screen can be sent to someone.

---

## 5. Out of scope

- **The two screener backends.** `screener.py` vs `screen.py` is #368's question.
- **Auto-execution.** Trade-it produces a strategy the user backtests and saves. It does
  not place orders. Active execution stays behind the existing exit-ladder chain.
- **New engine work.** Every strategy type this needs already ships and is validated.
- **Point-in-time basket history.** Deliberately not built; see §2.2.

---

## 6. Open questions

| # | Question | Why it matters |
|---|---|---|
| 1 | **Tier gating.** Save+track is Strategist+ today. Is Trade-it the same, or Quant? | It is the highest-value outcome; gating it hardest may be right, but see the Stripe question — everything ships ungated today |
| 2 | Does Trade-it need to reach **active execution**, or is backtest-and-save enough for v1? | Changes the scope by roughly a slice |
| 3 | ~~Is "Trade it" the right word?~~ | **CLOSED 2026-09-10 — "Create a Portfolio".** "Trade it" promised execution the product deliberately does not do (Home says "No automated trading"; `test_snaptrade_readonly_guard` bans every timer-driven order), which would have repeated the PRD-26 error in a PRD written to fix it |
| 4 | Should the drift notice **offer** re-promote, or only report drift? | Offering it makes the frozen basket feel living without lying about the backtest |
| 5 | ~~Do the doors gate differently?~~ | **CLOSED 2026-09-10 — no gates.** Both outcomes ship ungated, matching how 43b shipped while Stripe is built and unconfigured. Note this makes `save_screen` MORE open than today, where it is Strategist+: removing that gate is part of the work, not a no-op |

---

## 7. Slices

| Slice | Scope | DoD |
|---|---|---|
| **1 — Two doors** | Remove "Promote to strategy" and its code (§3); rename "Save + track" → **Save Live Rule**; render the two outcomes as a named pair stating what each keeps; drop the Strategist+ gate on `save_screen` | The surface offers exactly two doors and says what each keeps; no promote path remains from a screen; a free account can open both |
| **2 — Extract the overlay brick** | Lift `buildOverlayStrategyJson` + the card grid out of `overlay-picker.tsx` into a shared brick | `portfolio_mode` behaviour byte-unchanged; the brick mounts in two places |
| **3 — Create a Portfolio** | Screen basket → top-K → overlay pick → existing backtest → review → save | A technical *and* a fundamental basket both reach a saved portfolio strategy; `rebalance` excluded with a stated reason; below-minimum baskets refuse with the reason |
| **4 — Drift notice** | Set difference between `current_basket` and the strategy's frozen `inherited_universe`, rendered on `/screens/{id}` and the strategy page | A screen whose basket has moved says so on both surfaces |

| **5 — Conditions header** | Universe selector (S&P 500 / Russell 3000, re-scans on change); delete the `of {universe_size}` render in both surfaces; condition chips carried onto whichever surface wins §4b.5 | Changing the universe re-scans; no total-universe number renders anywhere; the match count stays |
| **5b — Your Livermore** | Link saved screens from `home-your-livermore.tsx`, which does not mention them today | A saved rule is reachable without knowing its URL |
| **6 — Company panel** | Extract the `openCompany` overview render out of `smart-search-box.tsx` into a shared panel; mount it right of the list | A row click opens the company beside the list without leaving the screen; one overview renderer, not two |
| **7 — Selection → basket** | Multi-select on the name map; selected names become Create-a-Portfolio's `inherited_universe`, overriding §2.4's top-K | Selecting nothing still works (falls back to ranked top-K); Save-Live-Rule ignores the selection |
| **8 — Name map** (decided) | Replace the table with a name grid; condition edits fade tickers in/out; condition values survive behind a toggle | More names visible than the table at the same height; "why is this name here" still answerable |

Slices 1 and 2 are independent and can land in either order. Slice 3 depends on 2.
Slice 4 depends on 3.

**The UI slices (5–8) all depend on §4b.5** — the surface question in #368 — because
they add to a page that has two competing implementations today. 5 and 6 are
independent of each other and of 1–4. **7 depends on slice 3**: selection has no
destination until Create-a-Portfolio exists. 8 is last and is the only one that
reverses a shipped decision.

---

## 8. What would make this proposal wrong

If a screen is meant to be a **discovery tool and nothing more** — a way to find names
you then research individually — then Create-a-Portfolio should not exist, and the
correct fix is slice 1 alone: remove the promote button, stop implying a screen becomes
a strategy, and let Save-Live-Rule be the only thing a screen persists as.

That is a legitimate product position. It should be decided deliberately rather than
inherited from a button label.
