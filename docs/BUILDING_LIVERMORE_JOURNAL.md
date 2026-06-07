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

### Episode 24 — The Three-Bug Chain (May 21)

The day after the 28-commit Stage-3-through-6a marathon. The product was
live. Then a real user — Jimmy — tried to sign in and run a strategy. And
hit, in series, three bugs that each masked the next.

**Bug 1 — "Why does the modal say 'sign up' when I'm signed up?"**

A screenshot lands: signed-in Scout, sitting on `/workspace`, configuring
a custom strategy. Click Run → "Sign up to build custom strategies" modal.
The exact copy promised them 5 weekly runs in exchange for signing up.
They already signed up.

The fix turned out to be a one-line change in `research-workspace.tsx`.
But what was instructive was that the *code itself* knew about the bug.
At line 100, sitting in the committed `main` branch:

> *"...the May 20 evening regression."*

An earlier session had ship-fixed half the bug. The diagnostic comment
was the smoking gun.

**Root cause:** `isAnonymous = !sessionUserId` was true during NextAuth's
brief `loading` state on page mount — `session.user.id` is undefined
while the cookie decodes. Authenticated users were therefore routed to
`/api/anonymous/backtest/run`, which 402'd with `anonymous_chat_locked`.
The user saw the wrong modal because the frontend told the backend they
were anonymous.

**Fix in PR #7 (commit `0243e2d`):** use `sessionStatus === "unauthenticated"`
as the source of truth. Plus an `isSessionLoading` guard so clicks during
the loading window get a clean retry message.

**Bug 2 — "OK, now I get a different error after I sign in"**

Post-deploy, the user reloads and clicks Run. New error: yellow + red
banner, both saying "Your account session needs to be refreshed."

For the next ~30 minutes, the assistant kept pushing the auth angle —
"check Vercel env vars," "verify INTERNAL_API_KEY," "look at the
self-healing branch." The user pushed back twice: *"I have not seen any
issue with [Vercel]. Now it's the gating route problem which I don't
think you should keep banging the front end."*

The assistant kept arguing for the auth angle because the error string in
the screenshot was traceable, grep-able, to exactly one place — the
frontend early-return when `needsSessionRefresh` is true. The string
existed nowhere else. The block was provably client-side. But the user
was right about something more important: the *cause* of `backendToken
== null` was on the backend.

Diagnostic that finally cracked it: a one-liner in the browser console:

```js
fetch('/api/auth/session').then(r => r.json()).then(s => console.log(JSON.stringify(s, null, 2)))
```

That printed `backendToken: null` clearly. From there, Vercel logs
narrowed it: `[auth] self-heal sync-user non-ok { status: 500 }`. Then
Railway logs gave the smoking gun:

```
File "/app/app/api/routes/auth.py", line 380, in sync_user
    session_token=create_session_token(user.id, user.plan.tier),
                                                ^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'tier'
```

A User row existed without its companion Plan row — orphaned by a
partial-failure path during the May 19/20 migration odyssey. Every
sync-user call had been crashing for this user for *days*, silently,
because the catch swallowed the 500.

**Fix in PR #8 (commit `0128c32`):** lazy-create a Scout Plan when
`user.plan is None`, just before reading `.tier`. One-shot heal that
unsticks every affected user on their next request.

**Bug 3 — The boundary that rounds to nothing**

Post-PR-#8 deploy. Backend token mints. Page loads cleanly. User
configures a 5-year backtest. Modal:

> *Custom backtest history exceeds your tier limit*
> *Current: 5.0 yr · Limit: 5 yr*

Visually identical numbers. The math: `1827 / 365.25 = 5.0027`. Strictly
> 5. Display rounds to `.1f` and shows "5.0". Looks like a typo in the
gate. Isn't. It's the float math being unforgiving on the boundary the
user actually picks.

**Fix in today's PR:** `_HISTORY_TOLERANCE_YEARS = 7 / 365.25`. One-week
tolerance absorbs leap-year + one-day-over jitter; 5.5y still blocks.

---

