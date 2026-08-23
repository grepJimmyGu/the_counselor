# DRAFT — The execution user path

**Status:** DRAFT for founder review. Design only, no code. Not approved.
**Date:** 2026-08-23
**Owner:** PM.
**Answers:** the three asks — (1) Upload portfolio should offer a SnapTrade connection, (2) strategy portals under Quant Rules should have order/placement steps, (3) where all of this connects to the existing home page.
**Sits under:** `build_specs/daily_path_v1.md` (Stage 2 Connect, Stage 4 Act, Stage 5 Reconcile). That file owns the engine and the slices; this file owns **where the user goes**.
**Legal floor:** `build_specs/research_execution_v0_signals_and_alerts.md` §11.

---

## 0. Two corrections to the premise, before anything else

**0.1 — "Upload portfolio" was never removed from home. It is live right now.**

`apps/web/src/components/home/home-quant-strategies.tsx:131` calls
`startFlow("portfolio_mode", { initialContext: { fromTrigger: "home/upload_portfolio" } })`
from a tile with `data-testid="quant-upload-portfolio"`, under the **Overlays** group of the Quant Rules block. `git log -S` puts it there in **#319**, and it survived #323. The old `home-focus-sections.tsx` tile was *consolidated into Quant Rules*, not deleted.

There is a second live entry: `components/strategy-builder/strategy-builder-modal.tsx:1002`, the "Use my portfolio →" option on multi-ticker templates. `/test/flows/portfolio` is a third, dev-only.

This matters more than a footnote. **The founder's ask #1 and ask #2 land on the same block.** "Upload portfolio should connect via SnapTrade" is a change to a tile that already sits inside "any strategy portal under Quant Rules". We are not adding a destination; we are finishing one.

(Dead code, separately: `lib/flows/bricks/entry-mode-picker.tsx` has zero non-test references. It offers a fourth way to launch the same three flows. Do not wire it up.)

**0.2 — Order placement is already on the home page. It has just never rendered.**

`page.tsx:140` renders `<UnresolvedExits />` → `exit-ticket.tsx:208` renders `<PlaceOrder>` → `place-order.tsx` calls preview then place. Merged as #336. It renders `null` unless **five** conditions hold at once:

1. the user has an unresolved exit at all (`items.length === 0 → null`),
2. the ticket's quantity is unambiguous (`q.kind === "exact"`),
3. `snaptrade_trading_enabled` is true (default `False`, `config.py:51`),
4. the user is `registered` with SnapTrade,
5. the connected broker reports holding that symbol.

Condition 4 is unsatisfiable today: `POST /api/snaptrade/connect` exists, returns `{redirect_uri}`, and **has zero callers — there is not even a helper for it in `lib/api.ts`.** So the shortest description of the work is not "design an execution path". It is: *the path exists end to end and one link is missing from the middle of it.*

---

## 1. THE MAP

Home blocks in render order, what each promises, and whether execution belongs on it.

| # | Block | What it promises today | Execution? |
|---|---|---|---|
| 1 | `SmartSearchBox` | "A ticker, a company, or a screen — type it." Answer a question. | **No.** A search box that can place an order collapses research and execution into one keystroke. It is also the first surface a compliance reviewer opens. And search has no notion of a position, a quantity, or a rule. |
| 2 | `HomeMarketStrip` | Index levels. Orientation. | **No.** It is a tape. |
| 3 | `HomeMarketPulseBlock` "Moving today" | What moved; links to `/stocks/[ticker]`. | **No.** Buying today's biggest mover is the exact behaviour a rules-first product exists to replace. An order button here is the product contradicting its own thesis. |
| 4 | `HomeCuratedScreens` "Hot Market Picks" | "Click and see the names" → `/screen?template=…`. | **No.** A screen hit is a candidate, not a decision. Between it and an order sit a rule, an exit ladder, a backtest and a save. That gap *is* the product. |
| 5 | `HomeQuantStrategies` "Quant Rules" | "Backtest before you commit." Templates · Overlays + Upload Portfolio · Build your own. | **Yes — but at the END of the flows it launches, never on the tile.** The tile must keep promising a backtest. This is where Connect (ask 1) and the post-save branch (ask 2) both originate. |
| 6 | `MarketCatalysts` | Sentiment templates + news ticker. | **No.** These are `toolkit_id` templates with no `rules`; they cannot produce a stock list, let alone a quantity. |
| 7 | `UnresolvedExits` | "A strategy signalled an exit." A decision you owe. | **Yes. This is the primary execution surface and it already exists.** |
| 8 | `NotificationBanner` | Something happened; dismissible. | **No** — it links onward to the strategy page. Correct as is. |
| 9 | `HomeYourLivermore` | `SavedStrategiesTile` (SignalCards) + Community + Account. | **Secondary — the ENTRY half.** A SignalCard in `in_signal` state is literally "the strategy signalled an entry". |

