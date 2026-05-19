# Livermore Tiered GTM — Build Roadmap

**Source:** `Livermore_Tiered_GTM_Proposal.docx` (May 19, 2026)
**Owner:** Jimmy Gu
**Status:** Ready for execution

This roadmap turns the tiered service plan (Scout / Strategist / Quant + Creator Program) into six sequenced engineering stages. Each stage has a dedicated PRD in this folder that can be handed directly to Claude Code as a single working session.

---

## How to use these files

Each `0N_*.md` file is a self-contained PRD. To execute a stage:

1. Open Claude Code in the repo root: `cd /Users/jimmygu/the_counselor && claude`
2. Paste or attach the stage PRD as the initial prompt: `/file build_specs/01_identity_and_entitlements.md`
3. Tell Claude Code to "implement Stage N per the attached spec, branch name `stage-N-<slug>`"
4. Claude Code branches, builds, tests, and opens a PR
5. Review, merge, deploy, move to next stage

Each PRD includes:
- **Context** — why this stage exists and what it depends on
- **In/Out of scope**
- **Data model changes** (SQLAlchemy + Pydantic)
- **API contracts** (new + modified routes)
- **Frontend work** (Next.js routes + components)
- **Acceptance criteria** (testable)
- **Test plan** (unit + integration + e2e)
- **Edge cases & error handling**
- **Migration plan** (where applicable)

---

## Tech stack assumptions

**Existing (do not change):**
- Backend: FastAPI (Python 3.11+), SQLAlchemy 2.0, PostgreSQL (prod) / SQLite (local fallback)
- Frontend: Next.js 14+ App Router, TypeScript, Tailwind, shadcn/ui
- Data: Alpha Vantage (prices), FMP Starter (fundamentals), SEC EDGAR (10-K), LLM (gpt-4o-mini)
- Hosting: Railway (API) + Vercel (web)
- LLM gateway: OpenAI-compatible chat completions adapter

**New (locked defaults):**
- Auth: NextAuth.js v5 (email/password + Google OAuth provider)
- Billing: Stripe (Checkout + Customer Portal + webhooks)
- Email: Resend (transactional + marketing)
- Analytics: PostHog Cloud (events + feature flags + A/B + session replay opt-in)
- Background jobs: FastAPI BackgroundTasks (existing) for short jobs; APScheduler in-process for scheduled jobs (no Celery yet)

**Why these defaults:**
- NextAuth: free, fits Next.js, no vendor lock-in; Google OAuth covers ~70% of US retail signup volume.
- Stripe: industry standard; Customer Portal eliminates ~5 self-build screens.
- Resend: best DX for transactional + marketing in one tool; 3K/mo free, $20/mo for 50K.
- PostHog: events + feature flags + A/B in one tool. Critical for the H1 paywall A/B test (Section D of the proposal). 1M events/mo free.

---

## Stage map

| # | Stage | Weeks | Depends on | Unblocks |
|---|---|---|---|---|
| 1 | Identity + Entitlements | 1–2 | — | All downstream stages |
| 2 | Billing + Trials | 3–4 | Stage 1 | Stages 3, 5 |
| 3 | Endpoint Gating + Upgrade UX | 5–6 | Stages 1, 2 | Revenue activation |
| 4 | Community + Sharing | 7–8 | Stage 1 | Stage 5 (Creator referrals) |
| 5 | SEO + Creator Program | 9–10 | Stages 2, 4 | Growth flywheel |
| 6 | Analytics + Lifecycle | 11–12 | Stages 1–5 | H1–H5 hypotheses can be tested |

**Critical path:** 1 → 2 → 3 unlocks revenue. 1 → 4 → 5 unlocks growth. Stages 4 and 2 can run in parallel after Stage 1 if you have two engineers.

---

## Stage 1 — Identity + Entitlements

Adds users to a product that currently has none, and the entitlements layer that every paid feature will hang off.

**Ships:** Signup/login (email + Google), user profile, plan record (`scout` default), entitlement resolver (`get_entitlements(user)` → caps), monthly run counter, migration adding nullable `user_id` to existing tables.

**Risks:** Existing anonymous backtests need a backfill story. Plan record needs to handle both authenticated and anonymous users in the gating layer (Stage 3).

