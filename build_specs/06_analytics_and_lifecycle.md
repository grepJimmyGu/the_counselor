# Stage 6 — Analytics + Lifecycle

**Depends on:** Stages 1–5 (events to track exist, users exist, paywalls fire, share URLs land).
**Unblocks:** H1–H5 hypotheses can be tested; retention loops close.
**Estimated build:** 2 weeks (10 working days).
**Branch:** `stage-6-analytics-lifecycle`

---

## 1. Context

Stages 1–5 ship the product. Stage 6 instruments it and runs the H1 paywall A/B test (the single highest-leverage product experiment in the GTM proposal: a 1ppt lift in Scout→Strategist conversion adds ~$26K MRR/mo). It also closes the retention loop with lifecycle email.

Two scopes, distinct subsystems:

1. **Analytics + experimentation** — PostHog. Event tracking, funnel definitions, feature flags for the H1 3-way paywall variant, session replay opt-in.
2. **Email lifecycle** — Resend. Transactional (verify, password reset, trial alerts) + lifecycle (welcome, weekly digest, upsell, winback).

---

## 2. Scope

### In scope
- PostHog SDK in `apps/web` (autocapture + identified users)
- PostHog Python SDK in `apps/api` (server-side events for billing + paywall)
- Event taxonomy (~25 events with stable schemas)
- 4 funnel definitions in PostHog dashboard
- Feature flag plumbing: read flags both client and server
- H1 paywall A/B: 3-way bucket (runs_meter / history_window / universe_size)
- Resend SDK in `apps/api`
- 8 email templates (HTML + plain text + EN/ZH)
- Lifecycle email scheduler (APScheduler)
- Email preferences page `/account/email`
- Unsubscribe handler (CAN-SPAM)
- Webhook listener for Resend events (delivered, bounced, complained)
- PII scrubbing for PostHog session replay

### Out of scope (deferred)
- SMS / push notifications (Year 2)
- In-app notifications (Year 2)
- Heatmaps + funnels beyond the 4 core ones (PostHog has them; not actively used Year 1)
- Multi-armed bandit on A/B (Year 2)
- Cohort-based email personalization beyond tier + locale (Year 2)

---

## 3. PostHog setup

### 3.1 Frontend SDK

`apps/web/src/app/providers/posthog-provider.tsx`:

```typescript
"use client";
import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";
import { useEffect } from "react";
import { useSession } from "next-auth/react";

if (typeof window !== "undefined" && !posthog.__loaded) {
  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY!, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
    person_profiles: "identified_only",
    capture_pageview: false,  // we send page_view manually for cleaner data
    capture_pageleave: true,
    autocapture: false,  // we send explicit events
    session_recording: { enabled: true, mask_all_text: false, mask_all_inputs: true },
  });
}

export function PostHogProvider({ children }) {
  const { data: session } = useSession();

  useEffect(() => {
    if (session?.user?.id) {
      posthog.identify(session.user.id, {
        email: session.user.email,
        tier: session.user.tier,  // available via custom session callback
      });
    } else {
      posthog.reset();
    }
  }, [session?.user?.id]);

  return <PHProvider client={posthog}>{children}</PHProvider>;
}
```

Wrap in `layout.tsx`.

### 3.2 Backend SDK

```python
# apps/api/app/services/posthog_service.py
from posthog import Posthog
posthog = Posthog(api_key=settings.POSTHOG_API_KEY, host=settings.POSTHOG_HOST)

def capture(user_id: str, event: str, props: dict | None = None):
    posthog.capture(distinct_id=user_id, event=event, properties=props or {})
```

### 3.3 Event taxonomy

All events are `snake_case`. Properties are flat (no nested objects). Currency in cents, dates ISO 8601.

