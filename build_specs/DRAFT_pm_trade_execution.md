# DRAFT — Acting on the rule: Order Ticket + (gated) read-only brokerage link

**Status:** DRAFT for founder review. Not approved. Slice 3 is a decision gate, not a plan.
**Owner:** PM. Design owns the UI; a separate quant agent owns the math audit.
**Legal floor:** `build_specs/research_execution_v0_signals_and_alerts.md` §11. Non-negotiable.
**Prior art in code:** `apps/api/app/jobs/intraday_jobs.py`, `apps/api/app/api/routes/saved_strategies.py` (declare / confirm-exit), `apps/api/app/emails/position_event.py`, `apps/api/app/api/routes/notifications.py`.
**Prior art in prose:** `docs/BUILDING_LIVERMORE_JOURNAL.md` Episode 40 — why notify-and-confirm exists.

---

## 1. Problem statement

Active execution is fully built and structurally idle. The cron, the exit ladder, the position store, the email renderer, the in-app banner, the live dashboard and the intraday chart all shipped in PRD-16c and active-execution-v2 — and the entire machine is gated behind **two typing tasks the user must perform in the right order**: they must hand-declare a position (symbol, shares, entry price, entry time, all typed from memory or from another browser tab), and then, after an alert fires, they must come back and hand-confirm the fill. The first gate is absolute — `_monitor_active_positions_async` early-returns the moment there are no open `PositionState` rows, so a user with zero declared positions is not a user with a quiet monitor, they are a user with no monitor at all. The second gate is where every number the product could ever show about whether the strategy worked goes to die. And a third gate nobody has named: for the user who clears both, the return path is broken — the position-event banner is written with `strategy_slug=None`, so the in-app alert renders with no link and no inline action, and the email's "I executed this" CTA points at `?action=executed`, for which no frontend handler exists. We built a loop, shipped every arc of it, and left both ends unconnected.

The two approved moves attack the two gates. The **order ticket** attacks the second gate: it makes the moment of action legible and one tap from confirmation. The **read-only brokerage connection** would attack the first — but it is not approved, and Section 5 argues we should not even price it until the funnel proves manual entry is the binding constraint.

---

## 2. What actually runs, and whether it is coherent

### 2.1 Three clocks, none of which agree

| Clock | Value | Source |
|---|---|---|
| Strategy's own resolution | 5 / 15 / 30 / 60 min | `bar_resolution` on the stored `StrategyJSON` |
| Monitor tick | fixed 5 min, independent of the above | `main.py` — `scheduler.add_job(monitor_active_positions, "cron", day_of_week="mon-fri", hour="14-20", minute="*/5")` |
| Price feed | ~15 min delayed | FMP intraday via `IntradayBarService.ensure_recent_bars` |

The monitor tick does not adapt to `bar_resolution`. A 60-minute strategy is polled twelve times per bar — eleven of those are paid FMP round-trips that re-read a bar that has not changed. A 5-minute strategy is polled once per bar but on an unaligned phase, so the bar it reads is between 0 and 5 minutes stale before the feed delay is even counted.

**Effective end-to-end detection latency**, worst case:

- 5min strategy: 5 (bar) + 15 (feed) + 5 (tick) = **~25 minutes**
- 60min strategy: 60 (bar) + 15 (feed) + 5 (tick) = **~80 minutes**

The `<BarResolutionPicker>` offers a radio labelled "5min". A retail user reads that as five minutes. We are selling a five-minute product on a twenty-five-minute clock. That is not a bug in the code; it is a claim in the UI that the system cannot honour, and it is the kind of gap that turns a missed stop into a support ticket that is very hard to answer well.

### 2.2 The scheduler window is wrong in both directions, and worse in winter

`BackgroundScheduler()` is constructed with no `timezone=`, so APScheduler binds to the container's local zone — UTC on Railway. The job therefore ticks 14:00 → 20:55 UTC, Mon–Fri, year round, against a market that moves with US daylight saving.

**EDT (mid-March → early November).** ET = UTC−4. Window = **10:00 → 16:55 ET**. Market = 09:30 → 16:00 ET.
- The first 30 minutes of the session are unmonitored. Confirmed — the founder's suspicion is correct.
- Eight to eleven ticks per day fire after the close and do nothing (the first few post-close ticks are actually useful, because the 15-minute delay means the closing bars only land around 16:15 ET).

**EST (November → March).** ET = UTC−5. Window = **09:00 → 15:55 ET**.
- Six ticks per day fire before the open. They are not merely wasteful: `ensure_recent_bars` windows the read to the trailing 360 minutes in ET, so at 09:00 ET the window starts at 03:00 ET, contains no bars, `frame.empty` is true, and the position is skipped. Each of those six ticks still pays an FMP fetch per open position to produce nothing.
- **The last tick is 15:55 ET, and with the 15-minute feed delay the newest bar it can see is roughly 15:40 ET.** The final twenty minutes of every winter session — including the close, including the closing auction — are never evaluated. A stop breached at 15:45 on a Friday is not delayed; it is *never detected*, because Monday's first useful tick reads a 6-hour window that starts at 03:00 ET Monday and contains none of Friday's bars.

