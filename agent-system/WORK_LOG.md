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

## Current state — 2026-08-13

**Shipped and merged today:** #313 (card generated once daily) · #314 (ornament +
bundled fonts) · #315 (the share button) · #316 (card layout overlap) · #317
(dividend-yield units). See `project_log.md` for what each did.

**The daily share card is live and reachable.** Share button sits on "Moving
today". English only in production — the Chinese card needs a bundled CJK font
(~4-5 MB), which is Jimmy's call; `can_render` hides the option until it lands,
so nothing is broken by its absence.

### In flight

| Branch | State |
|---|---|
| `claude/fix/fundamental-screen-path` | scan empty-rules fix + market cap in the backfill — **PR pending**, suite running |

### Next actions, in order

1. **Merge the fundamental-screen-path PR.** Unblocks "p/e under 15" and every
   fundamental condition in the Conditions composer — they resolve 564 / 884
   names today and the results page discards them.
2. **Jimmy runs `scripts/backfill_fundamentals.py`.** `market_cap` sits at
   **1.8%** across the Russell 3000; four presets and both market-cap filters
   read it. ~25 min. This is the highest-value outstanding item.
3. **Design the lazy-refresh mechanism.** No scheduled job refreshes
   fundamentals — coverage is an accident of which script ran last and which
   company pages people opened. Until that exists, every gap needs a manual
   backfill and drift resumes the same day. Sizing depends on the FMP quota.

### Known and deliberately not fixed

- **Chinese card** — refuses on Linux by design until a CJK font is bundled.
- **`market_cap` 1.8%** — needs the backfill run above.
- **25 stale dividend rows** — the #317 read guard stops them being reported;
  `scripts/fix_dividend_yield_units.py --apply` tidies the data when convenient.
- **[#308](https://github.com/grepJimmyGu/the_counselor/pull/308)** — stale
  work-log docs PR, open for weeks. Largely superseded by this restructure.

### Still-open deferrals carried forward from 2026-06-25

- **Stripe is fully built but unconfigured** — paywalls are live with no pay
  path. Turn-on is 4 price IDs + secret/webhook keys on Railway, test-mode
  first. PostHog is configured and flowing.
- **Liquidity floor on Russell 3000 presets** — the broad market's microcaps
  surface junk in `best_momentum`-type screens. Shipped raw deliberately; tune
  against real results.
- **Six AV-drift class shares** unreconciled (AKE / BF.A / BF.B / GEFB / HEIA /
  LENB) — hyphen convention, see trap #15.
- **`pct_below_high` primitive** — in `PROJECT_BACKLOG`.

### Don't touch without coordinating

The screener / fundamentals path — `scan_service.py`,
`backfill_fundamentals.py`, `fundamental_service.py`, `screener_service.py` —
has work in flight on the branch above.

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