| Event | When fired | Key properties |
|---|---|---|
| `page_view` | every navigation | `path`, `referrer`, `via_handle?` |
| `signup_started` | user lands on /signup | `intent?` (trial/template/etc.), `via_handle?` |
| `signup_completed` | account created | `provider` (password/google), `locale`, `via_handle?` |
| `trial_started` | POST /trial/start succeeds | `tier`, `days` |
| `template_run` | landing page backtest renders | `template_id` |
| `backtest_started` | POST /backtest/run sent | `strategy_type`, `universe_size`, `asset_classes` |
| `backtest_completed` | result returned | `strategy_type`, `total_return`, `sharpe`, `duration_ms` |
| `paywall_hit` | 402 returned | `code`, `current_tier`, `required_tier`, `paywall_variant` |
| `paywall_cta_clicked` | UpgradeModal primary CTA | `code`, `target` ("trial" / "checkout") |
| `checkout_started` | POST /checkout/session | `tier`, `billing_cycle` |
| `checkout_completed` | webhook subscription.created | `tier`, `billing_cycle`, `amount_cents` |
| `subscription_active` | webhook customer.subscription.updated → active | `tier` |
| `subscription_canceled` | webhook | `tier`, `reason?` |
| `strategy_published` | POST /community/strategies | `strategy_type`, `universe_size` |
| `strategy_viewed` | GET /s/<slug> | `slug`, `is_owner`, `via_handle?` |
| `strategy_followed` | POST /community/strategies/{id}/follow | `strategy_id` |
| `strategy_liked` | POST /community/strategies/{id}/like | `strategy_id` |
| `share_clicked` | user clicks Share button | `slug`, `surface` (twitter, copy, etc.) |
| `creator_applied` | submit application | `content_format` |
| `creator_approved` | admin approval | — |
| `referral_landed` | attribution row inserted | `via_handle` |
| `referral_converted_signup` | signup uses an attribution cookie | `via_handle` |
| `referral_converted_paid` | first paid invoice for an attributed user | `via_handle`, `amount_cents` |
| `email_sent` | Resend send | `template`, `subject_key` |
| `email_clicked` | Resend webhook | `template`, `link_url` |
| `unsubscribed` | unsub link clicked | `category` |

### 3.4 Funnels (PostHog dashboard config)

To build:

1. **Activation funnel** — `signup_completed` → `backtest_completed` (first one) → `strategy_published`. Track Day 1 / Day 7 / Day 30 cohorts.
2. **Conversion funnel** — `paywall_hit` → `paywall_cta_clicked` → `trial_started` → `checkout_completed`.
3. **Retention funnel** — `signup_completed` cohort → `backtest_completed` on Day 1 / 7 / 14 / 28.
4. **Referral funnel** — `referral_landed` → `signup_completed` → `subscription_active`.

These are dashboard-only; commit JSON exports of the dashboard configs to `apps/web/posthog/dashboards/` so they're reproducible.

### 3.5 H1 paywall A/B test

The H1 hypothesis: which paywall variant converts best for Scouts?

Three variants:
- **A: runs_meter** (current default) — Scout hits 5-runs/mo wall first, sees runs-exhausted upgrade modal.
- **B: history_window** — Scout's history window is gated at 3 years instead of 5; hit history paywall earlier.
- **C: universe_size** — Scout's universe is 3 tickers instead of 5; hit universe paywall earlier.

Implementation:

PostHog feature flag `paywall_variant` with 3-way bucket (33/33/34). Bucket key: `user.id`.

Server-side read (in entitlements service):

```python
def get_entitlements(user, usage):
    base = TIER_CAPS[user.plan.tier].copy()
    if user.plan.tier == "scout":
        variant = posthog.get_feature_flag("paywall_variant", user.id, default="A")
        if variant == "B":
            base["history_window_years"] = 3
        elif variant == "C":
            base["universe_size_max"] = 3
    # ... rest unchanged
```

Run for 4 weeks minimum, target ≥500 Scouts in each bucket. Look for ≥25% lift in `paywall_hit → trial_started → checkout_completed` end-to-end conversion.

Stop conditions:
- One variant ≥95% probability of being best (Bayesian, PostHog defaults)
- Or 4-week timer
- Or one variant tanks Scout retention (< 60% of D7 baseline)

### 3.6 PII scrubbing

PostHog session replay may capture form inputs. Chat strategies often contain ticker symbols + dollar amounts — fine. But avoid email/password fields:

```typescript
// Tag inputs with class="ph-no-capture" or data-ph-capture-attribute-noscrub
```

Verify: enable session replay, sign up, replay session → email field shows as masked.

---

## 4. Resend (email lifecycle)

### 4.1 Setup

