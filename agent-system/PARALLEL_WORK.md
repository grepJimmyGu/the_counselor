# Parallel-work protocol

Multiple AI agent sessions (Claude Code, codex, etc.) operate on this repo concurrently. This doc is the **first file every session reads on boot** to avoid cross-session contamination.

> **Why this exists:** on 2026-05-21 I created `feat/check-schema-drift`, except codex had already used that branch name — git silently kept me on `main`, and I committed schema-drift work to main by accident. Recovered without push. Pure protocol failure: no broken code, but a near-miss. Don't repeat.

---

## Master merger (designated 2026-05-21)

**`deepseek-main` is the current master merger** (as of 2026-06-01). Previously
`claude-main` held this role. Only the active master merger runs `gh pr merge`
against `main`.

Other sessions push branches and **open** PRs, but do **not** merge them. The master merger:

1. **Diff sanity check** — reads the PR diff, verifies files match the title/body, scans for muddy commits (unrelated files snuck in via the cross-session collisions we've seen).
2. **Detects no-op PRs** — if a PR's branch content is already on `main` (e.g., its commits got picked up by a sibling muddy PR), the master merger closes it with a comment rather than merging an empty squash.
3. **Self-merges its own work** under the same diff-sanity rigor.

**Why this exists:** between 2026-05-21 morning and afternoon, three separate PRs (#27, #29, #30) merged with unintended files attached because multiple `gh pr merge` calls fired from sessions that had drifted off their intended branches. Funneling all merges through one agent eliminates the class.

If you're a non-master session and want a PR merged:
- Push your branch and open the PR yourself (titles + bodies as normal)
- Leave it alone — don't call `gh pr merge`
- `deepseek-main` (current master merger) reviews + merges; if no-op, closes with a comment so you see why

If `claude-main` isn't reachable and you need to merge urgently, fall back to Jimmy. Don't bypass the master merger silently.

---

## Conventions

### 1. Branch prefix per agent

Every branch starts with an agent prefix. No exceptions:

```
deepseek/feat/<slug>    # deepseek-main (master merger, canonical root)
claude/feat/<slug>      # Claude Code sessions
codex/feat/<slug>       # codex
human/feat/<slug>       # Jimmy hand-coding
deepseek/docs/<slug>    # Non-feature work follows the same rule
deepseek/fix/<slug>
claude/docs/<slug>
claude/fix/<slug>
```

This prevents the collision class above. Two agents that both want `feat/chat-builder` end up on `claude/feat/chat-builder` and `codex/feat/chat-builder` — different branches, peacefully coexisting.

**Exception:** `main` and any branches predating this protocol are grandfathered (`feat/...`, `codex/...`). Don't rename them; just stop creating new un-prefixed branches.

### 2. Worktree per session

Each concurrent session works in its own `git worktree`. Same `.git` store, separate file checkouts. Eliminates "wait, what branch am I on" + "where did this file come from."

```bash
# From the canonical repo root:
git worktree add ../the_counselor-<session-tag> -b claude/feat/<slug> main

# Tear down when done:
git worktree remove ../the_counselor-<session-tag>
```

Path convention: `../the_counselor-<session-tag>/`. The tag is short and describes what the session is doing (e.g., `chat-v2-p2`, `tier-audit`, `qa-tripwires`).

The canonical repo root (`/Users/jimmygu/the_counselor`) stays on `main` and is the **default landing point for new sessions**. Sessions move out of it into their own worktree before doing real work.

### 3. State lives in git

If another session needs to know something, **commit it**. Slack messages, conversation memory, and out-of-band coordination drift faster than git itself. The PR description, the branch name, and this doc are the only durable communication channels.

---

## Protocol

### On session boot

```bash
cd /Users/jimmygu/the_counselor
git fetch origin                                    # see what's new
git worktree list                                   # see what's in flight
cat agent-system/PARALLEL_WORK.md                   # this file
```

Update the **Active sessions** table below — claim your slot. If you see a slot with someone else's name, leave it alone.

### On commit / push

After each push, update the row's commit hash + a one-line status. Push the doc update along with your work.

### On session end / when you walk away

Either:
- **Done** — the branch landed in a PR. Update status to `merged-to-main` or `pending-review`. The worktree can be removed.
- **Pause** — leave a note in your row: "paused at <state>, resume by <next step>." Branch and worktree stay.

---

## Active sessions

| Session | Worktree path | Branch | HEAD | Status |
|---|---|---|---|---|
| **deepseek-main** (master merger) | `/Users/jimmygu/the_counselor` | rotating per-task | latest | Active 2026-06-01 — current master merger. Runs on DeepSeek backend; uses `deepseek/` prefix. Owns all `gh pr merge` to `main`. |
| claude-main (former master merger) | — | — | — | Retired 2026-06-01. Master-merger role handed off to deepseek-main. |
| codex-chatbuilder | `/private/tmp/the_counselor_chatbuilder_test` | `codex/improve-chat-builder` | `0932c75` | abandoned 2026-05-19; rebase or delete |
| deepseek-overlay-expansion | — | — | — | Merged 2026-06-01 — PRD-13c: 3 new portfolio overlay strategies (dual momentum, defense-first, stability tilt). |

The old `claude-chat-v2-p7-widget` row was retired 2026-05-22. The
`claude-flow-runtime` and `claude-portfolio-mode` rows were retired
2026-06-01 (PRs #117, #125 merged and deployed).

When you start, **add a row.** When you finish, **delete it** (history is in git).

### Open feature branches not currently driven by a session

These exist on origin but no session is actively working on them. Sometimes a PR was opened and the session moved on; sometimes the branch was abandoned. Keep this list short:

- `claude/feat/market-pulse-v2-preview` — PR [#41](https://github.com/grepJimmyGu/the_counselor/pull/41) open. **Phase 0a SIGNED OFF 2026-05-21.** Holds the full Market Pulse v2 redesign as a preview at `/uiux/market-pulse-v2`. Waiting on Phase 1a (claude-main will lift to `/stocks` and delete the preview route).

A new session was reported spinning up its own worktree on 2026-05-21; Active Sessions row not yet visible on origin. Add row when first commit lands.

---

## Recovery procedures

### "I committed to main by accident" (the 2026-05-21 case)

You did not push yet. Recover non-destructively:

```bash
git branch claude/<rescue-slug>          # tag the bad commit on a new branch
git reset --keep HEAD~1                  # move main back; aborts if it would lose work
git switch claude/<rescue-slug>          # continue on the right branch
```

`--keep` is the non-destructive form. If git refuses, you have uncommitted changes that conflict; commit or stash first.

### "Another session committed my file"

Happened on 2026-05-21 with `build_specs/research_chat_v2.md`. Diagnosis:

```bash
git log --all --oneline -- <path>        # find commits that touched it
diff <(git show <commit>:<path>) <path>  # are they identical?
```

If identical, your file is already on the canonical timeline — no action needed; remove from your tree or proceed. If different, treat as a 3-way merge: resolve manually, never blindly overwrite.

### "I'm on a branch that's behind main by N commits"

Don't `merge main into branch` mid-flight unless you have to — creates noisy merge commits. Instead:

```bash
git fetch origin
git rebase origin/main           # if your branch is unpushed
# or, if pushed but no one else is on your branch:
git pull --rebase origin <your-branch>
```

`--rebase` keeps history linear and your PR diff reading clean.

---

## What NOT to do

- Don't kill processes you didn't start (e.g., `next dev` on port 3000) without confirming whose they are. `ps -ef | grep <pid>` + the working directory shown is the tell.
- Don't reuse an existing branch name without prefix. Check `git branch -a | grep <slug>` first.
- Don't rely on "I'll remember" — write it into this doc or the branch's PR description.
- Don't push to anyone else's branch unless they explicitly asked.
