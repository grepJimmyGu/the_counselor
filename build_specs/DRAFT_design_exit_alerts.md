# DRAFT — Exit Alert Design

**Status:** design draft, not yet a build spec
**Owner:** product design
**Constrains:** `apps/api/app/jobs/intraday_jobs.py`, `apps/api/app/emails/position_event.py`,
`apps/web/src/components/notifications/*`, `apps/web/src/components/active-execution/position-cards-grid.tsx`
**Legal register:** `build_specs/research_execution_v0_signals_and_alerts.md` §11 governs every string below.

---

## 0. The position I'm arguing for

The current exit alert is designed as if its job were **to tell the user what to do**. Three
verified facts say that is the wrong job:

1. The price is a 5-minute bar close from a ~15-minute-delayed feed. It is stale by up to ~20
   minutes and it is not a fill price.
2. **The share count can be wrong.** The live notifier computes `shares_initial × fraction`
   (fraction-of-initial); the backtester scales fraction-of-remaining. On any tier after the
   first scale-out these disagree, so the plan the user backtested is not the plan the alert
   states.
3. **A whole class of exit never fires.** `_tier_trigger_type` returns the constant `"stop_hit"`
   for *every* tier with `trigger_pct < 0`, and `_tier_already_fired` is keyed on that string.
   A legal ladder like "trim at −5%, stop out at −10%" fires the −5% tier as `stop_hit` and then
   permanently suppresses the −10% catastrophic stop. The tier that matters most is the one
   that never fires.

Add the fire-once guard — a `pending_confirmation` the user never touches disarms that tier
forever while the cron keeps polling every 5 minutes and says nothing — and the honest summary is:
**the alert knows a rule was met; it does not reliably know the price, the quantity, or whether
the position is still protected.**

So the alert's job is **to hand the user an auditable fact and their own agency**, not to hand
them an order. Every decision below follows from that.

### What I would cut

- **Cut the emoji.** 🛑 is an instruction glyph in a message that must not instruct.
- **Cut "suggests" / "Suggested action" / "Action needed" / "Review the suggested action."**
  Four separate §11 drifts, plus the code comment `is_suggestion=True, # this is advice`.
- **Cut the word "Current" from the price field.** "Current" is a claim that decays into a lie.
- **Cut the unconditional share count.** Print a quantity only when the quantity is derivable
  one way (§3.2). This is the single biggest change and it means the alert sometimes shows
  *less* than today's email. Correct.
- **Cut dollar P&L from any pre-confirmation surface.** A dollar figure on a stale price implies
  a realizable amount.
- **Cut re-notification by email.** (§2.4 — replaced by retry + persistent in-app state.)
- **Do not add push or SMS.** A "right now" channel on top of 20-minute-old data is the most
  misleading thing this product could ship. Real-time channels require real-time data first.
- **Cut per-position email dispatch.** `_dispatch_position_event` sits inside
  `for pos in positions:` inside `for strat in strategies:`. A −3% market day fires every stop
  in a portfolio in one 5-minute tick and sends N separate emails. Flood → spam-flag →
  every *future* exit permanently lost. Coalesce (§2.5).

---

## 1. The copy deck

### 1.0 Register rules (apply to every string)

- **Required patterns:** "The strategy signaled…", "Your ladder's {Tier} tier was reached",
  "You decide what to do."
- **Banned outright:** "we recommend", "you should", "best for your portfolio", "advised",
  **"suggests" / "suggested"** (a synonym for *recommend* — not literally in §11's list, but it
  is the exact drift §11 exists to prevent), "Action needed", "Act now", "don't miss".
- **The word "advice":** §11 forbids it *as a description of Livermore's output* while its own
  required disclaimer reads "not investment advice." Resolution — **the negated disclaimer is
  the sole sanctioned appearance.** Never affirmative, never as a noun for what we produce.
- **No counterfactual P&L, ever.** Never "had you sold at $184.20 you'd have $X more." It is
  cruel and it is fabricated — we do not know they would have filled there.
