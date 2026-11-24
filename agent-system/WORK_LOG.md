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

## Current state — 2026-11-20

**`main` is at #382.** Since the last checkpoint (2026-09-10, #365) these landed:

| PR | What it did |
|---|---|
| #366, #370 | Search lands on its answer; a screen can keep the rule or keep the names |
| #367, #368 | Sessions split by role; one results surface scoped, not built |
| #375 | Market data had gone two months stale: refreshed on a schedule |
| #373 | **Native iOS app** (`apps/ios`): research, live prices, strategy builder, brokerage, actions |
| #376 | Quarterly filing analysis from 10-Q / 10-K data |
| #377 | Password rules, reset by email, Google sign-in for the iOS app |
| #378 | Portfolio agent v1: monitor, findings, conversation, the Agent tab |
| #379 | Faster app loading; the agent holds up under many requests |
| #381, #382 | Options builder (PRD-44 step 1) and its first fix |

### Open PRs

| PR | State |
|---|---|
| #383 | CI: backend run 22 min → ~3, first checks for the iOS app and the site |
| #384 | iOS API contract generated from the backend code and checked in CI |
| #380 | Fresher live quotes (rebase of #374). Needs a decision, not work |
| #372 | Site stops running compute on every request. **The Vercel account is blocked until this or an account fix lands; the site does not deploy** |
| #371 | Company page 500 on a long country name |
| #369 | PRD-26b docs, open since 2026-09-10 |

The Vercel check fails on every PR for the reason in #372. Until it is fixed,
a red Vercel mark carries no information; read the other checks.

### Shipped but not yet proven with a real account

Six features merged on 2026-11-20. The code is tested; these paths have not
run end to end for a real user, and each is a candidate for "works on the
sample account only":

- the agent with a real model and its scheduled scan (needs LLM keys on Railway);
- Google sign-in on the phone (needs `GOOGLE_IOS_CLIENT_ID`);
- saving an option plan on production, and the broker ticket against a real broker;
- any order through a connected brokerage.

A dedicated test account on production would let a session check signed-in
flows itself. Today no session can.

### Next

- **iOS track** (roadmap Jimmy accepted on 2026-11-20): options step 2,
  preview and place through the connected broker; step 3, the agent proposes
  plans from holdings; step 4, backtest on historical chains. Plan and
  as-built notes: `agent-system/plans/PRD-44-options-builder.md`.
- **Before more surfaces:** the "not yet proven" list above. Recommended by
  the session that wrote this, not yet decided by Jimmy.
- **Known slow path, proposed and not started:** the first view of a company
  nobody opened that week takes 3–8 s, because its competitor ranking is
  rebuilt inside the request.
- **Quant Engine track:** unchanged since 2026-09-10; its order is below.

### Needs Jimmy

- Vercel: unblock the account or merge #372.
- Railway: LLM keys for the agent, `GOOGLE_IOS_CLIENT_ID`; `railway login`
  so sessions can read logs.
- A production test account for verification.
- Decisions on #380, #371 and #369: merge or close.

### Two things about this machine that will mislead you

- **The canonical root is stale.** `/Users/jimmygu/the_counselor` had `main`
  17 PRs behind `origin/main` on 2026-11-20, with files older than that and
  about 200 entries in `git status`. Branch from `origin/main` and read code
  from your own worktree.
- **The default `python3` is 3.9 with an unpinned FastAPI** (0.128, not the
  0.115.12 in `requirements.txt`). Tests pass on it, but anything that depends
  on the schema's exact shape does not match production. Use an environment
  built from `requirements.txt` for that (`apps/ios/README.md` has the command).

---

## Quant Engine track — as left on 2026-09-10

*Unchanged by the 2026-11-20 checkpoint. The planning session owns this block.*

**Eleven PRs merged**, #355 → #365.

> 📍 **Read [`docs/QUANT_ENGINE_MAP.md`](../docs/QUANT_ENGINE_MAP.md) before
> planning any 43-series work.** It maps the blueprint's §1–§40 to what ships
> and carries the ranked open questions. This file says where work *stopped*;
> the map says what the work is *for*.
>
> ⚠ Two sessions ran in parallel on 2026-09-09 and collided twice (#362
> duplicated a fix already written elsewhere; #365 rewrote the file #362 had
> just repaired). Both were in separate worktrees the whole time — worktrees
> did not prevent it. Sessions now split by **role**; see CLAUDE.md
> "Session roles".