### The one primary path

> **signal → decide → order → reconcile.**

Its home surfaces are `UnresolvedExits` (the exit half, live) and `SavedStrategiesTile`'s SignalCards (the entry half, live). Both are state-dependent. Neither is new.

Written out end to end:

```
Quant Rules → build → backtest → save
   → [NEW: track?]                       §3
   → daily job evaluates the ladder
   → entry signal  → SavedStrategiesTile SignalCard → declare form
     exit signal   → UnresolvedExits → ticket → PlaceOrder (if connected + enabled)
   → next morning's holdings sync reconciles          (daily_path_v1 Stage 5)
```

### Secondary paths

- **S1 — Quant Rules → Upload Portfolio → Connect broker.** Discovery route for the connection. §2.
- **S2 — `/account` → Connected brokerage.** Maintenance route: inspect, re-authorize, revoke. §2.
- **S3 — `/strategies/[slug]` and `/account/strategies/[id]`.** The per-strategy dashboard; the deep-link target for `?action=entered` / `?action=executed` emails.
- **S4 — `/account/positions`.** The missing cross-strategy destination. §5.

Every secondary path feeds *into* the primary one. None bypasses it. That is the test a proposed affordance has to pass.

### Direct pushback on the founder's own framing

The ask says **"any** strategy portal under Quant Rules … should have following steps on order trades and placement". Applied literally that is five surfaces: the template modal, `one_asset_mode`, `portfolio_mode`, `custom_build_mode`, and the screener. Four of the five terminate in an artifact that names **no tradeable quantity** — a backtest curve, a factor diagnosis, a ranked list. An order step on those either renders nothing or invents a number.

The honest version of the ask is: **one** portal (`custom_build_mode`, the one that ends in a saved strategy with an exit ladder) gets a step that decides *whether Livermore watches this*. Placement then happens later, on the surface that knows a position exists. Putting it anywhere earlier is the "every tile leads to trading" failure, and it is worse than having one clear path.

---

## 2. PORTFOLIO / CONNECT

### The decision

**Both — but the connection is a *peer input* to `portfolio_mode`'s upload step, not its mandatory first step; and it is *managed* in `/account`.** One component, two mounts. No third destination.

### Why not "connect first, then diagnose"

**a) `portfolio_mode`'s data contract throws away the payload that makes the connection worth having.**

`PortfolioUpload` collects `{ticker, weight}`. When no weight is given it pushes `{ ticker, shares: 1 }` (`portfolio-upload.tsx:72`) — a sentinel, not a share count. `Holding.cost_basis_per_share` is commented **"Display-only. Does not affect backtest."** (`contracts.ts:560`).

SnapTrade returns `units` **and** `average_purchase_price` (`BrokerPositionView`, `routes/snaptrade.py:53-59`) — which is exactly `{symbol, shares, entry_price}`, the three fields `declare_position` requires. If connect is only a faster way to fill the weights table, we discard the cost basis and gain a convenience. **Connect must write to two sinks:** the holdings table (for the overlay backtest) *and*, on an explicit user action, `PositionState` rows (for the monitor). The second sink is the whole point.

**b) The later steps are a legitimate destination, not the only one.**

Someone who just handed us their brokerage wants to see their holdings and have Livermore watch them. Making them sit through a factor diagnosis and an overlay picker first is charging them for a second product to get the first. **Connect needs an exit at step 1:** "these are your holdings — track them" without continuing to diagnose.

**c) A first-time visitor will not connect a brokerage, and the manual path must survive.**

