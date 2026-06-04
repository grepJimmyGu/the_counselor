# Stage 8 (v0) — Execution Bridge: Signals + Alerts

> **Research-to-execution v0.** This is the minimum bridge between Livermore's strategy research and a retail user actually trading on it. Intentionally narrow: one in-product "Today's Signal" surface + one email alert per signal change. No position sizing, no PDF tickets, no paper trading, no broker integration. Those land later if usage data warrants.

**Depends on:** Stages 1, 1a, 2, 3, 4 (community/saved strategies), 6 (Resend email infra).
**Unblocks:** Retail-friendly path from "I saved a strategy" → "I traded on it."
**Estimated build:** 1.5–2 weeks.
**Branch:** `stage-8-signals-and-alerts`
**Legal basis:** Publisher's exclusion under the Investment Advisers Act of 1940 (Lowe v. SEC). See §11.

---

## 0. Claude Code preflight

```bash
# Stage 1 + 1a + 3 shipped
ls apps/api/app/models/saved_strategy.py
grep "saved_strategies_always_public" apps/api/app/services/entitlements.py

# Stage 6 Resend infra exists
ls apps/api/app/services/email_service.py
ls apps/api/app/services/email_preferences_service.py
grep "resend.send" apps/api/app/services/email_service.py

# Backtest engine reachable for daily re-compute
ls apps/api/app/services/backtest_service.py 2>/dev/null || ls apps/api/app/services/engine.py

# Cached price data is fresh enough (daily Alpha Vantage updates)
ls apps/api/app/models/price_bar.py
```

If Stage 6's `email_service.py` is missing, this v0 needs to ship the email primitives itself — adds ~3 days to the estimate.

---

## 1. Context (read first)

Livermore today lets users research strategies. After a strategy is saved, the loop ends there. The user is left to figure out:

- "What does this strategy say to do today?"
- "If something changes, how will I know?"

This v0 closes that loop with the smallest possible product surface:

1. Every saved strategy gets a **"Today's Signal"** panel showing the strategy's current position (e.g., "Hold NVDA" or "In cash — strategy signaled SELL on 2026-05-12").
2. A daily cron re-runs each saved strategy with current price data and detects when the signal changes.
3. Users opt in per strategy to **email alerts on signal change**. The email tells them what changed and links back to the detail page.

That's the entire feature. Users still execute trades themselves in their own broker — Livermore does not place orders, does not collect dollar amounts, does not personalize. This keeps Livermore squarely on the publisher-exclusion side of the Investment Advisers Act (see §11 disclaimer requirements).

---

## 2. The user flow (end-to-end)

