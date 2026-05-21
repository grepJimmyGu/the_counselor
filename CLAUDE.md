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
- **Always prefix branches with your agent name.** `claude/feat/<slug>`,
  `codex/feat/<slug>`, `human/feat/<slug>`. No bare `feat/<slug>` for new
  work — that's how branches silently collide.
- **Work in your own worktree, not the canonical root.** Canonical root
  (`/Users/jimmygu/the_counselor`) is `claude-main`'s home and stays on
  `main`. Spin up `git worktree add ../the_counselor-<session-tag> -b <branch> main`.
- **Run `git status --short` immediately before every `git add`** to catch
  staging surprises. Don't `git add -A` or `git add .` — explicit pathspecs
  only.
- **Don't push to a branch you didn't create** unless explicitly asked.

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