Correct. Which is why connect is offered *above* the manual table, not *instead of* it, with the read-only claim on the button rather than in a modal after the click. Note this also puts me at odds with `daily_path_v1.md` Stage 2, which says connect "replaces hand-declared positions" — see §6.9.

**d) `/account` needs it for a different reason than discovery.**

A brokerage connection is a standing credential relationship. It has to be inspectable, re-authorizable and revocable in a permanent place. A wizard the user finished once is not that place. `/account` already renders Profile · Plan & Usage · Email · Billing as peer sections; **Connected brokerage** is a fifth of the same kind, showing `registered`, `connected_accounts`, `last_synced_at` from `GET /api/snaptrade/status`.

### Copy on the connect surface (§11-safe)

- Button: **"Connect your brokerage (read-only)"**
- Under it: "Livermore reads your holdings and cost basis so your strategies can watch what you actually own. Livermore does not place trades." (Change the second sentence at step 6 — see §7.)
- Never "we recommend", never "advice", never a claim about their financial situation.

### Rejected here

- **Making connect mandatory in `portfolio_mode`.** Converts a working flow into a trust paywall.
- **Renaming the tile to "Connect your broker".** Changes what the tile promises for the majority who will type tickers.
- **A `/portfolio` or `/broker` top-level route.** Two mounts cover it. A third destination is the sprawl that was objected to.

---

## 3. THE POST-SAVE STEP

Today: `custom_build_mode` `save` → `next: () => null` → `onComplete` → `window.location.assign('/strategies/{slug}')`.

### Why an order affordance here is the wrong instinct

Concretely, from the code: **at save time the strategy has no position, and for a screen-derived strategy may not name a single symbol at all.** `PlaceOrder` returns `null` unless the connected broker already reports holding the symbol (`place-order.tsx:138`). There is nothing to place. An order control here either renders nothing, or invents a quantity we have no basis for — and inventing a quantity from account value is the personalization line `daily_path_v1.md` §2 Q6 already drew.

A user who just ran a backtest has not decided to trade it. Most of them will never trade it. Designing this step around the minority is how the block stops being trustworthy.

### What is actually true at save time

The user has chosen rules and, if a ladder exists, an exit plan. The decision they genuinely face is **"do you want Livermore to watch this?"** — the join the entire daily path depends on, currently implicit and therefore usually never made.

### Design: one new step, `track`, between `save` and `onComplete`

Three answers, all first-class:

**1 — "Watch it. I'm not in it yet."** *(default, visually primary)*
The saved strategy is watched by the daily job; entry signals appear on `SavedStrategiesTile` as SignalCards. **No broker, no position, no ticket, no order.** This is the answer that makes the product work and it involves no execution at all.

**2 — "I already hold this."**
Opens the declare form prefilled with the strategy's symbol. **If a broker is connected**, offer the holding it already found — symbol / units / avg purchase price — as a one-tap prefill instead of typing. *This is where the connection earns its place: not as a pitch, as keystrokes saved on a form the user is already filling.*
Hard constraint: `POST /{id}/positions` **400s when the strategy has no `risk_management.exit_ladder`** (`saved_strategies.py`). So this option is **disabled, with the reason stated**, for ladder-less strategies: "This strategy has no exit rules, so there is nothing to watch a position against." Never render a control that is going to fail — that is how the last three features got shipped unreachable.

**3 — "Just save it."**
Exactly today's behaviour: land on `/strategies/{slug}`. No nag, no badge, no re-prompt on the next visit. **A backtest is a legitimate terminal artifact.** Most saves will be this and the design must not treat it as a failure state.

### Constraints

- Copy: "Saved. Do you want Livermore to watch this strategy?" Never "you should buy", never a recommendation.
- **No order ticket on this screen at all.** Placement belongs to the surface that knows a position exists.
- Screen-derived (basket) strategies: option 2 either asks which symbol first, or is simply not offered in v1. **Do not invent multi-symbol declare** — that is a different product.
- `portfolio_mode` does **not** use `FlowSave` (it ends at `summary` with `next: () => null` and navigates to `/workspace`). Do not retrofit `track` onto it. Out of scope.

---

## 4. STATE-DEPENDENT SURFACES

