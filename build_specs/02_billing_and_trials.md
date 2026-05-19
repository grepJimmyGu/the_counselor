# Stage 2 — Billing + Trials

**Depends on:** Stage 1 (Identity + Entitlements).
**Unblocks:** Stage 3 (gating uses subscription status), Stage 5 (Creator revshare uses subscription events).
**Estimated build:** 2 weeks (10 working days).
**Branch:** `stage-2-billing-trials`

---

## 1. Context

After Stage 1, every user has a Plan row. Stage 2 connects that Plan row to Stripe so users can actually pay. The proposal locks the SKUs:

| Tier | Monthly | Annual (eff./mo) | Annual total |
|---|---|---|---|
| Strategist | $24 | $19 | $228 |
| Quant | $79 | $59 | $708 |

Plus a **14-day free trial, no credit card required**. The trial starts on signup (every Scout signup is effectively a Strategist trial in disguise — but they must opt in). Trial converts to paid only if the user adds a card; otherwise it expires and they revert to Scout.

This stage does NOT yet apply gating. Stage 3 does that. Stage 2's job: get Stripe state into our `plans` table reliably.

---

## 2. Scope

### In scope
- Stripe products + prices (4 prices total: 2 tiers × 2 cycles)
- Pricing page (`/pricing`) — public, lists all three tiers + Creator Program
- Checkout endpoint — creates a Stripe Checkout Session, redirects user to Stripe-hosted UI
- Trial start endpoint — sets `plans.tier='strategist'`, `status='trialing'`, `trial_end=now+14d`, **no Stripe customer yet** (no-CC trial)
- Trial → paid conversion endpoint — user adds card; creates Stripe customer + subscription; status moves to `active`
- Stripe Customer Portal link — for plan switching, cancellation, payment method updates
- Webhook handler at `POST /api/stripe/webhook` — handles 6 events (see §4.4)
- Subscription state machine — `scout` → `trialing` → `active` → `past_due` → `canceled`
- Dunning grace period — 7 days `past_due` before reverting to `scout`
- Plan switching — proration via Stripe; updates `plans.tier` on `customer.subscription.updated`
- Annual ↔ monthly switch
- Receipts via Stripe email (no custom email work this stage)

### Out of scope (deferred)
- Per-tier feature gating (Stage 3)
- Trial reminder emails (Stage 6)
- Creator revshare payouts (Stage 5)
- International tax / VAT (Year 2)
- Stripe Connect for creator payments (Stage 5 — manual transfers OK at launch)
- Gift subscriptions, coupons, promo codes (Year 2 — except a single launch promo if needed)

---

## 3. Data model

### 3.1 Reuse `plans` table from Stage 1

Stage 1 already created `plans` with the right columns. This stage populates:

- `stripe_customer_id`
- `stripe_subscription_id`
- `status` (transitions through trialing → active → past_due → canceled)
- `billing_cycle` (`monthly` | `annual`)
- `trial_end`
- `current_period_end`
- `canceled_at`

### 3.2 New table — `stripe_events`

For webhook idempotency. Stripe retries failed deliveries; we must dedupe.

```python
# apps/api/app/models/stripe_event.py
class StripeEvent(Base):
    __tablename__ = "stripe_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Stripe event id
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

### 3.3 Pydantic schemas

`apps/api/app/schemas/billing.py`:

```python
class TierOption(BaseModel):
    tier: Literal["strategist", "quant"]
    billing_cycle: Literal["monthly", "annual"]
    price_id: str  # Stripe price id
    amount_cents: int
    display_price: str  # "$24" | "$19/mo"

class PricingPage(BaseModel):
    options: list[TierOption]
    trial_days: int = 14

class CheckoutSessionRequest(BaseModel):
    tier: Literal["strategist", "quant"]
    billing_cycle: Literal["monthly", "annual"]
    return_url: str  # frontend redirect target

class CheckoutSessionResponse(BaseModel):
    url: str  # Stripe-hosted Checkout URL

class TrialStartRequest(BaseModel):
    tier: Literal["strategist", "quant"]  # which tier to trial

class TrialStartResponse(BaseModel):
    trial_end: datetime
    tier: str

class CustomerPortalResponse(BaseModel):
    url: str
```

---

## 4. API contracts

All under `apps/api/app/api/routes/billing.py`.

### 4.1 Pricing page data

```
GET /api/billing/pricing
  auth: optional
  resp: PricingPage
