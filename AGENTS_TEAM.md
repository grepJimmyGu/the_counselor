# AGENTS_TEAM — read this first

If you are an AI agent (Claude Code, codex, any other) about to touch this
repository, this file is your boot sequence. Read it before you run any
command, open any branch, or write any file.

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

## For Claude Code sessions on Jimmy's machine

You auto-load user memory from `~/.claude/projects/-Users-jimmygu/memory/`
which includes the same rules summarized above. This file is the canonical
source if the two ever diverge. If memory says one thing and this file
says another, **this file wins** (it's in git, machine-independent,
versioned).

---

## For non-Claude agents (codex, other tools)

You don't share Jimmy's user memory. This file is your only on-boot
contract. Read PARALLEL_WORK.md immediately; claim a slot; pick an
agent prefix; work in a worktree.

---

*Created 2026-05-21 by `claude-main` (master merger).*
