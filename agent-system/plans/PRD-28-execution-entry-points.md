# PRD-28 — Execution entry points

**Status:** Steps 0–3 shipped (#337, #338, #339, #340, and the `track`
PR). Step 4 (`/account/positions`) and the four §7 decisions remain.
**Date:** 2026-08-21
**Companions:** `build_specs/execution_integration_plan.md` (engineering
plan), `build_specs/DRAFT_pm_execution_user_path.md` (PM design)

---

## 1. What this is, and what it is not

Ten PRs over five days built a complete execution spine — signal, decide,
order, reconcile — and every piece of it composes with the next. **This PRD
adds no capability. It adds the ways in.**

Two merged features have never rendered for a single user:

- SnapTrade brokerage connection (#334)
- Order placement (#336)

Not because they are broken. Because `POST /api/snaptrade/connect` has zero
callers, so `status.registered` is false for everyone, so every downstream
condition fails. One missing link in the middle of a finished chain.

Everything below is entry points, one shared step, and one destination.

---

## 2. THE TWO SIGN-OFF POINTS

Founder decision, 2026-08-21: **saving a strategy and placing an order both
require explicit user sign-off.**

Neither may be a side effect of some other click. And neither should rely on
a developer remembering to render a confirmation — both are enforced by the
shape of the API, so a client that forgets cannot transact.

### 2.1 Place order — already structural (#336)

`get_order_impact` -> `trade_id` -> `place_order(trade_id)`. The placing
function takes ONLY a trade id: there is no argument for a symbol or a
quantity. So an order can only ever be one that was priced first, and
pricing is what puts the numbers on screen. `place_force_order` — the
no-preview path — is banned by `test_snaptrade_readonly_guard.py`.

### 2.2 Save strategy — must become structural HERE

The `track` step writes an exit ladder onto a strategy the user already
saved. That is a mutation of their work and it must be confirmed.

**The rule, mirroring 2.1:** the attach endpoint accepts the ladder ONLY as
an explicit payload. There is no server-side path that applies a default.

```
POST /api/saved-strategies/{id}/exit-ladder   { exit_ladder: [...] }
```

Because the server never invents a ladder, the ladder that lands on a
strategy is always one the client sent — and the client can only send what
it rendered. The confirmation is a consequence of the API shape rather than
a promise about the UI.

A guard test asserts no code path outside this endpoint writes
`risk_management.exit_ladder` on an existing saved strategy.

---

## 3. The user path

### Journey A — "I already own things, watch them"

| Step | Surface | State |
|---|---|---|
| 1 | Home -> **Quant Rules** -> **Upload portfolio** | exists (`quant-upload-portfolio`) |
| 2 | `/flow/portfolio_mode`, step `upload` | exists |
| 3 | **Connect your brokerage** card, PEER to "add a ticker" | **NEW** |
| 4 | SnapTrade portal — user signs in at their OWN broker | exists (#334) |
| 5 | Return to the flow; holdings filled in WITH cost basis | **NEW** |
| 6 | diagnose -> overlay -> summary | unchanged |
| 7 | **Track these** -> `track` step | **NEW** |

The connect card carries its own exit ("add them myself"). A brokerage
login is a high-trust action and a meaningful share of users will decline
it; the manual paths stay exactly as they are.

### Journey B — "I built or picked a strategy"

| Step | Surface | State |
|---|---|---|
| 1 | Home -> **Quant Rules** -> **Build** or **Try a template** | exists |
| 2 | `custom_build_mode` or `one_asset_mode` | exists |
| 3 | ... -> backtest -> review -> save | unchanged |
| 4 | **`track`** — the shared terminal step | **NEW** |

### Journey C — "My stop fired" (already runs end to end)

| Step | Surface | State |
|---|---|---|
| 1 | `daily_position_jobs` detects it after the close | exists (#327) |
| 2 | Email + in-app banner | exists (#328) |
| 3 | Home -> `<UnresolvedExits />` | exists (#329) |
| 4 | **Show order ticket** | exists (#332) |
| 5 | **Place this order at your broker** | **built (#336), never rendered** |
| 6 | preview -> real commission and cash-after -> **Send it** | exists (#336) |
| 7 | next morning's sync confirms the fill | exists (#334) |

Nothing in Journey C is new code. It becomes reachable the moment Journey A
step 3 exists.

### Journey D — "Where is my stuff"

| Step | Surface | State |
|---|---|---|
| 1 | Home -> **Your Livermore** -> My strategies | exists |
| 2 | `/account/strategies/{id}` | **BROKEN — see Step 0** |
| 3 | `/account/positions` | **NEW** |

---

## 4. The shared `track` step

ONE step. Both `custom_build_mode` and `one_asset_mode` end in it. Not two
implementations — a second copy would drift exactly the way the exit-ladder
logic drifted before #325, and that divergence cost a week to find.

### 4.1 Three doors

- **Watch it** — entry signals on, nothing tracked yet
- **I already hold this** — declare form, prefilled from the broker when
  connected
- **Just save it** — today's behaviour, no nag. A backtest is a legitimate
  end in itself and most users stop here.

### 4.2 Seeding the ladder

A template strategy arrives with no exit rule. `recommended-templates.ts`
carries none, `one_asset_mode` never offered one, and `DEFAULT_EXIT_LADDER`
exists in the backend but is applied nowhere — its only consumer returns it
as advisory data.

Without a ladder the strategy cannot be tracked at all: `declare_position`
400s, the dashboard will not render, and the daily monitor skips it at
`if not ladder: continue`.

So `track` offers one — ATR-scaled, stop at 2x, targets at 3x and 5x,
clamped — **pre-filled, editable, and shown only to a user who chose one of
the first two doors.**

It is saved ONTO THE STRATEGY, not onto the position. Otherwise two
strategies with the same name behave differently depending on whether
anyone happened to track them, and that split is invisible until it
confuses somebody badly.

Per §2.2 this is an explicit confirm that names what is changing. The screen
says the strategy is being updated; it does not happen because the user
clicked "watch it".

**Rejected, and why — the reasoning is the part that gets lost:**

- *Apply the default silently at save.* Attaches a stop nobody chose to a
  strategy someone may only be browsing. A stop the user did not pick is one
  they will not believe when it fires.
- *Add a ladder step to `one_asset_mode`.* A fifth step in a flow whose
  entire appeal is being short, paid by every user including the majority
  who are only looking.

### 4.3 Not an order step

At save time the strategy holds no position and may name no symbol.
`<PlaceOrder>` would render nothing. Offering to trade here would be an
empty gesture, and the founder's "order steps on every strategy portal"
applied literally would put a dead button on four surfaces.

---

## 5. Build sequence

Each step independently shippable, each independently valuable.

### Step 0 — the one-line unblock
`app/account/strategies/[id]/page.tsx:44` — gate on the exit ladder, pass
`barResolution`. Mirrors what #331 did to the public page.

FIRST because `SavedStrategiesTile:231` sends every SignalCard click here,
so Journeys B and D land on a page that hides the feature until this lands.

### Step 1 — connect a broker
`lib/api.ts` gains `connectBrokerage()`. `<ConnectBrokerage>` calls it and
sends the user to the portal. Two mounts: `portfolio_mode` step 1, and
permanently in `/account`. Plus the return path, which must re-read status
and resume rather than dropping the user cold.

**This is the step that makes #334 and #336 reachable.**

### Step 2 — portfolio_mode keeps the cost basis
It currently marks `cost_basis_per_share` display-only, which would discard
`average_purchase_price` — the field that makes connecting worth anything.
Connected holdings feed `inherited_universe` (overlays consume it unchanged)
AND carry cost basis to `declare_position`.

### Step 3 — the shared `track` step ✅
Per §4. Includes `POST /{id}/exit-ladder` and its guard test.

**Cost three prerequisite bug fixes (#340) that the spec did not
anticipate**, each of which independently blocked it:

1. `ladderFromNatr` emitted `trigger_pct` in PERCENT where every
   consumer reads a FRACTION, so every calculated ladder was inert —
   a 3%-ATR stop sat at -600%. §4.2 planned to REUSE that function as
   the seeder, which would have put the bug on every tracked strategy.
2. `save` refused to create a `SavedStrategy` row for daily
   strategies. The third daily gate after #331/#337, and the deepest:
   no row meant an empty "My strategies" page.
3. `save` also refused one for ladder-less strategies, which made
   §4.2 circular — you needed a ladder to get a row, and a row to
   save a ladder.

The lesson worth keeping: §4.2's instinct to reuse the existing
seeder rather than write a second one was right, and it is what
surfaced the unit bug. A fresh implementation would have been
correct in isolation and left the promote path broken.

### Step 4 — `/account/positions`
Unresolved exits first, tracked positions with their next tier, untracked
broker holdings third. Under `/account`, not top-level — a permanent
trading advertisement to signed-out visitors is a different product.

---

## 6. Invariants this must not break

| Invariant | Enforced by |
|---|---|
| No order without a preview the user saw | `test_snaptrade_readonly_guard.py` |
| No order from anywhere but a person's request | same — nothing under `jobs/` |
| **No ladder written without an explicit payload** | **NEW guard, §2.2** |
| One rule engine for exits | `exit_ladder.py`, imported by both consumers |
| Refuse rather than guess | `quantityFor` -> `ambiguous`; `<PlaceOrder>` gated on `exact` |
| Unresolved state is DERIVED | `list_unresolved_exits` reads `trade_log` |
| Broker holdings stay the BROKER's view | never merged into a `PositionState` |
| Livermore never implies it transacted | §11 register |

---

## 7. Open decisions

1. **Does the execution surface show when nothing is unresolved?**
   `<UnresolvedExits />` renders nothing today, so a user with a tracked
   position sees no evidence the feature exists until something fires.

2. **When does `SNAPTRADE_TRADING_ENABLED` flip?** Everything up to the
   ticket works with it off.

3. **The hero chip says "No live trading."** False the day the flag flips,
   and nobody owns it.

4. **Does the manual declare form survive?** `daily_path_v1.md` Stage 2
   implies the connection retires it. The PM pass and this spec both say
   keep it — a brokerage login is exactly the kind of thing users decline.