- **Imperatives are permitted only inside the quoted ticket**, where they transcribe the
  *strategy's rule*, not our instruction to the user — and only under a label that says so
  ("What the rule says"). This is the Lowe posture: a newsletter may print "Model portfolio:
  sell NVDA."

### 1.1 Email subject

| | |
|---|---|
| **Old** | `🛑 NVDA Stop on My Strategy (-8.2%)` |
| **New** | `NVDA — exit signaled (Stop tier, −8.2%)` |

Front-loads the symbol for a truncated mobile lock screen. No emoji, no imperative.
For a take-profit tier: `NVDA — exit signaled (TP1 tier, +15.4%)`.
Coalesced (§2.5): `3 exits signaled — NVDA, AMD, SMCI`.

**Preheader** (new — currently absent, so inboxes leak the byline):

> `Your ladder's Stop tier was reached on the 11:35 AM ET bar. Prices are delayed. You decide what to do.`

### 1.2 Email body

| Slot | Old | New |
|---|---|---|
| Byline | `June 5, 2026 02:15 PM UTC · Active execution` | `JUNE 5, 2026 · 11:35 AM ET · {strategy name}` |
| H1 | `🛑 NVDA — Stop` | `NVDA — Stop tier reached` |
| Subhead | `{strategy_name} · -8.2%` | *(removed — strategy name moved to byline; pct lives with the price)* |
| Section label | `What happened` | `What the strategy signaled` |
| Body line | `NVDA reached the stop hit tier of your exit ladder.` | `Your exit ladder's Stop tier is defined at −8% from entry. The 11:35 AM ET bar closed at −8.2%, which met it.` |
| Price row | `Current  $184.20 (-8.2%)` | `Trigger price  $184.20  ·  5-min bar close, 11:35 AM ET` |
| Action heading | `Suggested action` | `What the rule says` |
| Action line | `Your strategy suggests selling 13.3333 of your 40 shares. Execute in your brokerage, then mark it executed in Livermore.` | *(see §1.3 — now conditional on quantity confidence)* |
| CTA primary | `View strategy detail →` | `Open the position in Livermore →` |
| CTA secondary | `I executed this` | *(removed from email — see §2.3)* |
| Footer | *(unchanged, it already passes)* | `Not investment advice. Past performance does not guarantee future results. Livermore does not place trades on your behalf. You decide whether to act on this signal.` |

**Byline note:** today `fired_at` (a `utcnow()` at dispatch) is printed next to a price sampled
from a bar close up to ~20 minutes earlier. Two different times rendered as one. The byline and
the price row must both carry the **bar close time in ET** — this requires passing `bar_time`
into `PositionEventPayload`. UTC is wrong for a US-equities retail user regardless.

### 1.3 The action line — three variants by quantity confidence

**Confident** (`sell_all`, or the first scale-out on an untouched position where
`shares_remaining == shares_initial`, the one case where both scale-out conventions agree):

> **Stop tier — sell all.**
> `SELL · 40 shares · NVDA`
> That is the full remaining position. You decide whether to place it.

**Ambiguous** (any scale-out where `shares_remaining != shares_initial` — the two conventions
disagree and we do not know which the user believes they backtested):

> **TP2 tier — trim one third.**
> Your ladder defines this tier as a one-third scale-out. Livermore is not stating a share
> count here: this position has already been partially sold, and "one third" can mean one third
> of your original 40 shares (13.33) or one third of the 26.67 you still hold (8.89).
> You hold **26.67 shares**. You decide the size.

That is a deliberate refusal to print a number we cannot stand behind. It reads as rigor, not
as a bug, because it explains itself in one sentence and still gives the user the two facts
they need (what they hold, what the tier means).

**Degraded** (ladder contains a second negative tier — the config whose lower stop is
permanently suppressed):

> **Note on this ladder.** Livermore is monitoring only the first downside tier on this
> position. A second downside tier is configured and is not being evaluated. Treat this
> position as unmonitored below the tier above.

Honest disclosure of a live defect, in the alert where it matters. Remove this string when the
`stop_hit` keying is fixed.