```

Returns the four `TierOption`s (Strategist monthly/annual, Quant monthly/annual) with display strings localized via the `Accept-Language` header. Used by frontend `/pricing` and by the upgrade modal (Stage 3).

### 4.2 Start trial (no card)

```
POST /api/billing/trial/start
  auth: required (Scout user)
  body: TrialStartRequest
  resp: 200 TrialStartResponse | 409 if user already trialing or paid
```

Behavior:
- Sets `plans.tier=<tier>`, `plans.status='trialing'`, `plans.trial_end=now+14d`, `plans.billing_cycle=None`.
- **Does not** create a Stripe customer or subscription yet.
- Idempotent: calling again for an already-trialing user returns the existing `trial_end`.
- One trial per user lifetime. If `plans.trial_end` was ever set in the past, return 409.

### 4.3 Create Checkout Session

```
POST /api/billing/checkout/session
  auth: required
  body: CheckoutSessionRequest
  resp: 200 CheckoutSessionResponse
```

Behavior:
- Look up the Stripe price id for `(tier, billing_cycle)` from env (see §6).
- If user has no `stripe_customer_id`, create one in Stripe with `email=user.email, metadata={'user_id': user.id}`. Save id to `plans`.
- Create Checkout Session with:
  - `mode='subscription'`
  - `customer=<id>`
  - `line_items=[{price: <price_id>, quantity: 1}]`
  - `subscription_data.trial_from_plan=False, subscription_data.trial_period_days=<remaining_trial_days>` if user is in trial (so they don't get a fresh 14 days; they only get what's left)
  - `success_url=<return_url>?session_id={CHECKOUT_SESSION_ID}`
  - `cancel_url=<return_url>?canceled=true`
  - `metadata={'user_id': user.id, 'tier': tier, 'billing_cycle': billing_cycle}`
- Return the URL.

### 4.4 Stripe webhook

```
POST /api/stripe/webhook
  auth: signature header (no JWT)
  body: Stripe event payload
  resp: 200 always (after enqueueing); 400 if signature invalid
```

**Critical:** verify signature using `stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)`. Reject if invalid.

Idempotency: insert into `stripe_events` first; if `IntegrityError` (already processed), return 200 immediately.

Events handled:

| Event | Action |
|---|---|
| `customer.subscription.created` | Set `plans.stripe_subscription_id`, `status='trialing'` or `'active'` based on event status, `current_period_end`, `billing_cycle` |
| `customer.subscription.updated` | Sync `status`, `current_period_end`, `billing_cycle`, `tier` (from plan price id) |
| `customer.subscription.deleted` | Set `status='canceled'`, `canceled_at=now`. Revert `tier` to `scout` **at `current_period_end`** (don't immediately strip access). |
| `invoice.payment_succeeded` | Confirm status is `active`; nothing else required |
| `invoice.payment_failed` | Set `status='past_due'`. Mark `dunning_started_at=now`. Stage 6 will send dunning email. |
| `checkout.session.completed` | Belt-and-suspenders — also verify subscription is created |

**Tier inference from price id:** maintain a constant `PRICE_ID_TO_TIER` map (loaded from env at startup). If a webhook arrives with an unknown price id, log error + alert (don't crash).

### 4.5 Customer Portal

```
POST /api/billing/portal
  auth: required (must have stripe_customer_id)
  resp: 200 CustomerPortalResponse | 404 if no customer
```

Creates a Stripe Billing Portal Session with `return_url` set to the user's `/account` page. Returns the hosted URL.

### 4.6 Cancellation (covered by Customer Portal)

No custom endpoint needed. Portal handles it. Stripe will send `customer.subscription.updated` with `cancel_at_period_end=true`, then `customer.subscription.deleted` at period end.

### 4.7 Plan switching (covered by Customer Portal)

Same — portal handles. Stripe sends `customer.subscription.updated`; webhook syncs new tier.

---

## 5. State machine

```
                       ┌──────────────────┐
                       │  scout (default) │
                       └────────┬─────────┘
                                │ POST /trial/start
                                ▼
                       ┌──────────────────┐
            ┌─────────►│    trialing      │
            │          └────┬─────────────┘
            │               │
            │  trial_end    │ user adds card
            │  reached      │ via Checkout
            │  no card      ▼
            │          ┌──────────────────┐
            │          │     active       │
            │          └────┬─────────────┘
            │               │
            │               │ payment fails
            │               ▼
            │          ┌──────────────────┐
            │          │    past_due      │
            │          └────┬─────────────┘
            │               │
            │  7-day grace  │
            │  no recovery  │
            ▼               ▼
        ┌──────────────────────┐
        │   scout (reverted)   │
        └──────────────────────┘