- Domain `livermore.app` verified in Resend
- DKIM/SPF/DMARC configured
- From: `team@livermore.app` (transactional) and `growth@livermore.app` (marketing)
- Reply-to: `support@livermore.app`

### 4.2 Templates (8 emails)

All templates live in `apps/api/app/emails/templates/`. React Email format compiled at deploy.

| Template | Trigger | Audience |
|---|---|---|
| `welcome` | Signup completed | All users |
| `verify_email` | Signup with email/password | Email-not-verified users |
| `password_reset` | Reset request | All |
| `trial_started` | `POST /trial/start` succeeds | New trialists |
| `trial_day_7_check_in` | 7d after trial start, if no card | Trialists |
| `trial_day_13_last_call` | 24h before trial end, if no card | Trialists |
| `weekly_digest` | Monday 9am user-locale | All authed; opt-out via prefs |
| `soft_upsell` | After 3rd paywall_hit in a week | Scouts on free, no trial |
| `winback` | 30d after trial expired without paying | Lapsed scouts |
| `payment_failed` | webhook invoice.payment_failed | Active paid users |
| `creator_approved` | Admin approves | Approved creators |
| `creator_suspended` | Performance gate fails | Suspended creators |

(8 in scope, others above are nice-to-have; pick top 8 for Year 1: welcome, verify, trial_started, trial_day_7, trial_day_13, weekly_digest, soft_upsell, payment_failed.)

### 4.3 Template structure

```
apps/api/app/emails/
  templates/
    welcome.tsx           // React Email component
    welcome_en.json       // strings
    welcome_zh.json
    trial_started.tsx
    ...
  send.py                 // wraps Resend client
  scheduler.py            // APScheduler jobs
  preferences.py          // unsubscribe state
```

Each template renders to HTML + plain text. Localized via `locale` arg.

### 4.4 Weekly digest content

Personalized to user:
- "Your week" — strategies you ran, top result by Sharpe
- "Community" — top 3 trending strategies (matching your asset class preferences)
- "What's new" — product changelog (optional, hand-maintained)
- "Upgrade nudge" — only for Scouts who hit a paywall this week; shows tier benefits inline