| # | State | What home shows |
|---|---|---|
| 0 | **Signed out** | Search · strip · pulse · picks · Quant Rules · catalysts. `UnresolvedExits` → `null` (no token). `SavedStrategiesTile` → sign-in prompt (already built). **No execution surface. No mention of brokers anywhere.** |
| 1 | **Signed in, nothing saved** | As 0, plus the tile's empty state. Still no execution surface — there is nothing to execute. |
| 2 | **Has ≥1 saved strategy, no position** | `SavedStrategiesTile` renders SignalCards. A card in `in_signal` is the entry surface. Nothing else changes. |
| 3 | **Has a tracked position, nothing fired** | Nothing new on home today. See the exception below. |
| 4 | **Has an unresolved exit** | `UnresolvedExits` renders (already). Ticket collapsed by default; "I'm holding" posts directly; "I sold — record it" navigates. |
| 5 | **Broker connected, trading OFF** | Identical to 0–4. `/account` shows the connection and last sync. `PlaceOrder` → `null`, correctly. |
| 6 | **Broker connected, trading ON** | `PlaceOrder` appears *inside an already-open ticket*. **Nothing new appears at the top level of home.** |

### Should the execution surface be visible when there is nothing to resolve? **No.**

`UnresolvedExits` returning `null` is the correct pattern and should be preserved verbatim.

A standing "Trade" block on home would (a) be empty in ~99% of sessions, (b) advertise a capability almost nobody can use — trading is flag-off by default and gated on counsel — and (c) silently reposition the product from research tool to brokerage front-end without anyone deciding to. Execution blocks should appear **because a decision is owed**, and vanish when it isn't. That is precisely what makes their appearance meaningful rather than decorative.

### The one exception, and it is small

**State 3 is a real hole.** A user with money at risk against a rule has no standing surface saying so; the position is visible only on a per-strategy page they must remember to open.

The fix is **not** an execution block. It is one marker inside the tile that already exists: a strategy with an open position shows *"holding {symbol}"* on its SignalCard. That requires the `in_position` state which `apps/api/app/schemas/signal_card.py` explicitly **defers** (`signal-card.tsx` header: the state set is `in_signal / basket / flat / pending`; market-fill states are deferred). **Scope it as a backend change; do not fake it client-side.**

### A copy problem that ships with state 6

`page.tsx` currently prints three chips under the hero: **"No live trading"** · "End-of-day prices" · "Research tool, not advice".

The first becomes **false** the day `SNAPTRADE_TRADING_ENABLED` flips. It is in `page.tsx`, nobody owns it, and it is the most quotable false statement the site could carry. It changes in the same PR as the flag or not at all. (Open question 4.)

---

## 5. THE MISSING DESTINATION

Today there is no `positions` route anywhere under `apps/web/src/app`. Positions are visible **only per strategy**, via `PositionCardsGrid` inside `ActiveExecutionDashboard`, on two routes. The only cross-strategy surface is `UnresolvedExits`, which lists exits — not holdings.

### Decision: `/account/positions`, not top-level `/positions`

- It matches the shape that exists: `/account`, `/account/strategies`, `/account/notifications`, `/account/email` — signed-in, personal, token-required. Every *top-level* route (`/stocks`, `/screen`, `/community`, `/strategies`, `/templates`) is public or shareable. `/positions` would be the only top-level route that means nothing to a logged-out visitor.
- A top-level `/positions` in the main nav is a permanent execution advertisement to signed-out visitors — the §4 objection, restated as information architecture.
- It stays one click away in the user menu, which is where the same user already goes for "My Strategies".

**Navigation:** the user-menu dropdown in `nav-header.tsx`, immediately under the existing `user-menu-my-strategies` item, labelled **"Positions"**. **Not** the main nav bar. A count badge **only** when there is an unresolved exit — a count of open positions is noise.

**Backend:** there is no cross-strategy positions endpoint. `GET /api/saved-strategies/{strategy_id}/positions` is per-strategy. This route needs a new one.

### What it shows

**Empty (no positions ever)** — not a marketing panel. One sentence in the §11 register plus one link:

> "No positions tracked. When a strategy you saved signals an entry, record what you bought and Livermore watches it against that strategy's exit rules."
> → **My strategies** (or → **Quant Rules** if the user has zero saved strategies)

