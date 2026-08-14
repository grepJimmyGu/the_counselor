# Work Log — current state

> **This file is STATE, not history.** It answers one question: *where did work
> stop and what happens next?* Read it at boot; **rewrite** the top section at
> every checkpoint rather than appending to it.
>
> **Do not add dated entries here.** Narrative history goes in
> [`project_log.md`](../project_log.md) — the one chronological log. Reflection
> and lessons go in [`docs/BUILDING_LIVERMORE_JOURNAL.md`](../docs/BUILDING_LIVERMORE_JOURNAL.md),
> which is a journal, not a log.
>
> *Restructured 2026-08-13: this file had grown to 1,025 lines and stopped being
> readable at boot — the one thing it was for. Its history moved to
> `project_log.md` under "Earlier sessions"; nothing was lost.*

---

## Current state — 2026-08-13 (end of day)

**Seven PRs merged today**, #313 → #319. Two open.

The daily share card went from built-but-unreachable to live. The screener's
fundamental filters went from silently empty to working. The home page became a
2×2. And the fundamentals backfill ran end to end for the first time in weeks.

### Open

| PR | State | Note |
|---|---|---|
| [#320](https://github.com/grepJimmyGu/the_counselor/pull/320) | CLEAN | backlog salvage from the closed #308 + what the backfill measured |
| [#321](https://github.com/grepJimmyGu/the_counselor/pull/321) | CI running | home 2×2: Traders ask folds into Hot Market Picks, sector board |

#308 is **closed** — superseded by the doc restructure, with its
`PROJECT_BACKLOG.md` half salvaged into #320 rather than lost.

### Data: fixed today, measured not assumed

Seeded 400-name sample of the Russell 3000, before/after Jimmy's backfill run
(2,542 updated / 728 genuinely unprofitable / 26 failed, **3h27m**):

| column | before | after |
|---|---|---|
| `sector` | 100% | 100% |
| `pe_ratio` | 70.5% | 70.8% |
| `dividend_yield` | 63.2% | 63.0% |
| **`market_cap`** | **1.8%** | **99.2%** |

`min_market_cap=2e9`: 99 names → 1,677. Four presets and both market-cap
filters were reading a column almost nothing populated.

Also fixed: dollars-per-share stored as dividend yields (#317 — write guard,
read guard, and 0 bad rows remaining) and the empty-rules scan that discarded
564 already-matched names (#318).

### Next actions, in order

1. **Merge #320 and #321** once CI settles. Both are low-risk; #320 is
   docs-only.
2. **Design the lazy-refresh mechanism.** This is the largest *engineering*
   item and now has its governing number: a full sweep is ~5,100 FMP calls at
   ~5s/symbol = **3.5 hours**, which rules out a nightly full refresh and
   argues for refresh driven by traffic, with a cron only as a floor. Blocked
   on one input: **the FMP plan's rate ceiling** — Jimmy's to supply. Brief is
   in `docs/PROJECT_BACKLOG.md` §5.
3. **Stripe.** Fully built, unconfigured — paywalls are live with no pay path.
   Turn-on is 4 price IDs + secret/webhook keys on Railway, test-mode first.
   This is the largest *product* item on the board and has been quiet for
   weeks; it surfaced only because the doc restructure nearly deleted the note.

### Known and deliberately not fixed

- **Chinese share card** refuses on Linux by design until a CJK font (~4-5 MB)
  is bundled — Jimmy's call. `can_render` hides the option, so nothing breaks.
- **26 failed calls** in the backfill, unexamined. Class-share tickers
  (BRK.B → BRK-B, trap #15) are the usual suspect; the log would say.
- **Blocks 5+6** (今天炒什麼 theme+catalyst read) still blocked on the Alpha
  Vantage tier. **Not** the same as the `Catalysts` block shipped in #319 —
  see the warning in `PROJECT_BACKLOG.md`.
- `scripts/fix_dividend_yield_units.py --apply` is available but unnecessary:
  the #317 read guard already stops bad rows being reported.

### Don't touch without coordinating

Nothing is in flight on a branch. #320 and #321 are pushed and awaiting merge;
both touch docs and `apps/web/src/components/home/` respectively.

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

---

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

---

## Resumption Checklist

For any Claude session (new or returning) picking up Livermore, follow this
exact sequence. It takes ~3 minutes and bootstraps the full project state.

```bash
# 1. From the canonical root, see what shipped recently and what's open
cd /Users/jimmygu/the_counselor
git log --oneline -15                  # last 15 PRs to land on main
gh pr list --state open                # in-flight work from sibling sessions
git worktree list                      # other sessions' active worktrees
```

```bash
# 2. Read these four files in order — they're the canonical sources
#    The root CLAUDE.md auto-loads via Claude Code; the others must be read explicitly.
cat agent-system/WORK_LOG.md           # ← THIS file: current state + next action (read first)
head -120 project_log.md               # latest day's shipped work (chronological)
cat docs/PROJECT_BACKLOG.md            # every open item with trigger conditions
cat apps/api/CLAUDE.md                 # all 16 backend traps (auto-loads when editing apps/api/)
```

```bash
# 3. (Optional) Episodic context for why decisions were made the way they were
sed -n '/^### Episode 2[5-9]/,/^### Episode/p' docs/BUILDING_LIVERMORE_JOURNAL.md
# Each episode is story-shaped — useful when you need WHY, not just WHAT.
```

```bash
# 4. Before touching code, verify production is healthy
curl -s https://thecounselor-production.up.railway.app/health
# If the task involves Market Pulse, run the audit skill before changing anything:
#   /market-pulse-audit
# It surfaces drift and confirms 11 OK · 0 WARN · 0 ERROR baseline.
```

**Pickup prompt for a fresh Claude session (copy/paste-ready):**

> *Pick up Livermore. Read `agent-system/WORK_LOG.md` first for current
> state + next action, then `docs/PROJECT_BACKLOG.md` for open items,
> then `project_log.md`'s most recent entry for what shipped today. Run
> `git log --oneline -15` and `gh pr list --state open` to see live PRs.
> If the task touches Market Pulse / Top Movers / Sector Rotation, run
> `/market-pulse-audit` before changing anything.*

**Pre-existing hard rules** (from CLAUDE.md, restated for emphasis):

- Work in a `git worktree`, not the canonical root (which stays on `main` for `claude-main`)
- Never `gh pr merge` — open the PR and stop; `claude-main` is sole master merger
- Branch prefix `<agent>/<type>/<slug>` (e.g. `claude/feat/<slug>`)
- Backend tests pass + frontend build clean before any PR opens for merge
- Disambiguate suspect hashes with `git cat-file -t <hash>` before treating as a git SHA — the Railway-deploy-ID confusion cost 16 hours on 2026-05-26

---

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

---