### 1.4 In-app banner

| | |
|---|---|
| **Old title** | *(email subject, verbatim)* |
| **Old body** | `Your strategy '{name}' signalled an exit on {SYMBOL}. Review the suggested action and mark it executed once you've acted.` |
| **New title** | `NVDA — Stop tier reached` |
| **New body** | `{strategy name} signaled an exit at 11:35 AM ET. Nothing has been sold — Livermore does not place trades. Open the position to see the details and record what you did.` |

"Nothing has been sold" is load-bearing. The banner is the surface most likely to be read in
isolation, and the single worst misread of this product is believing an exit was executed.

> **Bug, blocking:** `_write_position_banner` passes `strategy_slug=None`, and `BannerRow` gates
> both the "Mark as executed" button and the "View strategy" link on `item.strategy_slug`. The
> exit banner is currently a **dead end with no way to act.** Pass `strat.id`.

> **Second bug:** the email's `?action=executed` link and `MarkAsExecutedButton` hit
> `/api/saved-strategies/{id}/mark-executed` (the PRD-19 *signal-acknowledgement metric*), while
> the real exit confirm is `confirmPositionExit(strategyId, positionId, {trigger_type,
> shares_sold})`. Two different "executed" concepts, one label. A user can click "I executed
> this," see a green check, and never resolve the position.

### 1.5 Ticket header

> `EXIT TICKET · NVDA · STOP TIER`
> `{strategy name} · signaled 11:35 AM ET, June 5`

### 1.6 Confirm-fill prompt

| | |
|---|---|
| **Old** | `Exit signalled (Stop) — your strategy suggests selling 13.3333 shares. Sell in your brokerage, then confirm below.` / placeholder `Shares sold` / button `Mark as executed` |
| **New** | Heading: `Record what you did` |

> If you sold in your brokerage, enter the fill so Livermore's P&L matches your account.
> Livermore has no connection to your broker and cannot see your trades.
>
> `Shares sold  [        ]`   `Fill price (optional)  [        ]`
> `[ Record this sale ]`   `[ I'm holding — don't close this ]`

- Placeholder `Shares you sold` (not `Shares sold` — the possessive prevents reading it as our number).
- Fill-price field is **new and important**: it is the only way P&L stops being computed from a
  stale trigger price. Optional, so it never blocks.
- Error: `Enter the number of shares you sold.` — unchanged, already fine.
- Success: `Recorded — 13 shares at $183.90. 26.67 shares remaining.`

### 1.7 Empty / expired / degraded states

| State | String |
|---|---|
| No positions (old) | `No open positions yet. The monitor cron will open positions as your rules trigger.` |
| No positions (new) | `No open positions. When you declare a position, Livermore watches it against your exit ladder during market hours and emails you when a tier is reached.` |
| No unresolved exits | `No exits signaled. Your open positions are being monitored against their exit ladders.` |
| Position closed elsewhere | `This exit is no longer open. You closed this position on June 6, so the Stop tier signal from June 5 was closed out with it.` |
| Monitoring degraded | `Monitoring is limited on this position. The {Tier} tier already signaled, so it will not signal again. {n} tier(s) remain armed: {list}.` / when none remain: `No exit tiers remain armed on this position.` |
| Market closed | `Markets are closed. Exit tiers are evaluated during regular trading hours.` |
| Stale data | `Livermore has not received a price for NVDA since 10:05 AM ET. Exit tiers are not being evaluated on this position right now.` |

The "no tiers remain armed" string is a disclosure obligation, not a nicety. After a stop fires
and goes unconfirmed, the position is genuinely unprotected and the UI currently implies
otherwise.

### 1.8 Strings to delete outright

`Action needed` badge → `Exit signaled` (descriptive, neutral, amber not red).
`_TRIGGER_META` emoji keys (`🛑 🎯 ✅ 📍`) → delete.
`action_label` values `Sell all` / `Partial out` / `Close position` → these describe the tier and
are fine *inside* the ticket, but must never appear as a standalone heading over the user's name.
`is_suggestion` field and its docstring ("the email is framed as advice") → rename to
`quantity_confidence: "exact" | "ambiguous"` per §1.3.

