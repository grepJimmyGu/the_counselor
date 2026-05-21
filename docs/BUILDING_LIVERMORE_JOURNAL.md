# Building Livermore — a working journal

> A behind-the-scenes record of how Livermore Alpha (谋士) got built — the
> shipped commits, the dead-ends, the decisions, the production crashes, and
> the lessons earned the hard way. Intended as raw material for future videos,
> articles, and posts.
>
> This document is **chronologically anchored but thematically organized.**
> Sections under "Episodes" are stories worth telling on their own. The
> "Quantitative timeline" at the end gives you the facts to fact-check against.
> Add to it freely — every shipping day is an episode.

---

## About this doc

- **Scope:** Backend-leaning. The frontend story (Next.js App Router, i18n, the strategy builder UX overhaul) is partially captured in git but lives mostly in screenshots and the user's memory. Annotate it later.
- **Source:** Git history (201 commits over 17 active days), `docs/KNOWN_ISSUES.md`, `build_specs/*.md`, and the session transcript from 2026-05-19/20 when this doc was authored.
- **Voice:** Notes from a long building day — not a polished post-mortem. Edit ruthlessly when you turn pieces into content.

---

## The shape of the project

**Product:** Livermore Alpha (谋士) — a tiered investment research tool. Quantitative strategy backtester + market pulse + community layer + AI strategy builder. Three tiers: Scout (free), Strategist ($24/mo), Quant ($79/mo).

**Architecture:**
- FastAPI backend on Railway (Python 3.13, SQLAlchemy 2.0, psycopg 3, Postgres 16)
- Next.js App Router frontend on Vercel (TypeScript, NextAuth, Tailwind)
- Stripe for billing (test mode through Stage 2)
- Alpha Vantage + FMP for market data

**Build cadence:** ~17 active days between April 30 and May 20 — driven by a mix of feature PRs, AI-agent collaborations (Claude Code + codex), and a stage-based roadmap in `build_specs/`.

---

## Episodes

### Episode 1 — From StrategyLab AI to Livermore (early April → early May)

The repo opens with `Initial commit` followed by `Build StrategyLab AI MVP`. Names matter: the project was called StrategyLab AI for the first ~30 commits before being renamed **Livermore (EN) / 谋士 (ZH)** in `fe496c0` (early May).

**Why the rename:** A trader who beat the market, not a tool that helps build strategies. The Chinese name 谋士 (móushì) — "the counselor / strategist" — became the project's working alias. The repo directory `the_counselor` still carries that.

**Content hook:** *Naming your product is your first product decision. We changed ours after 30 commits.*

### Episode 2 — The early bugs were boring (and that was the point)

The first three weeks were spent on infrastructure plumbing:
- Pydantic-settings JSON parsing for `ALLOWED_ORIGINS` (`963d4e9`, `d43352b`)
- Railway Postgres driver URL normalization (`f34ea1f`)
- Vercel CSS build deps (`b18a2da`)
- A `parents[]` index OOB in `config.py` for shallow path depths (`4dc8876`, `8b1d9f6`)

None of these made the demo flashier. All of them stopped the deploys. **The dull bugs at the start are what let you build the interesting features later.**

**Content hook:** *Showing the unglamorous first three weeks of a side project. Nobody talks about Pydantic env-var parsing in their YouTube intro.*

### Episode 3 — Internationalization arrived early (May 9)

`41e3913 feat: Chinese/English i18n with live language switcher` — followed immediately by `966d08a fix: resolve TypeScript build errors in i18n`.

The Chinese-first audience was a known target from the start, not a bolt-on. By the time the project rebranded a week later, ZH copy was already in the repo.

The cost: every new English string has a ZH counterpart. The benefit: half the addressable market is Chinese-speaking retail investors who don't have a tool like this.

**Decision recorded:** ZH support is in scope for every feature *except* the upgrade modal copy in Stage 1a (deliberately deferred to keep that build short).

### Episode 4 — The data-quality gate (mid-May)

`c253937 feat: data quality, buy-and-hold baseline, async robustness engine, sandbox v2` is the largest single feature commit in the repo. It introduced:

- A data-quality pre-flight that runs before every backtest
- Buy-and-hold baseline auto-displayed alongside any strategy
- Async robustness engine (5 tests: parameter sensitivity, sub-period, transaction cost, benchmark, peer ticker)
- Sandbox v2 — a "skeptical reviewer" agent that critiques the strategy