The whole point of v0 is to make this flow short. Here's what a user does:

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │  USER FLOW — Strategy research → Real-world execution                │
 ├─────────────────────────────────────────────────────────────────────┤
 │                                                                       │
 │   Step 1: Build / save a strategy                                    │
 │     User runs a backtest in /workspace → likes the result            │
 │     → clicks "Save strategy" → strategy lives in /account/saved      │
 │     (already shipped in Stage 1a)                                    │
 │                                                                       │
 │                              │                                        │
 │                              ▼                                        │
 │                                                                       │
 │   Step 2: Open the strategy detail page                              │
 │     User clicks the strategy in /account/saved                       │
 │     → sees new "Today's Signal" panel at top                         │
 │     → reads:  "Currently HOLD NVDA  ·  signal last changed: never"  │
 │                                                                       │
 │                              │                                        │
 │                              ▼                                        │
 │                                                                       │
 │   Step 3: Opt in to email alerts (one click)                         │
 │     User toggles "Email me when this signal changes" ON              │
 │     → confirmation toast: "You'll get an email when the strategy    │
 │       changes its recommendation. Unsubscribe anytime."             │
 │                                                                       │
 │                              │                                        │
 │                              ▼                                        │
 │                                                                       │
 │   Step 4: Wait — nothing happens (silent good)                       │
 │     User goes about their week / month                               │
 │     Daily cron silently checks; no email until something changes     │
 │                                                                       │
 │                              │                                        │
 │                              ▼                                        │
 │                                                                       │
 │   Step 5: Signal changes — email arrives                             │
 │     One sentence subject: "Your saved strategy signaled SELL NVDA"  │
 │     Body: strategy name · what changed · reference price ·          │
 │           disclaimer · link to detail page                          │
 │                                                                       │
 │                              │                                        │
 │                              ▼                                        │
 │                                                                       │
 │   Step 6: User decides (entirely on their own)                       │
 │     User reads the alert                                             │
 │     → opens their own broker (Robinhood / Fidelity / Schwab / IBKR) │
 │     → places the trade themselves (Livermore does not execute)      │
 │                                                                       │
 │                              │                                        │
 │                              ▼                                        │
 │                                                                       │
 │   Step 7 (optional): Mark as handled                                 │
 │     User comes back to Livermore                                     │
 │     → on the strategy detail page, clicks "I acted on this signal"  │
 │     → button records timestamp (for the user's own log only)        │
 │     → strategy returns to the "waiting" state until next change     │
 │                                                                       │
 │   Step 7 alternative: do nothing                                     │
 │     User can just close the email if they don't want to trade       │
 │     → no penalty, no follow-up nag, no behavioural pressure         │
 │                                                                       │
 └─────────────────────────────────────────────────────────────────────┘

 Frequency expectations (rough heuristics from backtest history):
   - Moving-average filter: signal flips ~2–4 times per year
   - Momentum rotation:    signal updates monthly (on rebalance dates)
   - RSI mean reversion:   signal flips ~6–12 times per year per ticker
   - Static allocation:    rebalance signals (not flips)
```

**Total user actions to complete the full loop:** 3 (save + toggle + execute in broker). Steps 4 and 5 are passive. Step 7 is optional. The product does the rest.

---

## 3. Scope

### In scope (v0)

- `saved_strategy_signal_state` table — current signal state per saved strategy
- `signal_event` table — log of signal changes
- `signal_alert_subscription` table — per-(user, strategy) email opt-in
- Daily cron job that re-computes signals for every saved strategy with at least one subscriber
- Email template `signal_alert` (single template, EN only)
- "Today's Signal" panel on saved strategy detail page
- One-click email opt-in toggle
- Optional "I acted on this signal" button (timestamp-only, no integration)
- Unsubscribe link in email (single signal vs all signals)
- Disclaimer copy on detail page + in email + in opt-in confirmation

### Out of scope (deferred to later versions)

- Position-sizing calculator (v1+ if requested)
- PDF trade tickets
- SMS / push notifications
- Paper trading / virtual portfolio
- Broker integration (Plaid, deep-links, Alpaca)
- Multi-channel alert preferences UI beyond email on/off
- Real-time intra-day signals (daily resolution only)
- Per-strategy signal frequency analysis (e.g., "this strategy signals avg 3x/year")
- Calendar integration for rebalance dates

---

## 4. Data model

### 4.1 `saved_strategy_signal_state`

One row per saved strategy. Created lazily — only when at least one alert subscription exists or when the user opens the detail page for the first time post-deploy.

```python
# apps/api/app/models/saved_strategy_signal_state.py
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, DateTime, Date, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SavedStrategySignalState(Base):
    """Current cached signal for a saved strategy. Recomputed daily by cron."""
    __tablename__ = "saved_strategy_signal_states"

    saved_strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("saved_strategies.id", ondelete="CASCADE"), primary_key=True
    )
    current_signal: Mapped[dict] = mapped_column(JSON, nullable=False)
    # ^ Free-form JSON; shape depends on strategy_type:
    #   MA filter:        {"position": "long", "ticker": "NVDA"} or {"position": "cash"}
    #   MA crossover:     {"position": "long", "ticker": "QQQ"} or {"position": "cash"}
    #   Momentum rotation:{"holdings": [{"ticker":"GLD","weight":0.5}, {"ticker":"SLV","weight":0.5}]}
    #   RSI mean rev:     {"position": "long", "ticker": "AAPL", "trigger_rsi": 28.4} or {"position": "cash"}
    #   Breakout:         {"position": "long", "ticker": "TSLA", "breakout_level": 312.50} or {"position": "cash"}
    #   Static alloc:     {"target_weights": [{"ticker":"SPY","weight":0.6}, {"ticker":"TLT","weight":0.4}]}
    current_signal_display: Mapped[str] = mapped_column(String(280), nullable=False)
    # ^ Pre-rendered human-readable string: "Hold NVDA" / "In cash" / "Top 2: GLD (50%), SLV (50%)"
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
```

### 4.2 `signal_event`

Append-only log. One row per signal *change*. Used for the detail-page history and to drive emails.

```python
# apps/api/app/models/signal_event.py
class SignalEvent(Base):
    __tablename__ = "signal_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("saved_strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_signal: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    previous_signal_display: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    new_signal: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_signal_display: Mapped[str] = mapped_column(String(280), nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # ^ "flip_to_cash" | "flip_to_long" | "rotation" | "rebalance"
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference_price_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # ^ {"NVDA": 145.23, "SPY": 412.10}  — close prices on the signal date
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    email_dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    email_dispatch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

### 4.3 `signal_alert_subscription`

Per (user, saved_strategy) opt-in.

```python
# apps/api/app/models/signal_alert_subscription.py
class SignalAlertSubscription(Base):
    __tablename__ = "signal_alert_subscriptions"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("saved_strategies.id", ondelete="CASCADE"), primary_key=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # ^ User-clicked "I acted on this signal" timestamp. Optional, no integration.
```

A subscription row exists only when the user has opted in. Unsubscribing deletes the row.

---

## 5. API contracts

`apps/api/app/api/routes/signals.py`:

### 5.1 Get current signal

```
GET /api/saved_strategies/{id}/signal
  auth: required (must be owner)
  resp: {
    saved_strategy_id: str,
    current_signal: dict,
    current_signal_display: str,
    as_of_date: ISO date,
    last_changed_at: ISO datetime | null,
    subscription_active: bool,
    recent_events: SignalEvent[]  // last 5
  }
```

### 5.2 Toggle email alerts

```
POST /api/saved_strategies/{id}/signal/subscribe
  auth: required (owner)
  resp: 200 { subscription_active: true }

DELETE /api/saved_strategies/{id}/signal/subscribe
  auth: required (owner)
  resp: 200 { subscription_active: false }
```

### 5.3 Mark "I acted on this signal"

```
POST /api/saved_strategies/{id}/signal/acknowledge
  auth: required (owner)
  resp: 200 { last_acted_at: ISO datetime }
```

No integration to a broker. Just updates the timestamp on the subscription row. UI shows "Last acted: 3 days ago" so the user has a simple log.

### 5.4 Unsubscribe via email link

```
GET /api/email/signal-unsub?token=<signed>
  auth: none (token is HMAC of user_id + saved_strategy_id + scope)
  scope ∈ {"single_strategy", "all_signals"}
  resp: simple HTML "Unsubscribed" page
```

CAN-SPAM compliance: every signal email includes both a per-strategy and an all-signals unsub link.

---

## 6. Daily cron — signal recomputation

`apps/api/app/jobs/signal_jobs.py`. Single APScheduler job, runs once per day at 22:00 UTC (after US market close + Alpha Vantage daily refresh).

```python
@scheduler.scheduled_job("cron", hour=22, minute=0)
def recompute_signals_job():
    """For each saved strategy with at least one subscriber, recompute the current signal.
    If it differs from the cached state, write a SignalEvent and enqueue alert emails."""
    today = date.today()
    strategy_ids = db.query(SignalAlertSubscription.saved_strategy_id).distinct().all()

    for (sid,) in strategy_ids:
        strategy = db.get(SavedStrategy, sid)
        if not strategy:
            continue

        try:
            new_signal = compute_current_signal(strategy.strategy_json, as_of=today)
        except Exception as e:
            logger.exception(f"Signal recompute failed for {sid}", exc_info=e)
            continue

        state = db.get(SavedStrategySignalState, sid)
        if state is None:
            # First-time computation — store, don't email
            state = SavedStrategySignalState(
                saved_strategy_id=sid,
                current_signal=new_signal["signal"],
                current_signal_display=new_signal["display"],
                as_of_date=today,
            )
            db.add(state)
            db.commit()
            continue

        if signals_equal(state.current_signal, new_signal["signal"]):
            state.last_computed_at = datetime.utcnow()
            db.commit()
            continue

        # Signal changed — log event + queue emails
        event = SignalEvent(
            id=str(uuid4()),
            saved_strategy_id=sid,
            previous_signal=state.current_signal,
            previous_signal_display=state.current_signal_display,
            new_signal=new_signal["signal"],
            new_signal_display=new_signal["display"],
            change_type=classify_change(state.current_signal, new_signal["signal"]),
            as_of_date=today,
            reference_price_snapshot=new_signal.get("prices"),
        )
        db.add(event)

        state.current_signal = new_signal["signal"]
        state.current_signal_display = new_signal["display"]
        state.last_changed_at = datetime.utcnow()
        state.as_of_date = today

        # Enqueue emails for active subscribers
        subs = db.query(SignalAlertSubscription).filter(
            SignalAlertSubscription.saved_strategy_id == sid,
            SignalAlertSubscription.email_enabled.is_(True),
        ).all()
        for sub in subs:
            queue_signal_alert_email(sub.user_id, event.id)

        db.commit()
```

`compute_current_signal()` is a thin wrapper around the existing backtest engine — run the strategy with cached price data through `today`, return the position at the end. No new engine work needed.

`classify_change()` is a simple heuristic: cash→long = `flip_to_long`; long→cash = `flip_to_cash`; basket change = `rotation`; weight tweak = `rebalance`.

**Performance.** 5K saved strategies × ~500ms per recompute (cached prices) = ~40 minutes. Fits inside a one-hour daily window comfortably. If it grows past 50K strategies, parallelize with a thread pool.

---

## 7. Email template

`apps/api/app/emails/templates/signal_alert.tsx`. React Email format compiled at deploy.

**Subject:**
`Your saved strategy signaled {{change_type_short}} {{primary_ticker}}`

Examples:
- `Your saved strategy signaled SELL NVDA`
- `Your saved strategy signaled BUY QQQ`
- `Your saved strategy rotated holdings`

**Body (text version for reference):**

```
Hi {{user_display_name or "there"}},

Your saved strategy [{{strategy_title}}] changed its signal today.

  Previous: {{previous_signal_display}}
  Now:      {{new_signal_display}}
  As of:    {{as_of_date}}
  Reference prices: {{prices_compact}}

This is what the strategy you chose to follow is saying. Livermore is not
recommending you trade — that decision is yours, in your own broker.

View the strategy → {{strategy_detail_url}}

---
{{disclaimer_short}}

Stop alerts for this strategy: {{unsub_single_url}}
Stop all signal alerts:        {{unsub_all_url}}
```

**HTML version** uses the existing Stage 6 React Email chrome (header + footer with physical mailing address per CAN-SPAM).

Localization: EN only for v0. Add ZH in a later iteration if user demand exists.

---

## 8. Frontend

### 8.1 "Today's Signal" panel on `/account/saved/[id]`

Placed at the top of the saved strategy detail page, above the backtest result.

```
┌────────────────────────────────────────────────────────────────┐
│  TODAY'S SIGNAL                              as of May 20      │
│                                                                  │
│  ●  Currently HOLD NVDA                                         │
│      Signal last changed: 8 days ago (was: in cash)             │
│                                                                  │
│  ☐  Email me when this changes                                  │
│                                                                  │
│  [ I acted on this signal ]      View signal history →          │
│                                                                  │
│  ───────────────────────────────────────────────────────────    │
│  This is what the strategy says — you decide what to do.        │
│  Livermore does not place trades or recommend specific actions  │
│  to you personally. Research only, not investment advice.       │
└────────────────────────────────────────────────────────────────┘
```

For "in cash" state, the indicator dot is grey instead of green; for rotation strategies, the panel shows up to 5 holdings with weights.

### 8.2 "Signal history" link

Opens a side drawer listing the SignalEvent log (date, previous → new, reference prices). Simple table.

### 8.3 Saved-strategies list page

Add a small inline badge next to each strategy showing current state:

```
●  200-day MA on NVDA       Hold NVDA    last changed 8d ago
○  RSI mean rev on AAPL     In cash      last changed 21d ago
●  Momentum rotation        2 holdings   updated today
```

### 8.4 First-time opt-in modal

When user toggles "Email me when this changes" for the very first time across any strategy:

```
┌────────────────────────────────────────────────────────────┐
│  How signal alerts work                                    │
│                                                             │
│  • One email per signal change. Most strategies change a   │
│    few times a year.                                       │
│  • You'll receive: what changed, when, and reference       │
│    prices. We don't tell you to trade — your call.         │
│  • Unsubscribe anytime, per-strategy or all at once.       │
│                                                             │
│  This is research, not investment advice. Past             │
│  performance does not guarantee future results.            │
│                                                             │
│  [ Got it, turn on alerts ]      [ Cancel ]                │
└────────────────────────────────────────────────────────────┘
```

Shown once. After that, the toggle is a simple checkbox.

### 8.5 TypeScript types

Add to `apps/web/src/lib/contracts.ts`:

```typescript
export interface SignalState {
  saved_strategy_id: string;
  current_signal: Record<string, unknown>;
  current_signal_display: string;
  as_of_date: string;
  last_changed_at: string | null;
  subscription_active: boolean;
  recent_events: SignalEvent[];
}

export interface SignalEvent {
  id: string;
  previous_signal_display: string | null;
  new_signal_display: string;
  change_type: "flip_to_cash" | "flip_to_long" | "rotation" | "rebalance";
  as_of_date: string;
  reference_price_snapshot: Record<string, number> | null;
}
```

---

## 9. Tier policy

All paid tiers and Scout get equal access to signal alerts. The compute cost per saved strategy is tiny (sub-second daily recompute with cached prices), and signals are core to the value of the product even for free users. Adding tier gates here would weaken the product without meaningful cost savings.

| Tier | Signal alert access |
|---|---|
| Anonymous | Locked (signal alerts require a saved strategy, which requires signup) |
| Scout | ✅ All 10 saved strategies can have alerts on |
| Strategist | ✅ All 25 saved strategies can have alerts on |
| Quant | ✅ Unlimited |

The natural scaling limit IS the saved-strategy quota itself — already enforced in Stage 1a.

---

## 10. Acceptance criteria

1. **Signal first compute** — Subscribe to a fresh saved strategy → `saved_strategy_signal_states` row created on next cron run with no email sent (first-time computation is silent).
2. **No-change cron** — Subsequent daily runs with no signal change → no email, `last_computed_at` updates only.
3. **Signal flip** — When the underlying strategy's position changes (e.g., MA filter goes from long→cash because price dropped below 200-day MA), a `signal_event` is logged and an email goes out within the daily cron window.
4. **Email shape** — Email subject matches `Your saved strategy signaled {change_type_short} {primary_ticker}`. Body includes previous, new, date, reference price, disclaimer, and both unsub links.
5. **In-app current state** — `/account/saved/[id]` shows the current signal panel with correct display string.
6. **Subscribe** — Toggling on works idempotently. Re-toggling on twice produces one subscription row.
7. **Unsubscribe via email link** — Clicking single-strategy unsub deletes only that subscription. Clicking all-signals unsub deletes all of the user's signal subscriptions.
8. **Acknowledge button** — Clicking "I acted on this signal" updates `last_acted_at`. No external integration.
9. **First-time modal** — Shown exactly once across all of a user's strategies. Acknowledged in a `user.has_seen_signal_intro` flag (add to user table).
10. **Rotation strategy** — A momentum-rotation strategy whose top-2 holdings change generates a `change_type='rotation'` event with both previous and new baskets in the payload.
11. **CAN-SPAM** — Email footer contains physical mailing address; both unsub links work without auth.
12. **Cron resilience** — A single strategy that errors during recompute (e.g., missing price data) does NOT block other strategies' processing.

---

## 11. Legal & disclaimer requirements

This product ships under the publisher's exclusion (Lowe v. SEC, 1985). To maintain that posture, every surface that delivers a signal carries explicit disclaimers.

### Required disclaimer text

Use this exact text (or substantively equivalent — get a securities lawyer to bless the final wording before launch):

> **Research only — not investment advice.** Livermore publishes algorithmic signals from quantitative strategies you choose to follow. The signals, performance data, and any references to securities are educational research, not personalized investment advice. Livermore is not a registered investment adviser, broker-dealer, or financial planner. We do not know your financial situation, investment objectives, or risk tolerance, and we are not making recommendations to you personally. All performance data is hypothetical. Past performance does not guarantee future results. Trading involves substantial risk including loss of principal. Consult a licensed financial advisor before making investment decisions.

### Placement

| Surface | Disclaimer |
|---|---|
| `/account/saved/[id]` "Today's Signal" panel | Short version visible by default; "Read full disclaimer" link expands the full text. |
| First-time opt-in modal | Short version, visible. |
| Every signal email body | Short version above unsub links. |
| Signal history drawer | Footer. |

### Forbidden language

Do NOT use, anywhere in copy, email subjects, or UI:
- "We recommend you buy/sell..."
- "You should..."
- "Best for your portfolio..."
- "Advised allocation..."
- The word "advice" in any context referring to Livermore's output

### Required language patterns

- "The strategy signaled..."
- "What this strategy is saying..."
- "Strategy [X] changed its position to..."
- "You decide what to do"

### Pre-launch legal review

Get a securities-law opinion letter ($5–15K) before publicly enabling signal alerts. Reusable across all subsequent features that touch this same legal posture. See the parent research note (chat at the end of May 20) for recommended firm types.

---

## 12. Test plan

### Unit tests

`apps/api/tests/test_signal_compute.py`:
- `test_ma_filter_long_to_cash_detected`
- `test_ma_filter_cash_to_long_detected`
- `test_momentum_rotation_basket_change_detected`
- `test_signals_equal_handles_float_rounding` (price-derived signals shouldn't false-flip on float noise)

`apps/api/tests/test_signal_cron.py`:
- `test_first_compute_creates_state_no_email`
- `test_unchanged_signal_no_event_no_email`
- `test_changed_signal_creates_event_and_enqueues_emails`
- `test_failing_strategy_does_not_block_others`

`apps/api/tests/test_signal_subscribe.py`:
- `test_subscribe_creates_row`
- `test_subscribe_idempotent`
- `test_unsubscribe_deletes_row`
- `test_unsubscribe_via_token_works_anonymously`
- `test_unsubscribe_all_clears_every_strategy`

`apps/api/tests/test_signal_email.py`:
- `test_email_includes_required_disclaimer_text`
- `test_email_subject_format`
- `test_email_includes_both_unsub_links`
- `test_email_includes_physical_address` (CAN-SPAM)

### Integration tests

E2E: Save a strategy → subscribe → trigger a forced signal change (test seam) → assert email arrives in Resend test inbox → assert `signal_events` row exists.

### Frontend tests

Playwright `apps/web/tests/e2e/signals.spec.ts`:
- Open saved-strategy detail → panel renders with current signal
- Toggle email alert → first-time modal appears → confirm → toggle is on
- Click "I acted on this signal" → button confirms with new timestamp
- Open signal history drawer → events list renders

---

## 13. Edge cases & error handling

- **Strategy depending on a delisted ticker** — recompute throws; log + skip + monitor.
- **Multi-day gap due to market holidays** — cron runs every day; first market day after a holiday picks up any signal change. Subject line "as of {date}" reflects the actual market data date.
- **User subscribes to a strategy they don't own** — should be impossible (subscription requires saved-strategy ownership) but enforce in the endpoint regardless.
- **Strategy deleted while subscription exists** — CASCADE delete handles subscription + signal state + events.
- **Email bounce** — Stage 6's Resend webhook marks the user's email as undeliverable; subsequent signal emails skip. User still sees in-app current state.
- **Cron skipped a day** (deploy/restart) — next run still detects any change (state vs current is the comparison, not last vs current). One missed day = users learn one day late.
- **Cron runs twice on the same day** — second run sees no change, no-op. Safe.
- **Time zone for "today"** — UTC throughout. Document in user-facing copy that "as of date" reflects US market close on the previous trading day.
- **Float-noise false flips** — for any price-derived signal, normalize to 4 decimal places before equality comparison.
- **Very chatty strategy** — if a strategy flips daily (would be unusual), enforce an internal max of 3 alerts per strategy per week (avoid email-bombing). After 3rd alert, skip subsequent flips until the next week; in-app state still updates.

---

## 14. Files to create / modify

**Backend (create):**
- `apps/api/app/models/saved_strategy_signal_state.py`
- `apps/api/app/models/signal_event.py`
- `apps/api/app/models/signal_alert_subscription.py`
- `apps/api/app/services/signal_service.py` — compute, classify, email queue
- `apps/api/app/api/routes/signals.py`
- `apps/api/app/jobs/signal_jobs.py`
- `apps/api/app/emails/templates/signal_alert.tsx`
- `apps/api/app/emails/i18n/signal_alert_en.json`
- `apps/api/app/migrations/000X_signals_v0.py`
- Tests as listed

**Backend (modify):**
- `apps/api/app/models/user.py` — add `has_seen_signal_intro: bool` column
- `apps/api/app/services/email_service.py` — register `signal_alert` template
- `apps/api/app/main.py` — register signals router + cron job
- `apps/api/app/api/routes/email.py` — handle `signal-unsub` token

**Frontend (create):**
- `apps/web/src/components/SignalPanel.tsx` — the "Today's Signal" panel
- `apps/web/src/components/SignalHistoryDrawer.tsx`
- `apps/web/src/components/SignalIntroModal.tsx` — first-time opt-in modal
- `apps/web/src/lib/useSignal.ts` — hook

**Frontend (modify):**
- `apps/web/src/app/account/saved/[id]/page.tsx` — render `<SignalPanel />` at top
- `apps/web/src/app/account/saved/page.tsx` — add current-state badge in the list
- `apps/web/src/lib/api.ts` — `getSignal`, `subscribeSignal`, `unsubscribeSignal`, `acknowledgeSignal`
- `apps/web/src/lib/contracts.ts` — add `SignalState`, `SignalEvent` types
- `apps/web/src/lib/i18n.ts` — disclaimer copy + panel labels + modal copy (EN)

---

## 15. Definition of done

- All acceptance criteria pass.
- Full backend + frontend test suites green.
- Cron tested in staging for 3 consecutive days against ≥5 real saved strategies; verify no false positives, no missed flips.
- Manual E2E by Jimmy: save a strategy with a recent signal flip in its backtest history → opt in → forced re-trigger via test seam → email arrives in Resend test inbox → click through → land on detail page with refreshed state.
- Lawyer review of disclaimer copy complete (or scheduled for before public enablement; safe to ship behind feature flag `SIGNAL_ALERTS_ENABLED=false` until then).
- Telemetry events firing (Stage 6 PostHog): `signal_subscribed`, `signal_unsubscribed`, `signal_email_sent`, `signal_email_clicked`, `signal_acknowledged`.
- Documentation: a short `SIGNALS.md` runbook covering cron monitoring + troubleshooting + how to manually trigger a recompute for a specific strategy.

---

## 16. What to measure post-launch (decide what to build next)

These metrics determine whether to expand to position sizing, paper trading, broker integration:

| Signal | Threshold | Decision |
|---|---|---|
| % of paid users with ≥1 active signal subscription within 7 days of signup | ≥40% | Feature is meaningful — expand. |
| Email open rate | ≥35% | Channel works. |
| "I acted on this signal" click rate | ≥10% of subscribers per signal event | Users are actually trading. Worth investing in broker integration. |
| Support tickets asking for position sizing | ≥10% of paid users in 2 months | Add position sizing calculator. |
| Support tickets asking for paper trading | ≥5% of paid users in 3 months | Add virtual portfolio tracker. |
| Support tickets asking for "auto-execute" | ≥3% in 6 months | Evaluate Alpaca integration for Quant tier (separate spec, careful review). |
| Unsubscribe rate | >20% within first month of subscribing | Reconsider email cadence or copy. |

Run this scoreboard quarterly. The retail-first principle holds: don't expand until usage data demands it.