While in there, fix the neighbouring lie: `position-cards-grid.tsx:128-138` currently reads *"The monitor cron will open positions as your rules trigger."* **The cron opens nothing.** The user declares, or the broker sync does. That copy predates user-declared positions.

**Populated** — one row per open position: symbol · shares · entry · latest · % from entry · which strategy · the ladder's next tier. Unresolved exits pinned at the top by **reusing `<UnresolvedExits />`**, not reimplementing it.

**Broker connected** — a reconciliation line per row: what SnapTrade reports versus what Livermore recorded. **This is the highest-value thing on the page and the reason it is worth building.** `shares_remaining` only decrements on manual confirmation (`confirm-exit` is the sole mutator), so drift is guaranteed and today it is silent. This page is where silent drift becomes visible.

---

## 6. WHAT NOT TO BUILD

1. **A "Trade" or "Positions" item in the main nav bar.** Permanent, empty for most users, repositions the product. User menu only.
2. **Order buttons on Hot Market Picks / Moving today / Catalysts / search results.** No rule, no ladder, no quantity. This is the specific thing that would make every tile lead to trading.
3. **Buy/entry order placement through `PlaceOrder`.** It structurally cannot: it returns `null` unless the broker already reports the symbol. Making it work means deriving a quantity from account value — the personalization line already drawn in `daily_path_v1.md` §2 Q6. Entries stay: signal → ticket → the user's own broker.
4. **A position-size calculator, anywhere.** Same ruling. It **will** be asked for; the answer is written down now so it isn't relitigated in a PR.
5. **Auto-placing an order when a tier fires.** Forbidden by posture and structurally blocked: `tests/test_snaptrade_readonly_guard.py` fails the build if anything under `app/jobs/` so much as mentions snaptrade. **Do not weaken that test.**
6. **Broker deep-links with prefilled side or quantity.** `daily_path_v1.md` ships 4b symbol-only; `DRAFT_pm_trade_execution.md` §6.6 sends prefill to counsel. Not a PR decision.
7. **A `/portfolio`, `/broker`, or `/connect` top-level route.** Two mounts of one component.
8. **Reviving `entry-mode-picker.tsx`.** Zero non-test references; a fourth launcher for three flows that already have launchers.
9. **Deleting the manual declare form once connect ships.** `daily_path_v1.md` Stage 2 says connect "replaces hand-declared positions". **I disagree as written:** it replaces it *for connected users*. Deleting the manual path makes the entire execution loop conditional on a brokerage OAuth — the strongest possible version of the trust problem, applied to the users least likely to clear it. Keep both.
10. **A confirm-exit paperwork flow for connected users.** `daily_path_v1.md` Stage 5 is right — the next morning's sync confirms the fill. Do not build a second manual path for people who do not need one.
11. **Multi-symbol / basket declare.** Screen strategies produce baskets; one declared position per name is a different product with different exits.
12. **An onboarding tour or interstitial explaining execution.** Nobody asked. The surfaces are designed to explain themselves by appearing only when relevant; a tour is an admission that they don't.
13. **A new home block of any kind.** Ask #3 is answered entirely by blocks 5, 7 and 9, which already exist.

---

## 7. SEQUENCING

The stated failure mode — three features whose UI entry point did not exist — has one cause: **the entry point shipped in a different PR from the capability.** Every step below carries its own entry point.