This was where the product started feeling like a real tool. Without the quality gate, garbage strategies returned garbage backtests with no warning. With it, you saw "AAPL data is suspect — 47% of bars are interpolated" before wasting cycles on a doomed test.

**Content hook:** *The single feature that turned my MVP into something I'd actually trust for my own money.*

### Episode 5 — The strategy library grew template-by-template (mid-May)

May 13-17 was a strategy-engine sprint. In sequence:
- Moving average crossover (baseline)
- Cross-sectional momentum
- Time series momentum
- Sector rotation, dual momentum, low vol
- Bollinger mean reversion, pairs trading
- **Value composite, quality Piotroski, buyback yield** (fundamental factor templates)
- **PEAD drift, earnings revision** (post-earnings-announcement strategies)
- **News sentiment momentum, insider buying** (alternative-data strategies)
- **Multi-factor composite** (Pro-tier capstone — combines value + quality + momentum + low-vol)

Each template was a separate PR, merged in sequence. By the end of the sprint, the library covered 22 distinct strategy types — enough that the homepage could credibly promise "find a strategy that matches your thesis."

**Content hook:** *Building a strategy library is not 22 features. It's one feature you build 22 times. Here's the template framework that made each one a 2-hour task instead of a 2-day task.*

### Episode 6 — The PRD-numbered marathon (May 16-17)

Eight PRDs in two days:
- PRD-04: Interactive parameter clarification + strategy capability glossary
- PRD-06: FMP data integration + fundamental service
- PRD-07: Stock screener backend + `/stocks` page
- PRD-08a: Company overview page + financial validation
- PRD-08b: 10-K business intelligence via SEC EDGAR
- PRD-09: News & sentiment backend
- PRD-10: News & sentiment frontend
- PRD-11: Auth (an early-access version, later superseded by Stage 1)
- PRD-12/13/14: Community layer (watchlists, votes, signals, comments)

Branch names mostly followed `feat/prd-NN-topic`. They merged quickly because each PRD was scoped tight. The Auth and Community ones would later have to be re-done as part of Stages 1–3, but PRD-11/12/13/14 served as exploratory drafts.

**Content hook:** *I shipped 8 PRDs in 48 hours. Half of them got rewritten 3 weeks later. Was it worth it?* (Spoiler: yes — the throwaway versions de-risked the real builds.)

### Episode 7 — The strategy builder V2 overhaul (May 18)

`32b8f6a feat(strategy-builder): V2 chat-based guided builder + research report workspace` — the UX redo.

The original strategy builder was a form. The V2 was a chat-based modal that walked users through a template or a custom strategy, with an animated loading screen and a Strategy Brief card showing academic evidence + historical performance context.

UI/UX Pro Max polish followed (`eaa221a polish(ui): UI/UX Pro Max pass — glassmorphism, motion design, semantic color, a11y`) — making it actually look like a paid product.

**Content hook:** *I had a working form. I rebuilt it as a chat interaction. Funnel conversion went up X%. Was the UX rewrite worth it?* (Numbers to fill in after launch.)

### Episode 8 — Stage 1: Identity & Entitlements (May 18-19)

The roadmap formalized into stages. Stage 1 introduced:
- Real user accounts (email/password + Google OAuth)
- Tier-based entitlements (Scout / Strategist / Quant)
- Monthly usage metering
- A `Plan` record per user

`30713ee feat(stage-1): Identity + Entitlements — user accounts, plans, usage metering` — the foundation.

Then it broke production. Twice.

### Episode 9 — The migration odyssey (May 19, morning)

This is the day that earned us a `KNOWN_ISSUES.md`.

