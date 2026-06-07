# CLAUDE.md — read this first

If you are an AI agent (Claude Code, codex, any other) about to touch this
repository, this file is your boot sequence. Read it before you run any
command, open any branch, or write any file.

> **Filename note:** named `CLAUDE.md` because Claude Code auto-loads files
> with that name from anywhere in the repo, so every new Claude Code
> session picks up these rules on boot without any extra wiring. Other
> agents (codex, etc.) should still read this file — its scope is *every*
> agent on the team, not just Claude Code.

The Livermore codebase is worked on by multiple agent sessions in parallel
plus a human (Jimmy). That arrangement has specific rules — break them and
you cause cross-session contamination that has already burned three PRs.
Don't be the fourth.

> **Session identity:** the AI session running in the canonical root at
> `/Users/jimmygu/the_counselor` is currently **`deepseek-main`** (master
> merger, on DeepSeek backend). It uses the `deepseek/` branch prefix. It
> took over the master-merger role from `claude-main` on 2026-06-01. Other
> sessions may use `claude/` or `codex/`; all follow the same protocol.

---

## Boot sequence

Read these files in order. Each is the canonical source for its topic; do
not improvise rules from training-data assumptions.

1. **[`agent-system/PARALLEL_WORK.md`](agent-system/PARALLEL_WORK.md)** —
   branch-naming convention (`<agent>/<type>/<slug>`), worktree-per-session
   rule, the **master-merger policy** (only `claude-main` runs `gh pr merge`
   against `main`; everyone else opens PRs and waits), and the Active
   Sessions table you may need to claim a row in.
2. **[`docs/PROJECT_BACKLOG.md`](docs/PROJECT_BACKLOG.md)** — single source
   of every open item. If you finish something here, delete its row in the
   same PR.
3. **[`apps/api/CLAUDE.md`](apps/api/CLAUDE.md)** — top backend traps
   (Postgres/SQLite divergence, orphan users without Plans, FastAPI 0.115
   strictness, etc.). Read before any change in `apps/api/`.
4. **[`apps/web/AGENTS.md`](apps/web/AGENTS.md)** — frontend agent rules.
   Notably: *"This is NOT the Next.js you know"* — Next.js 16 has breaking
   API changes; read `node_modules/next/dist/docs/` before writing code.

---

## Hard rules (do not violate)

- **Don't merge to `main` yourself.** Open a PR; `claude-main` reviews and
  merges. If `claude-main` is offline and a merge is urgent, escalate to
  Jimmy. The master-merger gate exists to catch cross-session contamination
  (see PARALLEL_WORK.md for the failure history that motivated it).
- **Always prefix branches with your agent name.** `deepseek/feat/<slug>`,
  `claude/feat/<slug>`, `codex/feat/<slug>`, `human/feat/<slug>`. No bare
  `feat/<slug>` for new work — that's how branches silently collide.
- **Work in your own worktree, not the canonical root.** Canonical root
  (`/Users/jimmygu/the_counselor`) is `claude-main`'s home and stays on
  `main`. Spin up `git worktree add ../the_counselor-<session-tag> -b <branch> main`.
- **Run `git status --short` immediately before every `git add`** to catch
  staging surprises. Don't `git add -A` or `git add .` — explicit pathspecs
  only.
- **Don't push to a branch you didn't create** unless explicitly asked.
- **Explain → plan → permission → code.** Before any non-trivial change:
  1. Explain the problem and context in a few sentences.
  2. Summarize the plan — files to touch, approach, risks.
  3. Wait for Jimmy's explicit go-ahead.
  4. Then write code.
  Hotfixes for production bugs we just introduced are exempt; everything
  else follows this sequence. *Why:* 2026-06-01 — the one_asset_mode
  backtest shipped with two bugs (missing auth token, wrong endpoint
  for anonymous users) that a plan review would have caught before the
  first push.
