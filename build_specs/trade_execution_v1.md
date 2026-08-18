# Acting on the rule — consolidated spec

**Status:** pre-build. No code written. Awaiting founder decisions in §6.
**Date:** 2026-08-18
**Question that started it:** *"how can we have users execute trades following our
trading rules on Livermore, what approaches can we enable?"*

Six approaches were surveyed. Four were rejected for crossing the publisher's
exclusion (position sizing from account balance, order placement, discretionary
auto-trade, anything personalised). **Two were selected:**

1. **Order ticket** — a structured artifact the user carries to their own broker
2. **Read-only brokerage connection** — auto-detect holdings and fills

This spec covers what must be true before either ships.

> Sources: a quant audit of the exit engine, a PM scope pass, and a design pass,
> run in parallel 2026-08-18. Detail in `DRAFT_pm_trade_execution.md` (420 lines)
> and `DRAFT_design_exit_alerts.md` (539 lines). **This file is the decision
> document; those are the appendices.**

---

## 1. The four questions, answered

**Q1 — What interval does a strategy run on?**
Three clocks, none of which agree. The strategy declares a `bar_resolution`; the
feed is FMP intraday at **~15 min delay**; the monitor polls every **5 min**.
Separately: a strategy with `bar_resolution == 'daily'` **cannot hold a tracked
position at all** — `declare_position` 400s. The entire execution feature exists
only for intraday strategies, which is a product boundary nobody wrote down.

**Q2 — Does the reminder actually fire?**
Not reliably, and the failures are silent. See the chain in §3.

**Q3 — Are we calculating the right number?**
Not always. In legal, user-reachable configurations the share count is wrong, and
one whole class of exit never fires. See §2.

**Q4 — How is it communicated?**
Currently as prose that tells the user what to do, in a register that violates our
own §11 rules. The design pass argues the alert's job is to **hand over an
auditable fact and the user's agency, not an order** — because the alert knows a
rule was met, but does not reliably know the price, the quantity, or whether the
position is still protected.

---

## 2. Defect register

`V` = verified directly against the code during this pass.
`A` = agent analysis, not independently run — **confirm before relying on it.**

### Wrong number / silent non-event

| ID | Defect | User-visible effect | Where | |
|---|---|---|---|---|
| **D1** | `_tier_trigger_type` returns the constant `"stop_hit"` for *every* negative tier, and the fire-once guard keys on that string | A ladder like *"trim at −5%, stop out at −10%"* — legal, standard, validator-permitted — fires the −5% and then **the hard stop can never fire for the life of that position**. Silent, permanent | `intraday_jobs.py:383-389` | **V** |
| **D2** | Backtester and live monitor use **opposite** scale-out conventions — `w[k] *= (1-f)` (of remaining) vs `shares_initial * f` (of initial) | The equity curve the user backtested is not the plan the alert states. At two 1/3 tiers: 22 shares vs 33 | `engine.py:1288` vs `intraday_jobs.py:240` | **V** |
| **D3** | Monitor reads `frame["close"].iloc[-1]` only; `high`/`low` are fetched and never read | A flush to −12% that closes at −9% **never fires — not late, never** | `intraday_jobs.py:216` | **V** |
| **D4** | No trailing/high-water anchor; `pct_change` always measured from entry | A position that runs +40% then falls to +2% produces **no notification of any kind**. The default ladder is a *runner* plan (stop 2×ATR, targets 3×/5×), so the tranche where the return lives has no exit rule | `intraday_jobs.py:216` | **V** |
| **D5** | Fire-once guard matches `pending_confirmation` as well as executed | An alert the user never confirms **disarms that tier forever**, while the cron keeps polling every 5 min and says nothing more | `intraday_jobs.py:226-231` | **V** |
| **D6** | `shares_remaining` only decrements on user confirmation, and sizing reads it | A user who missed one confirmation is told at the next tier they hold shares they already sold | `intraday_jobs.py:240` | **V** |
| A1 | `_rows_to_frame([])` raises `KeyError`; the handler sits at strategy level | One bad symbol kills **every remaining position on that strategy** for that tick | `intraday_bar_service.py` | A |
| A2 | Positions endpoint selects the latest bar with no time window and no resolution filter | Dashboard can show a days-old price as live, and a different price than the one the monitor triggers on | `saved_strategies.py:~500` | A |
| A3 | Corporate actions unhandled | A stock split produces a false *"sell everything"* | — | A |
| A4 | `entry_price` unvalidated at declare time | A typo'd cost basis silently anchors every trigger for that position | `saved_strategies.py:736` | A |