**Crash 1 — `Uuid(as_uuid=False)` strips hyphens in SQLite.**
A remote PR (PR #5) tried to fix a Postgres type issue by switching `User.id` to `Uuid(as_uuid=False)`. SQLite stores those UUIDs without hyphens. The ORM returns hyphenated strings. Raw SQL queries match nothing. Tests that worked locally started returning `None` for billing-job assertions. **Fix:** revert to `String(36)`.

**Crash 2 — `InFailedSqlTransaction` on startup.**
Stage 1's migration ran multiple `ALTER TABLE` statements inside a single `with engine.begin() as conn:` block. Some were wrapped in `try/except` to handle "column already exists." In Postgres, a failed statement aborts the entire transaction — the Python `except` catches it, but Postgres still rejects every subsequent SQL on that connection. **Fix:** every risky DDL goes in its own isolated `engine.begin()` mini-transaction.

**Crash 3 — Community JOIN `operator does not exist: text = uuid`.**
Community tables (`user_watchlists`, `user_votes`, etc.) had `user_id UUID REFERENCES users(id)`. The frontend started passing Google's numeric OAuth provider ID (`115253677145661247079`) directly. Postgres rejected the non-UUID. The JOIN `u.id::text = t.user_id` also failed because you can't compare text to uuid in Postgres. **Fix:** drop the FK, widen `user_id` from UUID to TEXT.

**Crash 4 — `RENAME COLUMN` not idempotent.**
On the second deploy after a column rename, the migration tried to rename it again and failed (`RENAME COLUMN` has no `IF EXISTS` in Postgres). **Fix:** check `information_schema.columns` before renaming.

**The pattern:** Postgres and SQLite behave differently in ways that only manifest in production. Our local tests passed; Railway burned.

Four failed Railway deploys, one full afternoon of debugging, one rewritten `_run_stage1_isolated_ddl()` function.

**Content hook:** *Why every SQLite-only test suite is lying to you. The four Postgres bugs that crashed four production deploys in a single day.*

### Episode 10 — The branch graveyard (May 19, afternoon)

After the migration fight, we looked at the repo. Local + remote together: **35 stale branches.** All merged. None deleted.

```
LLM_chatbot, codex/community-trust-hub, feat/fintech-ui-revamp,
feat/fundamental-templates, feat/homepage, feat/i18n-consistency,
feat/market-pulse-data-quality, feat/multi-factor-composite,
feat/parser-new-templates, feat/pead-earnings-revision,
feat/prd-04-clarification-glossary, feat/prd-06-fmp-integration,
feat/prd-07-stock-screener, feat/prd-08a-fundamental-analysis,
feat/prd-08b-business-intelligence, feat/prd-09-news-sentiment-backend,
feat/prd-10-news-sentiment-frontend, feat/prd-11-auth,
feat/prd-12-13-14-community, feat/sentiment-insider-templates,
feat/strategy-template-iteration, feat/strategy-templates-v2,
feat/template-gallery, feat/uiux-optimization, feat/ux-journey,
feat/ux-polish-v2, feat/workspace-ui-rebuild, feature/commodity-trading,
feature/navigation-header, feature/research-templates, feature/strategy-library,
feature/strategy-storage, fix/market-snapshot-staleness,
stage-1-identity-entitlements, stage-2-billing-trials
```

Two `git branch -D` + `git push --delete` blasts later: one branch. `main`.

The convention from this point forward: **short-lived feature branches, deleted immediately after merge.** Branches outlive merges only by accident.

**Content hook:** *I had 35 git branches. I needed 1. Here's the branch hygiene I should have had from day one.*

### Episode 11 — KNOWN_ISSUES.md as a deliberate artifact (May 19, late afternoon)

After Crash 1-4, we created `docs/KNOWN_ISSUES.md`. Not as a wiki, as a **structured ledger**: short title, date, symptom, root cause, fix, files, rule.

Eleven entries by end of May 19, including pre-Stage-1 bugs (price_bars NOT NULL, ETFs leaking into stocks, multi_factor_composite divide-by-zero).

The doc included a Quick Reference: Cross-Dialect SQL Rules table — the kind of thing you reach for at 2 a.m. when your migration is on fire.

Critically: **at this point the doc existed but no one (human or agent) was reading it proactively.** That gap would be closed two days later (Episode 14).

### Episode 12 — Stage 2: Billing + Trials (May 19, evening)

Stripe integration with the full belt-and-suspenders treatment:
- Pricing page with 4 tier options (Strategist mo/yr, Quant mo/yr)
- 14-day trial flow (no card required, one-per-lifetime via `Plan.trial_end` audit)
- Checkout sessions + Customer Portal
- Webhook handler with HMAC verification + idempotency via `stripe_events` table
- APScheduler jobs: `expire_trials_job` (hourly :15), `dunning_expiry_job` (hourly :30)

Built and shipped in roughly the same evening that started with the migration odyssey. **Stage 2 was clean.** The work in Stage 1 — including the bug-fixing — had paid down enough technical debt that the Stripe layer slotted in without incident.

### Episode 13 — The strange decision about Stage 3 (May 20, morning)

The Stage 3 PRD as originally written (`build_specs/03_endpoint_gating_and_upgrade_ux.md`) was 600+ lines covering: 10 gating codes, an upgrade modal, a soft paywall, a quota badge, a top-250 ticker registry, API access with rate limits, an `ApiKey` model, and more.

The honest read: **too ambitious for one stage.** And: **the API access piece doesn't have a single requesting user.**

Counter-proposal: cut API access entirely, defer asset-class gating, defer the supply-chain gate, only ship the highest-leverage gates (runs quota, universe size, history window, Market Pulse top-250). And add a graceful anonymous flow so visitors can try the product before signing up.

Result: a new build spec — `01a_simplifications_and_anonymous_patches.md` — wedged between Stage 1 and Stage 3.

**Decision recorded:** *Just because a feature is in a PRD doesn't mean it's required. Cut what no one asked for. Ship what unlocks revenue.*

**Content hook:** *I had a 600-line PRD. I cut 60% of it. Here's how I decided what to keep.*

### Episode 14 — Stage 1a in one session (May 20, mid-day)

Six commits, in phases:
1. **Data models** — `WeeklyUsage`, `AnonymousSession`, `SavedStrategy` + DB migration
2. **Entitlements rewrite** — weekly meter, anonymous caps, new `TIER_CAPS` matrix
3. **Services** — anonymous cookie management, saved-strategy CRUD with Scout force-public
4. **Routes** — anonymous endpoints, saved-strategy CRUD, auth merge on signup, Stripe webhook attribution log
5. **Tests** — 24 new backend unit tests
6. **Frontend** — types, hook, `QuotaBadge` in nav, `AnonymousCTA` component

347 tests passing. Frontend builds clean. Six commits, all green per phase.

**Key architectural decisions made along the way:**
- **Path A vs Path B** for saved strategies: the legacy mechanism stored "saved" strategies as `backtests` rows with `slug != null`. Cleaner: a separate `SavedStrategy` table. Chose Path A (new table). Marked `backtests.slug != null` rows as not backfilled (their `strategy_json` can't be reconstructed from `result_payload`).
- **No backend template registry.** The frontend's `researchTemplates` array stays as the source of truth. Anonymous endpoint accepts strategy_json from the client — the template_id is a free-form telemetry string. Server-side whitelist deferred to Stage 5.
- **Route collision averted.** New saved-strategy CRUD got mounted at `/api/saved-strategies` instead of `/api/strategies` to avoid colliding with the legacy slug-based PRD-02 routes.

### Episode 15 — Production crash twins (May 20, afternoon)

Two more deploys failed in sequence:

**Crash 5 — FastAPI `status_code=204` strict mode.**
The `DELETE /api/saved-strategies/{id}` route was declared `status_code=204` with `-> None` return type. FastAPI 0.115 on Railway's Python 3.13 asserts at import time that 204 routes cannot have a response body. Local Python 3.9 didn't enforce this; production did. **Fix:** `response_class=Response` and return `Response(status_code=204)`.

**Crash 6 — Foreign-key type mismatch.**
The new `AnonymousSession.converted_to_user_id`, `WeeklyUsage.user_id`, and `SavedStrategy.user_id` each had `ForeignKey("users.id")`. `Base.metadata.create_all` generated `FOREIGN KEY (user_id) REFERENCES users(id)` in the DDL. Production rejected it. Why was murky — production `users.id` *should* have been VARCHAR(36) matching the source columns, but the FK creation failed regardless. **Fix:** drop the FK constraints entirely. App-layer enforces user identity, mirroring the community-tables pattern.

Two more failed deploys. Two more entries to add to `KNOWN_ISSUES.md`.

**Content hook:** *Why every "it works locally" deploy crash should be a candidate test in your CI.*

### Episode 16 — Building the learning loop (May 20, late afternoon)

The breaking realization: **`KNOWN_ISSUES.md` was a graveyard.** Created, never read, every bug repeated.

Three-layer fix:

1. **`apps/api/CLAUDE.md`** — automatically loaded by Claude (and any agent) when working in the backend. TL;DR of the eight highest-frequency traps, each with a code pattern and a pointer back to the post-mortem. The doc gets read on every session start. Cost: 1k tokens per session. Value: agent stops and checks before writing the same bug.

2. **`tests/test_app_invariants.py`** — runs on every `pytest` invocation. Imports the app (catches FastAPI startup assertions like the 204 trap). Inspects routes (catches 204+response_model combos). Two tests, fast, no Postgres needed.

3. **Extended `tests/test_postgres_migrations.py`** — was 4 tests, became 7. New regressions:
   - `test_all_user_id_columns_across_schema_are_text_compatible` — generalizes the community check
   - `test_no_new_fk_constraints_point_at_users_id` — catches future tables introducing FKs to users.id (the trap from Crash 6), with `plans`/`monthly_usage` grandfathered explicitly
   - `test_stage_1a_tables_accept_non_uuid_user_id` — Google numeric ID regression for the new tables

The CI ran. The new tests caught issues *in our own work* — `server_default` missing on `WeeklyUsage` counters, `is_public` on `SavedStrategy`, the JSONB cast. Three more iteration commits to get green. The system was working.

**Content hook:** *I had a wiki of past bugs. Nobody read it. Here's how I turned it into automated guardrails that prevent the same bug from happening twice.*

### Episode 17 — The codex agent at the same time (May 20, ongoing)

An undercurrent throughout the day: **a codex agent was working in parallel** on a separate branch (`codex/improve-chat-builder`). It added `feat: add builder chat drawer` and `feat: expose guest chat builder section` — independent work that landed on its own branch.

This caused exactly one moment of confusion: switching to `main` showed Stage 1a missing from `git log -8`, because the local checkout was actually on the codex branch (which had branched off pre-Stage-1a). A `git log origin/main` confirmed Stage 1a was on the remote.

The implicit lesson: **agents working in parallel on long-running branches need clear ownership.** The codex branch never picked up Stage 1a; if/when it gets merged, it'll need a rebase or merge first.

### Episode 18 — Midday May 20 checkpoint

- **Stages 1, 1a, 2 shipped.** Production stable.
- **Stage 3 planned and scoped down** to the high-leverage gates.
- **Stages 4-6 in `build_specs/`** but not started: community publish, SEO/Creator Program, analytics + lifecycle.
- **Learning loop active.** Backend agents read `apps/api/CLAUDE.md` automatically. CI catches the recurring traps. `KNOWN_ISSUES.md` cross-links to both.
- **Tests: 349 SQLite + 7 Postgres + 2 app-invariant = 358** all green.
- **One open follow-up:** 26 pre-existing frontend lint errors waiting for cleanup.

### Episode 19 — Stage 3 in one afternoon (May 20, evening)

The original Stage 3 spec was 600 lines: API access namespace, asset-class gating, supply-chain deep-dive, commodity framework, 50-page top-250 list, ZH localization for upgrade modal copy. Cut it down to the revenue-blocking core in a 90-minute conversation:

- **Cut entirely:** API access (no one asked), asset-class gating (defer), commodity framework gating (defer), supply-chain (defer), ZH copy (defer), refresh script (static file v1).
- **Kept:** runs quota, custom-strategy universe + history, robustness suite test names, Market Pulse S&P 500 scope.
- **Cleaner mental model:** use the full S&P 500 (~500 tickers) instead of "top 250 by market cap" so the gate doesn't drift.

The build went in six phases — `require_entitlement` dep + `GATING_ENABLED` flag + S&P 500 list, then per-route wiring, then 24 backend tests, then the frontend `UpgradeModal` + `SoftPaywall` + 402 interceptor. Six commits. All green per phase.

**Key save:** the `runBacktest()` frontend call didn't pass an auth token. Adding gating broke production for everyone who'd hit the workspace. Caught in design review before any code shipped to prod; fixed alongside the modal wire in Phase 6.

**Quote, accidentally produced:** *"Just because a feature is in a PRD doesn't mean it's required."*

### Episode 20 — Stage 4a: the viral loop primitive (May 20, late evening)

The community pillar was "thin." Stage 4 spec promised feeds, comments, follows, likes, moderation, OG image generation, profile pages. Same cut pattern: keep only the *primitive that creates the viral loop.*

What shipped:
- `published_strategies` table — frozen snapshot semantics (editing the saved version doesn't leak)
- `attribution_visits` table — every `/s/<slug>?via=<handle>` click recorded; HMAC-cookie joins it to the eventual signup; Stripe webhook stamps `converted_to_paid_at`
- `/s/[slug]` public page — anonymous-viewable, persistent signup CTA preserving the referrer handle
- Scout *auto-publish* — every Scout save also creates a published row (no privacy option at Scout tier, per Stage 1a's `saved_strategies_always_public`)
- `ShareButton`, `VerifiedBadge`, `PublishModal`

**The naming collision moment:** the existing community route was `community.py` (signals/votes from PRD-12/13/14). We mounted the new CRUD at `/api/community/strategies/*` and the saved-strategy CRUD at `/api/saved-strategies/*` to avoid the legacy `/api/strategies/{slug}` path.

**Content angle:** *"The viral loop in 23 tests."* The tests document every conversion path: track-visit → signup converts → Stripe paid converts → first-touch wins → self-attribution rejected → annual prepay ($228 → $22.80 revshare).

### Episode 21 — Stage 4b in 90 minutes, Stage 5a in 2 hours (May 20, night)

- **4b:** Discovery feed on `/community` (so published strategies are reachable without a direct URL) + "Clone to workspace" button on `/s/[slug]`. Two surfaces. Both shipped in one commit.
- **5a:** `stripe_invoices` ledger + `Plan.comped` + `creators` / `creator_applications` / `creator_payouts` + the **revshare math itself.** 10% of first-year MRR; excludes refunded; caps at 365 days; self-attribution belt-and-suspenders. 8 unit tests.

The SEO half of Stage 5 got cut hardest: 50 landing pages reduced to *3 sample pages* (NVDA 200-day MA, AAPL RSI, Mag-7 momentum) because the other 47 are editorial work, not code. Pages prerender as static HTML via Next 15 `generateStaticParams`. JSON-LD blocks (`FAQPage`, `HowTo`, `BreadcrumbList`). Static OG image deferred to dynamic in 5b.

**Honest disclosure inside the spec:** the `seo-templates.ts` registry now sits next to a comment saying "never fabricate returns; reference real data only." That rule's important for SEO credibility AND for Google E-E-A-T scoring.

### Episode 22 — Stage 6a + the forget-proofing layer (May 20, very late)

Stage 6 is two subsystems (PostHog + Resend) that mostly need traffic to matter. The "what if I forget" question came up before we started building.

The answer that landed: **`docs/DEFERRED.md`** as a canonical list of cuts, with each entry carrying a *concrete trigger condition*. Plus **three tripwire log lines** that emit `DEFERRED_TRIGGER: <name> — <why>` when the corresponding condition fires.

Run `railway logs --service api | grep DEFERRED_TRIGGER` to surface the catch-up backlog. The day the first trial expires without a card, you see `DEFERRED_TRIGGER: trial_day_7_email`. The day the first ZH user signs up: `DEFERRED_TRIGGER: zh_email_templates`. The doc tells you what's still owed and roughly how long.

The technical pattern is **safe no-op** — both PostHog and Resend wrappers silently skip when API keys aren't set. The day env vars land in Railway / Vercel, events start flowing and emails start sending. Zero code change required.

**Content angle:** *"How to build for 10x traffic when you have 0x traffic."* Most of Stage 6's value is in the rails — `track()` calls everywhere, `send_email()` calls on signup — that activate the moment you have users to act on. The forget-proofing layer means you don't have to remember to wake them up.

### Episode 23 — Where we actually are at the end of May 20

- **Stages 1, 1a, 2, 3, 4a, 4b, 5a, 6a all shipped.**
- **`main` at `ce5492d`.** 28 commits since this morning.
- **Tests:** 411 backend + 7 Postgres + 2 app-invariant = **420** all green.
- **Frontend:** clean build, `/sitemap.xml` + `/s/[slug]` + `/templates/[slug]` (3 SSG pages) live.
- **Production:** Railway healthy, Vercel healthy, gating in shadow mode by default.
- **Stage 5b + Stage 6b:** roughly 50 hours of content authoring + admin UI + cron jobs, all gated on traffic events. Tracked in `docs/DEFERRED.md`.

The infrastructure side of the GTM roadmap is complete. Everything from here is content (SEO pages, additional emails), admin tooling that's only useful with creators applying, or A/B tests that need ≥1500 Scout signups to power.

---

## Recurring journeys (themes)

### "Scope-cut every stage"
The single most important pattern of May 20. Every stage spec, as written, was 400-600 lines. Every stage shipped at roughly 30-40% of the original scope, with the cuts explicit in the commit messages and in `docs/DEFERRED.md`. The cuts followed a consistent rubric:

| Cut | Reason |
|---|---|
| API access (Stage 3) | Zero requests, dilutes Quant value prop |
| ZH copy (every stage) | Defer until first ZH user shows up |
| Comments / follows / likes / moderation (Stage 4) | Need users to moderate |
| 47 SEO landing pages (Stage 5) | Editorial work, not code |
| Comparison pages (Stage 5) | Legal review needed |
| Creator dashboard + admin (Stage 5) | Zero creators yet |
| 7 of 8 email templates (Stage 6) | Need trialists / cohorts to email |
| 15 of 25 analytics events (Stage 6) | One-line additions; do when funnels show gaps |
| Resend webhook (Stage 6) | No sends → no webhook events |
| H1 A/B test running (Stage 6) | Need ≥1500 Scouts |

The framework: ship the *primitive that unblocks revenue or growth*, defer the *polish that needs traffic to validate*.

### "Postgres ≠ SQLite"
Most of the production-only bugs trace to this. Counter-strategies:
- Run a Postgres smoke test in CI (added May 19)
- Document each gotcha in `KNOWN_ISSUES.md` with a "Rule" line
- Whitelist patterns as `apps/api/CLAUDE.md` rules
- Stop using `try/except` around DDL in shared transactions

### "It worked locally"
Most local-vs-prod divergences came from version skew:
- Local Python 3.9 vs Railway Python 3.13 (different FastAPI strictness)
- Local SQLite vs Railway Postgres (different transaction semantics)
- Local FastAPI 0.115 vs Railway FastAPI 0.115 (same version, but enforcement varies by Python version interaction)

Mitigation: the Postgres CI test runs on the same Python+FastAPI as Railway. Every regression added to that test is a permanent guard.

### "PRD said so but we changed our minds"
Multiple times we deviated from the build spec mid-build, with explicit notes:
- Stage 3's `is_anonymous` and `cta_action` fields backported to the 402 envelope earlier
- API access cut entirely
- Saved-strategy gate split between Stage 1a (saves quota) and Stage 3 (run gates)
- Path A vs Path B for SavedStrategy: spec assumed new table; we confirmed by grep that none existed and went with the spec

The build_specs are PRDs, not contracts. Notes inline when reality requires a deviation.

### "Branches are infrastructure"
Three patterns established in this project:
1. **Short-lived branches.** Delete after merge.
2. **Phase commits.** Each meaningful checkpoint is its own commit (Stage 1a had 6 phased commits on one branch).
3. **Empty commits to trigger redeploys** are legitimate. `git commit --allow-empty -m "chore: trigger Railway redeploy"` after an infrastructure outage.

---

## Quotable moments

- *"In Postgres, never mix try/except DDL with non-DDL SQL in the same `engine.begin()` block."* — `KNOWN_ISSUES.md` rule, born of 4 failed deploys
- *"Just because a feature is in a PRD doesn't mean it's required."* — Stage 3 scope-cut discussion
- *"Delete after merge."* — branch hygiene rule, from the 35-branch cleanup
- *"`KNOWN_ISSUES.md` was a graveyard."* — moment we built the learning loop
- *"Templates exempt from custom caps."* — the central Stage 1a invariant
- *"The frontend would silently report success."* — the day TypeScript types didn't catch a backend schema change
- *"App-layer enforces user identity."* — the post-mortem reasoning for dropping FK constraints
- *"Code ships today; the day env vars are set, events start flowing."* — the safe no-op pattern that defined Stage 6a
- *"Build the rails; light them up later."* — the same pattern, summarized
- *"How to build for 10× traffic when you have 0× traffic."* — possible video title for the deferred-trigger pattern
- *"Every stage shipped at 30-40% of its original spec."* — the scope-cut discipline that made the day possible
- *"What if I forget?"* — the user's question that triggered the entire `DEFERRED.md` + tripwire log lines layer

---

## Lessons (extractable for articles)

1. **CI is cheap. Use it.** Adding a 60-line CI workflow + a 100-line Postgres test caught more bugs than three months of local testing. The test runs in 90 seconds. Why didn't we have it on day one? (Honest answer: nobody felt the pain yet.)

2. **Documentation that nobody reads is worse than no documentation.** `KNOWN_ISSUES.md` sat unread for a day before we turned it into automatic-loading instructions and CI tests. The doc isn't the asset; the *reading* is.

3. **Repeat bugs are a process problem, not a knowledge problem.** Every bug in `KNOWN_ISSUES.md` was something the developer had *already learned* by the time it was documented. The problem was that *next time* — different developer, different agent, different month — the same lesson had to be re-learned. Fix the loop, not the lesson.

4. **Cross-dialect SQL is a tax, but a payable one.** SQLite for local dev + Postgres for production saves money and lets every contributor run tests without Docker. The price: every migration must be cross-dialect aware. The `is_sqlite` branch in `migrations.py` shows up everywhere — and that's correct.

5. **PRDs are starting points, not specifications.** Most stages of Livermore deviated meaningfully from the original spec. The 600-line Stage 3 PRD became a 200-line scope after talking through what we actually needed. Cut early, cut hard.

6. **Short-lived branches are non-negotiable.** 35 stale branches is what happens when "I'll delete it later" becomes the default. Make merging-and-deleting one motion.

7. **Production-only bugs are version-skew bugs.** Make local match production. Or test against production-equivalent in CI. Both, ideally.

8. **The most valuable test is the one that replays the production bug.** Not coverage. Not edge cases. The exact scenario that crashed prod, now in CI. That's how a one-time crash becomes never-again.

9. **AI agents are great at the muscle work, less great at the judgment work.** The codex agent shipped 2 commits to a chat-builder feature while we built Stage 1a. That worked because chat-builder was scoped. It would NOT have worked for the Stage 3 scope-cut decision.

10. **Tracking is part of building.** This journal is the meta-version of that lesson. The git log is technical history. The decisions and dead-ends are *product* history. Keep both.

11. **Defer-with-triggers beats defer-with-prayer.** Every cut item in `docs/DEFERRED.md` carries a *concrete trigger condition* — usually a one-line DB query or a grep against Railway logs. Without that, "we'll do it later" reliably becomes "we forgot." The cost: ~5 minutes per deferred item to write the trigger spec. The value: zero forgotten work + a clear mental model for what's actually in the backlog vs. what's just pre-launch infrastructure waiting to wake up.

12. **Safe no-op is a deployment pattern, not just a code pattern.** The PostHog + Resend wrappers in Stage 6a let us ship instrumentation that's *production-correct from day one* but does nothing until env vars activate it. This means: no second deploy when the API key arrives, no risk of accidentally sending email or polluting analytics during local dev, no special "test mode" config. Just one path through the code that does the right thing in every environment.

13. **Scope-cut every stage, every time.** The original Stage 3 was 600 lines. Stage 4 was 587. Stage 5 was 564. Stage 6 was 482. Every stage shipped at 30-40% of the original scope. The cuts followed a consistent rubric: ship the primitive that unblocks revenue or growth; defer everything that needs real traffic to validate. The cut decisions themselves are captured in commit messages and `docs/DEFERRED.md` — so the cuts are recoverable, not invisible.

---

## Quantitative timeline

| Metric | Value |
|---|---|
| First commit | 2026-04-30 |
| Most recent | 2026-05-20 |
| Active days | 17 |
| Total commits on `main` | ~230 |
| Commits on May 20 alone | 28 |
| Branches at peak | 35 |
| Branches now | 1 (`main`) |
| Backend tests | **411 SQLite + 7 Postgres + 2 invariant = 420** |
| Test count growth on May 20 | 319 → 420 (+101) |
| Frontend pages | 21 (including `/s/[slug]`, 3× `/templates/[slug]`, `/account/email`) |
| API routes | 93 |
| Strategy templates | 22 |
| SEO landing pages live | 3 of 50 planned |
| Failed production deploys (one bad day, 2026-05-19/20) | 8 |
| Stages shipped | **1, 1a, 2, 3, 4a, 4b, 5a, 6a** |
| Stages remaining | 5b, 6b (both traffic-gated) |
| Deferred items in `DEFERRED.md` | ~30 across all stages |
| Tripwire log lines for forgotten work | 3 (`trial_day_7_email`, `soft_upsell_candidate`, `zh_email_templates`) |
| Open follow-up tasks | 1 (frontend lint cleanup) |

---

## Open chapters (still to be written)

- **The first paying customer.** Still pending. When it lands, every Stage 1-2-3 design assumption gets tested for real. The H1 A/B test goes live once cumulative Scout signups cross ~1,500.
- **Stage 5b — the SEO catch-up sprint.** 47 more landing pages, comparison pages, OG image generation, creator UI. Triggered by the first 1K of organic traffic OR the first creator applying.
- **Stage 6b — lifecycle email + dashboards.** 7 more email templates, Resend webhook, PostHog funnels. Triggered by first trial expiry, first 100 sent emails, first ZH user.
- **The DEFERRED.md test.** Does the trigger-based forget-proofing actually work? We won't know until we've grepped `DEFERRED_TRIGGER` and found something we'd forgotten about.
- **First real traffic.** Every infrastructure assumption in Stages 3-6 was designed for traffic we don't have yet. Some will hold. Some will break in interesting ways.
- **The creator-driven flywheel.** Stage 4a built the watermarked share URL + attribution pipeline. Stage 5a built the payout math. The question whether ten paid creators can sustainably drive 100 paid signups/quarter is unanswered until we have ten paid creators.

---

*Last updated: 2026-05-20 (end of day). Author: Jimmy + Claude (co-pilot). This is a working journal — edit, expand, and turn pieces of it into content as the journey continues. Today added Episodes 19-23 covering Stages 3, 4a/b, 5a, 6a + the DEFERRED.md pattern.*