- **Bug fixes: explain cause → fix → verify.** Every bug fix commit must state:
  1. What the **symptom** was (user-visible error, log line, status code)
  2. What the **root cause** was (which line, why it happened)
  3. What the **fix** was and how it addresses the cause
  This applies to hotfixes too — production bugs are the most important
  ones to document clearly. *Why:* 2026-06-04 — the CN company overview
  returned a 502 for every A-share stock because `FinancialCheckMetrics`
  takes no `__init__` kwargs; the fix was 5 lines but four commits were
  needed because the root cause wasn't diagnosed before the first patch.
- **Wrap up with a goal-vs-result summary.** After every meaningful chunk
  of work, summarize: (1) what the original goal was, (2) what was actually
  achieved, and (3) what was started vs ended with (a before/after table if
  applicable). Keeps the session grounded and prevents scope creep. *Why:*
  2026-06-02 — the overlay picker redesign spanned 3 iterations before
  converging on the condensed card + two-column detail pattern; the wrap-up
  summary confirmed we actually solved the original problem (quick
  comparison + depth on demand).
- **Ask permission before deep research or multi-agent workflows.** The
  deep-research skill and Workflow tool fan out ~100 agents and burn
  significant tokens. Never launch one without Jimmy's explicit go-ahead.
  Before asking, check: can this be answered with a single API call or
  codebase search instead? *Why:* 2026-06-03 — a 30-minute deep-research
  workflow on CN stock APIs returned the same conclusion (FMP/AV don't
  support CN stocks on free tier) that one `curl` to FMP's endpoint
  would have confirmed in 30 seconds.

---

## Soft rules (operating defaults)

- **Karpathy coding principles** apply by default: think before coding,
  simplicity first, surgical changes (every changed line traces directly
  to the request), goal-driven execution (define verifiable success).
  Persisted in the canonical Claude Code user-memory as
  `feedback_karpathy_coding_principles.md`; the source is
  https://github.com/multica-ai/andrej-karpathy-skills.
- **Branch before main** for any feature work. The `feedback_git_workflow`
  rule is canon.
- **Python 3.9 compat** for backend — use `Optional[X]`, not `X | None`,
  because the CI runs on 3.9 even though Railway runs 3.13. The discrepancy
  is documented in `apps/api/CLAUDE.md`.
- **Avoid `until <cond>; do sleep N; done` in `run_in_background`.** The
  shape leaves orphaned entries in the harness's "Background tasks" panel
  even after the underlying process dies — the user has to manually click
  Stop to clear each one. Prefer a bounded `for i in $(seq 1 N); do …;
  done` with an explicit max iteration count, or just poll from the
  foreground. *Why:* 2026-05-24 — a SameSite=None deploy poll sat in the
  "Running" list for 128 minutes after its condition was met because the
  harness never received the success signal from the dead OS process.
- **Verify post-deploy under concurrent load, not single-curl, when your
  change touches shared mutable state across loops or threads.** A single
  sequential curl after deploy can't generate the conditions for
  concurrency bugs (cross-loop locks, race conditions, pool exhaustion)
  to manifest — they need overlapping requests. The cheap version: 10
  parallel curls or two browser tabs hammering refresh; if any hangs,
  the sequential check was lying. *Why:* 2026-06-07 — PR #138's "verified
  live in production" was one curl that landed warm; the cross-loop
  `asyncio.Lock` bug only manifested under concurrent traffic 48 hours
  later, taking US Market Pulse down for 28+ minutes. Trap #22 codifies
  the code-level pattern; this rule covers the verification gap.
  Full discussion: `docs/LEARNINGS.md` "Single-user post-deploy
  verification can't catch concurrency bugs by design."

---

## Pre-push checklist (Livermore)

Before any PR ready to merge into `main`:

1. Backend tests pass: `cd apps/api && python3 -m pytest -q`
2. Frontend build clean: `cd apps/web && npm run build`
3. Backend smoke test if you touched API surface: hit `/health` + the
   specific endpoint you changed
