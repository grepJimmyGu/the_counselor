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

| Outcome | Keeps | Produces | Lands on | Status |
|---|---|---|---|---|
| **Watch it** | the basket, living | new-entrant / exit alerts | `/screens/{id}` | ✅ ships (PRD-23c) |
| **Trade it** | the basket, frozen | a portfolio-overlay strategy | `/account/strategies/{id}` | ⬅ **this PRD** |
| **Study one** | the rules, one name | a single-asset strategy | `/account/strategies/{id}` | ✅ ships as "Promote", **misnamed** |

Read down the "Keeps" column: that is the whole product decision. A screen's value is
either the *basket* or the *rule*, and the user has to be told which one each door
keeps. Today neither door says.

---

## 2. Trade it — the new outcome

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

## 3. Study one — the rename

Keep the feature exactly as built. Change the label to what it does:

> **Promote to strategy** → **Build a strategy for one name**

and put the seeded-thresholds/ATR-ladder explanation in the sheet, where it already
partly lives. No code change beyond copy and the button's placement among three peers.

---

## 4. Watch it — unchanged, promoted to primary

"Save + track" is the only outcome that keeps the basket living, and it is the one a
screen is *for*. It should read as the primary action, with the other two as peers
beneath it. No functional change.

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
| 3 | Is **"Trade it"** the right word, given the product places no orders? Alternatives: "Hold the basket", "Build a portfolio from this" | Naming is the whole point of this PRD; getting it wrong repeats PRD-26 |
| 4 | Should the drift notice **offer** re-promote, or only report drift? | Offering it makes the frozen basket feel living without lying about the backtest |

---

## 7. Slices

| Slice | Scope | DoD |
|---|---|---|
| **1 — Rename** | "Promote to strategy" → "Build a strategy for one name"; three outcomes rendered as a named set with the Keeps column stated in copy | The results surface says what each door keeps; existing promote behaviour byte-unchanged |
| **2 — Extract the overlay brick** | Lift `buildOverlayStrategyJson` + the card grid out of `overlay-picker.tsx` into a shared brick | `portfolio_mode` behaviour byte-unchanged; the brick mounts in two places |
| **3 — Trade it** | Screen basket → top-K → overlay pick → existing backtest → review → save | A technical *and* a fundamental basket both reach a saved portfolio strategy; `rebalance` excluded with a stated reason; below-minimum baskets refuse with the reason |
| **4 — Drift notice** | Set difference between `current_basket` and the strategy's frozen `inherited_universe`, rendered on `/screens/{id}` and the strategy page | A screen whose basket has moved says so on both surfaces |

Slices 1 and 2 are independent and can land in either order. Slice 3 depends on 2.
Slice 4 depends on 3.

---

## 8. What would make this proposal wrong

If a screen is meant to be a **discovery tool and nothing more** — a way to find names
you then research individually — then Trade-it should not exist, and the correct fix is
slice 1 alone: rename the button, stop implying a screen becomes a strategy, and let
"Watch it" be the only thing a screen persists as.

That is a legitimate product position. It should be decided deliberately rather than
inherited from a button label.