```

State transition rules:

- **scout → trialing** — `POST /api/billing/trial/start` (one-time, per user)
- **trialing → scout** — APScheduler job `expire_trials_job`, runs hourly, finds rows where `status='trialing' AND trial_end < now AND stripe_subscription_id IS NULL`, sets `tier='scout', status='active'`
- **trialing → active** — webhook `customer.subscription.updated` when Stripe ends the trial and starts billing successfully
- **active → past_due** — webhook `invoice.payment_failed`
- **past_due → active** — webhook `invoice.payment_succeeded` after recovery
- **past_due → scout** — APScheduler job `dunning_expiry_job`, runs hourly, finds rows where `status='past_due' AND updated_at < now-7d`, reverts to `tier='scout', status='active'`, and cancels the Stripe subscription
- **active → canceled (period end)** — webhook `customer.subscription.deleted`; revert `tier` to `scout` at the cancel time

---

## 6. Env vars

```bash
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Price IDs (created in Stripe Dashboard or via Stripe CLI)
STRIPE_PRICE_STRATEGIST_MONTHLY=price_...
STRIPE_PRICE_STRATEGIST_ANNUAL=price_...
STRIPE_PRICE_QUANT_MONTHLY=price_...
STRIPE_PRICE_QUANT_ANNUAL=price_...
```

Use Stripe test mode keys in non-prod. Document Stripe CLI setup in `apps/api/STRIPE.md`.

### Stripe Dashboard setup script

Provide `apps/api/scripts/setup_stripe.py` that creates the four prices via Stripe API, idempotently. Run once per environment.

```python
# pseudocode
products = {
    "strategist": {"name": "Livermore Strategist", "metadata": {"tier": "strategist"}},
    "quant":      {"name": "Livermore Quant",      "metadata": {"tier": "quant"}},
}
prices = {
    ("strategist", "monthly"): {"unit_amount": 2400, "recurring": {"interval": "month"}},
    ("strategist", "annual"):  {"unit_amount": 22800, "recurring": {"interval": "year"}},
    ("quant", "monthly"):      {"unit_amount": 7900, "recurring": {"interval": "month"}},
    ("quant", "annual"):       {"unit_amount": 70800, "recurring": {"interval": "year"}},
}
```

---

## 7. Frontend

### 7.1 Pricing page

`apps/web/src/app/pricing/page.tsx` — public, full-width, four-column comparison (Scout / Strategist / Quant / Creator).

Per tier card:
- Tier name + persona tagline
- Monthly toggle / Annual toggle (single switch at top of card array; both prices visible)
- Feature list (12–15 rows; same content as the doc's capability gating matrix)
- CTA button: `Start free trial` (if not signed in → `/signup?intent=trial&tier=strategist&cycle=monthly`)

Implementation note: the toggle state is preserved in localStorage and URL query (`?cycle=annual`) for sharing.

### 7.2 Trial CTA flow

1. Anonymous user on `/pricing` clicks `Start free trial` on Strategist Annual card.
2. Redirect to `/signup?intent=trial&tier=strategist&cycle=annual` (cycle preserved for post-trial conversion).
3. After signup, frontend calls `POST /api/billing/trial/start` with `tier='strategist'`.
4. Redirect to `/workspace?welcome=1` with a banner: "Your 14-day Strategist trial has started. No card required."

### 7.3 Add-card / convert-to-paid flow

When user is in trial:
- Banner in nav: "Trial ends in X days · Add a card to keep your Strategist features"
- Click → calls `POST /api/billing/checkout/session` with their original `tier` + `billing_cycle`
- Redirect to Stripe-hosted Checkout
- On return, success page shows: "You're upgraded to Strategist (annual). Welcome." Failure → "Card declined. Try again or contact support."

### 7.4 Account page additions

Extend `/account` (created in Stage 1):

- **Plan section** — Current plan badge, billing cycle, trial countdown (if trialing), next billing date (if active), payment method last 4 (if active)
- **Manage button** — calls `POST /api/billing/portal`, opens Stripe-hosted portal in new tab
- **Upgrade/Downgrade buttons** — if Strategist, "Upgrade to Quant" button → portal with target subscription set
- **Cancel** — handled in portal (no inline cancel UI)

### 7.5 TypeScript types

Add to `src/lib/contracts.ts`:

```typescript
export interface PricingTierOption {
  tier: "strategist" | "quant";
  billing_cycle: "monthly" | "annual";
  price_id: string;
  amount_cents: number;
  display_price: string;
}