4. Python 3.9 compat: grep your diff for `| None` / `X | Y` — replace with
   `Optional[X]` / `Union[X, Y]` if any
5. Env var audit if you added one: Railway and/or Vercel matches; document
   in [docs/PROJECT_BACKLOG.md](docs/PROJECT_BACKLOG.md) §2 if not yet set

*Why:* 2026-05-07 — a push without this checklist would have shipped the
multi-asset backtester crash and an empty `momentum_rotation.rules` bug.

## Test discipline (Livermore)

- **Every bugfix pairs with a regression test.** No exceptions. The
  pattern: write the test that reproduces the bug, watch it fail, then
  fix the code until it passes. The test suite has grown 37 → 44 → 51
  → 52 → 420 → 446+ via this rule.
- **Frontend: define TypeScript types in `apps/web/src/lib/contracts.ts`
  *before* writing the UI component.** Catches schema drift between
  backend response and frontend render at the type-check step instead of
  at runtime. *Why:* a sandbox-schema rename once silently broke
  `research-workspace.tsx`; types-first would have surfaced it pre-commit.

## PR & branch mechanics (Livermore)

Three traps that bit us on 2026-05-21 — codify before they repeat.

### Stacked PRs lose backend CI

`.github/workflows/backend-ci.yml` has `on.pull_request.branches: [main]` —
backend tests only fire when the PR's base is `main`. A PR stacked on
another branch (base != main) gets only the Vercel preview checks; no
pytest, no Postgres migration smoke test. Either:

- Rebase every PR onto current `main` and set `base=main` before opening
  it — get full CI per PR (recommended)
- Or stack and manually verify locally with `pytest -q` before merging
  each. Master-merger must run the local check explicitly; CI green on
  parent ≠ CI green on child.

### Stacked-PR cascade on parent-delete

When you squash-merge a parent with `--delete-branch`, GitHub does NOT
auto-retarget child PRs to `main`. Children become `mergeStateStatus:
DIRTY, state: CLOSED` instantly — and `gh pr edit --base main` refuses
("Cannot change the base branch of a closed pull request"). Recovery:

1. The child's head branch still exists. Rebase it onto current `main`
   to drop the squash-duplicate commits:
   ```bash
   git rebase --onto main <old-parent-tip-sha> <child-head-branch>
   ```
2. Open a new PR from the rebased branch with `base=main`. New PR
   number, same content, full CI fires.

Avoiding this entirely: don't stack. Open each ticket as `base=main` once
the previous ticket has landed.

### Detect shadow branches with `git cherry`

A branch is a "shadow" when its content is on `main` (via squash) but its
commit hashes differ. Safe to delete if:

```bash
git cherry main origin/<branch>
```

- Outputs `+ <sha>` for commits NOT in main (real unmerged work)
- Outputs `- <sha>` for commits patch-identical to something on main
- Branch is a shadow if every line starts with `-` (zero `+`).

When `+` lines exist but the diff is only docs / session-slot bookkeeping,
the branch is still effectively a shadow. Verify with
`git diff main..origin/<branch> -- <key-files>`.

### Force-push blocked by classifier → fresh-branch rebase

The auto-mode classifier blocks `git push --force-with-lease` (and
`--force`) without explicit user sign-off, because force-push rewrites
remote history. The safe workaround is *never* to ask for the
exception — open a fresh branch instead:

1. Rebase the conflicted branch onto current `main` locally
2. Push the rebased commit under a new branch name (`...-rebased`
   suffix is the convention)
3. Close the old PR with a comment pointing at the new PR
4. Open a new PR from the rebased branch with `base=main`