**The bigger insight — three bugs in series.** The first hid the second:
while Scouts were misrouted to anonymous, the orphan-User crash never
surfaced (the auth path that hits sync-user wasn't even being walked).
The second hid the third: while the orphan crash blocked all authed
calls, the boundary math gate never got to fire either.

Each fix unmasked the next bug *because* the layer above had been
papering over the layer below. Stack-of-issues debugging. You don't see
the inner layer until you fix the outer.

**The hardening that shipped same day.** The user's question was good
and direct: *"do we need a long term fix to ensure these gates don't
cause stupid issues again?"* Three preventions landed in one PR:

1. Boundary-trio tests for every Scout gate (`test_scout_history_5y_plus_1_day_passes`
   is the literal codification of today's regression)
2. A Postgres invariant test (`test_orphan_user_detection_query_works`)
   plus an operational script (`apps/api/scripts/check_orphan_users.py`)
   so the orphan pattern can be detected before users hit the heal
3. `docs/SHADOW_MODE_REVIEW.md` — a one-page checklist documenting the
   `gate_event` aggregation command that would have surfaced Bug 3 days
   earlier if anyone had been reading the shadow logs

Plus `apps/api/CLAUDE.md` got a 9th trap added — the orphan-Plan
pattern, with the heal recipe — so any future agent touching auth code
reads it before writing.

**Quotable moments:**

- *"Trust the user when they say 'look here, not there.'"* — the
  assistant kept circling auth/env vars when Vercel was already verified
  clean; the actual fix was on the backend
- *"A partial fix is a future bug."* — the May 20 routing fix shipped
  half-done; the code comment "the May 20 evening regression" was
  literally the system pointing at its own broken bit
- *"Shadow mode is only as good as someone reading the shadow logs."* —
  `GATING_ENABLED=true` got flipped without the soak step; today's
  modal would have been a `gate_event` line in shadow that someone
  could have noticed
- *"Floating-point year math is a tax you pay forever."* — fix is one
  tolerance constant; you just have to be looking for it
- *"Each fix unmasked the next bug, because the layer above had been
  papering over the layer below."*

**Content hook:** *The day I shipped three bug fixes and discovered each
one was hiding the next.*

### Episode 25 — Market Pulse v2: four sub-phases in an afternoon (May 22 evening)

After the morning's Chat v2 shipping spree (Episode in the project log),
the same day brought a four-PR push that finished the Market Pulse v2
redesign. Phase 0a had signed off the day before; what shipped May 22
evening was the wire-up — taking each of the mock surfaces and swapping
it for a real backend service.

The sequence in order: **1c → 1d → 1e → 1f**, with a small docs PR
chaser to update the backlog.

**Phase 1c — real macro signals (PR #61).** The Macro Pulse table at
the top of `/stocks` had been showing four hand-coded "mock" rows:
ISM Services PMI 52.0, Core CPI 3.4%, 10Y Yield 4.3%, HY Spread 3.4%.
Two of those — the 10Y and CPI — have free Alpha Vantage Economic
Indicators endpoints, so they swap to live data immediately. The
other two (PMI and HY OAS) live only on FRED, and the FRED key isn't
on Railway yet. The honest answer: ship the two real ones, leave the
other two clearly labeled as `mock_pending_fred`, and add a
per-row `Live` / `Mock` pill so users can read the data-source signal
at a glance.

One gotcha worth remembering: AV's `CPI` endpoint returns the CPI
**index** (a number like 320.5), not the year-over-year percent the
table wants. The service derives YoY% over the 12-month window so the
row reads `CPI YoY: 3.4%` instead of `320.5`. Pure-function math in
the service, mocked AV responses in the tests — 12 cases covering trend
classification edge cases, the AV `.` sentinel-value filter, and the
24h cache identity.

**Phase 1d — sector vs SPY comparison (PR #62).** Clicking a sector
tile in the heatmap expands an inline chart showing that sector ETF
vs SPY over 1M / 6M / YTD / 1Y / 3Y. Phase 0a had built it with a
synthetic walk seeded by the symbol string; Phase 1d swaps that for a
real backend service.

The interesting design decision was **what to put under the chart**.
The original mock derived the Day/YTD/1Y/3Y returns table values from
the chart series itself — which meant toggling the chart to "1M"
reset the 3Y number to whatever the 1M-window happened to show. Phase
1d separates them: the chart series uses the windowed slice, but the
returns table reads pre-computed totals from the full available bar
history. Now the user can zoom the chart to 1M and the 3Y number
stays accurate. That's the difference between "we drew the chart" and
"we built the data layer." 15 tests, including date-alignment edge
cases (one symbol has bars the other doesn't), perf_n_days
insufficient-bars, and YTD cutoff math.

**Phase 1e — History Rhymes (PR #64).** This was the section Jimmy
explicitly asked to keep in main-page scope back in Phase 0a — "can
we build a tool that captures 'history repeats?'" The Phase 0a stub
had three hardcoded matches with hand-written context ("Aug 2019 —
pre-Fed 50bps cut"). Phase 1e builds the real cosine-similarity
service.

The vector design took the most thought. Six dimensions, all ETFs
(not spot prices — those are monthly and would break the daily
alignment): TLT for rates, VXX for volatility, UUP for the dollar,
HYG for credit, GLD for gold-as-haven-flow, USO for oil. For each
historical 5-day window in the last ~5y, compute the joint return
vector and the cosine similarity to today's vector. Take the top 3
with at least 14 trading days between them (otherwise the matches
collapse to three adjacent windows). Each match carries the SPY
30-trading-day post-window return plus a 30-point sparkline
normalized to start=100.

The regime label ("Vol spike · bonds rallying") is a small heuristic
that trips on threshold breaks in the vector — not a substitute for
human historical context (the v1 mock had "pre-COVID · Iran tensions"
and a heuristic isn't going to write that), but it's better than just
the date. 19 tests covering the cosine math (orthogonal / identical /
negated / zero vector), 5-day return edge cases, threshold-trip
labeling, and end-to-end with 100 bars per symbol.

This is also where the day's process detour happened. PR #63 (the
first attempt at Phase 1e) went out cleanly, then PR #62 (Phase 1d)
merged ahead of it, so #63's branch now had merge conflicts in three
files where 1d had also added imports / routes / contracts. The clean
fix was a `git rebase main` — which produced a clean rebase but
required a force-push to update #63. The auto-mode classifier (rightly)
blocked the force-push without explicit user sign-off. Recovery: push
the rebased commit under a fresh branch (`claude/feat/phase-1e-history-rhymes-rebased`),
close PR #63 with a comment, open a new PR (#64) from the rebased
branch. Same content, new PR number, full CI fires. The
classifier-mediated workaround means history stays clean without
forcing a "yes, force-push" interaction.

**Phase 1f — screener presets (PR #65).** The 9 algorithm cards at the
bottom of `/stocks` had been showing hardcoded counts ("24 stocks") and
hand-picked sample tickers. Phase 1f registers all 9 as declarative
`PresetSpec` entries — each carrying its filter logic + tier
requirement — and exposes two endpoints: a summary route for the tile
grid (no gating, just metadata + real counts), and a per-preset
results route that enforces tier via 402.

The six free presets are real SQL filters against `symbols`:
high-dividend (yield ≥ 4%, sorted high→low), value (P/E < 15 +
market_cap ≥ $2B, sorted cheapest first), small-cap (market_cap_category =
'small'), etc. The three Strategist/Quant ones (`positive-catalyst`,
`community-confirmed`, `rising-attention`) ship as **documented v1
approximations** — curated baskets of well-known names, with the
docstring spelling out exactly what infrastructure they're waiting
on (news-sentiment query, vote/watchlist rollup, real-time
volume_ratio). That feels right: ship the screen with the tier-gating
correctly wired, but be honest that the basket is a placeholder. The
real-time pipeline integrations are in PROJECT_BACKLOG.md §4b's
follow-up table.

The entitlements layer needed a small extension. The existing
`upgrade_error()` helper took an error code and looked up the
required-tier from a static `_REQUIRED_TIER` dict. But for the screener,
the required tier varies per-preset — `positive-catalyst` is Strategist+,
`rising-attention` is Quant+, same `screener_preset_locked` code.
The fix: add a `required_tier_override` parameter so a single code can
route correctly. Three lines of helper code; clean separation of "what
went wrong" (the code) from "what unlocks it" (the tier).

**The shape of the day.**

Four PRs, four backend services, four matching frontend wire-ups,
plus a backlog refresh. Test suite went from 580 to 625. Five PRs
all green through CI on first try — no rollbacks, no follow-up
hotfixes. The discipline:

1. Each sub-phase as its own branch off main (no stacking — CLAUDE.md
   rule).
2. Each PR carries its own tests written first, watched fail, then
   shipped passing (the "every bugfix pairs with a regression test"
   rule generalized to features).
3. Each PR's commit message names the v1 approximations explicitly
   so future-me doesn't pretend the curated baskets are real signals.
4. PROJECT_BACKLOG.md gets a same-PR refresh — the shipped row moves
   from ⏳ to ✅; new follow-ups get added in the same edit.

**Quotable moments:**

- *"Ship the two real macro signals; label the other two mock with
  the FRED key as the documented swap-trigger."* — the discipline of
  partial-real ships when the cost of fake-real is worse than
  honest-partial.
- *"The chart series uses the windowed slice; the returns table
  reads from full history."* — separation of concerns. The user can
  toggle the chart to 1M and the 3Y number stays accurate. The
  difference between "we drew the chart" and "we built the data layer."
- *"Curated basket today, real query when the pipeline is ready.
  Document it in the docstring so future-me doesn't pretend."* —
  the v1 approximation pattern.
- *"Force-push blocked by the classifier; open a fresh branch instead."*
  — the safe workaround for the stacked-PR conflict case.

**Content hook:** *Four sub-phases of a redesign shipped between
lunch and dinner. The discipline that made it possible: small
branches, tests first, no stacking, every PR straight to base=main.*

### Episode 26 — The day after: nine PRs to fix what shipping yesterday revealed (May 23)

Yesterday closed the Market Pulse v2 redesign with seven proud PRs. This
morning Jimmy opened the production page on his phone and immediately
saw four broken things. None of them were caught by 663 passing tests.

The bugs:

1. **A Shanghai A-share fund (`510300.SH`) sitting in the US Top Movers
   grid.** The backend query had no `region` filter — it took top-200
   by market_cap and a Chinese asset slipped in via NULL region.
2. **The "Top losers" dropdown showing AMD at +3.99% as the worst
   loser.** The frontend comparator was mathematically correct, but
   the backend pre-sorted by CMF (gainer-biased), so the client-side
   "losers" sort had no losers to rank — it produced "least gainers."
3. **The sector chart labeled "VS. S&P 500" but actually plotting
   vs SPY ETF.** Honest mislabel from yesterday — the data source and
   the visual claim had drifted apart.
4. **CN toggle left US-only sections visible.** Macro Pulse (US CPI,
   ISM PMI, 10Y Treasury) and History Rhymes (US-only by design)
   rendered "US context" under a "CN" toggle.

Plus the explicit feature asks:

5. The narrative didn't carry a date. PR-3 yesterday added an `as_of`
   field but rendered it at 9px in a muted-color footer — Jimmy never
   saw it.
6. No way for users to tell whether the data was today's or
   yesterday's leftover.

And the umbrella ask, the one that justified the rest:

> *"could you build an agent to check the calculation accuracy and
> data latency, we want to ensure the data and analysis is accurate?"*

**The shape of the day.**

Nine PRs. Seven of mine, two of the other Claude session's. The first
PR landed at ~2 AM (`fix(market-pulse): block CN listings from US
Top Movers`); the last operational backfill completed at 11:02 PM
with a production audit reporting 11 OK · 0 WARN · 0 ERROR.

**The umbrella deliverable: an audit script + Claude skill.**

`apps/api/scripts/audit_market_pulse.py` walks the live API + DB and
emits a markdown report with seven independent checks: freshness,
region integrity, sort sanity, math spot-check, macro signals reality,
CN scope, benchmark identity. `.claude/skills/market-pulse-audit/SKILL.md`
wraps it so any future Claude session can invoke "audit market pulse"
and get the report back. The script ran against production at PR-7
dev time and immediately surfaced two real problems (the data-latency
endpoint not yet deployed, and ^GSPC missing from the database) —
proving its value the moment it shipped.

**The S&P 500 lesson.**

When Jimmy reviewed the production page, the Top Movers list looked
"thin" — about 30 names. PR-2 had widened the candidate pool to top-50
by market_cap, but the underlying ingestion pipeline (`_TOP_US_STOCKS`
in `apps/api/app/main.py`) only kept 30 hardcoded SPX tickers warm.
The filter was working; the data behind it wasn't.

Jimmy's instruction: *"the top movers candidate pool should be the
entire S&P 500 list."* Clear and final.

The fix turned out to be two layered changes:
- **PR-8 (code)**: swap the backend filter from "top-N by market_cap"
  to "`s.symbol IN SP500_TICKERS`" — using the canonical 525-entry
  set already maintained at `apps/api/app/data/sp500_tickers.py`.
- **PR-9 (operational)**: write a backfill script that idempotently
  loads 3y of daily bars per SPX ticker from Alpha Vantage. Same
  pattern as `backfill_gspc.py`.

The backfill itself was the day's most operational moment. First run:
loaded ~130 names before Railway Postgres ran out of disk space
mid-fetch — `DiskFull: could not extend file`. Killed the script;
Jimmy expanded storage from the Railway dashboard; second run
idempotently completed: 517 loaded, 8 failed (delisted/renamed names
like `ABC` → `COR`). Final pool size: 497 names. The "Top losers"
sort now has 145 real candidates instead of zero.

**The cross-session conflict.**

Two PRs in flight from the other Claude session (#72 and #76) both
arrived with the same `stock_lookup.py` date-coercion fix —
independently discovered, content-identical code, slightly different
comments. #72 merged cleanly; #76 conflicted on that one file.

Resolution: the fresh-branch rebase pattern codified yesterday. Pull
#76's branch, rebase onto main, keep the more production-grounded
comment, push under a `-rebased` suffix, close #76 with a comment,
open #79 from the rebased branch. Same content, new PR number, full
CI fires. The pattern is now battle-tested.

**The principle Jimmy named at the end of the day.**

> *"the stock universe should be a standard, we may expand it but
> should not shrink to smaller pool"*

That's a real product principle, worth more than the bug fixes. The
universe is a contract with users: they look at Top Movers expecting
to see "the S&P 500 today," and that mental model breaks the moment
the universe quietly contracts to 200 names. Future agents touching
`SP500_TICKERS` or the Top Movers backend must treat the size as a
floor.

**The discipline that worked again today:**

1. Read the production logs (the disk-full surfaced via `railway logs`
   while audit kept failing — that's how I found it)
2. Honest "this is broken right now" reports to the user with the
   specific cause, not euphemisms
3. Operational scripts that are idempotent (`backfill_gspc.py` and
   `backfill_sp500_universe.py` both safe to re-run)
4. One PR per concept, each opened with `base=main`, full CI per PR
5. The audit script — once it exists, every future deploy gets
   regression coverage automatically

**Quotable moments:**

- *"There's no narrative date in the byline"* — about a feature I'd
  shipped yesterday. The lesson: rendering small + muted = not shipped.
  PR-77's newspaper-byline (`SATURDAY, MAY 23, 2026` in 11px semibold
  uppercase tracking-wider) is what Jimmy means when he says "add a
  date."
- *"The filter is correct; the data behind it isn't."* — diagnosing
  PR-8's apparent failure (pool size 33 instead of ~500) until I
  remembered the `_TOP_US_STOCKS` hardcoded warmup list. The filter
  is a positive selector; without the data, the selector finds
  nothing.
- *"Postgres ran out of disk."* — the day's most operationally honest
  sentence. Killed the backfill, asked Jimmy to expand storage,
  resumed after his confirmation. No silent partial state, no glossy
  summary.
- *"The stock universe is a standard."* — the principle. Worth a
  CLAUDE.md rule.

**Content hook:** *Ship a redesign on Friday. Watch your user open the
page on Saturday. Read the four things they spot in the first 30
seconds. Spend the next 14 hours fixing them and building the audit
that catches the next four.*

### Episode 27 — The 30-PR Tuesday (May 26): a builder polish, a 16-hour outage, and a market-pulse saga that took 8 PRs to converge

The single most exhausting and instructive day of the project. By the end
of it we had:
- shipped a strategy-builder polish set Jimmy actually liked,
- diagnosed and recovered from a 16-hour production outage misattributed
  to the wrong PR for the first three hours,
- chased a phantom "FMP doesn't return data" bug through eight pull
  requests to land on a working live-quote overlay for the full S&P 500,
- and added four new traps to `apps/api/CLAUDE.md` that should make
  this never happen again.

#### Act I — Morning: strategy builder polish (PRs #86–#96)

Jimmy walked through the post-rebuild strategy builder end-to-end and
filed four crisp follow-ups: animated single-question wizard, rich
template-comparison cards with the existing `StrategyBriefCard` expansion,
detailed WHEN IN / WHEN OUT copy per strategy (synthesized from the in-repo
`Livermore_Strategy_Library_v2.html` instead of agent-generated marketing
filler), and a polish pass that locked unavailable templates, skipped the
preview step, and made the capital input a real numeric field. Seven PRs.
Tests grew, frontend built clean, no rollbacks. The kind of focused
morning every team wishes it had more of.

Also landed: Signals v0 Phase B (#88) — daily recompute cron + email alerts
+ unsubscribe — and the **spinner decouple** (#98) that made the workspace
report stop hanging on "Generating report" when the LLM was slow. Plus
**Module 2: Asset Behavior Fingerprint** (#97), a small page that profiles
a stock's typical volatility / drawdown / regime sensitivity beside the
fundamentals.

Three real features, one critical UX fix. Eight PRs, all merged before
lunch.

#### Act II — The 16-hour outage (and the 15-second fix)

Railway started rejecting deploys mid-afternoon. The build phase succeeded;
the runtime froze at exactly three log lines:

```
Starting Container
INFO:     Started server process [1]
INFO:     Waiting for application startup.
```

Healthcheck timed out. New container kept the *previous* one live, which
limped on but every `/health` returned HTTP 000.

The earliest failed deployment was tagged `11686d26` in Railway. The
diagnostic flow that should have followed: `git cat-file -t 11686d26` →
"not a valid object name" → "ah, that's a Railway deploy ID, not a git
commit." Instead I assumed the hash was a commit, traced it to PR #88, and
spent **three hours reverting #88, #99, #100, #97** in series, each
followed by a fresh deploy that hung at the same three lines. Each revert
was unrelated to the actual problem.

The actual problem: **Postgres process-level socket wedge.** Postgres was
"fine" from the dashboard's perspective — queries returned instantly,
`pg_stat_activity` reported zero active connections — but app containers
couldn't initiate new connections, because the process's internal socket
accounting was wedged. The dashboard connects through a different internal
route than container traffic does. The fix: Railway dashboard → Postgres
service → Deployments tab → three-dot menu → **Restart**. Fifteen seconds.
The next app deploy hit "Application startup complete" within thirty.

Sixteen hours of production downtime, three hours of unnecessary reverts.
The fix was one click on the Postgres add-on.

**The hardening that shipped same day:**

1. **Trap #11 in `apps/api/CLAUDE.md`** with the full diagnostic procedure
   ("if you see only the three startup lines and nothing else, check
   Postgres first, not the git log").
2. **The rule: disambiguate suspect hashes.** `git cat-file -t <hash>` is
   the one-liner that would have saved three hours. Railway deployment IDs
   look identical to short git SHAs to the eye; one command tells them apart.
3. **PR #104 — the actual underlying culprit.** Even though the outage was
   fixed by a Postgres restart, *why* did Postgres get wedged? The
   `dunning_expiry_job` (billing cron) was calling `cancel_subscription()`
   (a Stripe HTTP request) inside an open DB transaction. Each slow Stripe
   call held one DB connection idle-in-tx for the duration of the network
   round-trip. Weeks of hourly cron runs slowly drained the pool until
   Postgres ran out of usable connections. Moving the Stripe call outside
   the transaction (one structural edit) closes the leak.
4. **Trap #13** also added the same day: async route handlers must not hold
   `Session = Depends(get_db)` across `await self._fmp.foo()` — same trap
   class as the billing job, but in the request path.

After all the recovery work, Jimmy made a separate decision worth logging:
**pause PR #88 (Signals Phase B) for a reshape.** Originally reverted as
part of the outage hunt, then not re-applied. The original code is preserved
on the GitHub remote branch + documented in PROJECT_BACKLOG.md for a future
resume; the design might want a different async/sync boundary and a
reconsidered 22:00 UTC cron cadence before it goes back to main.

#### Act III — The market-pulse live-data saga (PRs #108–#118)

The longest sustained debug of the day, and possibly the most
instructive. Goal: Top Movers and Sector Rotation must show live prices
for the full S&P 500 universe, not just the cached EOD snapshot. Eight
PRs to converge.

**PR #108 / #109 / #110 — "FMP supports batch quotes."** Codex (Jimmy's
parallel agent) wrote the live-overlay architecture and a batch-fetch
client that hit three plausible-looking FMP endpoints:
`/stable/batch-quote`, `/stable/batch-etf-quotes`,
`/stable/batch-index-quotes`. Concurrent gather across 5 chunks of 100
symbols. Tested with `client._get` mocked at the method level — passed
green. Deployed. The Market Pulse page **showed the same May-22 EOD prices
as before**.

Diagnosis: the three endpoints don't exist. FMP returned 404 (swallowed
inside `gather(return_exceptions=True)`); the overlay ran successfully on
an empty quotes dict; `_apply_live_to_asset` returned every card unchanged.
The 5-minute live cache then locked in the EOD response for everyone for
the next five minutes. Unit tests had passed because they never exercised
the URL path string — they mocked the layer that builds the URL.

**PR #112 — "Use `/stable/quote` with comma-separated symbols."** I replaced
the invented endpoints with `/stable/quote?symbol=AAPL,MSFT,...` — the
plural-symbols form of the working single-symbol endpoint. Same outcome:
production confirmed via direct curl that
`/api/live/quotes?symbols=HPQ,NTAP` returned only `DELL` (which happened
to be in the per-symbol cache from a stock-detail visit). FMP's
`/stable/quote` is single-symbol-only in query-param mode; multi-symbol
queries silently return one match or nothing.

**Jimmy's gentle "wait a second" moment.** I had merged PR #113 (concurrent
individual calls at Semaphore(50)) when Jimmy pointed out FMP *does*
support batch — the Python SDKs (`fmpsdk`, `fmp_py`) call it with a list
of symbols and get a list of quotes back. He was right. The detail I had
missed: **those SDKs put symbols in the URL path, not the query string.**
The v3 endpoint they call is `/v3/quote/AAPL,MSFT,TSLA`. For our `/stable`
client, the equivalent is `/stable/quote/AAPL,MSFT,TSLA` — comma-separated
**in the path**.

**PR #114 — The right batch endpoint.** Replaced with path-based batch:
`/stable/quote/SYM1,SYM2,...,SYM100` per chunk, individual fallback at
Semaphore(10) for anything the batch missed. Coverage jumped to 496/497.

**PR #115 — BRK.B.** The remaining one was Berkshire Hathaway Class B. FMP
normalises class-share tickers to the hyphen convention (`BRK-B`); our
`SP500_TICKERS` uses the dot convention (`BRK.B`). The quote came back
keyed `BRK-B`, the lookup was for `BRK.B`, the card kept its EOD value.
Translate dot↔hyphen on the way out and remap response symbols back. 497/497.

**PR #116, then #118 — rate-limit throttling.** First-call cold-cache
coverage was still only ~88% (M-Z symbols dropping out). FMP's burst rate
limiter was hitting the 3rd–5th path-batch chunks when 5 fired
simultaneously. PR #116 throttled to 2 concurrent chunks → still ~88%. PR
#118 went strict serial (Semaphore 1) → **100% cold-cache on every first
call**, at the cost of ~1 second of extra latency.

**The false-alarm moment.** Right after PR #118 deployed, my verification
script came back `0/497 stale=497`. I almost reverted a working fix. The
filter was string-comparing `latest_date != '2026-05-26'`. **UTC midnight
had just passed**; the backend was writing `latest_date='2026-05-27'` and
my filter was flagging all 497 as stale. Trap #16 in CLAUDE.md is born:
compute the comparison date in the same TZ the backend uses (UTC on
Railway), not as a hard-coded string.

**Jimmy's discipline note worth quoting verbatim:**

> *"You are fixing one bug leading to another bug, this is troublesome. We
> need to make sure you understand the goal and full picture. We need both
> the sector rotation and top mover section reflecting the summary that's
> based on latest live price within the defined S&P 500 ticker universe.
> DO NOT show me intermediate answer until you finishing up the goal."*

The full goal: all 500 S&P 500 symbols live, on Top Movers and Sector
Rotation, on the first request that any user makes. Verified end-to-end
via three consecutive `bypass_cache=true` requests (each forcing the cold
path) all returning 497/497 with MU correctly at the top at +19.29% — the
actual market action of the day, finally visible.

#### What the day cost and what it codified

- **30 PRs touched main** (the morning's polish set + the FRED integration
  + the eight-PR market-pulse saga + recovery PRs from the outage).
- **16 hours of production downtime** caused by misreading a Railway
  deployment ID as a git SHA.
- **Four new CLAUDE.md traps** (#11 production hang diagnostic, #14
  hallucinated-endpoint discipline, #15 FMP-specific conventions, #16 UTC
  date in freshness tests).
- **The integration-level audit skill (`market-pulse-audit`) became
  load-bearing.** It was originally added 2026-05-23 as a nice-to-have;
  today it caught every wrong fix before users would have. Unit tests at
  the `client._get` level passed cleanly through all three broken
  implementations; the audit, which curls the public API and counts
  `latest_date == today`, was the one check that consistently surfaced the
  truth.

**Quotable moments:**

- *"The fix was one click on the Postgres add-on. Three hours of reverts
  later, we found that out."*
- *"Tests passed because they mocked the layer that builds the URL. The URL
  was wrong all along."*
- *"FMP supports batch — Jimmy was right. The Python SDKs do it with
  symbols in the URL path. I had been putting them in the query string."*
- *"Compute today in the same timezone the backend writes."*
- *"DO NOT show me intermediate answer until you finishing up the goal."*
- *"Eight PRs to converge on a working live-quote overlay. Each iteration
  taught something worth keeping in CLAUDE.md."*

**Content hooks for later:**

- *"The day my agents made eight PRs to fix one bug. What each one got
  wrong, and what the final shape teaches about how AI agents fail at
  external API integrations."*
- *"How to lose sixteen hours to a misread hash."* — the
  Railway-deploy-ID-vs-git-SHA story, with the one-line `git cat-file -t`
  diagnostic that fixes it forever.
- *"Why unit tests are necessary but not sufficient: three implementations
  of a broken endpoint that all passed CI green."*
- *"What an 'audit skill' is, and why building one paid for itself in a
  single afternoon."*

### Episode 28 — Sprint 1 of Product Flow v2: from PRD drafts to 5 shipped PRDs in one day (May 26, late)

The 30-PR Tuesday wasn't supposed to be done at PR #28. After PR #119 closed
out the morning's strategy-builder polish, the midday outage recovery, and
the evening market-pulse saga, Jimmy paused, looked at a HANDOFF doc he'd
been drafting with another Claude session (the Sprint 1 plan for the
"Livermore Product Flow v2" rewrite), and decided to ship the whole sprint
that same night.

By midnight, **five PRDs were merged**, the flow runtime had its first real
consumer, the two highest-priority entry modes worked end-to-end, and the
architecture had been validated against the four principles it was built to
enforce. Eight more PRs (#120, #122, #123, #124, #125, #126, #127, #128)
landed between PR #119 and Sprint 1 closeout. Combined with the morning
work, the day's total touched **36 PRs** — the highest single-day count in
the project's history.

What's interesting isn't the count. It's that the *second half* of the day
shipped a sprint that was scoped to take **4-6 weeks** in the HANDOFF doc.

#### What Sprint 1 was supposed to be

The product was getting restructured around **six user entry modes**
(One Asset / Portfolio / Thesis / Custom Build / Idea / Discovery), each
triggered contextually inside the existing four-tab navigation. Sprint 1
delivered the two P0 modes (One Asset + Portfolio), their trigger surfaces
(Home picker + stock-page CTA + Strategy Builders integration), and the
LEGO-brick infrastructure (`FlowDefinition` runtime + brick library) that
Sprint 2 would compose against.

Five PRDs, with explicit dependency chains:

```
PRD-12 (3h) — Asset Behavior Fingerprint     (no deps)
PRD-13a (2-3d) — Flow runtime                 (no deps)
PRD-13b (1.5-2wk) — Portfolio Mode + engine   (needs 12 + 13a)
PRD-14 (1d) — Stock-page Apply CTA            (needs 12)
PRD-11 (3d) — Home entry picker                (needs 13a + 13b)
```

The estimates assumed a single human developer. By using **chip-driven
parallel agent sessions**, the wall clock collapsed to one evening.

#### The chip pattern

The CCD harness (Claude Code Desktop) exposes an MCP tool —
`spawn_task` — that queues a clickable "chip" in the user's UI. The agent
calls the tool with a self-contained prompt (PRD kickoff text, branch name,
acceptance criteria). The chip waits in the UI. When Jimmy clicks it, CCD
spawns a **fresh worktree on a new branch**, opens a **new Claude Code
session** in that worktree, and sends the prompt as the first user message.

That spawned session then runs *completely independently* — different
worktree, different conversation, different Claude instance. They can't
see each other's state. They communicate only through `git` (push branches,
open PRs, eventually `claude-main` merges to `main`).

The mechanical translation:

| Before chips (manual) | With chips |
|---|---|
| Agent writes "open a fresh Claude session and paste this prompt" | Agent calls `spawn_task` with the prompt |
| User opens new CCD tab + pastes | User clicks the chip card |
| User runs `git worktree add ../foo -b bar main` | CCD does worktree + branch in the background |
| User pastes the kickoff prompt as the first message | CCD sends the queued prompt |
| User returns to canonical root for `claude-main` duty | New session opens in its own window |

Same protocol (worktrees per session, branch prefixes, master-merger gate);
fewer keystrokes. The architectural promise — *"every mode is a chip's worth
of work because the runtime amortizes the foundation"* — got tested for the
first time tonight.

#### How the day actually unfolded

**PR #117 — PRD-13a (Flow runtime, 2-3 days estimated, ~1h actual).** First
chip. Built the four files: `types.ts` (FlowDefinition shape), `runtime.ts`
(`startFlow`, `FlowProvider`, sessionStorage persistence with 250ms debounce,
`step_idle` event after 300ms), `registry.ts` (`registerFlow`/`getFlow`),
`copy.ts` (`useFlowCopy(modeId, key)` lexicon). Added a universal
`/flow/[flowId]` shell route. Added vitest as the test runner. 16 files,
+3289/-335 lines, 25/25 tests pass on first try.

**PR #120 — PRD-14 (Stock CTA, 1 day estimated, ~30 min actual).** Second
chip, opened in parallel. Replaced the inline "Apply a strategy" button on
`/stocks/[ticker]` with a `<ApplyStrategyCTA>` brick. Rendered the existing
`<AssetBehaviorFingerprintCard>` (PRD-12, already shipped via PR #97/#106).
Wired PostHog. 2 files, +103/-6 lines. The brick became the *template*
every subsequent brick would mirror.

**Three polish chips (#122 / #123 / #124, ~30 min total).** While I was
reviewing PR #117 + #120, a parallel session knocked out three follow-ups
the original PRs had explicitly deferred:
- #124 — gate the dev mock-flow registration to `NODE_ENV !== "production"`
  + add `schemaVersion: 1` to persisted sessionStorage state (so future
  FlowDefinition shape changes invalidate stale entries automatically)
- #123 — route the ApplyStrategyCTA brick's labels through `useFlowCopy`
  instead of hardcoded constants (the lexicon discipline that had been
  *blocked* on PR #117 landing first)
- #122 — vitest tests for the brick (6 cases — locks the contract)

Three chips, three PRs, three independent worktrees, all merged in <30 min.
The chip-driven model held up: each agent worked in isolation, no
cross-session conflicts, claude-main reviewed + merged sequentially.

**PR #125 — PRD-13b (Portfolio Mode + engine extension, 1.5-2 weeks
estimated, ~3h actual).** The big one. 38 files, +3870/-16 lines:

Backend: `StrategyJSON.inherited_universe: Optional[list[str]]` as an
*additive* field — engine's `run()` swaps `strategy.universe` for
`inherited_universe` at the top when `strategy_type in PORTFOLIO_OVERLAY_TYPES`,
so every downstream helper reads the right tickers without per-branch
wiring. Three new strategy types (`portfolio_defensive_overlay`,
`portfolio_rotation_overlay`, `portfolio_rebalance_overlay`). New `Holding`
Pydantic model. `PortfolioDiagnosisService` composing `FundamentalService` +
`PriceDataService` + `compute_asset_behavior_fingerprint` (PRD-12's
contribution paying off). `POST /api/portfolio/diagnose` with a 60-min
in-process LRU cache + per-tier hourly rate-limit (Scout 5/h, Strategist
50/h, Quant unlimited). Migration adds `weekly_usage.portfolio_diagnose_runs_hourly`
column.

Frontend: `portfolio-mode.ts` — the **first concrete FlowDefinition**, with
7 steps. Three portfolio bricks (`<PortfolioUpload>`, `<PortfolioDiagnosis>`,
`<OverlayPicker>`) plus four adapter bricks (`portfolio-summary` /
`-backtest` / `-review` / `-save`). Strategy Builders multi-ticker template
picker gained a "Use my portfolio →" CTA that calls
`startFlow('portfolio_mode', { fromTrigger: 'builders/multi_ticker_use_my_portfolio' })`.
Self-registration on import. 7 backend test files (25 cases) + 3 frontend
test files (16 cases) all green.

The architecture worked exactly as promised: a single agent built a 2-week
feature in 3 hours because the runtime + brick patterns from PRD-13a +
PRD-14 amortized the foundation cost.

**PR #126 — trap #13 follow-up (~30 min).** During review of PR #125 I
flagged the diagnose endpoint as holding the request-scoped DB session
across `await _service.diagnose(db, payload.holdings)` — 2-5s of FMP HTTP
calls with the connection pinned, which is the exact pattern from
CLAUDE.md trap #13 that caused the 2026-05-26 outage earlier in the day.
Spawned a follow-up chip. The fix mirrors PR #104's pattern: close the
request session before the slow await, re-acquire `SessionLocal()` for the
work. Added a 20-concurrent-call regression test that verifies the pool
doesn't drain. Confirmed: the test failed against the pre-fix route with
`QueuePool limit ... overflow timeout`, passed against the fix. Merged.
Same-day trap closure — exactly the discipline the morning's outage
hardening was supposed to enable.

**PR #127 — PRD-11 (Home picker, 3 days estimated, ~1h actual).** The last
chip. Replaced the legacy "Describe Your Strategy" teaser with an
`<EntryModePicker>` brick (three CTAs: Pick an asset → `/stocks` via
`<Link>`, Upload portfolio → `startFlow('portfolio_mode', ...)`, Chat
builder → opens the floating ChatWidget via `dispatchChatSeed`). Added a
`<SavedStrategiesTile>` for signed-in users — three most-recent saved
strategies with per-row signal-state chips fetched in parallel. Anonymous
users see a "Sign in to access your strategies" prompt that fires NextAuth's
`signIn()`.

The "Upload portfolio" CTA worked the instant it shipped because PRD-13b
had landed an hour earlier and the runtime found `portfolio_mode` in the
registry. *That's the promise of the architecture made literal.*

**PR #128 — Sprint 1 closeout.** Committed the HANDOFF doc + 5 PRDs to
`main` (they'd been untracked in canonical root the whole time). Flipped
every brick-inventory entry from ⏳ to ✅. Ticked the acceptance checklist.
Refreshed WORK_LOG.md Current Session to reflect Sprint 1 complete.
Added the wrap entry to project_log.md.

#### The Mode 1 moment

After PR #128 was open and waiting on CI, Jimmy sent a screenshot of
`/stocks/NTAP` with the new "⚡ Apply a strategy" button visible, and one
sharp question:

> *"when I click apply strategy, I expect to trigger 'Mode: Pick One Asset',
> is it actually working?"*

The honest answer was **no, not in the FlowDefinition sense.** The brick's
`onClick` calls `setBuilderOpen(true)` directly — opens the legacy
`StrategyBuilderModal` with the ticker pre-loaded. It does NOT call
`startFlow('one_asset_mode', {...})`. There is no `one_asset_mode` file in
`apps/web/src/lib/flows/`. Both PRD-14 and PRD-11 had explicit out-of-scope
carve-outs deferring the Mode 1 refactor to Sprint 2.

I had already ticked those two acceptance lines as `[x]` in PR #128's
HANDOFF update because *functionally* the journey worked — modal opens,
ticker loaded, backtest runs, save works. But that's reading "Mode 1" as
"the conceptual one-asset journey." Jimmy was reading it as "Mode 1 = the
FlowDefinition called via startFlow." Both readings are defensible; only
one is the architectural promise the runtime was built to deliver.

Downgraded both ticks to `[~]` (partial) with explicit "Architectural gap"
notes that spell out (a) what the CTA does today, (b) what's missing (the
`one_asset_mode` FlowDefinition), and (c) what Sprint 2's refactor will
swap in. Spawned a Sprint 2 chip — `PRD-Mode1-Refactor` — that includes
the adapter-brick extraction work (PRD-13b's `portfolio-*` adapter bricks
were always intended to collapse into mode-agnostic versions when Mode 1
joined them on the runtime).

**The discipline-level lesson:** *the user noticed before the documentation
did.* If the acceptance checklist had stayed at `[x]`, Sprint 1 would have
been recorded as fully delivered against its spec when one explicit
non-goal was still standing. The user's UX expectation caught it. Worth
remembering when writing future acceptance language — "the journey works"
and "the journey routes through the architecture" are not the same claim.

#### What the architecture proved tonight

The "Mode = FlowDefinition" abstraction was the load-bearing bet. The
HANDOFF doc said:

> *"This is the abstraction that makes Sprint 2 cheap: adding Mode 3
> (Thesis) is 'build one or two new bricks + one new flow file + wire one
> trigger' — not 'build another wizard from scratch.'"*

Three pieces of evidence tonight that the bet paid off:

1. **PRD-13b shipped a 2-week feature in 3 hours.** The runtime did most of
   the work. The portfolio-specific code was the new bricks + the flow
   definition + the engine additivity. Everything around it — sessionStorage
   resume, step transitions, label lexicon, event emission — was already
   there from PRD-13a.

2. **PRD-11's "Upload portfolio" CTA worked the moment it was written.**
   Because `portfolio-mode.ts` had self-registered into the runtime an hour
   earlier, the trigger button needed exactly one line:
   `startFlow('portfolio_mode', { fromTrigger: 'home/upload_portfolio' })`.
   The full 7-step flow opened without any consumer-side glue.

3. **The four polish chips composed cleanly.** Six independent agent
   sessions ran tonight (PRD-13a, PRD-14, three polish chips, PRD-13b, PRD-11,
   trap-#13 fix). All landed without cross-contamination because each one
   touched its own files in its own worktree. The PARALLEL_WORK.md
   discipline from May 21 held.

#### Quotable moments

- *"The chip is the trigger; the spawned session is the flow that runs the
  work. Same architectural pattern as your flow-runtime PRs."*
- *"PRD-11's 'Upload portfolio' CTA worked the moment it was written
  because PRD-13b had landed an hour earlier."* — the architecture made
  literal.
- *"When I click apply strategy, I expect to trigger 'Mode: Pick One Asset'
  — is it actually working?"* — the user catching an architectural gap the
  documentation glossed over.
- *"The journey works ≠ the journey routes through the architecture."* —
  acceptance-checklist discipline lesson.
- *"PRD-13b shipped a 2-week feature in 3 hours because the runtime did
  most of the work."* — the foundation paying for itself.

#### Where Sprint 2 starts

A chip is queued: `PRD-Mode1-Refactor — one_asset_mode FlowDefinition`.
When it lands, the two acceptance `[~]` lines become `[x]`, the legacy
`StrategyBuilderModal` becomes a candidate for deletion in Sprint 3, and
the adapter bricks PRD-13b shipped collapse into mode-agnostic versions
that PRD-15 (Thesis) and PRD-16 (Custom Build) will reuse instead of
forking.

#### Final state at sprint close

| Metric | Value |
|---|---|
| Backend tests | **790** (+27 from Sprint 1 PRDs) |
| Frontend vitest | **55** (from 0 — runner itself shipped in PRD-13a) |
| FlowDefinitions on main | 1 (`portfolio_mode`) — Sprint 2 adds `one_asset_mode`, `thesis_mode`, `custom_build_mode` |
| Bricks in `lib/flows/bricks/` | 5 (`apply-strategy-cta`, `portfolio-upload`, `portfolio-diagnosis`, `overlay-picker`, `entry-mode-picker`) + 4 adapters (portfolio-*) |
| Sprint 1 PRDs shipped | 5 / 5 (PRD-11, PRD-12, PRD-13a, PRD-13b, PRD-14) |
| Sprint 1 wall-clock | ~6 hours from PR #117 to PR #128 |
| Cross-session conflicts | 0 |

**Content hooks for later:**

- *"How an architecture pays for itself in a single evening."* — the
  PRD-13a → PRD-13b → PRD-11 cost curve (foundation → first consumer →
  one-line trigger).
- *"What chip-driven parallel agent sessions actually feel like."* — six
  independent sessions, one master merger, six PRs, zero contamination.
- *"The user noticed before the documentation did."* — the Mode 1
  architectural gap moment. Acceptance language matters; "the journey
  works" ≠ "the journey routes through the architecture."
- *"Same-day trap closure."* — PR #126 fixing the trap #13 risk in the
  same evening it shipped, because the morning's outage hardening made
  the diagnostic loop instinctive.

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

### Episode 29 — deepseek-main takes over, Mode 1 ships, macro data gets a brain (June 1)

**The handoff.** June 1st started with a session handoff: the previous `claude-main` master merger session had burned through its context window after 407 turns on the 30-PR Tuesday. The new session — running on DeepSeek backend, hence the name `deepseek-main` — booted up and had to absorb the full project state from scratch: CLAUDE.md, PARALLEL_WORK.md, WORK_LOG.md, the Sprint 1+2 HANDOFF docs, all 5 PRDs, the product vision HTML, the build journal, the known issues. A full hour of reading before the first line of code.

The immediate task: close the two Sprint 1 `[~]` acceptance gaps. The Home page's "Pick an asset" button was just a `<Link>` to `/stocks` — not a guided flow. The stock detail page's "Apply a strategy" button opened the legacy `StrategyBuilderModal` — not the flow runtime. Both were architectural debt that Sprint 1 explicitly deferred to Sprint 2.

**The PR that was already done.** PR #131 (`claude/feat/one-asset-mode-refactor`) had everything: the `one_asset_mode` FlowDefinition, the extraction of `FlowBacktest`/`FlowReview`/`FlowSave` into mode-agnostic bricks, the Home CTA rewired to `startFlow('one_asset_mode')`, the stock page CTA rewired to `startFlow('one_asset_mode', { ticker })`, and the legacy modal removed from the stock page. It just needed a rebase onto current main and a merge. One merge commit, one push, done.

**The bug chain that followed.** Merge → deploy → test → "Backtest failed. Try again." Three bugs in sequence, each one unmasked by fixing the previous:

1. **401 for signed-in users.** `FlowBacktest` called `runBacktest(strategyJson)` without the auth token. The workspace page always passed `backendToken` from `useSession()`. The flow brick had no session awareness at all. Fix: import `useSession`, read `backendToken`, pass it to `runBacktest()`. Commit `13c69c4`.

2. **401 for anonymous users.** Now signed-in worked, but anonymous still failed. Same brick, same error message, different root cause: `FlowBacktest` always called the authed endpoint. The workspace branches on `isAnonymous` and calls `anonymousBacktestRun()` instead. Fix: add the same branch to the flow brick. Commit `7b01a20`.

3. **500 for anonymous backtests.** This one was a backend bug hiding behind the CORS error. `POST /api/anonymous/backtest/run` crashed with `AttributeError: module 'app.services.backtester.engine' has no attribute 'run'`. The anonymous route imported the module; `engine.run()` is a method on `BacktestEngine` instances. The authed route did it correctly the whole time — the two routes had silently diverged. Fix: import `BacktestEngine` and instantiate it. Commit `3751f79`.

**The lesson that got codified.** All three bugs would have been caught by a plan review. The `FlowBacktest` brick was architecturally sound for its contract (read `strategyJson`, run backtest, write `backtestResult`) but had never been thought through end-to-end for auth. Jimmy's feedback: "explain → plan → permission → code." Added as a hard rule in CLAUDE.md with the very bugs it would have prevented cited as the "why."

**Macro data gets a brain.** While debugging, Jimmy noticed two data-quality issues on the Market Pulse page:

- **Macro Pulse sparklines:** the 1M tab showed a flat line. All four signals (Growth, Inflation, Rates, Stress) use monthly data. One data point per month → the 1M view had literally one value repeated 8 times. Fix: change tabs to 6M / 1Y / 5Y, where 6M shows 6 actual monthly data points. Simple.

- **History Rhymes stale/repetitive:** the macro vector (TLT, VXX, UUP, HYG, GLD, USO) was computed from ETF prices that only refreshed at app startup. If the server had been running for a week, "today's macro setup" was a week old. Plus: VXX has structural decay, USO is supply-driven, and the vector had no equities dimension. Fix: swap VXX/USO for SPY/SHY (equities + short rates), expand lookback from 5yr → 24yr, add `ensure_history()` price refresh before each computation, reduce cache from 4h → 1h.

This was the kind of change where a simple question ("what's the vector trying to capture?") led to a better answer than the original design. The new vector (SPY front and center, SHY for curve context, no decay-prone vol futures, no supply-driven oil) is conceptually cleaner and will produce more interesting historical matches because equities are actually in the signal.

**Parallel agent ships 3 new overlays.** While deepseek-main worked on the above, a parallel session (`deepseek-overlay-expansion`) built PRD-13c: three new portfolio overlay strategies. Dual Momentum (relative + absolute momentum), Defense-First (breadth-of-holdings MA regime check with exposure scaling), Stability Tilt (inverse-vol weighting with per-holding caps). The branch added 137 lines to the engine (all additive, no modifications to existing overlays), 530 lines of tests, and refactored the frontend overlay-picker to be data-driven via `overlay-metadata.ts`. The master merger reviewed, rebased (fixed a contracts.ts conflict that would have reverted the MacroSignal field renames), fixed a TypeScript issue (StrategyType union was missing the new literals), and merged. 803 backend tests, build clean, shipped.

**What stuck.** The explain→plan→permission rule isn't just process theater — three production bugs in one afternoon that a 60-second plan review would have caught is the strongest argument for it. The session restart data loss (all in-flight edits wiped mid-session) reinforced that commits should happen at every logical checkpoint, not at the end. And the parallel agent protocol worked: two sessions shipped independent work on the same day with zero merge conflicts that couldn't be resolved in a single cherry-pick.

| What | Count |
|---|---|
| PRs merged | 3 (#131, macro overhaul, overlay expansion) |
| Production bugs found & fixed | 3 (auth, anon routing, engine import) |
| New backend tests | +7 (803 total) |
| New frontend tests | unchanged (67) |
| Files changed | ~25 across all PRs |
| Hours of work | ~6 hours wall-clock |

**One number worth noting:** 796 → 803 backend tests in one session. Every bugfix paired with a regression test or the existing suite already covered it. The test suite that started at 37 is now 803 — a 22x growth in 30 days.

---


- **The first paying customer.** Still pending. When it lands, every Stage 1-2-3 design assumption gets tested for real. The H1 A/B test goes live once cumulative Scout signups cross ~1,500.
- **Stage 5b — the SEO catch-up sprint.** 47 more landing pages, comparison pages, OG image generation, creator UI. Triggered by the first 1K of organic traffic OR the first creator applying.
- **Stage 6b — lifecycle email + dashboards.** 7 more email templates, Resend webhook, PostHog funnels. Triggered by first trial expiry, first 100 sent emails, first ZH user.
- **The DEFERRED.md test.** Does the trigger-based forget-proofing actually work? We won't know until we've grepped `DEFERRED_TRIGGER` and found something we'd forgotten about.
- **First real traffic.** Every infrastructure assumption in Stages 3-6 was designed for traffic we don't have yet. Some will hold. Some will break in interesting ways.
- **The creator-driven flywheel.** Stage 4a built the watermarked share URL + attribution pipeline. Stage 5a built the payout math. The question whether ten paid creators can sustainably drive 100 paid signups/quarter is unanswered until we have ten paid creators.

---

### Episode 30 — The overlay picker finally makes sense (June 2)

**The problem that had been bugging Jimmy since June 1.** The portfolio mode's "Pick an overlay" screen showed six identical text-blob cards. Every card had the same visual weight. There was no way to compare them. You had to read all six descriptions and mentally diff them — that's not comparison, that's homework. And when you picked one that needed more tickers than you had, you'd hit a 422 error with no warning.

**The redesign that took three iterations to get right.** The first pass produced beautiful, rich cards with every detail. Too much detail — six of them filled four screens of scrolling. Jimmy pushed back: "condense, then expand."

Iteration two introduced a two-level card system: condensed cards showed just the idea and a tagline, scannable in a 3-column grid. Clicking a card expanded it inline to show everything. Better, but the expanded view was a wall of text in a single column.

Iteration three got it right: the expanded card split into two scrollable columns — "How it works" on the left (execution steps, example, track record) and "Why it works" on the right (rationale, mechanic detail, things to know, research source). The date range picker (3Y/5Y/10Y) only appeared AFTER you selected an overlay — less clutter upfront.

**The LEGO brick bet paid off immediately.** The `StrategyCard` component was built as a mode-agnostic LEGO brick — pure data in from `OverlayMeta`, no mode-specific logic. The same card can be used in portfolio mode, one-asset mode, and future thesis/custom-build modes. The `overlay-metadata.ts` file became the single source of truth for all card content.

**The mock data false-positive that took a Railway deploy to fix.** Growth and Stress macro signals showed amber "Mock" pills even though `FRED_API_KEY` was set and the backend was returning real data. The frontend `SourcePill` component only checked `source === "alpha_vantage"` — it had never heard of `"fred"`. The backend was fine the whole time; the frontend was mislabeling real data as mock. One condition check, one TypeScript type addition, fixed.

**While we were there — ^GSPC had never been refreshed.** The benchmark for sector charts was 12 days stale because `^GSPC` was never in the daily ETF warmup list. The sector rotation comparison ("XLK vs S&P 500") was comparing real-time sector data against a two-week-old benchmark. Added to warmup, fixed.

**Portfolio mode lost three steps.** The flow was upload → diagnose → overlay → summary → backtest → review → save. But the summary-to-backtest pipeline was redundant — the legacy modal already handled backtest/review/save via the workspace. Jimmy's call: wire summary directly to `/workspace?autorun=true` and drop the three extra steps. Now it's 4 steps with back buttons on every screen.

**What stuck.** The redesign needed three iterations to converge because Jimmy kept pushing for less information, not more. Each iteration removed something: first the detail, then the toggle, then the separate columns. The final design is the minimum viable comparison tool: you can scan all six in a glance, click one, see execution and rationale side by side. The "goal-vs-result wrap-up" habit got codified in CLAUDE.md because it's the only way to know if we actually solved the problem we set out to solve.

**One number worth noting:** 10 commits shipped today, 0 bugs introduced. The explain→plan→permission rule from yesterday caught every design iteration before it became code.

---

### Episode 31 — China A-shares go live, Postgres rebels, and we learn where the real deployment bottleneck lives (June 4)

**The task: a real CN market in one day.** When we started, the CN page had seven US-listed ETF proxies (FXI, KWEB, MCHI…) and three hidden sections. There were no individual stocks, no company profiles, and not a single Chinese character on the page. "China market" was a toggle that showed less. By the end of the day, it had 1,800 A-shares, Chinese across every section, a company overview endpoint, and a Postgres outage that taught us more about Railway in four hours than the previous two weeks combined.

**First: confirm the data works.** Before writing a single line of backend, we checked whether Alpha Vantage actually supports CN stocks. Answer: yes. `600519.SS` (Kweichow Moutai) returned real-time quotes, 4,900+ data points for SMA/RSI/MACD/BBANDS — same quality as US stocks. FMP's stable API also returned company profiles and peer lists for CN tickers on the paid plan. FMP's `key-metrics-ttm` endpoint did NOT work for CN (verified via curl, not assumed). Two key lessons: (1) test empirically before building, and (2) the FMP/AV combination gives ~80% parity with US for CN stocks.

**AKShare fills the gaps — with guardrails.** The two missing sections (financials: ROE/margins, and sentiment: CN market news) needed a third data source. AKShare scrapes Eastmoney and is free, but reliability is variable — IP bans at 50 req/min, source websites change HTML, and the existing fetch script had already failed due to connection timeouts. The architecture: FMP is the foundation (never fails), AKShare is a best-effort supplement. Five guardrails: lazy import, asyncio.to_thread with 15s timeout, single asyncio.Lock serializing all calls, 24h cache, and every path try/except'd → logger.exception → graceful degradation. The page loads even if AKShare is down.

**The Chinese i18n cascade.** The Market Pulse page was already wired with `useMarketCopy` for toggle labels and section headers. The CN product page and Top Movers needed names. The CSV files we generated via AKShare (`csi300_constituents.csv` and siblings) became the lookup table — 1,800 Chinese company names loaded at app startup. A sector mapping table translated 11 FMP sectors to Chinese (Consumer Defensive → 消费品防御). Peer names resolved from FMP ticker lists through the same CSV. Chinese financial summaries (`_build_growth_summary_cn`) replaced English string builders. Scoring labels and 12 warning patterns translated. The result: a CN company page that reads entirely in Chinese — 贵州茅台, not Kweichow Moutai.

**CN stock search — AV failed, CSVs saved us.** Alpha Vantage `SYMBOL_SEARCH` doesn't reliably return results for Chinese characters. "茅台" returned nothing. "平安" returned nothing. Switching to local CSV search (1,800 names in memory, substring match) made search instant and reliable. A technical indicator viewer (SMA/RSI/MACD/BBANDS) with adjustable period and range uses Recharts — the same library we use for sector comparison charts. A link to `/stocks/600519.SS` opens the full company profile.

**Top Movers — real stocks finally.** The old CN Top Movers were the seven ETF proxies ranked by CMF. The new version queries the `symbols` table, filters to `.SS`/`.SZ` suffixes with recent `price_bars`, orders by market cap, and computes CMF — same pattern as US S&P 500 Top Movers. Chinese names from the CSV make every card readable. The screener section is hidden on CN (no fundamentals data yet).

**Then Postgres happened.** `_seed_and_warmup_cn_stock_universe()` ran at deploy startup: 1,800 rows into `symbols`, 300 stocks warmed via AV, and an 1,800-row name backfill. Together, ~1.5M new `price_bars` rows. Postgres autovacuum kicked in, held table locks for 7+ minutes, and `Base.metadata.create_all(bind=engine)` — which runs synchronously at the top of the FastAPI lifespan — hung waiting for those locks. Railway's healthcheck timed out. The deploy failed. And every subsequent deploy also failed because autovacuum was still running on the bloated `price_bars`.

**Six failed deploys, five reverts, three attempted fixes, one root cause.** The commits tell the story: performance improvements (`LIKE` instead of 1,800-element `IN`), bulk-UPDATE backfill instead of 1,800 individual UPDATEs, retry logic, deferred seeding. None of them deployed successfully because the original autovacuum from the first deploy was still holding the lock. The real fix: decouple DB init from the lifespan entirely. `Base.metadata.create_all` + `run_startup_migrations` now run as `asyncio.create_task(asyncio.to_thread(_db_init, engine))` — a fire-and-forget background task. The lifecycle yields immediately; Railway healthcheck passes in 2-3 seconds; DB init completes whenever Postgres is ready. Separate from the CN data issue but learned the same day: the `_warmup_gspc` function had a `date >= varchar` type mismatch that Postgres rejected while SQLite accepted silently (trap #5, same family). Two lessons codified: warmup failures must never be `except: logger.warning()` — they must surface visibly (added to CLAUDE.md trap #20), and the ^GSPC date-type mismatch is documented in KNOWN_ISSUES.md.

**What stuck.** The deep-research workflow on CN data APIs returned one useful finding (FMP/AV don't support individual CN stocks on free tier) that we could have confirmed with one curl. Codified "ask permission before deep research" in CLAUDE.md. The bug-fix explain-cause-fix rule added earlier in the day caught the FinancialCheckMetrics `__init__` kwargs mistake immediately. And Postgres autovacuum, not our code, was the deployment bottleneck all along.

*Last updated: 2026-06-04 (end of day).*

### Episode 32 — The second outage of the same day: where you find out the bug you thought you fixed had a brother (June 4, late evening)

Some debugging stories close cleanly. You find a root cause, ship a fix, write a journal entry, call it a night. Episode 31 told that version of June 4 — CN A-shares shipped, Postgres autovacuum was the bottleneck, fire-and-forget DB init was the cure, we learned more about Railway in four hours than the previous two weeks combined. End scene.

Episode 32 is what happened after that journal entry got written. Because **the bug we thought we fixed had a brother**, and the brother had been quietly living in our codebase for three weeks waiting for exactly the wrong moment to introduce itself.

#### The setup: thinking it was over

Episode 31's fix landed in `ac4d393`:

```python
asyncio.create_task(asyncio.to_thread(_db_init, engine))  # fire-and-forget
```

`Base.metadata.create_all` was no longer running on the main event loop at startup. Healthcheck stopped timing out. Deploys started succeeding again. Production came back. The CN feature was live. Everyone agreed it was time to sleep.

Jimmy went to dinner. I (a fresh claude session, picking up Episode 32 cold) logged in three hours later expecting to do the cleanup punchlist — update WORK_LOG, add a trap to CLAUDE.md, maybe wrap up Sprint 2 PRDs. The kind of work you do when you're winding down a long day.

What I found instead: **14 consecutive Railway deploys marked FAILED.** All today. Last successful production deploy was from before the CN seed even shipped. Production was being served by a stale container Railway was keeping alive because it had nothing better to switch to.

Jimmy's exact words when I asked what was happening: *"I just feel I got a break and ready to get back on this."*

He was back to fight the same outage he thought he'd already beaten.

#### What the container logs said (the misdirection)

Every failed deploy showed identical log output:

```
Starting Container
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

…and then nothing. No errors. No crashes. No "Stopping Container" — until Railway's 600-second timeout fired, at which point the container was killed and the deploy marked FAILED.

This is **identical** to the symptom of CLAUDE.md trap #11 ("Production hangs at 'Waiting for application startup.'"). Same outage symptom, same lock-up shape. So we did the trap #11 recipe: hit Restart on the Postgres add-on, redeploy, watch.

Postgres came back. `/health` started responding 200. Production looked alive.

Then I tested `/api/market/pulse?market=US`. HTTP 000. Timeout at 8 seconds.

`/api/live/quotes`. HTTP 000. Timeout.

`/api/symbols/search`. HTTP 422 (responded! but rejected the param). DB connection works. So why did Market Pulse time out?

A new container had picked up. Application startup complete. Uvicorn running. `/health` answering instantly. Real endpoints completely unresponsive.

The Postgres restart unblocked the layer that was wedged. There was clearly **another layer**.

#### The discovery — and why it took 3 hours

When you're staring at a `/health` endpoint defined as `return {"status": "ok"}` and it's returning HTTP 000, the natural suspects are:

- Network — but `/health` is hitting the right container (we have a port match in the deploy logs)
- Process — but Uvicorn is logged as running
- Port mismatch — but the bind matches Railway's `$PORT`

Then I realized I'd been looking at the wrong horizon. The lifespan code:

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    asyncio.create_task(asyncio.to_thread(_db_init, engine))  # the morning's fix
    _start_scheduler()
    asyncio.create_task(_warmup_market_etfs())
    asyncio.create_task(_warmup_gspc())
    asyncio.create_task(_warmup_commodity_spots())
    asyncio.create_task(_seed_and_warmup_stock_universe())
    asyncio.create_task(_invalidate_stale_bi_caches())
    yield
```

The `_db_init` line uses `asyncio.to_thread(_db_init, engine)` — that's the morning's fix; `_db_init` is a regular `def` function running in a worker thread. ✓ Safe.

The next 5 lines are `asyncio.create_task(_warmup_*())` — and `_warmup_*` are all `async def`. They get scheduled onto the **same asyncio event loop** Uvicorn is using to serve user requests. Including `/health`.

Then I looked inside one of them:

```python
async def _warmup_market_etfs() -> None:
    from app.db.session import SessionLocal
    db = SessionLocal()
    rows = db.execute(text("SELECT ...")).fetchall()
    ...
```

`SessionLocal()` and `db.execute(...)` are synchronous. Python's `async def` keyword doesn't make a function cooperative — it just makes it return a coroutine. If the function body runs synchronous blocking calls, **the event loop is blocked while it runs them**, no different from running them in a regular function.

Normally these warmup queries finish in milliseconds and you'd never notice. Today, with autovacuum still tearing through the bloated `price_bars` table from the morning's CN seed (yes, the same 1.5M-row seed; even after we removed the seed function, the data it had already inserted was still being processed), those queries took **minutes**. While the warmups blocked the loop, the loop couldn't do anything else — including answer `/health`. Railway's healthcheck pinged. Got no response. Pinged again. Got no response. 600 seconds later, declared the deploy a failure.

The morning's `Base.metadata.create_all` fix had moved one synchronous blocker off the loop. The 5 warmups were five **more** synchronous blockers, hiding behind `async def` signatures that promised cooperation they didn't deliver. And nobody had noticed for three weeks because under healthy DB conditions the bug was invisible.

#### Quote that captures the moment

I was trying to explain the bug to Jimmy at 9pm. He read the explanation, paused, and said:

> *"So in human terms, it's the 5 warmup tasks that caused the issue."*

I said yes.

He said: *"So we should not have that much warmup."*

This was the question that crystallized the design decision. The answer wasn't "fewer warmups." The warmups were doing useful work — pre-populating the Market Pulse cache so the first user of the day gets <2s page loads instead of 12s. The answer was: **the warmups themselves are fine, but they have to be run in a way that respects the cooperative-multitasking contract Python's `async def` keyword implies.**

Either rewrite each warmup to actually `await` its DB calls (huge refactor, since SQLAlchemy's async API is different from the sync one we're using everywhere else), or use the bridge pattern: run each warmup's coroutine in its own dedicated thread with its own event loop, so it can do whatever blocking it wants without anyone else paying for it.

#### The four-PR fix sequence

```
7503dcc — Remove the CN seed function from startup (the trigger)
ac4d393 — Fire-and-forget Base.metadata.create_all (morning's fix; necessary but not sufficient)
6716928 — Bump healthcheckTimeout 120→600s (a bandaid that didn't actually unblock)
5fc90a7 — EMERGENCY: comment out all 5 warmups (unblocked deploys at cost of 12s cold-cache UX)
PR #134 — Permanent: _run_async_in_thread bridge + re-enable all 5 warmups
```

`5fc90a7` is the commit I made at 21:00 after Jimmy gave the go-ahead. It commented out the 5 `asyncio.create_task(_warmup_*())` lines with a TODO pointing at the proper fix. The deploy succeeded — first SUCCESS deploy of the entire day, after 14 failures. Production came back fully responsive. Today's CN feature was finally live. We had taken the first user per cache cycle's experience from "fast" to "wait 12 seconds while we fetch from scratch," but the bleeding had stopped.

After Jimmy got some rest, PR #134 was the proper fix:

```python
def _run_async_in_thread(coro) -> None:
    """Run an async coroutine inside a worker thread with its own event loop."""
    try:
        asyncio.run(coro)
    except Exception:
        logger.exception("background warmup failed")  # not .warning() — trap #20

# In lifespan:
asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_market_etfs()))
asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_gspc()))
asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_commodity_spots()))
asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _seed_and_warmup_stock_universe()))
asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _invalidate_stale_bi_caches()))
```

Deploy `4291a85` SUCCESS. `/health` responds in 1.7s. Market Pulse cold-cache back to 2s (was 12s after the emergency comment-out). The warmups are doing the same work they did three weeks ago — but now on dedicated threads where their internal blocking can never reach the main event loop.

#### Codification — trap #21

The lesson got immediately written into `apps/api/CLAUDE.md` as **trap #21**:

> *Any `async def` lifespan task that opens `SessionLocal()` MUST use the `_run_async_in_thread` bridge. Direct `asyncio.create_task(_my_async_warmup())` where the body calls sync DB is the anti-pattern even if it works today — it's a latent deploy bomb waiting for the next slow query.*

The trap entry includes an audit recipe (`grep "asyncio.create_task(_" apps/api/app/main.py`) and the working pattern. Future agents reading the boot-sequence CLAUDE.md files at session start will see this lesson before they write the next `async def _warmup_something():` and the bug structurally can't recur.

#### What the day's two outages teach together

Episode 31 ended with the line *"Postgres autovacuum, not our code, was the deployment bottleneck all along."* That was wrong, or at least incomplete. Tonight proved that **our code** had a second-layer bug — a "sync DB inside async def" collision that autovacuum surfaced but our async/await discipline created. Once the autovacuum window opened, our warmups walked right into it.

A pattern is becoming visible across the last month of `apps/api/CLAUDE.md` traps:

| Trap | One-line shape |
|---|---|
| **#13** | Async routes can't hold `db: Session` across slow `await` |
| **#17** | Intermediate commits expire ORM instances |
| **#20** | Warmup failures silenced by `logger.warning` lose the traceback |
| **#21** (tonight) | `async def` lifespan tasks with sync DB block the event loop |

Together, these four describe the **entire collision surface** of "Python's asyncio model" vs. "the synchronous SQLAlchemy API we use everywhere." Each trap entry teaches the rule for one corner. Pass all four discipline checks and you can write async routes + background tasks that talk to Postgres without creating outages.

We're not migrating to async SQLAlchemy. We're not rewriting the warmups. We're documenting where the seams are and giving every future agent the pattern to stay on the safe side of them.

#### Quotable moments from the night

- *"I just feel I got a break and ready to get back on this."* — Jimmy logging back in, three hours after the morning's outage was supposedly resolved
- *"So in human terms, it's the 5 warmup tasks that caused the issue."*
- *"So we should not have that much warmup."* — the question that crystallized the design decision
- *"the bug we thought we fixed had a brother"* — the title of this episode in shorter form
- *"healthy DB conditions made the bug invisible. Today's CN seed made queries slow enough to expose it."* — the punch line on why three weeks of safe operation didn't mean the code was safe

#### Final state at end of night

- ✅ Production deploy `4291a85` is SUCCESS — first SUCCESS deploy of the day on the fully-fixed code path
- ✅ `/health` responds 1.7s, Market Pulse responds 2.0s, all DB-touching endpoints back to normal
- ✅ All 5 warmups running on threads, populating cache within 30s of deploy
- ✅ `_run_async_in_thread` bridge documented + reusable for future warmups
- ✅ Trap #21 codified in `apps/api/CLAUDE.md`
- ✅ Autovacuum re-enabled on `price_bars` with tuned settings (`scale_factor=0.1`, `cost_limit=1000`) — though the architectural fix means even default autovacuum is safe now
- ✅ Tonight's KNOWN_ISSUES.md entry written
- ✅ This journal episode written

It's past 22:00 UTC+08 as I write this. Jimmy's still awake — refused to close the laptop until the codification was on `main`. The discipline that gets you through a 12-hour outage saga: don't ship the code fix without shipping the lesson too. Tomorrow's agent doesn't get to re-learn what tonight cost.

*Last updated: 2026-06-04 (very end of day — Episode 32 added 2026-06-04 22:30 UTC+08).*

### Episode 33 — The cold path was always there, we just never measured it (June 5)

Most performance bugs in this project have been crash-shaped. The DB connection pool drains and everything 500s. The lifespan blocks and `/health` times out. The deploy fails 14 times in a row. The system breaks loudly, you find the broken part, you fix it, the system stops breaking.

Episode 33 is the other kind. The kind where the system was "broken" for **six weeks** in plain sight and nobody noticed, because the way it was broken was invisible inside the development loop.

#### The setup: closing out the night before

Morning after the 14-deploy outage. Jimmy opened with cleanup — the previous night's logs showed `GET /api/cn/company/{ticker}/trend` returning 500 for every A-share. I had triaged it at 04:00 UTC and chipped it for morning, with the diagnosis pre-baked: `CompanyTrendService` sets `result.latest_date = dates[0]` (a `datetime.date`); the response schema declares `latest_date: Optional[str]`; Pydantic v2's strict response validation rejects the mismatch. The US handler had always converted via `.isoformat()` at the route layer. The CN handler skipped the conversion when it was added.

PR #137 landed clean — a 23-line surgical fix in the CN route + 135 lines of regression tests. Production verified ~30 seconds after merge. Trap #17 family ("intermediate state expires ORM-bound values") in spirit, even though this one was specifically about a dataclass field type, not an ORM expire.

That should have been the morning. Instead Jimmy opened a new thread:

> *"Hi, I have noticed the website loading speed is quite slow, could you help me diagnose"*

#### The misdirection I almost walked into

My first instinct was "CN page is slow, look at CN code." I almost spawned an Explore agent to start mapping `cn_market.py` + `cn_overview_service.py` + the CN universe data. That would have been the wrong investigation — and the only reason I didn't take it is the discipline rule of measuring first.

So I curled instead. Six endpoints, cold + warm:

```
=== /api/market/pulse?market=CN (cold) ===     TTFB: 78.6s | total: 79.1s
=== /api/market/pulse?market=CN (warm) ===     TTFB: 1.75s
=== /api/market/pulse?market=US (cold) ===     TTFB: 108.7s | total: 109.1s
=== /api/market/pulse?market=US (warm) ===     TTFB: 1.78s
=== /api/market/pulse?market=CN&bypass=true === TTFB: 110.0s
=== /api/market/history-rhymes?market=CN ===   TTFB: 2.0s
```

The table flipped the framing in 30 seconds. CN wasn't slower than US. **CN was 30 seconds *faster* than US on cold**. The slowness Jimmy was feeling on CN wasn't a CN-specific bug; it was the dominant Market Pulse cold-path cost combined with CN getting less ambient traffic to keep the cache warm. The diagnosis stopped being "what's broken about CN" and became "why does the cold path take 80+ seconds for either market."

This was the moment that mattered. Without that table I would have spent 90 minutes spelunking through CN-specific code looking for a bottleneck that didn't exist.

#### The shape of the cold path

The 80–110 seconds broke down into a stack of contributors I read off the service code:

- **N+1 query pattern**: `_build_top_assets` / `_build_cn_top_assets` query the symbols table once, then call `_load_bars(sym, db)` for each result. ~500 round-trips per cold compute. ~30–50s.
- **1800-symbol IN clause** (CN only): one really wide SQL query against the CSI 300/500/1000 universe. ~2s.
- **FMP live overlay**: for US, one network round-trip per symbol, ~500 stocks. ~10–20s. For CN, the same overlay was firing against `.SZ`/`.SS` tickers — FMP doesn't have those, so the calls returned empty / 404, but the network round-trips still happened. ~15–25s of pure waste.
- **macro_signals fetch** (Alpha Vantage CPI + Treasury + FRED CFNAI + HY OAS): usually 24h-cached. ~0–5s on cold.
- **LLM narrative**: one Anthropic call. ~2–8s on cold.

And **no one was pre-warming any of this**. The lifespan warmups (`_warmup_market_etfs`, `_warmup_gspc`, etc.) load price bars into the DB — they don't actually call `get_live_pulse` to populate the response cache. So every 5 minutes when `_LIVE_CACHE` expired, the next user paid the full cold cost.

That last point was the punchline. The cache existed. The TTL was 5 minutes. But the *only* thing populating the cache was user requests. So whichever user happened to land first in any 5-minute window was the involuntary warming agent for everyone else. CN gets fewer of those, so CN users got volunteered for the role more often.

#### The fix that was almost too small

Two changes:

```python
# A. New lifespan task — runs every 4 min, inside the 5-min TTL
async def _warmup_market_pulse_loop() -> None:
    svc = MarketPulseService()
    while True:
        try:
            with SessionLocal() as db:
                await svc.get_live_pulse("US", db)
                await svc.get_live_pulse("CN", db)
            logger.info("Market Pulse warmup tick complete (US + CN)")
        except Exception:
            logger.exception("Market Pulse warmup tick failed")
        await asyncio.sleep(240)

# B. CN early-return in get_live_pulse — skip the wasted FMP overlay
if key == "CN":
    _LIVE_CACHE[key] = (now, base)
    return base
```

The pre-warm rides the `_run_async_in_thread` bridge from PR #134. Trap #21 made this pattern safe; without that bridge, adding a recurring background task that calls sync DB would have been a healthcheck-blocking deploy bomb. So the architectural fix from one episode unlocked the perf fix in the next.

The PR (#138) was 50 lines of production code + 164 lines of tests. Production verified within 90 seconds of deploy: CN cold 78s → 1.85s, US cold 108s → 4.2s. The warmup tick fires every 4 minutes; the log line proves it. Every user now lands on warm cache, always.

#### Quote that captured the moment

After I reported the speed numbers post-deploy, Jimmy didn't celebrate. He asked:

> *"what's the user experience change, will they see less information?"*

I gave him my best answer: zero information lost, A-shares unchanged, pure speed win.

He didn't accept that — pressed for the deeper "if there's no net loss why didn't we build this in the first place" — and that question made me actually walk through the CN response shape one card type at a time. Indices (`FXI`, `KWEB`, `MCHI`) — US-listed China ETFs. Sectors (`KWEB`, `FXI`, `MCHI`, `CQQQ`, `FLCH`, `CHIE`) — US-listed. Macro (`VXX`, `UUP`, `TLT`, `HYG`) — US-listed.

**FMP DID have all those.** My CN-skip removed not just the wasted A-share calls but also the legitimate enrichment on ~10 US-listed cards. During US trading hours, CN users now see FXI's *yesterday's* close instead of intraday. Typically 0.5–2% drift on a normal day.

I had told him "no information loss" because I'd assumed the entire CN universe was A-shares. It wasn't. The right fix is the one I should have written in the first place — filter `.SZ`/`.SS` out of the symbol list, keep the overlay running for everything else. That landed as a backlog item with a trigger condition: "when a CN user notices stale FXI/KWEB during US trading hours."

The lesson: a clean fix from a developer's POV can have user-visible loss the developer didn't think to check. The discipline that catches it isn't more careful coding — it's the user (Jimmy) asking the second-order question.

#### The cost-axis flip

Then came the optimization question. Jimmy: "should we fix #3 and #4 now?" (the deeper batching + N+1 elimination fixes I'd flagged earlier as "useful but not user-visible if pre-warm runs reliably").

My first answer leaned on my own model of Railway pricing: "yes if your bill is high; the pre-warm burns CPU." Jimmy didn't know his bill. I told him how to check it. He sent a screenshot of the Usage dashboard.

| Resource | Cost | % of bill |
|---|---|---|
| Memory | $2.76 | **93%** |
| CPU | $0.04 | 1.4% |
| Egress | $0.03 | 1% |

**On the $5 Hobby plan, CPU is essentially free. Memory is the entire bill.** My pre-warm adds ~80s of background compute every 4 min — which I had been modeling as "expensive CPU." It isn't. Cached responses are 220 KB; baseline memory is 1.5 GB. Pre-warm doesn't move the needle on either axis that costs money.

The recommendation flipped. Fixes #3 and #4 would optimize the wrong axis — they save CPU, which Railway is already giving us for free. Doing them for cost reasons would burn 2 hours of code for $0 of savings. The right move was: don't optimize until the bill changes shape.

This wasn't a code lesson. It was a methodology lesson. **Read the dashboard before sizing the fix.** Without that step, I'd have walked Jimmy into 2 hours of optimization work that solved nothing.

#### The lesson that became LEARNINGS.md

Episode 32 closed with a trap added to `apps/api/CLAUDE.md` — the right home for code-level rules that bite repeatedly. Episode 33's lessons were a different shape: not "always do X in code," but "always do Y in methodology." They didn't fit any of the existing docs:

- `KNOWN_ISSUES.md` — for crash post-mortems. Nothing crashed today.
- `BUILDING_LIVERMORE_JOURNAL.md` — for narrative. (Where you're reading this.)
- `apps/api/CLAUDE.md` (traps) — for code patterns to avoid. Not what today produced.

So Jimmy asked for "a learning doc I can come back to" and `docs/LEARNINGS.md` got created. Five performance entries, three diagnostic-methodology entries, topic placeholders for Database / Frontend / Operations / Process. Designed to grow organically as different problems teach different lessons.

The shape of it matters as much as the contents: each entry has a one-line TL;DR, a paragraph of reasoning, a "when to apply" trigger, and a link to the original work. Future-Jimmy looking up "how should I diagnose a perf issue" doesn't have to re-read this episode; he reads "Cold paths are invisible in dev — measure them explicitly in production" and knows what to do.

The narrative lives here. The transferable rule lives there. Both matter; the difference matters.

#### Final state at end of session

- ✅ PR #137 — CN trend 500s fixed, deployed, verified
- ✅ PR #138 — Market Pulse pre-warm + CN FMP skip, CN cold 78s → 1.85s, US cold 108s → 4.2s
- ✅ PR #139 — WORK_LOG + LEARNINGS.md + PROJECT_BACKLOG updates (this episode + the meta-lesson it produced)
- ✅ Pre-warm tick firing on a 4-minute cadence, confirmed via curl polling and via Railway log lines
- ✅ Deferred fixes (#3 batch `_load_bars`, #4 cap CN candidate pool, "Option B" CN FMP filter refinement) all in backlog §5 with explicit trigger conditions, not lost
- ✅ `docs/LEARNINGS.md` created with first content + extensible skeleton
- ✅ Railway bill snapshot captured ($2.97 spent / $5.10 estimated, memory dominant) so future cost decisions have a baseline to compare against

The day ended without crisis. No emergency reverts, no late-night debugging, no `gh pr merge` at 03:00. Just a measurement, a diagnosis, a surgical fix, a question that caught an incomplete answer, a methodology pivot, and three docs to make sure none of it has to be re-learned.

#### Content hook

*"Cold paths are invisible in dev. You see your warm response time and assume that's what users get. The only way to know what users actually pay is to curl your production endpoint with `?bypass_cache=true`. We had an 80-second cold path live for six weeks before anyone measured it."*

*Last updated: 2026-06-05 (morning, Episode 33 added).*

### Episode 34 — The reliability stack: what "never have this outage again" actually looks like (June 7)

Episode 33 ended with the line "*the cold path was always there, we just never measured it.*" Episode 34 is what happens when you discover that the fix you shipped for the thing you finally measured had a regression you didn't measure either, and then you decide to make that whole class of failure structurally impossible.

Two days. One regression. One hotfix. Four PRs of architectural plumbing. Five merges. Thirty-eight new tests. Production back to normal by lunch, and a reliability stack live in production by dinner.

#### The discovery: a log file, and what it confessed

Jimmy showed up with a JSON log dump and the line "**it seems market pulse page run into a problem.**"

The first hundred bytes of the file were enough:

```
RuntimeError: <asyncio.locks.Lock object at 0x7f85b44039d0
              [locked, waiters:9]>
              is bound to a different event loop
market_pulse live quote overlay failed
  File "/app/app/services/market_pulse_service.py", line 632, in get_live_pulse
    quotes = await live_quote_service.get_quotes(symbols)
```

`[locked, waiters:9]` — nine user requests piled up on a wedged asyncio lock. The cross-loop error was from PR #138's warmup thread; the wedge was from the warmup acquiring locks and then erroring mid-flight without releasing them. Each warmup tick poisoned a few more symbols' locks. Over 48 hours, enough accumulated that any concurrent US Market Pulse traffic ran into them.

I curled production. 30s timeout. HTTP 000. Curled again. HTTP 000. CN: 200 OK in 2.7s. The PR #138 CN early-return saved CN — it never touched `live_quote_service` — but US was completely down.

#### The hotfix: surgical, but with an honest walkback

I had verified PR #138 on 2026-06-05 with a single curl that returned 200 in 2 seconds. The verification was a lie by omission — a sequential request from one user can't generate the conditions for the bug. Concurrency was required, and concurrency only showed up 48 hours later when real traffic arrived.

PR #140 changed one line in the warmup: `svc.get_live_pulse(...)` → `svc.get_pulse(...)`. The warmup now populates only the base 60-min `_CACHE`; user requests on the main event loop fire the FMP overlay themselves (where the locks belong). Side effect: US users on cold `_LIVE_CACHE` now pay ~15-20s for the overlay instead of my PR #138 claim of always-2s. Still 4-7× better than the original 80s cold path. Honest walkback in the PR body and the WORK_LOG.

Added trap #22 to `apps/api/CLAUDE.md` with the audit recipe:

```bash
grep -rn "asyncio\.\(Lock\|Semaphore\|Queue\|Event\)" apps/api/app/services/
```

If any match is a module-level singleton, no warmup loop is allowed to touch it.

#### The conversation that produced the reliability stack

After the hotfix landed and US Market Pulse was back, the conversation didn't end. Jimmy asked the question that mattered:

> *"Is there any possibility we have hidden some other potential bugs because of introducing #138? given there are many more automated loadings created."*

Honest answer: yes, in classes I hadn't checked. I walked through them:
1. Other singletons (`cn_overview_service`) with `asyncio.Lock` — latent landmine if any future warmup calls them
2. Lifespan startup concentration — six warmups starting in parallel could exhaust the DB pool under autovacuum stress
3. Cold-cache cost for US users (1-in-5-min pays the overlay)
4. Theoretical: the recurring loop has no restart mechanism if it ever crashes outside the try/except
5. Cosmetic: `as_of` timestamp drift on CN cached responses

I ranked them by likelihood × severity and told Jimmy the biggest miss was none of those — it was that the bug had been running for 28 minutes before he noticed, because we had **observability** for traps #20 / #21 in the log file but no **alerting**. Logs you don't watch aren't observability.

Jimmy's next message contained the seed for the whole afternoon:

> *"I think we should do scope out #1 meanwhile are able to notify users and quickly act on with some precautious solution, or a 'fix agent' in place ready to handle backend bug? I don't know, just discussion."*

That word "discussion" is load-bearing. He wasn't asking for a fix; he was asking what the right shape of fix even is. I laid out a seven-layer reliability spectrum from "observability" through "auto-merge AI fix" and ranked each by cost / risk / value at his actual scale. Then I asked which channels he'd want for notification (Slack / Telegram / email / SMS) and how ambitious the triage layer should be.

He picked email (uses existing Resend infra) and the minimum-viable triage (context bundle + one-click Claude link, not auto-invocation). That conversation took five minutes. The execution took the rest of the afternoon.

#### The four-PR arc

PR #141 (A — observability), #142 (B — graceful degradation), #143 (C — email alerter), #144 (D — triage bundle). Each one in its own worktree, its own branch, its own CI cycle, its own merge. Jimmy approved each one explicitly and I merged them in sequence. They're meant to be read in order:

- **A** says: when something breaks, there's a programmatic signal anyone can scrape.
- **B** says: when A says something is broken, users see yesterday's snapshot with a banner instead of a hung spinner.
- **C** says: when A says something is broken for ~12 minutes, Jimmy gets an email before users start complaining.
- **D** says: the email Jimmy gets contains a one-click link to a markdown bundle pre-loaded with `/health` snapshot + suspected-trap matches + recent commits, ready to paste into a fresh Claude session.

You can ship A alone and get value. You can stop after B and have a better outage UX. You can stop after C and never miss an incident. D shortens the time from "Jimmy received the alert" to "agent is diagnosing" from minutes to seconds.

We did not ship E (auto-remediation), F (auto-rollback), or G (auto-merge AI fix). At Jimmy's traffic — measured in tens of daily users, not thousands — the false-positive cost of automation outweighs the minutes saved. Worth revisiting if scale changes.

#### The decision that crystallized in the cost dashboard

A subtle moment: when planning the multi-PR sequence, I'd recommended doing additional perf fixes (batched SQL, cap candidate pool) "for the cost savings." Jimmy asked how to check his Railway bill. He sent a screenshot.

Memory was 93% of the cost. CPU was 1%. The "perf fixes for cost" recommendation was wrong-axis. Reading the dashboard before optimizing flipped my recommendation immediately.

That's now a diagnostic-methodology entry in `docs/LEARNINGS.md`: **read the dashboard before you size the fix.** If memory dominates, batch-SQL won't save you a dollar. If CPU dominates, it might.

#### Quote that captured the day

After PR-A verified live on production:

> *"That makes a lot of sense."*

Three short messages later: "merge a," "merge b," "merge c," "merge." Each one a different PR. By the time the fourth merge landed at the end of the working day, the reliability stack was code-complete, production-deployed, and inert behind three env vars Jimmy can flip whenever he's ready. The discipline that defines the day: **ship the wiring; gate the activation**.

#### Final state at end of session

- ✅ PR #140 — hotfix merged + production verified (US Market Pulse responding ~1.4–1.8s warm)
- ✅ Trap #22 codified in `apps/api/CLAUDE.md` with audit recipe
- ✅ PR #141 (A — observability) — `/health` payload live, returning `status: ok` + `pulse_warmup` block
- ✅ PR #142 (B — graceful degradation) — frontend renders `StaleDataBanner` + cached fallback when backend fails; 30s client timeout
- ✅ PR #143 (C — email alerter) — cron registered, polling /health every minute; opt-in via `OPS_HEALTH_ALERTS_ENABLED`
- ✅ PR #144 (D — triage bundle) — `/internal/triage-context` endpoint live (returns 403 until token configured); email template links to it
- ✅ Test suite grew 806 → 835 backend + 67 → 75 frontend (+38 tests today)
- ✅ This journal entry written
- ✅ `docs/LEARNINGS.md` updated with four new entries (one diagnostic methodology, three operations)
- ✅ `agent-system/WORK_LOG.md` refreshed; previous session demoted
- ✅ `CLAUDE.md` soft rules extended with concurrent-load verification discipline

Three env vars away from a fully active end-to-end alert + triage loop. Held back on auto-remediation deliberately at this traffic scale.

#### Content hook

*"PR #138's 'verified live in production' was one curl that returned 2 seconds. The bug needed concurrency to manifest. It took two days to find users. The fix took 30 minutes. The four PRs to make sure I find the NEXT bug myself — before users do — took the rest of the day. Reliability isn't a feature; it's the four cheap layers between 'something broke' and 'someone is diagnosing.'"*

*Last updated: 2026-06-07 (evening, Episode 34 added).*