---

## 2. The unacknowledged-alert state machine

### 2.1 Why the current model loses alerts

`_tier_already_fired` returns `True` for **pending or executed**. So "we told them" and "they
resolved it" are the same state. A tier that fired and was never acted on is indistinguishable
from a tier that fired and was fully handled, and both permanently disarm the tier. The cron
then polls that position every 5 minutes forever and says nothing.

**The fix is to split one boolean into two.** *Fire-once* stays keyed on the tier (correct — a
rule should not re-trigger). *Resolution* becomes a separate, persistent, user-visible field.

### 2.2 States

On the `trade_log` event, extend beyond `status: "pending_confirmation"`:

```
event: { trigger_type, tier_label, bar_time, price, pct_change,
         action, quantity_confidence, shares_suggested|null,
         notified_at, notify_channels[], notify_failed_at|null,
         seen_at|null, resolved_at|null, resolution|null }
```

```
                    tier condition met
                            │
                            ▼
                    ┌───────────────┐
                    │   SIGNALED    │  trade_log event written; tier disarmed
                    └───────┬───────┘  (permanent — unchanged)
                            │ dispatch
                            ▼
              ┌─────────────────────────┐
              │        NOTIFIED         │  email attempted + banner written
              └──────┬───────────┬──────┘
           send fails│           │ ok
                     ▼           │
              ┌────────────┐     │
              │  RETRYING  │─────┤  same content, ≤2 retries, 15 min apart
              └─────┬──────┘     │  exhausted → UNDELIVERED (in-app only,
                    │            │  + a "we couldn't email you" row in-app)
                    └────────────┤
                                 ▼
                    ┌─────────────────────┐
                    │       UNSEEN        │◄── persists indefinitely
                    └──────────┬──────────┘
        user renders the unresolved-exit card, or clicks through from email
                               ▼
                    ┌─────────────────────┐
                    │        SEEN         │  seen_at set; still unresolved
                    └──────────┬──────────┘
                               │
        ┌──────────────┬───────┴────────┬──────────────────┐
        ▼              ▼                ▼                  ▼
  ┌───────────┐  ┌───────────┐   ┌────────────┐   ┌───────────────┐
  │ CONFIRMED │  │  HOLDING  │   │ SUPERSEDED │   │  ABANDONED    │
  │ user sold │  │ user kept │   │ position   │   │ position or   │
  │ + fill    │  │ it, said  │   │ closed via │   │ strategy      │
  │ recorded  │  │ so        │   │ later tier │   │ deleted       │
  └───────────┘  └───────────┘   └────────────┘   └───────────────┘
```

**`SEEN` is set by in-app render, not by an email open pixel.** Open tracking is unreliable and a
tracking pixel in a transactional legal-register email is a bad look. In-app render is honest and
deterministic.

**`HOLDING` is the state the current design is missing entirely**, and it is the most important
one. Today the only exit from the banner is an `X` that reads as *hide*, not as *decide*. A user
who consciously chose not to sell must be able to record that without the product treating them
as delinquent. `HOLDING` resolves the alert, keeps the position open, and keeps any remaining
tiers armed.

### 2.3 Where each state renders

- `UNSEEN` / `SEEN`, unresolved → **pinned row**, top of the strategy page *and* the home feed.
  Not dismissible by `X`. The `X` opens the resolve control; it never silently hides.
- The email carries **no resolve action.** Removing `I executed this` from the email is
  deliberate: a one-click "I executed this" from an inbox, with no share count and no fill price,
  produces a false resolution and corrupts P&L. Resolution requires the in-app form.
- Resolved → collapses into the position's event timeline. Never deleted; the audit trail is the
  product.

### 2.4 Escalation — deliberately minimal

**One email per tier. Ever.** What replaces escalation:

1. **Retry, not re-notify.** Identical content, ≤2 attempts, 15 minutes apart, only on a
   dispatch failure or bounce. Zero legal surface (same words) and it is the highest-value fix
   for "a missed email is a permanently missed exit."