**Spec:** [`01_identity_and_entitlements.md`](./01_identity_and_entitlements.md)

---

## Stage 2 — Billing + Trials

Stripe Checkout + Customer Portal + webhooks, 14-day no-credit-card trial, monthly + annual SKUs for Strategist ($24/$19) and Quant ($79/$59).

**Ships:** Stripe products + prices, checkout endpoint, webhook handler, subscription state machine (`trialing` / `active` / `past_due` / `canceled`), Customer Portal link, dunning grace period (7 days), plan-switching prorations.

**Risks:** Webhook idempotency, trial-to-paid conversion edge cases (card declined on conversion), tax/VAT handling for international (deferred — US only at launch).

**Spec:** [`02_billing_and_trials.md`](./02_billing_and_trials.md)

---

## Stage 3 — Endpoint Gating + Upgrade UX

Apply the entitlements layer to the 7 existing endpoints. Build the in-product upgrade UX: soft paywalls, upgrade modals, quota badge, trial banner.

**Ships:** Decorator/dependency that gates each FastAPI route; universe-size validator; history-window enforcer; Market Pulse top-250 whitelist; commodity/A-share asset-class checks; upgrade modal component; quota badge in nav (`3 of 5 runs left`); trial countdown banner; expired-trial state.

**Risks:** Existing endpoints have no consistent error envelope for "upgrade required" — needs a new 402 contract. Universe validation must be backend-enforced (frontend can be bypassed).

**Spec:** [`03_endpoint_gating_and_upgrade_ux.md`](./03_endpoint_gating_and_upgrade_ux.md)

---

## Stage 4 — Community + Sharing

Build out the `/community` pillar from "thin" to "useful." Publishing a strategy is the core viral loop.

**Ships:** Publish/unpublish/edit endpoints, `/community` feed page, strategy detail page (with backtest viewer), follow/unfollow, watermarked share URL (`livermore.app/s/<slug>?via=<handle>`), verified badge UI for Quant + Creator, likes + threaded comments.

**Risks:** Spam strategies (low-quality publishing), moderation queue, watermark URL collision, search/discovery cold-start.

**Spec:** [`04_community_and_sharing.md`](./04_community_and_sharing.md)

---

## Stage 5 — SEO + Creator Program

Top-of-funnel growth. SEO landing pages + creator referral attribution.

**Ships:** 50 long-tail template landing pages with JSON-LD structured data; 2–3 comparison pages (`/compare/composer`, `/compare/tradingview-plus`); sitemap.xml; Creator application form (`/creators/apply`); UTM-based attribution; Creator dashboard (referrals, conversions, revshare estimate); revshare payout calculation (manual approve, automated email); performance gate (drop creator if <2 strategies/quarter or <10 referrals).

**Risks:** Templates must be runnable by Scouts (Stage 3 must be live first); SEO will be slow (~3–6 months to see real traffic).

**Spec:** [`05_seo_and_creator_program.md`](./05_seo_and_creator_program.md)

---

## Stage 6 — Analytics + Lifecycle

Instrumentation + email lifecycle. Without this, you cannot run the H1–H5 hypotheses or build the retention loop.

**Ships:** PostHog event taxonomy (~25 events), funnel definitions, feature flags for the H1 paywall A/B (3-way: runs-meter vs history-window vs universe-size), Resend email templates (welcome, weekly digest, trial day 7/13, soft upsell, winback), scheduled email workflow runner.

**Risks:** Email deliverability cold-start, PostHog session replay PII exposure (must scrub financial inputs from chat parser), CAN-SPAM compliance.

**Spec:** [`06_analytics_and_lifecycle.md`](./06_analytics_and_lifecycle.md)

---

## Out of scope (deferred to Year 2)

These were intentionally excluded from this build plan:

- **QA agent** — removed from tier proposal per May 19 revision
- **Live trading execution** — Livermore is research-only; this is a separate product
- **Mobile app** — Year 1 is responsive web only
- **Multi-currency / international tax** — US-only at launch
- **Enterprise / RIA admin tools** (team seats, audit logs, SSO) — Year 2 if Quant traction validates
- **Custom strategy engine extensions** (factor-based, options, pairs) — separate engine work, not a tiering question
- **A-share execution data beyond ETFs** — current FMP/Alpha Vantage coverage is enough for the Year 1 Quant tier
- **Self-service Creator payouts** — Year 1 uses Stripe Connect manual transfers; full self-serve in Year 2