The Quant Engine packet went from "43a shipped, both lenses blocked" to
**level 0, 1 and 2 of the maturity ladder live end to end**: the Mirror
measures your record, the Timing Engine measures your entries and exits
against it, and a finding can now be saved as a rule that outlives the tab.

| PR | What it did |
|---|---|
| [#355](https://github.com/grepJimmyGu/the_counselor/pull/355) | 43a §3.8 — `TradeEpisode` + `PortfolioSnapshot`, the reconstruction both lenses read. Unblocked 43b and 43c |
| [#356](https://github.com/grepJimmyGu/the_counselor/pull/356) | 43b P0 — markouts, excursions, catalog snapshot, the two classifications, `GET /api/mirror/timing` |
| [#357](https://github.com/grepJimmyGu/the_counselor/pull/357) | Mirror v2 four zones + the WHEN section rendering 43b's numbers |
| [#359](https://github.com/grepJimmyGu/the_counselor/pull/359) | 43e Rules P0 — `Rule` object, `/api/rules`, `/account/rules`, and Save-as-a-rule on the WHEN section |
| [#360](https://github.com/grepJimmyGu/the_counselor/pull/360) | Session handoff docs |
| [#361](https://github.com/grepJimmyGu/the_counselor/pull/361) | The exit plan — `POST /api/mirror/exit-plan`, `LeakTrade` evidence rows, the exit-gap net split, `SnapTradeReadFailed` |
| [#362](https://github.com/grepJimmyGu/the_counselor/pull/362) | `/account/brokerage` died on load — `LeakView` computed `trades` and never serialised them. `ExitGapView` had the same hole |
| [#363](https://github.com/grepJimmyGu/the_counselor/pull/363) | Two ways into Quant Rules from Home — **closes the "no entry from Home" gap** |
| [#364](https://github.com/grepJimmyGu/the_counselor/pull/364) | The Mirror was gated on a value that means something else |
| [#365](https://github.com/grepJimmyGu/the_counselor/pull/365) | The portfolio step fits one screen; overlay shortlist |

### Next, in order

1. **43c P0 — Allocation Lens.** Unblocked since #355. Slots into the
   HOW MUCH section of the frame #357 built. ~1.5 wk.
2. **43b P0's trade page** — the per-episode drill-down (chart with entry/exit
   markers plus that episode's numbers). The last open item on P0's DoD; the
   aggregate view shipped without it, deliberately.
3. **43d**, before 43b P1 rather than after.

⚠ **Items 1 and 2 are contested.** #361 ships an exit plan whose rule saves at
`saved` with no path to `tested`, because the blueprint's §22 validation
methodology does not exist. The larger question: *is rule discovery
statistically possible on a 33-episode record at all?* See the map's "fork
worth deciding first" — do not start 43b P1 without settling it.
4. **43b P1**, then **43c P1** (43c P1 never waits on 43d).
5. **43e Playbooks** — needs 43d for the `validated` state.

Jimmy owns three: the 43f blueprint (unblocked now that 43b P0 exists), the
free/paid tier boundary, and Stripe.

### ⚠ Stripe is the decision that compounds

43b shipped **ungated** on 2026-08-28 — correct, since a tier gate today
enforces against a paywall nobody can pass (four price IDs and the
secret/webhook keys sit on Railway in test mode). But 43c, 43d and the paid
half of 43e all queue behind the same question, and every surface shipped
ungated is one somebody has to gate retroactively.

### Coverage gap worth knowing before reading any 43b output

`price_bars` holds **no ETFs or ADRs**. On the live account that cost 24 of 57
episodes — UVXY alone carried 15 — so the WHEN section measured 58% of that
record and omitted its most-traded symbol. The engine names every exclusion
and the surface states the measured share, so this is coverage rather than
correctness. Deferred by Jimmy; see `docs/PROJECT_BACKLOG.md` §5.

### Three defects the live runs caught that fixtures did not

Worth repeating because the pattern held all session: **this packet's failure
mode is not a broken page, it is a plausible number.**

- **§3.8 same-day netting.** BHP and UVXY netted to exactly zero units against
  a broker holding zero and were still excluded — a same-day buy and sell were
  judged in feed order. Day deltas are now netted per symbol first.
- **Giveback priced on the wrong units.** It used the episode's total units,
  assuming the whole position was on at the high. Priced on units actually
  held at the MFE date it fell $10,535 → $4,349, collapsing its lead over
  `panic_exit` from 3.2× to 1.3×. A slightly different record would have named
  the wrong thing as the user's biggest problem.
- **A mock that had drifted from its contract.**
  `strategy-dashboard-page.test.tsx` mocked two endpoints as `[]` when both
  return objects, throwing during render about one run in five. I "fixed" it
  first by hardening the components, re-sampled, and it still failed — which
  is what sent me to the mock. `vi.mock` is untyped, so it drifted: the same
  schema-drift class the types-first rule exists to catch, one layer down.

### Don't touch without coordinating

Nothing on this track is in flight. All branches through #365 are landed.

Lane split as of 2026-09-10: the **planning session** owns `docs/`,
`agent-system/` and the roadmap; **executing sessions** own `apps/`. See
CLAUDE.md "Session roles".


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

## Open To-Dos (non-Stage)

| # | Item | Priority | Trigger |
|---|---|---|---|
| 1 | Set `EMAIL_UNSUB_SIGNING_KEY` on Railway | High | Before first real email send (currently unsafe dev default) |
| 2 | Set `CAN_SPAM_ADDRESS` on Railway | High | Before scale-marketing (≥100 users) |
| 3 | Move uncommitted `research-workspace.tsx` to feature branch | High | Git workflow rule — never edit on `main` |
| 4 | Reddit API credentials | Medium | When approved → add `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| 5 | Frontend lint debt (92 errors on 2026-11-20; it was 26) | Medium | Clear it, then add lint to `web-ci.yml`; until then lint is not a CI gate |
| 6 | PRD-05: `not_supported` strategy handling | Low | Redirect UX — needs design decision |
| 7 | Market snapshot staleness bug | Low | `fix/market-snapshot-staleness` branch |
| 8 | Sentiment pre-warmer background job | Low | Top-100 S&P 500 every 3h via APScheduler |

See [docs/DEFERRED.md](../docs/DEFERRED.md) for the ~30 trigger-gated items split across Stage 5b + Stage 6b.

---

---

## Rollback Reference

```bash
# Railway: Deployments tab → previous deploy → Redeploy
# Vercel:  Deployments → previous deploy → Instant Rollback
# Code:    git revert <the squash commit of the PR> on a branch, then a PR
```

The `prd-NN-complete` tags stop at `prd-14-complete` (May 2026) and are not a
usable rollback point for anything since.

---

---

## Resumption Checklist

For any Claude session (new or returning) picking up Livermore, follow this
exact sequence. It takes ~3 minutes and bootstraps the full project state.

```bash
# 1. From the canonical root, see what shipped recently and what's open
cd /Users/jimmygu/the_counselor
git fetch origin && git log --oneline -15 origin/main   # last 15 PRs to land (local main may be stale)
gh pr list --state open                # in-flight work from sibling sessions
git worktree list                      # other sessions' active worktrees
```

```bash
# 2. Read these four files in order — they're the canonical sources
#    The root CLAUDE.md auto-loads via Claude Code; the others must be read explicitly.
cat agent-system/WORK_LOG.md           # ← THIS file: current state + next action (read first)
head -120 project_log.md               # latest day's shipped work (chronological)
cat docs/PROJECT_BACKLOG.md            # every open item with trigger conditions
cat apps/api/CLAUDE.md                 # the backend traps (auto-loads when editing apps/api/)
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

- Work in a `git worktree` cut from `origin/main`, not in the canonical root
- Merge a PR only when Jimmy names it; otherwise open the PR and stop
- Branch prefix `<agent>/<type>/<slug>` (e.g. `claude/feat/<slug>`)
- Backend tests pass + frontend build clean before any PR opens for merge
- Disambiguate suspect hashes with `git cat-file -t <hash>` before treating as a git SHA — the Railway-deploy-ID confusion cost 16 hours on 2026-05-26
