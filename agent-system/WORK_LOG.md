# Work Log — Livermore Development

> **How to use this file:**
> At the start of every session, read this file first. It tells you exactly where work stopped
> and what to do next. Update it at every meaningful checkpoint — after each completed step,
> before stopping, and whenever a blocker is discovered.

---

## Current Session

**Status:** Market Pulse v2 preview SIGNED OFF by Jimmy (Phase 0a complete) + Chat v2 widget shipped (PR #50 — chat now in workspace + stock detail pages) + 4 prior chat-v2 tickets shipped (#3/#4/#5/#6/#7/#9)
**Active branch:** main (HEAD: `bc3f7d1` — Stage 7 ticket #7 chat widget)
**Last stable tag:** `prd-14-complete` (2026-05-12) — no `stage-*` tags exist
**Tests:** **~535+ backend** all green; frontend build clean (PR #50 added 757 LoC of widget code)
**Deployed:** Railway + Vercel both healthy
- `GATING_ENABLED=true` (enforcement)
- `POSTHOG_API_KEY` not set → analytics queue silently
- `RESEND_API_KEY` not set → emails log `email_noop`
- Live-quote cache (FMP `/stable/quote` fan-out) confirmed working in prod
- CORS regex (`https://the-counselor-web-.*\.vercel\.app`) now permits Vercel preview deploys

**Open work in flight:**
- PR [#41](https://github.com/grepJimmyGu/the_counselor/pull/41) — Market Pulse v2 preview at `/uiux/market-pulse-v2`. **Phase 0a sign-off received 2026-05-21.** Branch holds 12 commits; Phase 1 plan splits the promote-to-/stocks + backend wiring into 6 sub-phases (1a–1f).
- `codex/improve-chat-builder` — abandoned codex work, 3 commits not on main. Kept; per-branch decision.
- A new parallel session spun up its own worktree per Jimmy's note 2026-05-21 — branch + Active Sessions row not yet visible on origin.

**Next action:**
- Phase 1a — promote `/uiux/market-pulse-v2` → `/stocks` (lift-and-shift, mock data with badges stays); subsequent sub-phases (1b LLM narrative, 1c real macro data, 1d sector chart real data, 1e History Rhymes backend, 1f Screener preset filters) progressively replace mocks
- Pre-launch env vars still owed:

```bash
# Railway:
#   EMAIL_UNSUB_SIGNING_KEY ($(openssl rand -hex 32))
#   CAN_SPAM_ADDRESS
# When PostHog/Resend keys land → no code change required (safe no-op pattern)
```

**Pre-flag-flip discipline (added 2026-05-21):** Before any future `GATING_ENABLED` or similar flag flip, walk [docs/SHADOW_MODE_REVIEW.md](../docs/SHADOW_MODE_REVIEW.md). The May 21 boundary bug would have been caught by it.

**Surface the catch-up backlog:**
```bash
railway logs --service api | grep -E "DEFERRED_TRIGGER|gate_event|email_noop"
```

---

## Stage Execution Queue

| Stage | Status | What landed |
|---|---|---|
| Stage 1 | ✅ SHIPPED 2026-05-18 | Real accounts + tier entitlements + monthly meter + `Plan` |
| Stage 1a | ✅ SHIPPED 2026-05-20 | `WeeklyUsage` + `AnonymousSession` + `SavedStrategy` + anonymous flow + `QuotaBadge` |
| Stage 2 | ✅ SHIPPED 2026-05-19 | Stripe billing (4 tiers, 14-day trial, Checkout + Portal, webhook + idempotency, APScheduler) |
| Stage 3 | ✅ SHIPPED 2026-05-20 | `require_entitlement` + `GATING_ENABLED` (shadow) + runs/universe/history caps + robustness whitelist + S&P 500 scope + UpgradeModal/SoftPaywall/402 interceptor |
| Stage 4a | ✅ SHIPPED 2026-05-20 | `published_strategies` + `attribution_visits` + `/s/[slug]` + ShareButton + Scout auto-publish |
| Stage 4b | ✅ SHIPPED 2026-05-20 | `/community` feed + Clone-to-workspace |
| Stage 5a | ✅ SHIPPED 2026-05-20 | `stripe_invoices` + creators tables + `revshare_service` + sitemap/robots + StructuredData + 3 SEO sample pages |
| Stage 6a | ✅ SHIPPED 2026-05-20 | PostHog + Resend safe-no-op wrappers + 10 events + EmailPreference + welcome email + `/account/email` + H1 A/B flag stub |
| **Stage 5b** | **Deferred — traffic-gated** | 47 more SEO landing pages (editorial), comparison pages (legal), creator UI, payout/gate crons |
| **Stage 6b** | **Deferred — traffic-gated** | 7 more email templates, ZH copy, 4 cron jobs, Resend webhook, PostHog dashboards |

> **Note:** PRDs 11/12/13/14 below were exploratory drafts (May 11-12). All four got rewritten properly as Stages 1-4. Do not reopen the PRD branch model — Stage 1-6 is canonical.

## Legacy PRD Execution Queue (historical)

| Order | PRD | Status | Notes |
|---|---|---|---|
| 1 | PRD-06 | ✅ DONE | `prd-06-complete` — FMP integration |
| 2 | PRD-07 | ✅ DONE | `prd-07-complete` — stock screener |
| 3 | PRD-08a | ✅ DONE | `prd-08a-complete` — fundamental analysis |
| 4 | PRD-08b | ✅ DONE | `prd-08b-complete` — 10-K business intelligence |
| 5 | PRD-09 | ✅ DONE | `prd-09-complete` — news/sentiment backend |
| 6 | PRD-10 | ✅ DONE | `prd-10-complete` — news/sentiment frontend |
| 7 | PRD-11 | ⚠ Superseded by Stage 1 | Early-access auth — rewritten properly with billing |
| 8 | PRD-12 | ⚠ Superseded by Stage 4a | Watchlists/profiles draft — community redone via publish primitive |
| 9 | PRD-13 | ⚠ Superseded by Stage 4a | Votes/signals draft — replaced by attribution model |
| 10 | PRD-14 | ⚠ Superseded by Stage 4b | Community page draft — replaced by discovery feed |
| — | PRD-05 | In discussion | `not_supported` strategy handling — no Stage equivalent yet |

---

## Open To-Dos (non-Stage)

| # | Item | Priority | Trigger |
|---|---|---|---|
| 1 | Set `EMAIL_UNSUB_SIGNING_KEY` on Railway | High | Before first real email send (currently unsafe dev default) |
| 2 | Set `CAN_SPAM_ADDRESS` on Railway | High | Before scale-marketing (≥100 users) |
| 3 | Move uncommitted `research-workspace.tsx` to feature branch | High | Git workflow rule — never edit on `main` |
| 4 | Reddit API credentials | Medium | When approved → add `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| 5 | Frontend lint debt (26 errors across 22 files) | Low | When touching one of the affected files for a real feature |
| 6 | PRD-05: `not_supported` strategy handling | Low | Redirect UX — needs design decision |
| 7 | Market snapshot staleness bug | Low | `fix/market-snapshot-staleness` branch |
| 8 | Sentiment pre-warmer background job | Low | Top-100 S&P 500 every 3h via APScheduler |

See [docs/DEFERRED.md](../docs/DEFERRED.md) for the ~30 trigger-gated items split across Stage 5b + Stage 6b.

---

## Session History

### 2026-05-21 (later still) — Market Pulse v2 preview iterated to sign-off, chat widget shipped

**Market Pulse v2 preview — 11 iteration commits on top of the initial scaffold (PR #41 still open):**

Three batches of revisions, each driven by Jimmy reviewing the Vercel preview:

*Batch A — initial layout revisions:*
- Rename Movers → Top Movers, drop commodities, attempt 2-line rows
- IndicesHero removed; absorbed as inline 4-cell ticker inside MarketBrief
- Sector heatmap → 2-row × 6+5 tiles, 5 metrics per tile
- MacroStrip → themed panels (Rates / Vol / FX / Commodities) with interpretation chips
- HistoryRhymes section added (was Phase 3 in v1 plan); sticky-nav updated

*Batch B — feature additions Jimmy specifically asked for:*
- Top Movers correctly redone as a 2-row card grid (had misread "two rows" as "two lines")
- Sector tile click → inline ETF-vs-S&P 500 comparison chart with 1M/6M/YTD/1Y/3Y tabs
- New Stock Screener section — 6 algorithm cards with tier-gate badges (Strategist/Quant)

*Batch C — final polish round to sign-off:*
- Market Brief ticker shows real index point values (Dow 38,234 etc.) not ETF proxy prices
- Stock Screener: rename + 3 new cards (Top Rated, Top Dividend, Top Value); now 9 cards
- Macro Pulse: themed panels → 4-row table layout (Growth / Inflation / Rates / Stress) with 1M/1Y/3Y sparkline toggle, takeaway column, per-row metric explanation tooltip

Phase 0a signed off. Phase 1 starts next.

**Chat v2 — 3 more tickets landed today:**
- PR #43 — ticket #4 (4 heavier chat tools: backtest_execute, backtest_explain, stock_lookup, strategy_builder_iterate)
- PR #44 — ticket #5 (authed chat endpoint with SSE + tool dispatch loop) — opened originally as #40, recovered after stacked-PR cascade auto-closure
- PR #45 — ticket #6 (anonymous chat endpoint)
- PR #48 — ticket #9 (chat guardrails)
- PR #50 — ticket #7 (frontend chat widget; mounted on /workspace + /stocks/[ticker])

Chat v2 Phase 1 backend + frontend widget now both shipped to main. Real-world chat usage starts when env vars / cache get exercised.

**Process / infra PRs:**
- PR #46 — docs polish (3 CLAUDE.md operational rules from stacked-PR + git-cherry learnings)
- PR #47 — API_BASE_URL fallback fix (prod URL on non-localhost hosts; unblocks Vercel previews without env-var fiddling)
- PR #49 — CORS regex for Vercel preview URLs (the actual root cause of the empty-data preview)

**Phase 1 plan refined** with 6 sub-phases (1a–1f) given that Phase 0a added many new mock surfaces (real index values, real macro data, real sector chart, real history rhymes, real screener filters, plus the LLM narrative + the lift-to-/stocks). Total ~22–28h split into ship-able PRs. Sequence: 1a (promote) → 1b (LLM narrative) → 1c (macro data) → 1d/1e/1f (parallel).

### 2026-05-21 (continued) — Live quotes everywhere, Chat v2 Phase 1, agent-team protocol

**Live-quote system (10 PRs)** — backend cache with TTL + per-symbol lock prevents thundering herd, FMP fan-out via N parallel `get_quote` calls (the comma-batch syntax doesn't work on `/stable/quote`), `/api/live/quotes` endpoint, `useLiveQuotes` SWR hook, `LiveTickerBar` global component, wired into stock-detail header / workspace strategy preview / community feed cards / Market Pulse cards. Commodity spot wire-in deliberately deferred — ETF-share-price vs commodity-$/oz scale mismatch (see [docs/PROJECT_BACKLOG.md](../docs/PROJECT_BACKLOG.md) §4).

PRs: [#24](https://github.com/grepJimmyGu/the_counselor/pull/24) (cache + endpoint + hook + ticker bar), [#25](https://github.com/grepJimmyGu/the_counselor/pull/25) (`/stocks/[ticker]`), [#26](https://github.com/grepJimmyGu/the_counselor/pull/26) (workspace), [#27](https://github.com/grepJimmyGu/the_counselor/pull/27) (community — landed a muddy commit with two unrelated `build_specs/` files, documented), [#29](https://github.com/grepJimmyGu/the_counselor/pull/29) (FMP fanout fix), [#31](https://github.com/grepJimmyGu/the_counselor/pull/31) (Market Pulse cards).

**Chat v2 Phase 1 — tickets #1–#6 all on main:**
| Ticket | PR | Subject |
|---|---|---|
| #1 schema | PR #28 → content via #29 muddy chain | chat_conversations + chat_messages tables, AnonymousSession.chat_turns_used |
| #2 adapter | [#37](https://github.com/grepJimmyGu/the_counselor/pull/37) | LLMGateway streaming tool-calling + 13 tests |
| #3 light tools | [#38](https://github.com/grepJimmyGu/the_counselor/pull/38) | chat_tools executor + 3 tools (concept_explainer, onboarding_tutor, template_search) |
| #4 heavy tools | [#43](https://github.com/grepJimmyGu/the_counselor/pull/43) | 4 wrappers around backtest/stock_lookup/strategy_builder_iterate |
| #5 authed endpoint | [#44](https://github.com/grepJimmyGu/the_counselor/pull/44) | `POST /api/chat/turn` SSE + tool dispatch loop |
| #6 anon endpoint | [#45](https://github.com/grepJimmyGu/the_counselor/pull/45) | Anonymous chat variant w/ 5-turn-per-session cap |

**Agent-team coordination protocol** — multi-session collisions burned ~3 PRs (PR #27 muddy commit, PR #30 picking up wrong branch, PR #40/#42 closed-on-base-delete). Recovery and prevention:
- [`agent-system/PARALLEL_WORK.md`](PARALLEL_WORK.md) (PR #30) — branch-prefix-per-agent convention (`claude/…`, `codex/…`), one worktree per session, state-in-git
- Root-of-repo [`CLAUDE.md`](../CLAUDE.md) (PRs #34 → #35 → #36) — onboarding pointer; auto-loaded by Claude Code on session boot; migrates Livermore operational rules out of user memory so new accounts get them from `git clone` alone
- Master-merger role — `claude-main` (this session) holds the sole authority on `gh pr merge` to `main`. Other sessions push branches + open PRs. Reduced muddy-commit rate to zero for the rest of the day.
- Six shadow branches deleted from origin via `git cherry`-based shadow detection. Two real-work branches preserved (`claude/feat/market-pulse-v2-preview`, `codex/improve-chat-builder`).

**Market Pulse Phase 0 preview** — full redesign plan (LLM-narrative hero + indices hero + sector heatmap + macro strip + unified Movers list + sticky sub-nav) shipped as a hidden route preview at `/uiux/market-pulse-v2`. Awaiting visual review before promoting to `/stocks` in Phase 1.

**Lessons codified into [CLAUDE.md](../CLAUDE.md):**
- Stacked PRs lose backend CI (`pull_request: branches: [main]` filter)
- Squash-merging a parent with `--delete-branch` closes stacked children automatically; recover with rebase + new PR
- `git cherry main origin/<branch>` is the canonical shadow-branch detector

### 2026-05-21 — The Three-Bug Chain + Gate Hardening

Three bugs in series, each unmasked by the fix for the previous one. Plus
hardening that ships the lessons as durable artifacts.

**Bug 1 — Scout misrouting (PR #7, `0243e2d`).** Signed-in Scouts saw the
"Sign up to build custom strategies" anonymous modal during NextAuth's
loading window. Code already self-diagnosed at line 100 as "the May 20
evening regression". Fix: use `sessionStatus === "unauthenticated"` not
`!sessionUserId`.

**Bug 2 — sync-user 500 on orphaned User (PR #8, `0128c32`).** User row
existed without companion Plan; `sync_user` crashed on `user.plan.tier`.
Self-healing branch silently swallowed the 500. Fix: lazy-create a Scout
Plan when `user.plan is None`.

**Bug 3 — History boundary off-by-one (today's PR).** 5-year backtest
(1827 days / 365.25 = 5.0027 yr) tripped the strict `> 5` Scout cap;
modal displayed "5.0 yr exceeds 5 yr" — visually identical numbers. Fix:
`_HISTORY_TOLERANCE_YEARS = 7 / 365.25`.

**Hardening shipped same PR:**
- 5 new boundary tests (3 history, 2 runs)
- 1 Postgres invariant test (`test_orphan_user_detection_query_works`)
- `apps/api/scripts/check_orphan_users.py` — operational mirror
- `apps/api/CLAUDE.md` rule #9 — orphan-Plan trap + heal recipe
- `docs/SHADOW_MODE_REVIEW.md` — pre-enforcement checklist
- Console.log diagnostic from PR #7 removed
- Confirmed `GATING_ENABLED=true` on Railway is intentional

Full saga in [project_log.md](../project_log.md) (2026-05-21 section) and
[docs/BUILDING_LIVERMORE_JOURNAL.md](../docs/BUILDING_LIVERMORE_JOURNAL.md) Episode 24.

### 2026-05-15 — Market Pulse data quality + domain + mobile UX

**Domain migration:**
- Registered `livermorealpha.com`; configured DNS (A + CNAME at registrar), Vercel custom domain, `NEXTAUTH_URL` env var, Railway `ALLOWED_ORIGINS`, Google OAuth redirect URI
- Updated `apps/api/app/core/config.py` CORS defaults to include `livermorealpha.com` and `www.livermorealpha.com`

**Market Pulse data quality (PRD-15 follow-up):**
- Fixed WTI price showing USO ETF share price ($133) instead of actual WTI $/bbl (~$83)
- Added `AlphaVantageClient.fetch_commodity_spot()` for AV commodity endpoints (WTI, COPPER, WHEAT)
- New `CommoditySpotService`: stores monthly spot prices in `price_bars` as `WTI_SPOT`, `GOLD_SPOT`, `COPPER_SPOT`, `WHEAT_SPOT`; gold derived from GLD × 1/0.093
- Startup warmup `_warmup_commodity_spots()` fetches spot prices at boot
- Commodities route overlays real spot price onto ETF trend data
- Market Pulse macro chips now use `GOLD_SPOT`/`WTI_SPOT` (fallback to ETF label)
- Fixed ETFs (QQQ, DBC, USO) appearing in Stocks tab — added `ETF_SYMBOLS` exclusion set in `_build_top_assets()`
- Fixed wrong sector labels for featured ETFs — added `ETF_META` with proper names/categories
- Added `latest_date` + `is_stale` fields to all card types with amber stale badge in UI
- Fixed `INTERVAL '30 days'` (PostgreSQL-only) → bound date param for SQLite compat
- Fixed `ADD COLUMN IF NOT EXISTS` migration for SQLite via PRAGMA table_info check

**CN market fix:**
- `_build_top_assets()` and `_build_featured_etfs()` both ignored `market` param — always returned US data
- CN market now shows CN ETF proxies (FXI, KWEB, MCHI, CQQQ, CHIE, FLCH, CNYA) in Stocks + ETFs tabs
- Added `CN_FEATURED_ETFS`, `CN_ETF_META`, `_build_cn_top_assets()` to market pulse service
- Frontend tab descriptions update dynamically based on selected market

**Mobile UX optimization (ui-ux-pro-max):**
- Nav: hamburger drawer for mobile (<md) with all 7 links, 44px touch targets, X to close; desktop nav hidden on mobile
- Market Pulse sector table: 5-column grid → 2-line card layout on mobile (sm:hidden)
- Macro chips: `grid-cols-3` → `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6`
- Asset cards: CMF bar moved to full-width row below title row
- Evaluation detail panel: 5-column table → card-per-metric on mobile, full table at sm+
- Commodity snapshot: `grid-cols-4` → `grid-cols-2 sm:grid-cols-4` with truncate
- Metric pills: `grid-cols-3` → `grid-cols-2 sm:grid-cols-3`
- Index cards: sparkline 60→44px, price `text-base` on mobile with truncate
- Global: viewport meta locked, `overscroll-y-none`, `touch-action: manipulation` on all tappable elements
- App title updated to "Livermore Alpha"

**Commits:** `67caaca` → `2491d7d` (9 commits total this session)

### 2026-05-12 — Phase 3 start
- PRD-11 complete: Auth.js v5, Google OAuth, JWT sessions, NavHeader sign-in/avatar
- Adversarial audit run: 3 HIGH findings fixed (internal key bypass, open redirect, ownership check)
- UI/UX review: skip link, inputMode on search fields, accessibility improvements
- FMP stable API migration: /api/v3 → /stable, sec-filings via EDGAR CIK, field remapping
- 14,548 symbols seeded into production PostgreSQL

### 2026-05-12 — Phase 1+2 deploy
- All PRD-06 through PRD-10 + PRD-08b pushed and deployed to production
- FMP key issue discovered and fixed (stable API migration)
- Symbol seed run via Railway CLI

### 2026-05-11/12 — Phases 1 + 2 build
- PRD-06: FMP, FundamentalService, yfinance fallback, seed script
- PRD-07: Stock screener, sector strip, filters, URL state
- PRD-08a: Company deep-dive, Financial Check, scoring
- PRD-08b: SEC EDGAR 10-K fetch, section parser, LLM business intelligence, 90-day cache
- PRD-09: Sentiment provider system, Haiku LLM chain, 9 scores, 7 toolkits, Sonnet sandbox
- PRD-10: /sentiment hub, toolkit cards, sentiment tab on ticker page

---

## Rollback Reference

```bash
# Platform rollback (fastest):
# Railway: Deployments tab → previous deploy → Redeploy
# Vercel:  Deployments → previous deploy → Instant Rollback

# Code rollback to last stable tag:
git revert --no-commit prd-11-complete..HEAD
git commit -m "revert: roll back to prd-11-complete"
git push origin main

# Stable rollback points:
# prd-11-complete — Auth + all Phase 1+2 features
# prd-10-complete — Phase 1+2 only (no auth)
# prd-09-complete — Phase 1 only
```

---

## Resumption Checklist

```bash
cd /Users/jimmygu/the_counselor
git log --oneline -5
cat agent-system/WORK_LOG.md
cat agent-system/PRODUCT_PLAN.md
```

---

## Autonomous Development Rules

1. **One PRD at a time** — complete current PRD fully before starting the next
2. **Commit at every logical checkpoint** — after each service, each route, each component
3. **Run build + tests before every commit** — `npm run build` and `pytest` must pass
4. **Update WORK_LOG.md at session end** — keep "Next action" accurate
5. **Never push to main** — push requires user confirmation
6. **Never `git reset --hard`** — use `git revert` to undo
7. **Stop and note a blocker if:** API key missing, dependency install fails, tests fail 3+ times
8. **Tag main after every PRD merge** — `git tag prd-XX-complete`