That last one is the serious finding. It is a permanent miss that does not even involve the fire-once guard, and it is invisible in logs because nothing fires.

**Fix:** pass an explicit `timezone=ZoneInfo("America/New_York")` to the scheduler (or to this job's trigger) and set `hour="9-16"`. Two lines. It is a slice-1 blocker.

### 2.3 The monitor point-samples the close and ignores the bar it just fetched

`_evaluate_position` reads `frame["close"].iloc[-1]` and compares it to the tiers. The `intraday_bars` table stores `open`, `high`, `low`, `close`, `volume` — and `high` and `low` are discarded.

Consequence: a stop breached inside a bar that closes back above the trigger **never fires**. On a 60-minute strategy this means an hour-long excursion of any depth is invisible unless it happens to be resolved at the bar boundary. This is the defect that makes the schedule gap much worse than it looks in isolation, and inverting it is the cheapest single improvement available: **stop tiers (`trigger_pct < 0`) test the bar `low`; take-profit tiers test the bar `high`.** No new data, no new provider, no new cost.

Note the sequencing insight this produces: fixing the sampling defect *partially heals the EDT morning gap on its own*, because the 10:00 ET tick's 6-hour window already contains the 09:30–09:45 bars — the logic simply refused to look at them. Fix the sampling first; the window fix is still required but is less load-bearing than it appears.

### 2.4 Multiple stop tiers silently cancel each other

`_tier_trigger_type` returns the constant `"stop_hit"` for **every** tier with `trigger_pct < 0`, and `_tier_already_fired` matches on that string. The schema validator (`RiskManagement.validate_exit_ladder`) requires *at least one* stop tier and does not forbid more.

So a perfectly valid ladder —

```
[-5% sell_fraction 0.5,  -10% sell_all,  +15% sell_fraction 0.33]
```

— fires the −5% scale-out, writes `stop_hit` to the trade log, and **the −10% hard stop can never fire for the life of that position.** The user is told their capital is protected at −10%. It is not. Nothing errors, nothing logs, and the dashboard looks correct.

This is the most dangerous defect in the file and it blocks everything. Fix: index stop tiers the way TP tiers are indexed (`stop0_hit`, `stop1_hit`, …), migrate the existing `stop_hit` string as an alias so historical trade logs still read, and add a validator warning when a ladder contains more than one negative tier so the composer can explain what will happen.

### 2.5 The entry price anchoring every trigger is unvalidated

Every tier is evaluated as `(current - pos.entry_price) / pos.entry_price`, and `entry_price` is a number the user typed. `declare_position` checks only that it is positive. A user who types 105 for a stock that traded at 150 gets a stop that is already 30% in the money and fires on the next tick, permanently burning the tier.

Fix: at declare time, read the symbol's cached bars around `entered_at` and warn (do not reject) when the declared basis falls outside the observed `[low, high]` range by more than a tolerance. Warning, not rejection, because the user's real average cost legitimately differs from any single bar — but a 30% miss is a typo, not a cost basis.

### 2.6 Corporate actions will produce a false "sell everything"

`IntradayBar` carries no adjusted close, no dividend amount, no split coefficient — by design, per its own docstring. A 2-for-1 split during a held position halves the raw price, produces a −50% `pct_change`, fires the stop, sends an email saying sell all, and burns the tier permanently.

Full corporate-action handling is out of scope. A **sanity gate** is not: suppress and flag any tier whose `pct_change` moves more than ±25% against the previous observed tick for the same position, write a `suppressed_anomaly` event instead of firing, and alert operations. Cheap, and it protects the one thing the entire legal posture rests on — that the number we publish is what the strategy actually said.

### 2.7 Answer to the founder's Q1: is the daily-bar boundary right?

`declare_position` rejects any strategy with `bar_resolution == "daily"` or no exit ladder, with copy telling the user to enable Active Execution. So today only intraday-with-ladder strategies can hold a tracked position.

**The boundary is drawn on the wrong axis.** The thing that makes a position trackable is not the bar resolution, it is *whether the strategy defines exit levels*. A daily-bar strategy with a −10% stop and a +25% target is a completely coherent object to track; it simply wants one evaluation per day on the daily close, not a 5-minute poll. The current gate is an implementation artifact of PRD-16c (the monitor was written against the intraday cache) that hardened into a product rule.

It is also excluding the larger population. Retail users mostly hold for weeks. The intraday-with-ladder cohort is the smallest addressable slice of the customer base, and it is the only one that can use the feature at all.

**But do not fix it in slice 1 or 2.** Extending the eligible population before the delivery guarantee works multiplies the number of alerts nobody sees. Sequence it into slice 3 as a once-daily post-close evaluation path — same detect-and-notify contract, same trade log, different clock. Call it a limitation, tell users it is coming, and fix the alerts first.

---

## 3. Answer to Q2 — the delivery guarantee

> "If the user constantly misses it, it's meaningless."

Correct, and today the system is structurally worse than "the user might miss it."

### 3.1 What is actually broken

1. **A silent, permanent drop.** `_prefs_allow` returns `False` for `template == "position_event"` when `prefs.signal_alerts_enabled` is off. `send_email` then returns `False` and logs at INFO. The tier has already fired and written its `pending_confirmation` event, so `_tier_already_fired` is now permanently true. **A user who once toggled off signal alerts loses every exit notification forever, and the guard guarantees no retry.** The same happens when the Resend client is unconfigured, and when `owner` resolves to `None`.
2. **No delivery evidence of any kind.** `send_email` returns `True` for *attempted* send and swallows the exception on failure with a `.warning`. There is no Resend webhook route in `app/api/routes/` (only `stripe_webhook.py`), so bounces, spam complaints, deferrals and hard failures are invisible. `stats["notifications_sent"]` counts attempts, not deliveries.
3. **The in-app channel is a dead end.** `_write_position_banner` passes `strategy_slug=None`; `notification-banner.tsx` renders no link and no inline mark-as-executed button in that case (pinned by its own test). So the fallback channel that exists precisely because email might fail cannot be acted on.
4. **The email's action CTA goes nowhere.** `position_event.py` links to `{detail_url}?action=executed`; grepping the web app for a handler on that param returns nothing.
5. **No acknowledgement concept.** Banner ack exists (`POST /notifications/{id}/ack`) but is a generic soft-delete on the banner row, not tied to a position or a tier. Nothing anywhere records that a human saw a stop alert.
6. **No telemetry.** `intraday_jobs.py` contains zero PostHog captures. Not one of the metrics in Section 6 is computable today.

### 3.2 The design principle

**Separate "the tier fired" from "the user was told."**

The fire-once-forever guard is *correct* and should not be weakened — it protects the invariant the whole compliance model rests on (one detection event per tier per entry, never a re-simulated fill, never a duplicated trade-log record). What is wrong is that the guard has been made to carry a second job it was never designed for: delivery. Those are different concerns with different retry semantics, and they belong in different tables.

Introduce `position_alert_delivery`, one row per (position, trigger_type, channel, attempt):

```
position_id, trigger_type, channel ('email'|'inapp'|'push'),
attempt_n, sent_at, delivered_at, failed_at, failure_reason,
acknowledged_at, ack_channel, ack_action ('confirmed'|'declined'|'seen')
```

The detection guard stays exactly as it is. The **reminder** ladder lives on this table:

- **T+0** — email + in-app banner (as today, with the banner deep-linked and the email CTA wired).
- **T+30 min** — if no row for this (position, trigger) has `acknowledged_at` and the market is still open, re-send. Same content, subject prefixed to make the repeat honest ("Still open —").
- **T+2 h** — third and final attempt, same conditions.
- **Hard cap 3 attempts.** Any acknowledgement stops the ladder immediately. Never re-send after the close on the trigger day; a stale stop alert arriving at 9pm is worse than none.
- **Every attempt writes a row.** The trade log gets exactly one event, forever. The delivery table gets up to three rows. The invariant holds and the user gets told three times.

If `signal_alerts_enabled` is off, do **not** silently drop: write the in-app row, write a `delivery_suppressed_by_prefs` row, and surface a persistent (not dismissable-to-nothing) in-app notice explaining that exit alerts are muted, with a one-tap re-enable. The user's opt-out is honoured — the email does not go — but the fact that a stop fired is not deleted from their world.

### 3.3 Channels — and the one I recommend against

**Do not add SMS.** It sounds like the obvious escalation and it is the wrong call here, for four reasons: (a) it makes a broker-grade urgency promise that a 15-minute delayed feed on a best-effort cron cannot keep, and the gap between the promise and the delivery is exactly where liability lives; (b) A2P 10DLC brand and campaign registration for finance-adjacent messaging is weeks of paperwork and ongoing carrier scrutiny; (c) per-message cost on a free tier is unbounded downside for a feature whose adoption we cannot yet measure; (d) it does not fix the actual failure, which is that the two channels we already have are broken at both ends.

**Do this instead, in order:** (1) fix the in-app channel so it deep-links and acts; (2) fix the email CTA so it acknowledges; (3) add the reminder ladder; (4) *then* evaluate **web push** as the third channel — free, no carrier, no registration, works on desktop Chrome and on installed PWAs from iOS 16.4 — and only if D2 in Section 6 is still under target after (1)–(3).

### 3.4 What happens to a stop alert nobody opened

State it as product policy, because it will otherwise be decided by accident:

- The position stays open. Livermore never closes it, never simulates a fill, never assumes.
- After the third unacknowledged attempt, the position is flagged `alert_unacknowledged` and the dashboard card carries a persistent, non-dismissable marker showing what fired and when. It does not expire. The user finding it three weeks later is a better outcome than a clean-looking card that hides a missed stop.
- The next tier can still fire normally. A missed stop does not suppress a subsequent take-profit.
- Emit `position_alert_unacknowledged` with the tier, the elapsed time and the channels attempted. This is D4 in Section 6 and it is the metric with money attached.

---

## 4. Scope

Three slices. Each independently shippable, each independently valuable, each behind its own flag.

### 4.1 Slice 1 — Make the existing alert true, deliverable, and measurable

**Nothing new is exposed to users except reliability.** This slice exists because shipping an order ticket on top of a monitor that can miss a stop is shipping a nicer wrapper around a wrong number.

Backend:
1. Scheduler timezone → `America/New_York`, hours `9-16`. (§2.2)
2. Stop tiers test bar `low`; TP tiers test bar `high`. (§2.3)
3. Index stop tiers (`stop0_hit`, `stop1_hit`, …) with `stop_hit` as a read alias; validator warning on multi-stop ladders. (§2.4)
4. Anomaly sanity gate at ±25% tick-over-tick; write `suppressed_anomaly`, do not fire, alert ops. (§2.6)
5. `entry_price` plausibility warning at declare time. (§2.5)
6. `position_alert_delivery` table + the T+0 / T+30m / T+2h reminder ladder, capped at 3, market-hours only. (§3.2)
7. Resend webhook route → write `delivered_at` / `failed_at`. Removes the "we have no idea if it arrived" blind spot.
8. `POST /positions/{id}/close` with a reason enum (`sold_outside_livermore`, `no_longer_tracking`, `basis_corrected`). Today a position that exits outside the ladder is immortal and the monitor pays for its bars forever.
9. `partially_executed` status on `confirm-exit` (see §6 reconciliation).
10. PostHog events: `position_tier_fired`, `position_alert_sent`, `position_alert_delivered`, `position_alert_acknowledged`, `position_exit_confirmed`, `position_closed_manually`, `position_alert_unacknowledged`. Every one carries `trigger_type`, `bar_resolution`, and seconds-since-trigger.

Frontend:
11. Banner passes the strategy id in `strategy_slug` so the in-app alert deep-links and shows the inline action. One-line backend change, large behavioural change.
12. Handle `?action=executed` on the strategy detail page — open the confirm sheet, prefilled.
13. Copy audit against §11 (see §4.4).

**Ships value on its own:** the users who already have declared positions stop missing alerts, and we can finally see the funnel.

### 4.2 Slice 2 — The Order Ticket

A structured, copy-able record of what the strategy signaled, rendered on the alert surface, in the email, and on the position card. The user carries it to their own broker. Livermore does not route, prefill, or transmit anything.

**Data contract** (design owns layout; this is the payload that must be present and correct):

| Field | Notes |
|---|---|
| Strategy name + link | |
| Symbol | |
| What the strategy signaled | Register-compliant verb — see §4.4 |
| Tier label + trigger level | e.g. "Stop · −10% from your entry" |
| Your entry basis | Echo the user's declared number, labelled as theirs |
| Price at trigger + bar timestamp | ET, with the session date |
| Current price + as-of + **explicit delay statement** | "as of 14:05 ET · prices delayed ~15 min" |
| Suggested share count | With the rounding policy stated (§4.3) |
| Shares remaining after | |
| Remaining ladder | What else is still armed |
| "You decide what to do." | Verbatim, from §11's required register |
| §11 short disclaimer | |

**Interactions:** copy-to-clipboard as one deterministic plain-text block; **Confirm** (opens the fill entry, prefilled with the suggested share count, editable); **Not acting** (records a decline with an optional reason and stops the reminder ladder); **This number looks wrong** (one tap, files a report — this is our cheapest listening post on the quant defects, see §7 G1).

**Explicitly not in the ticket:** any dollar total derived from an account balance, any position-size recommendation, any cross-position ranking or "most important" ordering, any broker deep-link with prefilled order parameters (that last one is an open decision, §10.6 — it is probably fine, it is probably also the first step onto a path we have decided not to walk, and it deserves a deliberate answer rather than a default).

### 4.3 Slice 3 — Widen the population, on evidence

Two independent items, both gated on slice 1's telemetry:

3a. **Daily-bar strategies with exit ladders become trackable** via a once-daily post-close evaluation. Same detect-and-notify contract, different clock. (§2.7)

3b. **Read-only brokerage connection — DECISION GATE, NOT A PLAN.** See §5. Do not staff this until the gate is answered and the adoption trigger in §6 is met.

### 4.4 Copy contract — and two existing violations

§11 forbids "We recommend you buy/sell", "You should", "Best for your portfolio", "Advised allocation", and the word "advice" applied to Livermore's output. Required register: "The strategy signaled…", "What this strategy is saying…", "You decide what to do."

Two things in the shipped code do not clear that bar:

1. `app/emails/position_event.py` renders **"Your strategy suggests selling N of your M shares."** "Suggests" is a recommendation verb. Replace with **"The strategy signaled a stop at −10%. Its rule calls for selling N of your M shares. You decide what to do."** The strategy is the subject; the rule is what is described; the decision is explicitly the user's.
2. `app/jobs/intraday_jobs.py` line ~330 carries the inline comment `is_suggestion=True,   # notify-and-confirm model — this is advice`. It is a comment, not user-facing copy, and it is still the exact word §11 forbids sitting in the file that generates the notification. In a discovery it reads as the team's own characterisation of what the product does. Change it.

Also rename the `PositionEventPayload.is_suggestion` flag to `is_pending_user_action`. Same semantics, no forbidden vocabulary in the schema.

**Rule for the design agent:** the ticket describes what a rule did. It never describes what the reader should do. If a sentence has "you" as the subject of an action verb, rewrite it.

---

## 5. Read-only brokerage connection — decision gate

**Recommendation: do not build this, and do not price it yet.** Frame it as two questions the founder must answer before anyone opens an aggregator's pricing page, plus a third I think is the actual crux.

### 5.1 Decision (a) — will you custody brokerage OAuth tokens?

What you would be taking on:

- **A durable secret that maps to a named person's brokerage account.** SnapTrade's model gives you a `userId`/`userSecret` pair that is functionally the key to that account's data; Plaid Investments gives you an access token. Either way, the credential lives in your database and is long-lived by design.
- **Read-only is not low-stakes.** A read-only breach yields a list of real people with real holdings and real balances. That is a targeting list for phishing and for physical extortion, and it is the kind of dataset whose loss triggers state breach-notification obligations in most of the US.
- **New obligations that arrive with the first connection:** an incident response plan with a real clock, encryption-at-rest for the token store with key rotation, an access log, cyber liability coverage, and — the moment you want a second aggregator or a partner — SOC 2 pressure. None of these are hard individually. Collectively they are a standing operational tax on a one-person team.
- **The part that is easy to miss and matters most.** The §11 disclaimer says, in the required text: *"We do not know your financial situation, investment objectives, or risk tolerance."* **The moment a brokerage account is connected, the first clause of that sentence is false.** Knowing holdings does not by itself destroy the publisher's exclusion — the exclusion turns on whether the publication is impersonal, not on what you happen to know — but it removes the cleanest, simplest version of the defence, and it means every surface downstream has to be audited to prove that no output varies with account value. That audit is a permanent constraint on the product, not a one-time cost. It is also, quietly, the reason position sizing was rejected: connecting the account puts the ingredients for it on the table, and someone will ask.

**What you would need in front of you to decide:** the exact credential each candidate aggregator hands you and where it rests; their breach history and their SOC 2 report; the sub-processor list; your insurance broker's quote for cyber liability at this data class; and a written statement of the "no output varies by account value" rule that you are willing to hold to permanently.

### 5.2 Decision (b) — does per-connected-account pricing survive a free tier?

Aggregators in this category price per connected account per month, typically with a platform minimum. Scout is free. **Every free-tier connection is pure cost with no offsetting revenue, forever, including for users who connect once and never return.**

**What you would need:** a real quote at your volume (not list price); whether the meter is per connection, per account, or per user (a household with four accounts is four connections at some vendors); the minimum monthly commitment; the churn behaviour of connections (a reconnect after a broker credential change often re-meters); and, critically, your own estimate of connect rate among *paid* users.

**Decision rule I would hold to:** if per-account monthly cost exceeds roughly 5% of the tier's monthly revenue, the connection cannot exist on that tier. At Strategist ($24) that is ~$1.20/account/month, which most aggregators clear. At Scout ($0) no price clears. So the real question is not "can we afford it" — it is **"is this a Strategist+ feature, and does it convert enough Scout users to pay for itself?"** That is a conversion hypothesis, and it needs a number attached before it needs an engineer.

### 5.3 Decision (c) — the crux, which is neither of the above

**We have no evidence that manual entry is the binding constraint, because we have never measured the funnel.** Slice 1 exists partly to produce that evidence. The honest current state is: the number of users with an open declared position is small enough that the founder can probably count them, and the reason may be that declaring a position is annoying — or it may be that almost nobody builds intraday strategies with exit ladders in the first place, in which case a brokerage connection removes friction from a step users are not reaching.

Buying an aggregator to fix step 2 of a funnel where step 1 has an unmeasured drop-off is the most expensive way to learn something a PostHog event would have told you for free.

**Adoption trigger before this gate is even worth opening** (from §7): ≥25 users holding ≥1 open declared position, **and** loop-completion rate (L1) below 50%. If L1 is already healthy with manual entry, the connection is solving a problem that does not exist — and if fewer than 25 users have ever declared a position, the problem is upstream of everything this section discusses.

---

## 6. Reconciliation design

### 6.1 The principle

**The broker is authoritative about what the user owns. `PositionState` is authoritative about what this strategy is tracking.** These are different questions and neither answer overwrites the other.

A user can hold 100 AAPL and have declared 80 to a strategy, because the other 20 is a long-term hold they do not want a −10% stop firing on. Auto-syncing to 100 would silently enrol shares the user deliberately excluded. **Broker data is an observation, never a mutation.**

### 6.2 Share-count drift: broker says 100, PositionState says 80

Three observed states, computed on read, never written automatically:

| State | Condition | Behaviour |
|---|---|---|
| MATCHED | broker == tracked (within epsilon) | nothing |
| DRIFTED | broker != tracked, broker > 0 | Drift chip on the position card. Two explicit one-tap resolutions: **"Track all 100"** and **"Keep tracking 80 — the rest isn't part of this strategy."** No default, no timeout, no silent write. |
| ABSENT | broker holds 0 of the symbol | Almost certainly closed elsewhere. Prompt to close with reason `sold_outside_livermore`. Auto-close only after **3 consecutive daily observations** of zero **and** only when an explicit per-user setting is on, defaulting **off**. |

**The de-risking fact, and it is worth stating loudly:** share count does not affect *whether* a tier fires. The ladder is evaluated on `pct_change` from `entry_price` — shares only determine the suggested quantity on the ticket. So drift degrades the ticket's number, not the safety trigger. Reconciliation is a correctness feature, not a safety-critical one, and can therefore ship behind a flag without gating the alert path.

### 6.3 Cost-basis drift — this one *is* safety-critical

If the broker reports an average cost that differs from the declared `entry_price`, every trigger level is anchored to the wrong number. Policy:

- Surface prominently; never adopt silently.
- Adopting the broker's basis **creates a new `PositionState` row** with the corrected basis and an empty trade log, and closes the old row with a `basis_corrected` event. It does **not** mutate the existing row.
- This is deliberate: it reuses the invariant already in the codebase — *"a fresh entry is a new PositionState row with an empty trade_log, so its tiers re-arm"* — which is exactly the semantics you want, because the trigger levels have moved and previously-fired tiers were computed against a basis we now believe was wrong. Mutating in place would leave a guard set against levels that no longer exist.
- The user is told plainly: "Tier alerts have been re-armed against the corrected basis."

### 6.4 Partially-filled exit tiers

**This is broken today, independent of any broker connection.** `confirm_position_exit` flips the matching `pending_confirmation` event to `executed` on *any* quantity. A user told to sell 33 shares who sells 20 loses the ability to confirm the other 13 — the pending event is gone, `_tier_already_fired` blocks re-notification, and the position is permanently out of sync.

Design:

- New status `partially_executed`. Confirming `shares_sold < suggested_shares` sets it, records `executed_shares` **cumulatively**, decrements `shares_remaining`, and **leaves the tier confirmable**.
- The tier flips to `executed` when cumulative executed ≥ suggested, **or** when the user explicitly taps "that's all I'm selling on this tier" (records `closed_out` with an optional reason).
- `_tier_already_fired` needs no change — it matches on `event` regardless of `status`, so the detection guard keeps holding while the confirmation stays open. The two concerns were already correctly separated in that function; only the confirm path assumed one-shot.
- Over-confirmation (`shares_sold > shares_remaining`) stays a 400, as today.
- `final_pnl` computation already sums over `status == "executed"` events; extend it to include `partially_executed` cumulative fills so a position closed by a manual close after partial exits still reports honest realised P&L.

### 6.5 Reconciliation cadence

If and only if slice 3b ships: reconcile on user-initiated dashboard load and once daily post-close. **Never inside the 5-minute monitor tick** — that path must stay free of external dependencies it can block on, and per `apps/api/CLAUDE.md` trap #22 it runs on a worker-thread event loop where any aggregator SDK's shared asyncio primitives would be a live landmine.

---

## 7. Success criteria

None of these are computable today. Producing them is a first-class deliverable of slice 1, not an afterthought.

### Delivery and reliability (the founder's Q2, made numeric)

| ID | Metric | Target | Notes |
|---|---|---|---|
| D1 | Alert delivery rate — % of fired tiers with ≥1 channel confirmed delivered (Resend `delivered` webhook, or banner surfaced in-session) | ≥99% | Today unmeasurable and structurally <100% |
| D2 | **Acknowledgement rate within 60 min** of trigger, during market hours | ≥60% by end of slice 2 | This is "if the user constantly misses it, it's meaningless," as a number |
| D3 | Median lag, trigger → first acknowledgement | ≤20 min | **Report P90 alongside.** Median flatters; P90 tells you whether the channel works |
| D4 | **Unacknowledged-at-close rate for stop tiers** | ≤10% | The metric with money attached. Own dashboard row |
| D5 | Silent-drop count — fired tiers where zero channels were attempted | **0** | Any nonzero value is a bug report, not a metric |

### Loop completion

| ID | Metric | Target |
|---|---|---|
| L1 | % of declared positions reaching a terminal state (confirmed exit, manual close, or explicit decline) rather than abandoned open, within 30 days of first tier fire | ≥70% |
| L2 | Confirm-or-decline rate per fired tier within 7 days | ≥50% |
| L3 | Ticket view → confirm within 24 h (slice 2; baseline in slice 1 from confirm-without-ticket) | +15pp over baseline |

### Guardrails

| ID | Metric | Target |
|---|---|---|
| G1 | "This number looks wrong" report rate per fired tier | <2% |
| G2 | Anomaly-suppression rate (§2.6 gate firing) | Monitored, no target — a spike means a corporate action or a feed problem |
| G3 | Drift rate, broker vs tracked (slice 3b only) | No target — a decision input for whether reconciliation UX is worth deepening |

### Gates between slices

- **Slice 1 → 2:** D5 == 0 for 10 consecutive trading days, and D1 ≥95%. Do not put a ticket on top of a monitor that still drops alerts.
- **Slice 2 → 3a:** L2 ≥40%. If users are not confirming on the population that already exists, widening the population makes the numbers worse, not better.
- **Slice 3b gate:** ≥25 users with ≥1 open declared position **and** L1 <50%. Both, not either.

---

## 8. Answer to Q3 — which quant defects block the ticket

The quant audit is running separately and will surface defects I have not seen. Rather than guess at its output, here is the **rule** for triage, which is the thing that actually needs deciding now:

**Blocking — the ticket cannot ship:** any defect that changes *whether* a tier fires, *which* tier fires, or *the share count printed on the ticket*.

The reason is specific to this feature and not generic caution. The ticket is the first artifact Livermore produces that a user carries to a broker and reads while placing a real order. It looks like an order. A wrong number on a dashboard is a bad chart; the same wrong number on a ticket is a wrong trade, and it is the artifact a regulator or a plaintiff would put on the table. The legal posture survives publishing a signal that turns out badly; it does not survive publishing a number that was not what the strategy said.

**Non-blocking — ships after:** defects affecting display precision, P&L attribution, historical or backtest reconstruction, tier label cosmetics, or the ordering of tiers in a list.

**Tiebreaker for anything ambiguous:** if the user *could not detect the discrepancy by looking at their own broker screen*, it blocks. If they would see it immediately (our `shares_remaining` is stale because they sold manually), it does not block — it goes into reconciliation (§6), which is exactly the machinery for user-visible divergence.

Applying the rule to what I found in this pass:

| Defect | Ref | Verdict |
|---|---|---|
| Multiple stop tiers collapse to one `stop_hit`; later stops never fire | §2.4 | **BLOCKING** — changes whether a tier fires; silently voids a hard stop |
| Close-only sampling ignores bar high/low | §2.3 | **BLOCKING** — changes whether a tier fires |
| Scheduler window vs market hours (EST close blindness, EDT open gap) | §2.2 | **BLOCKING** — the Friday-close case is a permanent, silent miss |
| No corporate-action handling → false stop on a split | §2.6 | **BLOCKING as a guard.** The sanity gate blocks; full adjustment defers |
| Unvalidated `entry_price` anchors every trigger | §2.5 | **BLOCKING as a warning.** Warn at declare; do not reject |
| `suggested_shares` rounding / fractional dust across tiers | §2.1, §10.3 | **BLOCKING** — it is the number printed on the ticket |
| Partial-fill confirmation is one-shot and lossy | §6.4 | **BLOCKING for the ticket** — the ticket invites partial action |
| `final_pnl` ignores fees and unexecuted-share basis | — | Non-blocking — attribution, user-visible, correctable |
| `_CLOSE_EPSILON` float dust at 1e-6 | — | Non-blocking |
| `_TRIGGER_META` has no copy for `tp3_hit`+ (falls to neutral) | — | Non-blocking — cosmetic, already degrades gracefully |

---

## 9. Non-goals and deferred items

**Permanently out of scope — outside the legal posture. Do not propose these again.**

| Item | Reason |
|---|---|
| Position sizing from account balance | Personalises to the user's financial situation. Directly contradicts §11's required disclaimer text |
| Placing orders / order routing | Requires broker-dealer registration. Not a scope question, a licensing one |
| Auto-trade / discretionary execution | Discretionary authority over an account is the definition of what the publisher's exclusion does not cover |
| Livermore-simulated fills | Violates the standing invariant from active-execution-v2: the cron may append `pending_confirmation` but must never mutate shares / `is_open` / `final_pnl` |
| Any output that varies by account value | Would remain forbidden even if slice 3b ships and we technically have the data |

**Deferred, with reasons and revisit triggers:**

| Item | Reason | Revisit when |
|---|---|---|
| SMS alerts | Broker-grade urgency promise on a 15-min delayed feed; 10DLC registration; per-message cost on a free tier | Never, unless the feed becomes real-time and the tier gates it |
| Web push | Real candidate, but fixing two broken channels beats adding a third | D2 still under target after slice 1 + 2 |
| Full corporate-action adjustment (splits, dividends) on intraday bars | Sanity gate covers the dangerous case at ~2% of the cost | G2 fires more than twice a quarter |
| Adaptive monitor tick aligned to `bar_resolution` | Correct, saves ~11 wasted FMP calls per 60min position per hour, but pure cost optimisation with no user-visible effect | FMP costs become material, or position count grows past ~200 |
| Real-time price entitlement | The "5min" label is a claim we cannot honour (§2.1). Either buy the entitlement or change the label | See open decision §10.4 |
| Daily-bar strategies holding positions | Right call on the merits, wrong to do before delivery works | Slice 3a, gated on L2 ≥40% |
| Broker deep-links with prefilled order parameters | Probably fine; also probably the first step onto a path we decided not to walk | Open decision §10.6 |
| Multi-leg, options, futures tickets | The share-count model does not describe them | No trigger — different product |
| Acknowledgement-based re-ranking of alerts ("most important first") | Ranking by importance-to-you personalises | Never |

---

## 10. Open decisions — founder only

1. **Do you custody brokerage OAuth credentials?** (§5.1) A yes brings a durable secret mapping named users to brokerage accounts, breach-notification exposure, and — the part that matters most — it makes the §11 sentence *"we do not know your financial situation"* literally false, permanently constraining every downstream surface to prove no output varies by account value. My recommendation: **not yet, and not on this evidence.**

2. **Is a brokerage connection a paid-tier-only feature, and what conversion lift justifies it?** (§5.2) Per-account aggregator pricing against a free Scout tier is unbounded cost with zero offsetting revenue. Needs a real quote plus a numeric conversion hypothesis, not a vibe. My recommendation: **do not open the pricing conversation until ≥25 users hold an open declared position and L1 is under 50%.**

3. **Rounding policy for the suggested share count on the ticket.** Round down to whole shares (safe, under-sells, works at every broker), round to the nearest whole share, or pass fractional through (correct for Robinhood/Fidelity fractional, meaningless at brokers without it)? This is the number a person types into an order box, so the policy must be stated on the ticket. **My recommendation: round down to whole shares, display the fractional remainder as a footnote.** Needs your call because it changes what the strategy's stated fraction actually delivers.

4. **The "5min" label.** We offer a five-minute resolution on a feed that is fifteen minutes delayed through a cron that ticks every five. Either buy a real-time entitlement, or remove 5min (and probably 15min) from `<BarResolutionPicker>` and relabel the rest honestly. **My recommendation: remove 5min and 15min, label the remainder "checked roughly every 30/60 minutes during market hours, prices delayed ~15 min."** Shipping a label we cannot honour is the same class of error as shipping copy §11 forbids.

5. **Auto-close on ABSENT.** If a connected broker shows zero shares for three consecutive days, may Livermore close the tracked position automatically (opt-in, default off), or must every close be a human action? **My recommendation: opt-in, default off** — but it touches the never-mutate invariant and is yours to rule on.

6. **Broker deep-links from the ticket.** A URL that opens the user's broker with the symbol pre-filled is common, convenient, and technically just a link. It is also the first artifact that starts to look like order transmission. **My recommendation: symbol-only deep-links yes, prefilled quantity or side no** — and get this one in front of counsel with the §11 opinion letter rather than deciding it in a PR.

7. **Sequencing sign-off.** This spec asserts that slice 1 (reliability + telemetry) must fully precede the order ticket, on the grounds that a ticket is a wrong number's best delivery vehicle. That costs you the visible feature for one slice. **Confirm you accept the trade**, or tell me to interleave and I will re-cut the slices.