export interface PricingPage {
  options: PricingTierOption[];
  trial_days: number;
}
```

### 7.6 New API client methods

Add to `src/lib/api.ts`:

- `getPricing()` → `GET /api/billing/pricing`
- `startTrial({tier})` → `POST /api/billing/trial/start`
- `createCheckoutSession({tier, billing_cycle, return_url})` → `POST /api/billing/checkout/session`
- `createPortalSession()` → `POST /api/billing/portal`

---

## 8. Scheduled jobs

Two APScheduler jobs, both hourly.

### `expire_trials_job`

```python
@scheduler.scheduled_job("cron", minute=15)
def expire_trials_job():
    """Trials end 14d after start. If no card was added, revert to Scout."""
    with get_db() as db:
        rows = db.query(Plan).filter(
            Plan.status == "trialing",
            Plan.trial_end < datetime.utcnow(),
            Plan.stripe_subscription_id.is_(None),
        ).all()
        for row in rows:
            row.tier = "scout"
            row.status = "active"
            row.trial_end = None  # keep audit? no — re-trial not allowed; track in audit_log later
        db.commit()
        logger.info(f"Expired {len(rows)} trials")
```

### `dunning_expiry_job`

```python
@scheduler.scheduled_job("cron", minute=30)
def dunning_expiry_job():
    """7-day grace after payment_failed. If still past_due, cancel and revert."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    with get_db() as db:
        rows = db.query(Plan).filter(
            Plan.status == "past_due",
            Plan.updated_at < cutoff,
        ).all()
        for row in rows:
            if row.stripe_subscription_id:
                stripe.Subscription.delete(row.stripe_subscription_id)  # cancels in Stripe
            row.tier = "scout"
            row.status = "active"
            row.canceled_at = datetime.utcnow()
        db.commit()
```

---

## 9. Acceptance criteria

1. `GET /api/billing/pricing` returns 4 options with correct prices ($24, $19, $79, $59) and trial_days=14.
2. New Scout user can call `POST /api/billing/trial/start` once → status becomes `trialing`, trial_end is now+14d.
3. Same user calling `/trial/start` a second time returns 409.
4. User in trial can call `POST /api/billing/checkout/session` → returns Stripe URL with `subscription_data.trial_period_days` equal to remaining trial days (0–14).
5. Stripe webhook `customer.subscription.created` with status `active` updates `plans.status='active'`, sets `stripe_subscription_id` and `current_period_end`.
6. Stripe webhook signature verification rejects unsigned/altered payloads with 400.
7. Same Stripe event id received twice: second one returns 200 with no-op (idempotency via `stripe_events`).
8. `customer.subscription.updated` with new price_id (annual → monthly) updates `plans.billing_cycle`.
9. `invoice.payment_failed` sets `status='past_due'`. After 7 days with no recovery, `dunning_expiry_job` reverts to Scout.
10. `expire_trials_job` reverts trialing users with no Stripe subscription after 14 days.
11. `POST /api/billing/portal` returns a Stripe-hosted URL for users with `stripe_customer_id`; 404 otherwise.
12. Frontend `/pricing` renders correctly in EN and ZH locales (use existing i18n strings).
13. Frontend trial start → checkout → return flow works end-to-end in Stripe test mode.

---

## 10. Test plan

### Unit tests

`apps/api/tests/test_billing_pricing.py`:
- `test_pricing_returns_four_options`
- `test_pricing_amounts_match_env`

`apps/api/tests/test_billing_trial.py`:
- `test_trial_start_creates_trialing_state`
- `test_trial_start_idempotent_same_session`
- `test_trial_start_409_if_already_trialed`
- `test_trial_start_409_if_paid`

`apps/api/tests/test_billing_checkout.py`:
- `test_checkout_creates_stripe_customer_first_time` (mock Stripe API)
- `test_checkout_reuses_existing_stripe_customer`
- `test_checkout_passes_remaining_trial_days`

`apps/api/tests/test_billing_webhook.py`:
- `test_webhook_signature_invalid_returns_400`
- `test_webhook_subscription_created_sets_active`
- `test_webhook_subscription_updated_changes_tier`
- `test_webhook_subscription_deleted_schedules_revert`
- `test_webhook_invoice_payment_failed_sets_past_due`
- `test_webhook_duplicate_event_is_noop`

`apps/api/tests/test_billing_jobs.py`:
- `test_expire_trials_job_reverts_to_scout`
- `test_dunning_expiry_job_cancels_after_7d`

### Integration tests

Run against Stripe test mode using `stripe-mock` (Docker) or live test keys in CI:

- E2E: signup → trial start → add card → webhook → verify `active`
- E2E: signup → trial start → wait 14d (or fast-forward via test job trigger) → verify reverted

### Frontend tests

Playwright `apps/web/tests/e2e/billing.spec.ts`:
- Visit `/pricing`, toggle annual, click Start free trial → land on `/signup?intent=trial&...`
- Sign up → land on workspace with welcome banner
- Click "Add a card" → mock Stripe redirect → return → see active plan in `/account`

---

## 11. Edge cases & error handling

- **Webhook arrives before user exists** — extremely rare (would mean Stripe signed up a customer without our endpoint). Log error, return 200, monitor.
- **User changes email in our app after Stripe customer is created** — Stripe customer email stays out of sync. Sync via `stripe.Customer.modify(...)` in the PATCH `/api/me` handler.
- **Refund flow** — Stripe handles in dashboard. Webhook `charge.refunded` is not handled in this stage; document for Year 2.
- **Subscription with multiple items** — we always create with single line item. Reject in webhook handler if `subscription.items.data.length > 1`.
- **Test mode webhook in prod** — verify by API key prefix; refuse `whsec_test_*` events in prod.
- **Failed background job** — `expire_trials_job` and `dunning_expiry_job` must be **safe to re-run**. Use idempotent updates (`WHERE status='trialing'`).
- **Daylight saving / time zones** — all timestamps are UTC.
- **Stripe rate limits** — webhook handler is fast (DB write only). Outbound API calls (customer creation, portal sessions) wrapped in retry-with-backoff.
- **Cancellation during trial** — user cancels trial via portal → `customer.subscription.deleted` arrives → revert to Scout immediately (since `current_period_end` is effectively the trial end).

---

## 12. Migration plan

1. Set up Stripe products + prices in test mode (run `setup_stripe.py`).
2. Configure webhook in Stripe Dashboard → point at `https://api-staging.livermore.app/api/stripe/webhook`.
3. Deploy backend with new tables + routes (no production traffic affected yet — endpoints just exist).
4. Deploy frontend with `/pricing` page; do not link from nav yet.
5. Smoke test full trial → checkout → webhook → portal cycle in staging.
6. Repeat in production with live Stripe keys.
7. Update nav to expose pricing link; announce trial availability.

Rollback: feature-flag the `/pricing` link in nav (PostHog feature flag, ready in Stage 6, or hardcoded env var until then). Webhook handler can be left running — it's a no-op until subscriptions exist.

---

## 13. Files to create / modify

**Backend (create):**
- `apps/api/app/models/stripe_event.py`
- `apps/api/app/schemas/billing.py`
- `apps/api/app/services/stripe_service.py` — wraps stripe API calls
- `apps/api/app/services/billing_state.py` — state-machine transitions
- `apps/api/app/api/routes/billing.py`
- `apps/api/app/api/routes/stripe_webhook.py`
- `apps/api/app/jobs/billing_jobs.py` — APScheduler jobs
- `apps/api/scripts/setup_stripe.py`
- `apps/api/STRIPE.md` — runbook for Stripe setup and webhook testing
- Tests as listed in §10

**Backend (modify):**
- `apps/api/app/main.py` — register routers + APScheduler jobs
- `apps/api/app/core/config.py` — add Stripe env vars + price id map loader
- `apps/api/app/api/routes/me.py` — PATCH endpoint syncs email to Stripe

**Frontend (create):**
- `apps/web/src/app/pricing/page.tsx`
- `apps/web/src/components/PricingTierCard.tsx`
- `apps/web/src/components/TrialBanner.tsx` (top-of-page, shows countdown)
- Tests as listed in §10

**Frontend (modify):**
- `apps/web/src/app/account/page.tsx` — add billing section
- `apps/web/src/app/signup/page.tsx` — handle `?intent=trial&tier=...&cycle=...` and auto-start trial post-signup
- `apps/web/src/lib/api.ts` — add 4 new methods
- `apps/web/src/lib/contracts.ts` — add billing types
- `apps/web/src/lib/i18n.ts` — pricing copy, trial banner copy, EN + ZH

---

## 14. Definition of done

- All acceptance criteria pass.
- Full Stripe test-mode lifecycle works end-to-end.
- Webhook idempotency verified (duplicate event sent → no-op).
- Both background jobs proven to run on schedule in staging for ≥48h.
- All new tests pass; existing tests still pass.
- Stripe Dashboard contains 2 products, 4 prices, 1 webhook endpoint.
- Documentation `STRIPE.md` reviewed.
- Production Stripe live keys configured; one live test purchase ($24 monthly Strategist) made by Jimmy as a final smoke check.
- Stage 3 can begin.