**Step 0 — Fix `/account/strategies/[id]`. Blocking, one file.**
Lines 44–47 still gate on `bar_resolution !== "daily"`; swap to the ladder gate and thread `barResolution` through, matching `/strategies/[slug]` (fixed in #331). Two extra facts make this blocking rather than tidy-up:
- `SavedStrategiesTile` passes **`href={/account/strategies/{id}}`** as each SignalCard's heading link (`saved-strategies-tile.tsx:231`, fallback row `:56`; `signal-card.tsx:56-58` uses the same target for "View backtest →"). **Home's own saved-strategy tile sends every click to the page that hides the dashboard.** That is the entry point for state 2 in §4.
- Line 78 passes **no `barResolution` prop**, so it defaults to `"daily"` and hides the two intraday bricks even on the intraday strategies this branch exclusively serves. Two bugs, one gate.
Also mount `<EnteredFromEmail>` / `<ExecutedFromEmail>` here; they are currently on `/strategies/[slug]` only.
*Ships alone. Nothing downstream is trustworthy until it does.*

**Step 1 — `connectBroker()` helper + `<ConnectBrokerage>` card, mounted in `/account`.**
`POST /api/snaptrade/connect` returns `{redirect_uri}` and has zero callers and no `lib/api.ts` helper. Add both; render state from `GET /api/snaptrade/status`.
*Ships alone: read-only holdings become reachable for the first time, and `PlaceOrder`'s `registered` precondition becomes satisfiable. Deliberately changes nothing user-visible in `PlaceOrder` — trading is still off.*

**Step 2 — Connect as a peer input on `portfolio_mode/upload`.** *(founder ask #1)*
Second mount of the same component, above the manual table. On success, fill the holdings table from `GET /api/snaptrade/positions`, and offer **both** "continue → diagnose" and "just track these". Requires step 1.

**Step 3 — The `track` step after `save`.** *(founder ask #2)*
New step in `custom_build_mode` between `save` and `onComplete`; three branches per §3. Requires step 0 for its "view it" destination to be correct. **Requires nothing from SnapTrade** — branch 2's broker prefill is an enhancement that no-ops when unconnected.

**Step 4 — `/account/positions` + a cross-strategy positions endpoint.**
New backend endpoint, new route, user-menu link. Reuses `<UnresolvedExits />` and the position cards. Fix the stale empty-state copy in the same PR.

**Step 5 — Reconciliation on `/account/positions`.**
SnapTrade holdings vs `PositionState.shares_remaining`. Requires steps 1 **and** 4. This is the payoff; attempting it earlier produces a panel with one side of the comparison.

**Step 6 — `SNAPTRADE_TRADING_ENABLED` → true.**
Gated on **counsel** per `daily_path_v1.md` Stage 4c, not on engineering. When it flips, `PlaceOrder` appears inside open tickets — **and the hero's "No live trading" chip changes in the same PR.** Nothing else changes anywhere.

### Unreachable-until (the recurring bug, named)

- Steps 2 and 5 are inert without step 1.
- `PlaceOrder` needs step 1 **and** step 6 **and** a broker that holds the symbol **and** an unambiguous quantity **and** an unresolved exit — five conditions, which is why it has rendered for nobody since #336.
- Step 3 branch 2 is unavailable for ladder-less strategies **by design** — the disabled state must say why, or it recreates the same class of bug at a smaller scale.

### Explicitly deferred, not sequenced

`in_position` on `SignalCard` (needs the deferred backend states) · entry-side order placement · importing cost basis into `Holding` for backtests · `track` for `portfolio_mode`.

---

## 8. OPEN QUESTIONS FOR THE FOUNDER

1. **Does `track` default to "watch it"?** I made "watch it" the visual default and "just save it" a peer. If saving should stay silent and watching be opt-in by navigation instead, that changes the whole step — say so before it is built.
2. **Is the brokerage connection paid-tier only?** `DRAFT_pm_trade_execution.md` §6.2 flagged unbounded per-account aggregator cost against a free Scout tier. Steps 1–2 make it reachable to every signed-in user unless you decide otherwise.
3. **Has counsel started on 4c?** Step 6 has no engineering blockers left — only this one. Everything else in §7 ships without it.
4. **The "No live trading" chip on the home hero.** At step 6: change it to something like *"You place your own orders"*, or drop the chip entirely?
5. **Do connected users skip `portfolio_mode`'s later steps?** Diagnose → overlay → summary was designed for a typed weights list. I have designed an exit at step 1 ("just track these"). Confirm, or say everyone goes through the overlay picker.
6. **Does connect ever create a `PositionState` automatically?** SnapTrade hands us `units` + `average_purchase_price`, which is enough to declare positions without asking. I designed it as a **prefill the user confirms**, never an automatic import. Confirm that is the line you want — it is the difference between a tool and an agent.
7. **Is `/account/positions` scoped to tracked positions only, or does it also become the home for connected holdings no strategy watches?** I scoped it narrowly. The wider version is a materially bigger page and a different promise.