---

## Success metrics (Day 90 from start of Stage 1)

From the GTM proposal:

- ≥2,500 paid Strategists active (≈$50K MRR run-rate)
- ≥10 active creators; ≥20% of new paid signups attributed to creator referrals
- H1 paywall variant resolved; production setting locked
- Day-30 retention for Strategists ≥ 65%
- NPS from paid users ≥ 30

If any of these slips by >25%, revisit pricing or gating before adding more features.

---

## Dependencies on existing codebase

These files will be touched. Stage PRDs assume they exist in their current form:

**Backend (`apps/api/`):**
- `app/main.py` — FastAPI entry, startup hooks
- `app/core/config.py` — pydantic settings
- `app/core/database.py` — engine, session
- `app/models/*.py` — SQLAlchemy models (will add `user.py`, `subscription.py`, `usage_event.py`, `community_strategy.py`, etc.)
- `app/api/routes/` — backtest, robustness, insights, chat, symbols, data, qa, admin
- `app/services/` — strategy_parser, insights, robustness_service, llm_adapter

**Frontend (`apps/web/`):**
- `src/app/layout.tsx` — root layout (will wrap with SessionProvider, PostHogProvider)
- `src/app/page.tsx` — homepage
- `src/app/templates/` — template gallery
- `src/app/workspace/` — research workspace (existing)
- `src/app/stocks/[ticker]/` — Market Pulse (existing)
- `src/app/commodities/[symbol]/` — commodity evaluation (existing)
- `src/app/community/` — community pillar (currently thin)
- `src/lib/api.ts` — API client
- `src/lib/contracts.ts` — TypeScript types
- `src/lib/i18n.ts` — locale strings

**New top-level routes added across stages:**
- `/login`, `/signup`, `/forgot` (Stage 1)
- `/pricing`, `/checkout/*`, `/account` (Stage 2)
- `/s/[slug]` — public watermarked strategy share (Stage 4)
- `/creators`, `/creators/apply`, `/creators/dashboard` (Stage 5)
- `/compare/[competitor]` (Stage 5)

---

## Env vars added across stages

Stage PRDs list these in detail. Summary:

```bash
# Stage 1
NEXTAUTH_URL=https://livermore.app
NEXTAUTH_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Stage 2
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STRATEGIST_MONTHLY=price_...
STRIPE_PRICE_STRATEGIST_ANNUAL=price_...
STRIPE_PRICE_QUANT_MONTHLY=price_...
STRIPE_PRICE_QUANT_ANNUAL=price_...

# Stage 5 (creator program)
STRIPE_CONNECT_CLIENT_ID=ca_...  # optional, manual transfers OK at launch

# Stage 6
RESEND_API_KEY=re_...
RESEND_FROM=team@livermore.app
NEXT_PUBLIC_POSTHOG_KEY=phc_...
NEXT_PUBLIC_POSTHOG_HOST=https://us.posthog.com
```

---

## Open product decisions (resolve before Stage 3 ships)

These were called out in the proposal but need a final answer:

1. **Trial duration** — proposal says 14 days. Confirm.
2. **Annual discount mechanism** — show two prices on pricing page, or one toggle? Proposal assumes one toggle.
3. **Creator revshare cliff** — 10% of first-year MRR. Does it stop at month 12, or is it lifetime? Proposal says first-year only.
4. **Free-tier abuse threshold** — Stage 1 enforces 1 account per email. Do we also enforce 1 per IP or device? Recommend yes, but allow override on appeal.
5. **A-share access** — Quant only. Confirm we do not show A-share search results to Scout (currently we do; will be gated in Stage 3).
6. **Sandbox reviewer iteration counter persistence** — counter currently resets per session. Should it persist per user? Recommend yes (Stage 1 makes user identity available, so this is cheap).

These are recorded again in Stage 3's "Open questions" section since that's where they land in code.
