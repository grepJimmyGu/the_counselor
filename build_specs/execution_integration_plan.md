# Execution — the integration plan

**Date:** 2026-08-21
**Status:** plan. Nothing built from this yet.
**Supersedes:** the sequencing in `daily_path_v1.md` §4 (its slices are done).
**Companion:** `DRAFT_pm_execution_user_path.md` — the user-path design this
is the engineering plan for.

---

## 1. What five days built, as one system

Ten merged PRs. They are not ten features — they are one spine, built
back-to-front:

```
        SIGNAL              DECIDE               ORDER            RECONCILE
   ┌──────────────┐   ┌────────────────┐   ┌──────────────┐   ┌─────────────┐
   │ signal_cron  │   │ UnresolvedExits│   │  ExitTicket  │   │ confirm-exit│
   │  (entry)     │──▶│  (can't be     │──▶│      +       │──▶│ shares      │
   │ daily_       │   │   dismissed)   │   │  PlaceOrder  │   │ decrement   │
   │ position_jobs│   │ "I'm holding"  │   │  (2-step)    │   │ broker sync │
   │  (exit)      │   │ declare form   │   │              │   │             │
   └──────────────┘   └────────────────┘   └──────────────┘   └─────────────┘
     #327 #333          #329 #331             #332 #336          #328 #334
```

Two flows feed the spine and both currently stop short of it:
`custom_build_mode` (compose your own rules) and `one_asset_mode` ("try a
template"). They differ in one way that matters — a composed strategy can
carry an exit ladder, a template never does.

Underneath, three PRs made the numbers on that spine true rather than
plausible: #325 (one evaluator, so the backtest and the monitor cannot
disagree), #326 (exits fill at the next open, carrying the overnight gap),
#330 (costs charged by default; methodology stamped on results).

**THE PIECES WERE BUILT TO COMPOSE, AND THEY DO.** This is the reason the
remaining work is small:

