# PRD-29 — Order intent, and Path 1 execution

**Status:** spec. Nothing built from this yet.
**Date:** 2026-08-25
**Supersedes:** the build order sketched in `PRD-28` §5 beyond Step 4.
**Companion artifact:** "The order desk" (walkthrough of all three paths).

---

## 0. How the facts below were established

An earlier pass at this design asserted three things about the product that
turned out to be false, and one of them became the headline of a walkthrough
document. All three had the same shape: **a file was read, and the rest of
the chain was inferred from it.**

| claim | reality | how the truth was found |
|---|---|---|
| "Multi-position tracking is a hard blocker — a change to what a tracked strategy *is*" | Already supported end to end since #327 | read the model, the monitor loop, the dashboard, and `list_open_positions` |
| "Promoting a screen saves a 10–15 name strategy" | Promote narrows to ONE name — `universe: [symbol]` | read `custom-build-strategy-json.ts:158` |
| "The overlay produces a per-holding sell signal we can use" | It reports every holding as held, whichever failed | **ran `_extract_signal`** |

`CLAUDE.md` already carries the rule that would have prevented all three —
*"Trace the path before blaming a known problem… State the cause only once
you have run the failing call yourself."* It was written after the same
mistake was made twice on the P/E filter.

**Every product fact in this document was executed, not read.** Where a
claim rests on reading a file, the file and line are cited so the next
person can check it in one command.

### Verified by running it

```
declare_position on a portfolio overlay
  -> 400: "This strategy has no exit ladder, so there is nothing to
           monitor a position against."

_extract_signal(portfolio_defensive_overlay, universe=[NVDA,MSFT,KO,XOM])
  -> {"holdings": [NVDA, MSFT, KO, XOM]}          # all four, always
  -> which ones failed their moving average?  UNKNOWABLE
```

### Verified by reading a cited line

| fact | where |
|---|---|
| Overlays build `risk_management: {}` — no exit ladder, ever | `overlay-picker.tsx:121` |
| `portfolio_mode` ends at `summary`, which pushes to `/workspace` | `portfolio-mode.ts:52`, `portfolio-summary.tsx:139` |
| The daily monitor skips any strategy with no ladder | `daily_position_jobs.py:122` |
| `Holding` carries `shares` and `cost_basis_per_share` | `contracts.ts:567` |
| …and `rowsToHoldings` carries both through from the broker | `portfolio-upload.tsx:76` |
| Positions are stored per **(strategy, symbol)** — N per strategy | `position_state.py:43` |
| `<PlaceOrder>` is mounted once, hardcoded `action="SELL"` | `exit-ticket.tsx:208` |
| `get_order_impact` accepts `stop` and `notional_value` | snaptrade-python-sdk 13.0.3 |
| `place_complex_order` has **no** preview twin | same |

---

## 1. The finding this whole spec turns on

**For an overlay, the overlay IS the exit rule.**

A defensive overlay says *"hold it while it's above its 200-day, otherwise
be in cash."* That is not a percent-from-entry ladder, and the two are not
interchangeable:

| | exit ladder | overlay rule |
|---|---|---|
| measured from | the user's entry price | the price series itself |
| fires on | −8% from what you paid | close crossing below its own MA |
| depends on your entry | yes | **no** |
| lives in | `risk_management.exit_ladder` | `rules[]` + `strategy_type` |

So the fix for Path 1 is **not** "make overlays get an exit ladder." Bolting
a ±% ladder onto a defensive overlay would replace the user's strategy with
a different one and then monitor *that*. The exits would fire on dates the
backtest never modelled, which is precisely the divergence `exit_ladder.py`
was extracted to prevent.

**Path 1 needs a second evaluator, beside the ladder evaluator, that
evaluates an overlay's own rule per holding.**

---

## 2. Scope

### In

- `OrderIntent` — one shared object every producer emits
- `<OrderTicket>` — one component, replacing the exit-only ticket
- Overlay position tracking, for the **defensive** family only
- The overlay evaluator, and its `pending_confirmation` events
- Bulk declare, prefilled from connected broker holdings

### Out, deliberately

- **Buys.** Path 1 is sell-only. Every holding is already owned, so no
  sizing question exists. Buys are PRD-30.
- **Rotation, dual-momentum, rebalance and stability-tilt overlays.** Those
  are cross-sectional — a name leaves because another ranked above it, not
  because of anything that name did. They need a rebalance object and they
  produce buys. See §7.
- **Resting stops at the broker.** Separate decision, separate PRD.
- **Multi-position tracking.** Already works; nothing to build.

### The overlay family this covers

`overlay-picker.tsx:78-104` builds six overlays. Only two are per-holding:

| overlay | rule | sell signal |
|---|---|---|
| **`defensive`** | close > 200-day MA | per-holding — **in scope** |
| **`defense_first`** | same, with a 0.5 threshold | per-holding — **in scope** |
| `rotation` | top 3 by 126-day return | cross-sectional — out |
| `dual_momentum` | rotation + 252-day absolute filter | cross-sectional — out |
| `stability_tilt` | 63-day, 0.25 | cross-sectional — out |
| `rebalance` | target weights, no rules | produces buys — out |

Shipping the defensive family alone is a complete, honest product: *"tell me
when one of my holdings loses its trend."*

---

## 3. `OrderIntent` — the shared object

Every producer emits this. One ticket renders it. One preview-and-approve
path sends it.

```python
class OrderIntent(BaseModel):
    # what to do
    side: Literal["BUY", "SELL"]
    symbol: str
    # exactly one of these
    units: Optional[float] = None
    notional: Optional[float] = None      # dollars; SnapTrade takes it natively

    order_type: Literal["Market", "Limit", "Stop", "StopLimit"] = "Market"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: Literal["Day", "GTC"] = "Day"

    # why — this is what makes it a Livermore ticket rather than a tip
    strategy_id: str
    strategy_title: str
    reason: str                           # "Lost its 200-day moving average"
    as_of_date: str                       # the session the rule was evaluated on
    reference_price: Optional[float] = None
    position_id: Optional[str] = None     # sells only

    # how stale the numbers are, in words the ticket prints verbatim
    staleness: Literal["daily_close", "intraday_delayed"]
```

**`units` xor `notional`, enforced by a validator.** A sell always has
units — you sell what you hold. A buy will use notional. Allowing both would
mean the ticket displays one number and sends another.

**`reason` is required and is prose.** "Lost its 200-day moving average" is
a sentence a user can check against their own chart. `"rule_0_false"` is
not. The exit ticket already does this well with `tier_label`; the intent
generalises it.

### Where order types come from

| producer | side | order type | price |
|---|---|---|---|
| Overlay: holding lost its MA | SELL | Market | — the signal is "be in cash" |
| Ladder: stop tier | SELL | **Stop** | `entry × (1 + trigger_pct)` |
| Ladder: target tier | SELL | **Limit** | `entry × (1 + trigger_pct)` |
| Entry signal (PRD-30) | BUY | Limit | the signal's close |

**The exit ladder is already an order spec.** `trigger_pct: -0.08` on a
$118.40 entry is `Stop @ 108.93`. Today the ticket sends a market order after
the fact; the price was computable all along.

---

## 4. `<OrderTicket>` — one component

Replaces `<ExitTicket>`, which is the same thing with a hardcoded side.

**What it must keep from the exit ticket** (these were hard-won):

- Refuses to print a share count it cannot derive. `quantityFor` returns
  `ambiguous` when an earlier tier fired unconfirmed, and the Place button
  is gated on `exact`. That rule survives verbatim.
- Never rounds a share count **up**.
- Prints the staleness story that matches how the position is monitored —
  a daily exit was measured on a completed session's close and is acted on
  at the next open; it is not a "delayed quote."
- **Copy always works**, whether or not order placement is enabled. The
  ticket is useful at any broker. This is what makes the component
  shippable before anything else in this PRD.

**What is new:** side, order type, and the two price fields render from the
intent rather than being assumed. A `Stop` intent shows "Stop · $108.93"; a
market sell shows what it shows today.

---

## 5. The overlay evaluator

New module, beside `exit_ladder.py`, same shape and the same discipline:
one implementation, imported by every consumer.

```python
# app/services/overlay_rules.py

def evaluate_holding(*, strategy_json, symbol, frame) -> Optional[OverlayFire]:
    """Does this holding still satisfy the overlay's rule on this bar?

    `frame` is the daily price frame the monitor already loads. Returns a
    fire when the holding has FALLEN OUT, None while it still qualifies.
    """
```

**It must produce the same answer the backtester does.** The engine computes
`weight = target_weight if close > MA else 0` (`engine.py:965`). The
evaluator has to agree with that line, or the live monitor and the backtest
will disagree about the same day — the exact failure that cost a week before
`exit_ladder.py` was extracted.

A test pins them together: run the engine over a fixture, run the evaluator
over the same bars, assert the fall-out dates match.

### Wiring into the daily monitor

`daily_position_jobs.py:122` currently does `if not ladder: continue`. That
becomes a branch:

```python
if ladder:
    fires = evaluate_bar(ladder=ladder, entry_price=pos.entry_price, ...)
elif is_overlay(sj):
    fires = evaluate_holding(strategy_json=sj, symbol=pos.symbol, frame=frame)
else:
    continue        # genuinely nothing to monitor
```

Per-position error isolation already exists and is kept.

### `declare_position` stops requiring a ladder

Its guard becomes: a strategy must have **an exit ladder OR be a supported
overlay**. Today it 400s on every overlay, which is why Path 1 has never
been reachable. The message stays specific about which is missing.