If a user did nothing this week, skip the digest (don't send if `weekly_digest_engagement_score == 0`). Avoid noise.

### 4.5 Soft upsell trigger

Fires after `paywall_hit_count_this_week ≥ 3` for a Scout who has not started a trial. Single send, snooze 30 days. Template emphasizes the specific paywall codes they hit (e.g., "You've hit the 5-run limit 3 times — Strategist gives you unlimited runs for $24/mo").

### 4.6 Email preferences

`apps/api/app/models/email_preference.py`:

```python
class EmailPreference(Base):
    __tablename__ = "email_preferences"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    transactional: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # cannot opt out of these legally
    weekly_digest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    upsell_nudges: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creator_program: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
```

UI at `/account/email` lets user toggle categories. Unsubscribe link in every marketing email goes to a one-click unsub endpoint that flips the right toggle.

### 4.7 Send pipeline

```python
# apps/api/app/emails/send.py
def send_email(user: User, template: str, props: dict, category: str = "marketing"):
    prefs = get_or_create_prefs(user.id)
    if category == "marketing" and not prefs_allows(prefs, template):
        log_skipped(user.id, template)
        return
    html, text = render_template(template, user.locale, props)
    subject = get_subject(template, user.locale, props)

    resend_id = resend.send({
        "from": FROM_TRANSACTIONAL if category == "transactional" else FROM_MARKETING,
        "to": user.email,
        "subject": subject,
        "html": html,
        "text": text,
        "tags": [{"name": "template", "value": template}, {"name": "category", "value": category}],
    })
    log_sent(user.id, template, resend_id)
    capture(user.id, "email_sent", {"template": template, "category": category})
```

### 4.8 Resend webhook

`POST /api/webhooks/resend` — handles `email.delivered`, `email.bounced`, `email.complained`, `email.opened` (optional), `email.clicked`.

On `bounced`: mark user email as undeliverable (suppress further sends). On `complained` (spam report): unsubscribe from all marketing automatically.

---

## 5. APScheduler jobs (Stage 6 additions)

| Job | Cadence | Action |
|---|---|---|
| `send_trial_day_7_emails` | hourly | Find trialists 7d in with no card; send email if not already sent |
| `send_trial_day_13_emails` | hourly | Find trialists 13d in with no card; send "last call" |
| `send_weekly_digest` | Monday 9am UTC (per locale fan-out) | Send weekly digest to opted-in active users |
| `send_soft_upsell` | daily 3am UTC | Find Scouts with paywall_hit_count_this_week ≥ 3, no trial, no upsell sent in past 30d |
| `send_payment_failed_email` | event-driven via Stage 2 webhook | Immediate on invoice.payment_failed |

---

## 6. API contracts

### Email preferences

```
GET /api/me/email-preferences
  auth: required
  resp: EmailPreferenceState

PATCH /api/me/email-preferences
  auth: required
  body: { weekly_digest?, upsell_nudges?, creator_program? }
  resp: EmailPreferenceState
```

### One-click unsubscribe (CAN-SPAM)

```
GET /api/email/unsub?token=<signed>
  auth: none (token is HMAC-signed user_id + category)
  resp: simple HTML "Unsubscribed" page
```

### Resend webhook

```
POST /api/webhooks/resend
  auth: signature header
  resp: 200
```

---

## 7. Acceptance criteria

1. **PostHog identified users** — signing in fires `signup_completed` event with user id; subsequent events are tied to that user.
2. **25 events fire** — manual smoke through the app fires all 25 events with correct property shapes (verify via PostHog Live Events view).
3. **Feature flag works** — `paywall_variant` flag returns one of A/B/C deterministically for a given user.
4. **H1 variant changes entitlements** — Scout user assigned variant B sees `history_window_years=3` in `/api/me/entitlements`.
5. **Welcome email** — new signup receives welcome within 60 seconds.
6. **Trial day 7 email** — trialist with no card receives email 7 days after trial start (test by setting `trial_end` to 7d ago in staging).
7. **Trial day 13 email** — same logic at day 13.
8. **Soft upsell** — Scout who hits 3 paywalls in a week receives upsell email next day; same scout doesn't receive a second within 30 days.
9. **Weekly digest** — Monday 9am local time, opted-in users receive digest with personalized content.
10. **Unsubscribe** — clicking unsubscribe link sets the right pref toggle; future sends respect it.
11. **Bounce handling** — Resend bounce webhook marks email as undeliverable; subsequent sends skipped.
12. **PII masking** — session replay video of signup form shows email field masked.
13. **Funnels in PostHog** — 4 funnel dashboards exist; counts non-zero in test data.
14. **EN + ZH** — every email has both locales; user with `locale='zh'` receives Chinese version.

---

## 8. Test plan

### Unit tests

`apps/api/tests/test_email_send.py`:
- `test_send_respects_marketing_preference`
- `test_send_always_respects_transactional`
- `test_send_skipped_for_bounced_email`
- `test_template_renders_en_and_zh`

`apps/api/tests/test_email_schedule.py`:
- `test_trial_day_7_picks_correct_users`
- `test_trial_day_7_idempotent_same_day`
- `test_weekly_digest_skips_inactive_users`
- `test_soft_upsell_30d_cooldown`

`apps/api/tests/test_unsubscribe.py`:
- `test_token_signature_invalid_returns_403`
- `test_unsub_link_toggles_specific_category`

`apps/api/tests/test_paywall_ab.py`:
- `test_variant_assignment_deterministic`
- `test_variant_b_lowers_history_window`
- `test_variant_c_lowers_universe_size`

### Frontend tests

Playwright `apps/web/tests/e2e/analytics.spec.ts`:
- Sign up → check PostHog event `signup_completed` fires (intercept network)
- Run a backtest → check `backtest_started` + `backtest_completed`
- Get paywalled → check `paywall_hit` with code

---

## 9. Edge cases & error handling

- **Email send during heavy load** — Resend rate-limits; backoff with retries (3 attempts, exponential).
- **User changes email** — old email becomes a "secondary"? No — for Year 1, simply switch and continue sending to new email. Document this.
- **Locale fan-out for digests** — to send "Monday 9am user-locale," run the job hourly and check each user's locale's local time. Simpler: send all in UTC 9am Monday; later year add locale-aware.
- **A/B contamination across tier changes** — once user upgrades from Scout, they're out of the experiment (paywalls no longer trigger). Stop including them in conversion-rate calculation after `trial_started`.
- **PostHog client SDK blocked by ad blockers** — fine; we'll undercount but still capture server events on 402, signup, etc.
- **CAN-SPAM physical address** — every marketing email must include a US physical mailing address in the footer. Add to template chrome.
- **EU users (GDPR)** — out of scope this stage (US-only); we still implement unsub for everyone.
- **Resend webhook signature mismatch** — return 400, log. Do not act on payload.
- **Email content review** — every new template must be reviewed before going to >100 users. Establish a manual review step in PR template.
- **Variant B/C also need different paywall copy** — UpgradeModal already pulls localized copy keyed by `code`; nothing extra needed because the same codes fire (just earlier in the funnel).

---

## 10. Env vars

```bash
NEXT_PUBLIC_POSTHOG_KEY=phc_...
NEXT_PUBLIC_POSTHOG_HOST=https://us.posthog.com
POSTHOG_API_KEY=phc_...  # backend
POSTHOG_HOST=https://us.posthog.com

RESEND_API_KEY=re_...
RESEND_WEBHOOK_SECRET=whsec_...
RESEND_FROM_TRANSACTIONAL=team@livermore.app
RESEND_FROM_MARKETING=growth@livermore.app

EMAIL_UNSUB_SIGNING_KEY=<32-byte hex>
```

---

## 11. Files to create / modify

**Backend (create):**
- `apps/api/app/services/posthog_service.py`
- `apps/api/app/services/email_service.py`
- `apps/api/app/services/email_preferences_service.py`
- `apps/api/app/models/email_preference.py`
- `apps/api/app/models/email_log.py` (sent log + dedupe)
- `apps/api/app/emails/templates/*.tsx` (8 templates)
- `apps/api/app/emails/i18n/*.json` (per template, en + zh)
- `apps/api/app/api/routes/email.py` (preferences + unsub)
- `apps/api/app/api/routes/webhooks_resend.py`
- `apps/api/app/jobs/email_jobs.py`
- Tests

**Backend (modify):**
- `apps/api/app/services/entitlements.py` — read PostHog feature flag for Scouts
- `apps/api/app/api/routes/auth.py` — fire `signup_completed`, `trial_started`
- `apps/api/app/api/routes/backtest.py` — fire `backtest_*` events
- `apps/api/app/api/deps_entitlement.py` — fire `paywall_hit` on every 402
- `apps/api/app/api/routes/stripe_webhook.py` — fire `subscription_*` and trigger `payment_failed` email
- `apps/api/app/main.py` — register new jobs and routes

**Frontend (create):**
- `apps/web/src/app/providers/posthog-provider.tsx`
- `apps/web/src/app/account/email/page.tsx`
- `apps/web/src/lib/analytics.ts` — typed wrapper around posthog.capture
- `apps/web/posthog/dashboards/*.json` — exported funnel definitions

**Frontend (modify):**
- `apps/web/src/app/layout.tsx` — wrap in PostHogProvider; inject Resend unsub footer
- Every meaningful interaction: emit typed event via `analytics.track(...)`
- `src/components/UpgradeModal.tsx` — fire `paywall_cta_clicked` on CTA click
- `src/components/ShareButton.tsx` — fire `share_clicked`
- `src/components/PublishModal.tsx` — fire `strategy_published`
- `src/lib/i18n.ts` — email-related strings (preferences page)

---

## 12. Definition of done

- All acceptance criteria pass.
- 4 PostHog funnels visible with live data within 48h of deploy.
- All 8 email templates render correctly in Litmus / Email on Acid for top clients (Gmail, Outlook, Apple Mail).
- H1 paywall A/B test live; first 100 Scouts bucketed; PostHog experiment view shows results updating.
- Manual smoke: walk through one full signup → backtest → paywall → upgrade flow and verify every event fires.
- All Stage 1-5 PRDs have their referenced events firing.
- Year 1 GTM proposal's H1 hypothesis officially in test; H2-H5 hypotheses have data-collection plans documented but not actively running yet (deferred to Year 2 unless H1 finishes early).
- All 6 stages complete. GTM motion is live.