2. **Digest mention, not alert.** An unresolved exit appears as a line in the existing daily
   digest — a channel the user already opted into, no new interrupt. It counts as "news" for
   `silent_days_enabled`, so a silent-days user still gets it.
3. **The pinned in-app state does the real work.** You do not chase the user across channels;
   you make the app impossible to use without encountering the unresolved exit.

**Why not re-notify.** Re-notifying about a stop that has moved 8% further delivers information
the user *cannot act on retroactively*. Its only function is to inform them that not reading the
first email hurt them. That is a punishment email, and it cannot be written in §11's register
without implying urgency. Silence plus a persistent, non-dismissible in-app state is strictly
better: same information, available the moment they look, with no manufactured pressure.

**Quiet hours: solved by market hours, not by clock.** The monitor only runs during regular
trading hours, so the ordinary case needs no rule. Do not suppress a tier that fires in the first
or last five minutes — that is when it matters most.

### 2.5 Coalescing (the real nagging risk)

Batch per user per cron tick. N tiers firing in one 5-minute tick → **one email, N tickets**,
subject `3 exits signaled — NVDA, AMD, SMCI`. One in-app pinned row per position (they resolve
independently), but never more than one email per tick. Without this, a correlated selloff
guarantees a mailbox flood, and a spam-flag costs the user every future exit notification.

### 2.6 The 6-hours-later, moved-8%-against-them case

This is the emotionally hardest moment in the product. Design rules:

1. **Never say "you missed it."** No counterfactual P&L, no "if you had acted."
2. **Neutral container.** No red, no alarm. The since-trigger delta may carry the loss color
   because it is a number; the card itself stays neutral. An alarm-colored card reads as the
   product blaming the user.
3. **Keep the trigger facts frozen.** The trigger price is a historical fact and never updates.
4. **Show the delta as data, not as a warning.** The honest answer to "how stale is this?" is not
   a duration, it is a price move.
5. **Pivot to what is still true and still ahead.** Whether tiers remain armed is the fact that
   restores agency.
6. **Offer both resolutions with equal weight.** Recording a sale and recording a hold are
   equally legitimate outcomes.

```
┌────────────────────────────────────────────────────────────┐
│ SIGNALED JUNE 5, 11:35 AM ET · UNRESOLVED                  │
│                                                            │
│  NVDA — Stop tier reached                                  │
│  Momentum ladder v2                                        │
│                                                            │
│  What the strategy signaled                                │
│  Your Stop tier is defined at −8% from entry. The          │
│  11:35 AM ET bar closed at $184.20, −8.2% vs your entry    │
│  of $200.65, which met it.                                 │
│                                                            │
│  Since then                                                │
│  Last price      $169.40   5-min bar close, 5:35 PM ET     │
│  vs trigger      −8.0%                                     │
│  vs your entry   −15.6%                                    │
│                                                            │
│  Where this position stands                                │
│  You still hold 40 shares in Livermore's records.          │
│  Nothing has been sold — Livermore does not place trades.  │
│  No exit tiers remain armed on this position.              │
│                                                            │
│  ── Record what you did ────────────────────────────────   │
│  Shares you sold [      ]  Fill price (optional) [      ]  │
│  [ Record this sale ]   [ I'm holding — don't close this ] │
│                                                            │
│  Not investment advice. Livermore does not place trades    │
│  on your behalf — you decide whether to act on any signal. │
└────────────────────────────────────────────────────────────┘
```

Exact strings:

- Header chip: `SIGNALED JUNE 5, 11:35 AM ET · UNRESOLVED` — "unresolved," never "overdue,"
  "missed," or "expired."
- `Since then` — never "Current," never "You could have."
- `You still hold 40 shares in Livermore's records.` — "in Livermore's records" is the honest
  hedge; we do not know their broker.
- `No exit tiers remain armed on this position.` — the disclosure that the stop already fired
  and will not fire again. When tiers do remain: `Your TP1 tier at $230.75 is still armed.`
