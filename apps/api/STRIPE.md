# Stripe Setup Runbook

## Prerequisites

1. A Stripe account with test mode enabled.
2. `stripe` CLI installed (`brew install stripe/stripe-cli/stripe`).
3. Price IDs from the setup script (see below).

---

## 1. Create products and prices

Run once per environment (test and production):

```bash
STRIPE_SECRET_KEY=sk_test_... python3 apps/api/scripts/setup_stripe.py
```

The script outputs the four price IDs — add them to your `.env`:

```
STRIPE_PRICE_STRATEGIST_MONTHLY=price_...
STRIPE_PRICE_STRATEGIST_ANNUAL=price_...
STRIPE_PRICE_QUANT_MONTHLY=price_...
STRIPE_PRICE_QUANT_ANNUAL=price_...
```

---

## 2. Configure the webhook

### Local development (Stripe CLI)

```bash
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

The CLI prints a webhook signing secret (`whsec_...`). Add it to `.env`:

```
STRIPE_WEBHOOK_SECRET=whsec_...
```

### Staging / Production

In the Stripe Dashboard → Developers → Webhooks → Add endpoint:

- URL: `https://api.livermorealpha.com/api/stripe/webhook`
- Events to listen for:
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`
  - `checkout.session.completed`

Copy the webhook signing secret and set `STRIPE_WEBHOOK_SECRET` in Railway.

---

## 3. Test the full lifecycle locally

```bash
# Start the API
cd apps/api && uvicorn app.main:app --reload

# Start the Stripe listener (separate terminal)
stripe listen --forward-to localhost:8000/api/stripe/webhook

# Trigger test events
stripe trigger customer.subscription.created
stripe trigger invoice.payment_failed
```

---

## 4. Stripe Customer Portal setup

In the Stripe Dashboard → Settings → Billing → Customer Portal:

- Enable "Allow customers to update subscriptions" (plan switching)
- Enable "Allow customers to cancel subscriptions"
- Set "Business information" to Livermore Alpha

---

## 5. JWT expiry and forced logout

Session tokens are HS256 JWTs signed with `NEXTAUTH_SECRET` (30-day expiry).  
No revocation list is maintained in Stage 1/2.

To force all users to log out (e.g., after a security incident):  
**Rotate `NEXTAUTH_SECRET`** in Railway environment variables and redeploy.

---

## 6. Test mode vs. production

- Test keys start with `sk_test_` / `pk_test_` / `whsec_test_`
- Production keys start with `sk_live_` / `pk_live_`
- The webhook handler does **not** accept test-mode events in production:
  the key prefix mismatch causes a signature verification failure.

---

## 7. Rollback

If billing must be disabled urgently:

1. Set `STRIPE_SECRET_KEY=""` — removes all Stripe API call capability.
2. Billing routes (`/api/billing/*`) will return 500; all other routes unaffected.
3. Users revert to Scout behaviour (entitlements engine uses `plan.tier`, which persists in DB).