| Producer | Consumer | Fits because |
|---|---|---|
| `BrokerPosition` (#334) | `declare_position` | carries `units` + `average_purchase_price` — symbol, shares, entry price, exactly the three required fields |
| `UnresolvedExit` (#329) | `ExitTicket` (#332) | derived from `trade_log`, so the ticket cannot describe a position that no longer exists |
| `ExitTicket.quantityFor` | `PlaceOrder` (#336) | the ticket refuses a quantity when holdings are unconfirmed, and the order button is gated on the same condition — it cannot offer to send a number the ticket won't state |
| `evaluate_bar` (#325) | backtester + daily monitor | one implementation, so "sell a third" means one thing everywhere |

Nothing here needs rebuilding to connect. The composition is already
written; what is missing is a way in.

---

## 2. What is actually missing — three links

Verified against the code, not assumed.

**A. The connect button.** `POST /api/snaptrade/connect` exists, works, and
has **zero callers** — not even a helper in `lib/api.ts`. Every downstream
condition of `<PlaceOrder>` is satisfiable except `status.registered`,
which requires this call. One link missing from the middle of a complete
chain.

**B. A stale gate on the page home links to.**
`app/account/strategies/[id]/page.tsx:44` still reads
`bar_resolution !== "daily"`, the condition #331 replaced on the public
page. `SavedStrategiesTile:231` sends **every** SignalCard click there. So
the most natural route to your own strategy is precisely the one that hides
the dashboard.

**C. The post-save handoff.** BOTH strategy flows end at `save` with
`next: () => null` — `custom_build_mode` and `one_asset_mode` alike. A user
who has just built or picked a strategy is returned to a detail page with no
statement of what happens next.

**D. Templates produce no exit ladder, and the ladder is the gate.**
`recommended-templates.ts` carries no `exit_ladder`. Only `custom_build_mode`
renders `<ExitLadderEditor>` (inside its canvas); `one_asset_mode` and the
strategy-builder modal do not. `DEFAULT_EXIT_LADDER` exists in the backend
but is never APPLIED — its only consumer is `signal_combo_matcher.py:123`,
which returns it as advisory `exit_ladder_defaults` rather than writing it
onto a saved strategy.

So a template-launched strategy saves and backtests normally, and then:
`declare_position` 400s ("nothing to monitor against"), the dashboard will
not render, and `daily_position_jobs` skips it at `if not ladder: continue`.
**The most prominent path into the product dead-ends for execution, and does
so silently** — the user gets a working backtest with no indication the
trading half was never available to them.

That is the whole list. Four links, one of them a single line.

---

## 3. The plan

Four steps. Each is independently shippable and independently valuable, and
none of them rewrites anything already merged.

### Step 0 — the one-line unblock
`app/account/strategies/[id]/page.tsx`: gate on the exit ladder, pass
`barResolution`. Mirrors what #331 did to the public page.

Why first: home's own strategy tile links here, so every other step is
partly invisible until it lands. One file.

### Step 1 — connect a broker
`lib/api.ts` gains `connectBrokerage()`; a `<ConnectBrokerage>` component
calls it and sends the user to the returned portal.

Two mounts, per the PM design:
- inside `portfolio_mode`'s `upload` step, as a peer to "add a ticker" —
  NOT a mandatory first step, and with its own exit ("just track these")
- permanently in `/account`, because a connection is a standing setting and
  a user who declines during a flow needs somewhere to change their mind

Plus the return path: SnapTrade redirects back, and that landing needs to
re-read status and resume rather than dropping the user on a cold page.

**This is the step that makes #334 and #336 reachable.** Both are merged and
neither has ever rendered.

### Step 2 — portfolio_mode consumes real cost basis
`portfolio_mode` currently collects `{ticker, weight}` and marks
`cost_basis_per_share` display-only, which would **discard**
`average_purchase_price` — the field that makes connecting worth anything.

Connected holdings feed `inherited_universe` (which the overlays already
consume unchanged) AND carry cost basis forward to `declare_position`.

### Step 3 — the shared `track` step

ONE step, used as the terminal step by BOTH `custom_build_mode` and
`one_asset_mode`. Not two implementations — the whole reason the rest of
this system connects without rework is that its pieces are shared, and a
second copy of this step would drift the same way the exit-ladder logic did
before #325.

Three doors:
- **Watch it** — entry signals on, nothing tracked yet
- **I already hold this** — declare form, prefilled from the broker if
  connected
- **Just save it** — today's behaviour, no nag. A backtest is a legitimate
  terminal artifact and most users stop here.

**IT SEEDS THE LADDER WHEN THERE ISN'T ONE (decided 2026-08-21).** A
template strategy arrives here with no exit rule, and without one it cannot
be tracked at all. The step offers `DEFAULT_EXIT_LADDER` — ATR-scaled, stop
at 2x, targets at 3x and 5x, already clamped for sanity — pre-filled and
editable, shown only to a user who picked one of the first two doors.

Two rejected alternatives, and why:

  - *Apply the default silently at save.* Tempting, since the constant
    exists. But it attaches a stop nobody chose to a strategy someone may
    only be browsing, and a stop the user did not pick is one they will not
    believe when it fires.
  - *Add a ladder step to `one_asset_mode`.* A fifth step in a flow whose
    entire appeal is being short, paid by every user including the majority
    who are only looking.

Surfacing it inside `track` asks the question at the only moment it means
something: when someone has said they want this watched.

DELIBERATELY NOT AN ORDER STEP. At save time the strategy holds no position
and may name no symbol, so `<PlaceOrder>` would render nothing. Offering to
trade there would be an empty gesture.

### Step 4 — `/account/positions`
The destination the spine has never had. Unresolved exits first (the only
thing owing a decision), tracked positions below with their next tier,
broker holdings that are not tracked in a third group.

Under `/account`, not top-level: a permanent trading advertisement to
signed-out visitors is a different product from this one.

---

## 4. The invariants that keep it consistent

New work must not break these. Two are enforced by tests that fail the
build; the rest are design rules that a reviewer has to hold.

| Invariant | Enforced by |
|---|---|
| No order without a preview the user saw | `test_snaptrade_readonly_guard.py` — `place_force_order` banned outright |
| No order from anywhere but a person's request | same test — nothing under `jobs/` may reference SnapTrade |
| One rule engine for exits | `exit_ladder.py`; both consumers import it |
| Refuse rather than guess | `quantityFor` returns `ambiguous` when holdings are unconfirmed, and `<PlaceOrder>` is gated on `exact` |
| Unresolved state is DERIVED, never stored | `list_unresolved_exits` reads `trade_log`; there is no row to dismiss |
| Livermore never implies it transacted | §11 register; "The strategy signalled…", never "we recommend" |
| Broker holdings are the BROKER's view | never merged into a `PositionState` — a Livermore position carries a strategy and a ladder; a holding does not |

---

## 5. Open decisions

1. **Does the execution surface show when there is nothing to resolve?**
   `<UnresolvedExits />` renders nothing today, so a user with a tracked
   position sees no evidence the feature exists until something fires. The
   PM pass argues for keeping it quiet; the counter-argument is
   discoverability. Yours.

2. **`SNAPTRADE_TRADING_ENABLED` — when?** Everything up to the ticket works
   with it off. Flipping it is the one step that moves real money, and the
   spec says counsel first.

3. **The hero chip says "No live trading."** It becomes false the day the
   flag flips, and nobody owns it.

4. **Is the manual declare form kept?** `daily_path_v1.md` Stage 2 implies
   the broker connection retires it. The PM pass disagrees, and so do I: a
   brokerage connection is a high-trust action many users will decline, and
   the manual path is the fallback for everyone who does.