- `I'm holding — don't close this` — a first-class, non-apologetic button.

---

## 3. The exit ticket

### 3.1 Principle

The user's job at the broker is to enter an order: **side, quantity, symbol.** Price is not
needed for a market order and is user-chosen for a limit order. So the *stale* number is
structurally excluded from the primary field, and the honesty problem is half-solved by
information architecture rather than by disclaimer. Today's email gives `Current: $184.20
(−8.2%)` the trigger color and equal weight with the action — it foregrounds precisely the field
that is stale and non-actionable.

### 3.2 The quantity rule

> **The ticket prints a quantity only when the quantity is derivable one way.**

| Case | Quantity |
|---|---|
| `sell_all` | Exact. `shares_remaining`. |
| First scale-out, `shares_remaining == shares_initial` | Exact. Both conventions agree here. |
| Any later scale-out | **No primary number.** Show the tier's definition, both readings, and current holdings (§1.3 "Ambiguous"). |

**Precision inherits the user's declared precision.** They declared the position by hand. If
`shares_initial` is a whole number, the ticket shows a whole number, rounded **down** so it can
never exceed what the tier describes. `13.3333` never reaches a broker ticket.

### 3.3 Layout (confident case)

```
┌────────────────────────────────────────────────────────────┐
│ JUNE 5, 2026 · 11:35 AM ET · MOMENTUM LADDER V2            │  ← byline, 10px
│                                                            │     uppercase, tracking-wider,
│ NVDA — Stop tier reached                                   │     muted (existing pattern)
│                                                            │
│ ┌──────────────────────────────────────────────────────┐   │
│ │  WHAT THE RULE SAYS                                  │   │  ← the ticket block:
│ │                                                      │   │    mono, bordered, the one
│ │  SELL      40 shares      NVDA                       │   │    thing you screenshot
│ │                                                      │   │
│ │  Stop tier · sell all · 0 shares remaining after     │   │
│ │                                     [ Copy ticket ]  │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                            │
│ Your exit ladder's Stop tier is defined at −8% from        │  ← why it fired
│ entry. The 11:35 AM ET bar closed at −8.2%, which met it.  │
│                                                            │
│ Trigger price   $184.20   5-min bar close, 11:35 AM ET     │  ← evidence, muted table
│ Your entry      $200.65                                    │
│ You hold        40 shares                                  │
│                                                            │
│ Prices are delayed up to ~20 minutes. This is the bar      │  ← 11px muted, one line
│ that met the rule, not a quote.                            │
│                                                            │
│ [ Open the position in Livermore → ]                       │
│                                                            │
│ Not investment advice. Past performance does not           │
│ guarantee future results. Livermore does not place trades  │
│ on your behalf. You decide whether to act on this signal.  │
└────────────────────────────────────────────────────────────┘
```

**Hierarchy:** ticket block (mono, boxed, largest) → why it fired (14px) → evidence table
(12px, muted labels) → delay note (11px, muted) → disclaimer (11px, muted).
**De-emphasized:** every price. **Primary:** side, quantity, symbol.

**One-action capture.** `[ Copy ticket ]` copies exactly:

```
SELL 40 NVDA
Stop tier (-8% from entry) — Momentum ladder v2
Signaled 11:35 AM ET, June 5 2026 · trigger price $184.20 (delayed data, not a fill price)
```

Three lines: the order, the provenance, the caveat. The caveat travels with the number wherever
it is pasted, which is the only durable way to prevent it being read later as a quote. In the
email the ticket is a bordered `<td>` with mono type so select-and-copy yields clean text, and
its border makes it a natural screenshot crop.

**Fits the product's visual language:** the byline reuses the established
`text-[10px] font-semibold uppercase tracking-wider text-muted-foreground` pattern
(`signal-card.tsx`, `home-market-pulse-block.tsx`); the container is the standard
`rounded-lg border border-border bg-card p-3`; percent coloring uses `--profit` / `--loss`;
the unresolved state uses `--warning-amber` at the *chip* level only, never as a card fill.

---

## 4. Staleness

### 4.1 The solution

**The trigger price's job is audit, not execution.** Everything follows:

1. **Rename the field: `Current` → `Trigger price`.** One word does most of the work. "Current"
   is a claim that becomes false within minutes; "trigger price" is a historical fact that is
   permanently true. A field name that never decays needs no warning attached.
2. **Timestamp it at its own bar time, in ET.** `$184.20 · 5-min bar close, 11:35 AM ET`.
   Field-level provenance is self-documenting. This requires threading `bar_time` into the
   payload — today `fired_at = utcnow()` is printed beside a price sampled up to ~20 minutes
   earlier, so the email currently *asserts* a freshness it does not have. That is the actual
   honesty bug, and it is a data-plumbing fix, not a copy fix.
3. **Name the delay once, quietly.** One 11px muted line: *"Prices are delayed up to ~20 minutes.
   This is the bar that met the rule, not a quote."* Muted register, adjacent to the evidence
   table where a skeptical reader is already looking.
4. **Escalate disclosure with time, not with prominence.** In-app, the trigger price stays frozen
   and a second `Since then` block appears (§2.6). The honest answer to "how stale is this?" is a
   price delta, not a duration — and it only appears once it is material.
5. **No dollar P&L before a confirmed fill.** Percent-from-entry only. P&L becomes real when the
   user records a fill price.

Under §3.2's ambiguity rule this composes correctly: when the quantity is uncertain we withhold
the quantity, and when the price is stale we relabel and timestamp it. Both are the same move —
**state each number at exactly the confidence we have in it.**

### 4.2 Rejected: a freshness countdown / expiry badge

Rejected — an expiry chip ("this signal expires in 30 min"), a decaying freshness meter, or a
red "STALE" badge after N minutes.

1. **It is false.** The strategy's rule did not expire; only the price context aged. An expiry
   badge misdescribes the artifact and teaches the user that the *signal* was time-limited.
2. **It manufactures urgency.** A countdown is the closest thing to "you should act now" that
   copy can imply without saying it — the exact pressure §11's impersonal register exists to
   prevent.
3. **It makes the product self-invalidating.** A user opening the app at hour three sees a red
   EXPIRED chip and learns that Livermore's alerts are unreliable. That is the trust failure we
   are trying to avoid, delivered by our own hand.

### 4.3 Also rejected: hide the price entirely

Tempting — it perfectly solves staleness. Rejected because the trigger price is the user's only
means of auditing that the rule fired on a real move rather than a bad tick. Bad ticks happen;
the user must be able to see "it fired on $184.20" and say "that was a spike, that is wrong."
Auditability is what makes people trust a rule engine, and removing the number removes it.

---

## 5. Engineering consequences

Ordered by user harm.

| # | Change | Why |
|---|---|---|
| 1 | Key negative tiers by ladder index, not the constant `"stop_hit"` | A configured catastrophic stop currently never fires. |
| 2 | Reconcile scale-out convention between backtester and notifier; until then, ship §1.3's ambiguous variant | The alert states a plan the user did not backtest. |
| 3 | `_write_position_banner(strategy_slug=strat.id)` | The exit banner is a dead end with no way to act. |
| 4 | Split fire-once from resolution: add `seen_at` / `resolved_at` / `resolution` to the trade_log event | A missed alert is currently permanent and silent. |
| 5 | Coalesce dispatch per user per tick | A correlated selloff sends N emails and earns a spam flag. |
| 6 | Thread `bar_time` into `PositionEventPayload`; render ET | The email asserts a freshness it does not have. |
| 7 | Add the `HOLDING` resolution + fill-price capture | The only non-delinquent exit from the alert, and the only path to true P&L. |
| 8 | Retry on dispatch failure (≤2, 15 min) | One email is the entire delivery guarantee. |
| 9 | Rename `is_suggestion` → `quantity_confidence`; delete "this is advice" comment | §11. |
| 10 | Disambiguate `mark-executed` (metric) from `confirmPositionExit` (resolution) | A user can "confirm" and resolve nothing. |