---

## 6. The user path, corrected

| # | step | state |
|---|---|---|
| 1 | Home → Upload Portfolio → connect broker or type holdings | ships (#338, #339) |
| 2 | Diagnose → pick the defensive overlay → summary | ships |
| 3 | Summary hands off to `/workspace`, which backtests and saves | ships |
| 4 | **`track` step, reached from portfolio_mode** | **NEW** |
| 5 | **Bulk declare — a checklist of the holdings, prefilled** | **NEW** |
| 6 | Monitored after each close, against the overlay's own rule | **NEW (§5)** |
| 7 | "Three of your twelve lost their trend" → three SELL intents | **NEW** |
| 8 | Review each ticket → copy it, or preview and send | **NEW (§4)** |

### Step 4 — `track`, for portfolio_mode

`portfolio_mode` has no `track` step today; it ends at `summary`
(`portfolio-mode.ts:52`). PRD-28 Journey A specified this and it was only
wired into `custom_build_mode` and `one_asset_mode`.

Two changes are needed and both are small:

1. `<FlowTrack>`'s ladder stage is **skipped for overlays** — the overlay is
   already the exit rule, so there is nothing to seed and nothing to sign
   off. The three doors and the confirmation stay.
2. `<FlowTrack>` sends `symbol: symbol ?? ""` (`flow-track.tsx:236`), which
   is an empty string for any multi-name strategy. Latent today because both
   flows using it are single-name; it goes live the moment portfolio_mode
   reaches it. Bulk declare replaces that form for overlays.

### Step 5 — bulk declare

**The broker already told us.** `context.holdings` carries `ticker`,
`shares` and `cost_basis_per_share` for every position the broker reported
(`portfolio-upload.tsx:76`). The user confirms rather than types.

```
Which of these are you tracking?

  [x] NVDA    120 sh   @ $118.40      from Schwab
  [x] MSFT     40 sh   @ $402.10      from Schwab
  [ ] KO      200 sh   @ $  —         cost basis needed
  [x] XOM      85 sh   @ $103.55      from Schwab

  Exits are measured from what you paid, so a missing cost basis
  has to be filled in before that holding can be tracked.

  [ Track 3 holdings ]        [ Skip for now ]
```

Rows without a cost basis are **unchecked and blocked**, not silently
defaulted — the whole point of connecting a broker is that these are the
user's real numbers. Manual entry stays available for the rows that need it.

`POST /api/saved-strategies/{id}/positions` is called once per checked row.
Partial failure reports per row and keeps the rest.

---

## 7. What this deliberately leaves broken

**Cross-sectional overlays still cannot be tracked.** Rotation, dual
momentum and stability tilt decide a name's fate by comparing it to the
others, so "did NVDA fall out" is not answerable per holding — and when it
does fall out, something else takes its place, which is a buy.

That is the rebalance problem, and it needs an object this PRD does not
introduce. The `track` step must therefore **refuse cross-sectional overlays
explicitly**, with a sentence saying tracking is not available for that
overlay yet, rather than accepting the declare and monitoring nothing.

A silent no-op here would be worse than the current 400.

---

## 8. Build order

Each step independently shippable.

| # | build | why here |
|---|---|---|
| 1 | `OrderIntent` + `<OrderTicket>`, replacing `<ExitTicket>` | Pure refactor of a shipped surface, and it lands with placement still off — Copy works regardless |
| 2 | `overlay_rules.py` + the backtest-agreement test | The evaluator is the risky part; build it against the engine before anything depends on it |
| 3 | Monitor branch + `declare_position` guard change | Positions become trackable and watched |
| 4 | `track` for portfolio_mode + bulk declare | The path becomes reachable |
| 5 | Overlay fires → SELL intents on the ticket | Path 1 closes |

Step 2 is where the risk is. Steps 1, 3 and 4 are small.

---

## 9. Open decisions

1. **What does a defensive overlay sell — all of it, or the target weight?**
   The engine sets `weight = 0` on a fail, which is "all of it." Confirming
   that reading matters, because the ticket prints a share count.

2. **Does a holding that recovers get re-entered?** The engine would put
   weight back on when the close crosses above the MA again. That is a BUY,
   which this PRD excludes — so a recovered holding currently produces
   nothing. The honest v1 is to say so on the ticket: *"if it recovers,
   you'll need to buy it back yourself."*

3. **What happens to a tracked holding the user sells outside Livermore?**
   The next broker sync sees the position gone. Today nothing reconciles it.

4. **Does the `track` step fire for an overlay the user reached via
   `/workspace`?** The workspace save path does not run the flow, so a user
   who saves from there skips `track` entirely and lands on the dashboard.
   Either the dashboard offers bulk declare too, or the workspace save
   routes back into the flow.