### Late

| ID | Defect | Effect | |
|---|---|---|---|
| **D7** | Cron is `hour="14-20"` UTC on a bare `BackgroundScheduler()` with no `timezone=`, and nothing sets `TZ` | **EDT (now):** 09:30–10:00 ET unmonitored — the highest-volatility window of the day. **EST:** last tick 15:55 ET, so with the 15-min delay the newest visible bar is ~15:40 | `main.py:340,458-464` | **V** |
| A5 | Compounding of the above | A Friday 15:45 EST breach is **never detected**, not merely late | — | A |
| — | Total latency, true cross → email | best ~15 min, typical **~25 min**, worst ~35, up to ~18h across a winter close. Costs ~1.3% of slippage at 1σ on a volatile small cap (an −8% stop behaves like −9.3%); ~0.3% on a large cap | — | A |

**Latency is a small-cap problem. Correctness is everywhere.**

### Delivery

| ID | Defect | Effect | Where | |
|---|---|---|---|---|
| **D8** | `position_event` email is gated on `prefs.signal_alerts_enabled` | A user who once muted signal alerts **never learns their stop was hit**. No retry, no fallback | `email_service.py:95` | **V** |
| **D9** | Banner written with `strategy_slug=None` | The in-app exit alert is a dead end with no link and no action | `intraday_jobs.py` `_write_position_banner` | **V** |
| **D10** | Email's `?action=executed` CTA has no frontend handler | The one-click confirm in the alert email **does nothing** | `position_event.py:119`; nothing in `apps/web/src` reads it | **V** |
| — | One email + one banner. No push, no SMS, no retry, no acknowledgement tracking | We cannot tell whether any alert was ever seen | — | **V** |

### Compliance (§11)

| ID | Defect | Where | |
|---|---|---|---|
| **D11** | Email reads *"Your strategy **suggests** selling N of your M shares"* | `position_event.py:131` | **V** |
| **D12** | Code comment: `is_suggestion=True,  # this is advice` | `intraday_jobs.py:330` | **V** |
| **D13** | Banner reads *"Review the **suggested action**"* | `_write_position_banner` | **V** |

---

## 3. Why this is one problem, not fourteen

The delivery defects chain into the correctness defects:

```
user mutes alerts (D8)          ─┐
   or email lands unread         ├─→ tier stays pending (D5)
   or banner has no link (D9)    │      → tier disarmed FOREVER
   or CTA does nothing (D10)    ─┘      → shares_remaining stale (D6)
                                             → next alert's number is WRONG
```

A user who once turned off alerts never learns their stop was hit. A user who
receives one and clicks the button inside it accomplishes nothing. Either way the
position's remaining tiers quietly stop working.

**The order ticket sits at the end of this chain.** Shipping it first gives a
wrong number its best possible delivery vehicle — a clean artifact a person reads
while typing a real order into a real broker.

### Severity calibration

D1 and D2 do **not** bite the shipped defaults: `DEFAULT_EXIT_LADDER` has one
negative tier, and its `[0.5, 1.0]` fractions happen to agree under both
conventions. They bite **custom ladders** — which is precisely what an order
ticket encourages. The defaults are safe; the custom paths are mined.

---

## 4. What we build, in order

### Slice 1 — Make the existing alert true, deliverable, measurable
**No new user-facing feature. Ships value on its own:** users with declared
positions stop missing alerts, and the funnel becomes visible for the first time.

*Correctness:* scheduler → `America/New_York`, hours `9-16` · stops test bar
`low`, TPs test bar `high`, over every unseen bar (this also decouples detection
from poll timing, retiring D7 rather than patching it) · index stop tiers
(`stop0_hit`…) with `stop_hit` as read alias + validator warning on multi-stop
ladders · pick one fraction convention and make backtester and monitor agree ·
±25% tick-over-tick anomaly gate → `suppressed_anomaly`, do not fire · plausibility
warning on `entry_price` at declare.

*Delivery:* `position_alert_delivery` table · decouple exit alerts from
`signal_alerts_enabled` · retry ≤2 on dispatch failure · Resend webhook →
`delivered_at`/`failed_at` · non-dismissible pinned in-app row until resolved ·
banner passes the real `strategy_slug` · frontend handles `?action=executed` ·
add the missing `HOLDING` state so a user who consciously kept the position can
record that without being treated as delinquent · `POST /positions/{id}/close`
with reason enum.