Same content, new PR number, full CI fires, no destructive op needed.
Used twice in the 2026-05-22/23 sprint (Phase 1e PR #63→#64, and
the chat-tools-qa PR #76→#79). Documented in
[`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md).

---

## Product invariants

These are product-level contracts with users — not API contracts, not
DB schema, but how features behave at a UX level. Future agents must
treat these as floors, never quietly violate them.

### Stock universe is a STANDARD — expand only, never shrink

The Market Pulse Top Movers universe is `SP500_TICKERS`
(`apps/api/app/data/sp500_tickers.py`, ~525 entries). When the S&P
500 reconstitutes quarterly, refresh the file — but the size must
trend up over time, not down. The mental contract with users is
"Top Movers shows me the S&P 500 today"; that breaks the moment the
universe quietly contracts.

Concrete rule: PRs that touch `SP500_TICKERS` should add (or
swap-in-place at index reconstitution) entries, not remove without
a corresponding add. PRs that change `_build_top_assets` to filter
to a smaller universe (e.g. "top 50 by market cap" again) are
regressions — see the 2026-05-23 saga that prompted this rule.

Same principle for the sector ETF list (`US_SECTORS` in
`market_pulse_service.py`) and the macro basket
(`MACRO_BASKET` in `macro_similarity_service.py`) — they're
universes, not snapshots.

### Date stamps must be visible

Anything with a calendar anchor — narrative `as_of`, last-refresh
timestamps, data freshness — should be readable at a glance, not
buried in 9px muted footer text. The newspaper-byline pattern
(11px semibold uppercase tracking-wider, above the headline) is the
canonical rendering. *Why:* PR-3 (2026-05-22) shipped the date
field but rendered it invisibly; Jimmy didn't notice until PR-8
moved it to the byline.

---

## Project context (Livermore)

The canonical in-repo sources of truth (read on demand, not all at boot):

| Topic | File |
|---|---|
| Current state + next action + resumption checklist | [`agent-system/WORK_LOG.md`](agent-system/WORK_LOG.md) |
| Chronological history of what shipped | [`project_log.md`](project_log.md) |
| Episodic build journal + lessons | [`docs/BUILDING_LIVERMORE_JOURNAL.md`](docs/BUILDING_LIVERMORE_JOURNAL.md) |
| Production crash post-mortems | [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) |
| Traffic-gated work (Stage 5b/6b) | [`docs/DEFERRED.md`](docs/DEFERRED.md) |
| Pre-enforcement checklist before `GATING_ENABLED=true` | [`docs/SHADOW_MODE_REVIEW.md`](docs/SHADOW_MODE_REVIEW.md) |

**Quick facts** (the things that don't fit anywhere else):

- Three-tier SaaS: Scout (free), Strategist ($24/mo), Quant ($79/mo).
  TIER_CAPS matrix in `apps/api/app/services/entitlements.py`.
- Deployed: Railway (`thecounselor-production.up.railway.app`) + Vercel
  (`livermorealpha.com`). GitHub repo: `grepJimmyGu/the_counselor`.
- `GATING_ENABLED=true` on Railway (confirmed intentional 2026-05-21).
- Live quote cache wired into 5 frontend surfaces (ticker bar, stock
  detail, workspace preview, community feed, Market Pulse). Commodity
  spot deferred — see PROJECT_BACKLOG.md §4.

---

## For Claude Code sessions

You auto-load this `CLAUDE.md` plus any other `CLAUDE.md` files in the repo
(see `apps/api/CLAUDE.md`). On Jimmy's primary machine you also auto-load
user memory at `~/.claude/projects/-Users-jimmygu/memory/` which has
overlapping rules. **This file wins** if memory ever diverges — it's in
git, machine-independent, versioned. New accounts / new machines don't
inherit memory; they inherit this file via `git clone`.

---

## For non-Claude agents (codex, other tools)

You don't share Jimmy's user memory. This file is your only on-boot
contract. Read PARALLEL_WORK.md immediately; claim a slot; pick an
agent prefix; work in a worktree.

---

*Created 2026-05-21 by `claude-main` (master merger).*
