# Deferred work — by stage

Canonical list of "things we cut from each stage spec" because they were
either pre-launch infrastructure with nothing to act on, or content/admin
work that doesn't have a code-only solution.

Each entry has:
- **Trigger** — the concrete condition that says "build this now"
- **Detection** — how to know the trigger fired (grep, query, or just notice)
- **Effort** — rough size if started cold

When you finish anything from this list, delete the entry.

---

## Operational triggers

When in production with users, scan Railway logs for:

```bash
railway logs --service api | grep -E "DEFERRED_TRIGGER|gate_event|email_noop"
```

Each `DEFERRED_TRIGGER` line names which item in this file just became real.

---

## Stage 3 (gating) — deferred from spec

### Templates auto-clip universe / history instead of 402
- **Trigger:** Sufficient Scout users hit `universe_too_large` / `history_too_long` paywalls AND template engagement is low
- **Detection:** `paywall_hit` event count by code in PostHog
- **Effort:** ~2 hours
- **Note:** Today templates ignore the caps entirely (they use the template's pre-set universe/history). The "clip" alternative would silently reduce a custom strategy to fit Scout caps. Defer pending real signal.

### Robustness "scheduled re-runs" for Quant
- **Trigger:** First Quant user requests recurring robustness
- **Detection:** Manual ask in support
- **Effort:** ~4 hours

---

## Stage 4 (community + sharing) — deferred from spec

### Threaded comments on published strategies
- **Trigger:** First user asks "can I comment?" OR feed has ≥50 publishes
- **Detection:** Support ticket OR `SELECT count(*) FROM published_strategies WHERE NOT is_deleted >= 50`
- **Effort:** ~3 hours (new `published_strategy_comments` table + threading + UI)

### Likes / follows on published strategies
- **Trigger:** ≥20 active publishers signaling they want feedback signals
- **Detection:** Same as comments
- **Effort:** ~2 hours (2 new tables, increment denormalized counts on the existing PublishedStrategy)

### Dynamic OG image generation via `next/og`
- **Trigger:** Active sharing on social (Twitter/Reddit) AND default OG image is hurting CTR
- **Detection:** Twitter/Reddit link previews look bland; check `share_clicked` PostHog event
- **Effort:** ~3 hours (per-strategy PNG with equity curve + return badge via Next.js image route)
- **Note:** Static placeholder at `/og-default.png` exists; need to actually drop a real image there too.

### User profile pages `/community/u/[handle]`
- **Trigger:** First user with ≥3 published strategies whose audience wants their full catalog
- **Detection:** `SELECT user_id, count(*) FROM published_strategies GROUP BY user_id HAVING count >= 3`
- **Effort:** ~2 hours

### Moderation queue + report button
- **Trigger:** First inappropriate publish OR ≥100 daily-active publishers
- **Detection:** Manual review; or `paywall_hit` events showing abuse patterns
- **Effort:** ~3 hours (Report model + admin queue + hide flag wiring)

### "Clone to workspace" anonymous variant
- **Trigger:** Anonymous viewers want to clone without signing up first
- **Detection:** `referral_landed` events with zero conversions on viral content
- **Effort:** ~1 hour (sessionStorage the strategy → restore after signup)

---

## Stage 5 (SEO + Creator Program) — deferred from spec

### 47 more SEO landing pages
- **Trigger:** Site verified in Google Search Console + 3 sample pages are indexed
- **Detection:** GSC "Pages" tab → indexed count = 3
- **Effort:** ~6-10 hours **per batch of 10** — bottleneck is editorial writing, not code
- **Note:** The `SEO_TEMPLATES` registry in `apps/web/src/lib/seo-templates.ts` is the place to add new entries. The page renderer at `/templates/[slug]` works for any new entry automatically.

### Comparison pages (`/compare/composer`, `/compare/tradingview-plus`)
- **Trigger:** Organic SEO traffic ≥1K/mo (suggests we're competing on quality)
- **Detection:** GSC impression count
- **Effort:** ~4 hours per page + legal review

### Dynamic per-template OG images
- **Trigger:** Same as the community OG image trigger (high social sharing)
- **Effort:** ~3 hours

### Creator application form `/creators/apply`
- **Trigger:** First user emails asking "do you have a creator program?"
- **Detection:** Manual / support
- **Effort:** ~3 hours (form + admin queue + approve/reject mechanics)

### Creator dashboard `/creators/dashboard`
- **Trigger:** First creator approved (need an applicant first)
- **Effort:** ~4 hours

### Performance gate quarterly cron
- **Trigger:** Same as creator dashboard — must have creators first
- **Effort:** ~2 hours (APScheduler job + suspension logic + admin reactivation)

### Payout CSV monthly cron + admin upload flow
- **Trigger:** Cumulative revshare across creators ≥$200 (i.e., real payouts to make)
- **Detection:** `SELECT SUM(amount_paid_cents) FROM stripe_invoices` joined to attribution_visits — Phase 3 service already exposes this
- **Effort:** ~3 hours

### Top-250 quarterly refresh script
- **Trigger:** S&P 500 reconstitutes meaningfully (typically every June/December)
- **Detection:** Calendar OR S&P press release
- **Effort:** ~1 hour (FMP API call + write to `sp500_tickers.py`)

---

## Stage 6 (analytics + lifecycle) — deferred from 6a

### Wire remaining 15 events
The 6a wire shipped 10 of the 25 events in the spec. Remaining:
`page_view` (frontend AnalyticsProvider already fires this), `signup_started`,
`template_run`, `checkout_started`, `subscription_active`, `subscription_canceled`,
`strategy_viewed`, `strategy_followed`, `strategy_liked`, `creator_applied`,
`creator_approved`, `referral_converted_signup`, `referral_converted_paid`,
`email_clicked`, `unsubscribed`.

- **Trigger:** Funnels in PostHog show gaps where data is sparse
- **Detection:** PostHog dashboard once first 100 events come in
- **Effort:** ~30 min per event (they're each one-line additions in existing code)

### 4 PostHog funnel dashboards (Activation, Conversion, Retention, Referral)
- **Trigger:** First day with real `signup_completed` data
- **Detection:** Just check PostHog
- **Effort:** ~1 hour total (PostHog UI work, not code)

### 7 more email templates (verify, password_reset, trial_day_7, trial_day_13, weekly_digest, soft_upsell, payment_failed)
- **Trigger by template:**
  - verify, password_reset: first user asks why they didn't get one (or proactive launch QA)
  - trial_day_7, trial_day_13: first user enters a trial (`plans.status='trialing'`)
  - weekly_digest: ≥50 WAU
  - soft_upsell: first Scout hits `paywall_hit_count >= 3` in a week
  - payment_failed: first invoice.payment_failed webhook
- **Detection:** Tripwire log lines below
- **Effort:** ~30 min per template (welcome.py is the pattern to copy)

### APScheduler email jobs (trial day 7/13, weekly digest, soft upsell)
- **Trigger:** Corresponding template exists + first user fits the criteria
- **Effort:** ~1 hour per job

### Resend webhook (`POST /api/webhooks/resend`)
- **Trigger:** First 100 sent emails (bounce % becomes meaningful)
- **Detection:** Logs show `email_sent` events accumulating
- **Effort:** ~2 hours (signature verification + delivered/bounced/complained handlers)

### Email log table + dedupe
- **Trigger:** First duplicate-send complaint
- **Effort:** ~1.5 hours

### ZH localization for emails
- **Trigger:** First `users.locale='zh'` signup
- **Detection:** `SELECT count(*) FROM users WHERE locale='zh'`
- **Effort:** ~30 min per template

### Session replay PII tuning
- **Trigger:** Session replay enabled in PostHog config
- **Effort:** ~1 hour (mark email/password inputs as `ph-no-capture`)

### A/B test actually running
- **Trigger:** ≥1500 Scout signups (500 per bucket for statistical power)
- **Detection:** `SELECT count(*) FROM plans WHERE tier='scout' AND status='active'`
- **Effort:** ~30 min in PostHog UI (create the feature flag with 33/33/34 bucket); code wire already shipped in 6a Phase 7
- **Stop condition:** ≥95% Bayesian probability OR 4 weeks elapsed OR a variant tanks D7 retention < 60% of baseline

### React Email migration
- **Trigger:** Template count ≥5 OR design polish blocked by string concat
- **Effort:** ~3 hours

### CAN-SPAM physical address
- **Trigger:** Before scaling marketing email past ~100 users
- **Detection:** Pre-launch checklist
- **Effort:** 1 minute (set `CAN_SPAM_ADDRESS` env var)

---

## Other follow-ups

### Frontend lint debt (26 errors across 22 files)
- **Trigger:** When you start touching one of the affected files for a real feature
- **Detection:** `cd apps/web && npm run lint`
- **Effort:** ~1-2 hours batch

### Postgres migration smoke test in CI for Stage 4/5/6 tables
- **Trigger:** Stage 4 OR Stage 5 OR Stage 6 production deploy regresses
- **Effort:** ~30 min (extend `apps/api/tests/test_postgres_migrations.py`)

### Set `CAN_SPAM_ADDRESS` env var
- **Trigger:** Before sending first marketing email at scale
- **Effort:** 1 minute

### Set `EMAIL_UNSUB_SIGNING_KEY` env var (currently uses an unsafe dev default)
- **Trigger:** Before going live with email sends
- **Detection:** `email_service.make_unsub_token` falls back to `"dev-only-not-secret"` when unset
- **Effort:** 1 minute (`openssl rand -hex 32`)

---

## Stage 5b / Stage 6b — pre-grouped buckets

If you eventually want clean "the next sprint" buckets:

**Stage 5b** = everything under Stage 5 here. Roughly creator UI + payout flow + the long tail of SEO content. ~25-40 hours total when content writing is included.

**Stage 6b** = everything under Stage 6 here. Roughly the remaining email templates + Resend webhook + PostHog dashboards + scheduled jobs. ~15-25 hours.

Both are gated on having traffic/users to act on.