*Telemetry:* `position_tier_fired`, `_alert_sent`, `_delivered`, `_acknowledged`,
`_exit_confirmed`, `_unacknowledged` — each carrying `trigger_type`,
`bar_resolution`, seconds-since-trigger.

*Copy:* full §11 audit. Delete "suggests", "Suggested action", "Action needed",
the `# this is advice` comment, and the instruction emoji. Add the load-bearing
line **"Nothing has been sold — Livermore does not place trades."**

### Slice 2 — The order ticket
Gated on slice 1's telemetry showing alerts are actually arriving.

The governing rule from the design pass:

> **The ticket prints a quantity only when the quantity is derivable one way.**
> `sell_all` → exact. First scale-out on an untouched position → exact (both
> conventions agree). **Any later scale-out → no primary number**; show the tier's
> definition, both readings, and current holdings.

Primary field is side/quantity/symbol in mono; **every price demoted to a muted
evidence table** — which solves half the staleness problem by information
hierarchy rather than by disclaimer. `Current` renames to **`Trigger price`**: a
field name that never decays needs no warning. Precision inherits the user's
declared precision, rounded down; `13.3333` never reaches a broker.

### Slice 3 — Read-only brokerage connection
**Not approved. Decision gate — see §6.1–6.3.**

---

## 5. Success criteria

Numeric, not "users like it":

- % of fired tiers with a delivery confirmation (target: >95%)
- % acknowledged within 30 min of dispatch, market hours
- median seconds from trigger → acknowledgement
- % of declared positions that ever reach a confirmed or `HOLDING` resolution
- count of `suppressed_anomaly` events (should be ~0; non-zero means bad ticks)
- **guardrail:** zero fired tiers with no delivery record

Gate on slice 2: slice 1 telemetry live for two full weeks with delivery >95%.

---

## 6. Open decisions — founder only

**6.0 — Which scale-out convention is correct?** Fraction of the **original**
position, or of what's **remaining**? Backtester and notifier currently disagree
(D2). Trading convention favours fraction-of-original ("a third off at the first
target"); the backtester's `w[k] *= (1-f)` is what falls out of naive weight
math. *Recommendation: fraction-of-original, rename the field
`fraction_of_initial`, fix the backtester, add a validator that the fractions sum
to ≤ 1.0.* **This blocks slice 1.**

**6.1 — Do you custody brokerage OAuth credentials?** Beyond breach exposure, the
non-obvious cost: connecting an account makes §11's required sentence *"we do not
know your financial situation"* **literally false**, permanently constraining
every downstream surface. *Recommendation: not yet, and not on this evidence.*

**6.2 — Is a brokerage connection paid-tier only?** Per-account aggregator pricing
against a free Scout tier is unbounded cost with no offsetting revenue.
*Recommendation: don't open the pricing conversation until ≥25 users hold an open
declared position.*

**6.3 — The crux neither of the above addresses:** we have never measured the
funnel, so **we do not actually know manual entry is the binding constraint.**
Slice 1's telemetry answers this. Deciding 6.1/6.2 before that data exists is
guessing.

**6.4 — Share rounding on the ticket.** Round down to whole shares / nearest whole
/ pass fractional through. This is the number a human types into an order box, so
the policy must be printed on the ticket. *Recommendation: round down, show the
fractional remainder as a footnote.*

**6.5 — The "5min" label.** We sell a five-minute resolution on a fifteen-minute
delayed feed through a five-minute cron. *Recommendation: remove 5min and 15min
from the resolution picker, relabel honestly.* Shipping a label we cannot honour
is the same class of error as shipping copy §11 forbids.

**6.6 — Broker deep-links from the ticket.** Symbol-only is a convenience; a
prefilled quantity and side starts to look like order transmission.
*Recommendation: symbol-only yes, prefilled quantity/side no — and put this one in
front of counsel rather than deciding it in a PR.*

**6.7 — Sequencing sign-off.** This spec asserts slice 1 must fully precede the
ticket, which costs one slice with no visible feature. **Confirm you accept that
trade**, or say interleave and the slices get re-cut.

---

## 7. Non-goals

Position sizing from account balance · order placement of any kind · discretionary
auto-trade · SMS (fix the two channels we have first) · re-notifying about a stop
that has since moved further against the user — that is a punishment email, and
silence is kinder · counterfactual P&L ("you would have saved $X") — banned
outright.
