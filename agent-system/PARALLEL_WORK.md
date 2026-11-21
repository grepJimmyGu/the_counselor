# Parallel-work protocol

Multiple AI agent sessions (Claude Code, codex, etc.) operate on this repo concurrently. This doc is the **first file every session reads on boot** to avoid cross-session contamination.

> **Why this exists:** on 2026-05-21 I created `feat/check-schema-drift`, except codex had already used that branch name — git silently kept me on `main`, and I committed schema-drift work to main by accident. Recovered without push. Pure protocol failure: no broken code, but a near-miss. Don't repeat.

---

## Who merges

*Rewritten 2026-11-20 to match what actually happens.*

**A session merges a PR only when Jimmy names that PR** in his message
("merge #381"). One named PR is one merge; it does not carry to the next one.
No session merges on its own judgement, its own docs included. Otherwise: push
the branch, open the PR, and stop.

Whoever merges does the check the old gate existed for:

1. **Read the diff against the title.** Files that do not belong to the PR's
   stated change are the failure this rule was written for.
2. **Close a no-op PR instead of merging it.** If the branch's content is
   already on `main`, say so in a comment and close it.
3. **Squash-merge.** The branch is deleted automatically (repository setting,
   on since 2026-11-20); the PR page can restore it.

**A standing master merger is optional, not the default.** Jimmy can appoint
one session to merge without per-PR naming for a stretch; he last did on
2026-08-09. That session addresses him as **"Mr Gu"** so the role is visible
at a glance, and every other session says "Jimmy". Nobody holds the role
unless he says so in that session: do not ask about it on boot, do not assume
it, and do not greet him as "Mr Gu" otherwise.

**Why the gate existed:** on 2026-05-21, three PRs (#27, #29, #30) merged with
unintended files attached, because several sessions that had drifted off their
branches each ran `gh pr merge`. Routing every merge through one session
(`claude-main`, then `deepseek-main` from 2026-06-01) removed the class. In
practice the single merger stopped being a running session, and Jimmy's naming
a PR became the gate. The diff check above is the part that still matters.

---

## Conventions

### 1. Branch prefix per agent

Every branch starts with an agent prefix. No exceptions:

```
deepseek/feat/<slug>    # sessions on the DeepSeek backend
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
git fetch origin
git worktree add ../the_counselor-<session-tag> -b claude/feat/<slug> origin/main

# Tear down once the PR has merged:
git worktree remove ../the_counselor-<session-tag>
```

**Branch from `origin/main`, never from local `main`.** On 2026-11-20 the
canonical root's `main` was 17 PRs behind `origin/main`, and its files were
older than that. A worktree cut from it starts months stale.

**Tear down is part of the job.** By 2026-11-20 there were 33 worktrees, 167
local branches and 59 remote ones, almost all for PRs long merged. The remote
side now cleans itself (GitHub deletes a branch when its PR merges); the
worktree and the local branch are yours to remove.

Path convention: `../the_counselor-<session-tag>/`. The tag is short and describes what the session is doing (e.g., `chat-v2-p2`, `tier-audit`, `qa-tripwires`).

The canonical repo root (`/Users/jimmygu/the_counselor`) is where a new session lands. Move out of it into your own worktree before doing real work, and do not treat its files as current: check `git status` and `git log -1` there before trusting anything you read in it.

### 3. State lives in git

If another session needs to know something, **commit it**. Slack messages, conversation memory, and out-of-band coordination drift faster than git itself. The PR description, the branch name, and this doc are the only durable communication channels.

---

## Protocol

### On session boot

```bash
cd /Users/jimmygu/the_counselor
git fetch origin                                    # see what's new
git log --oneline -15 origin/main                   # what landed recently
gh pr list --state open                             # what is in flight
git worktree list                                   # where other sessions are working
```

Open PRs and the worktree list are the record of what is in flight. There is
no table to claim a row in: the one this file used to keep was last accurate
in September and nobody was reading it.

Then say in your first reply whether you are an executing or a planning
session (CLAUDE.md "Session roles"), and create your worktree.

### On session end / when you walk away

- **Done** — the PR is open or merged. Once it has merged, remove the
  worktree and delete the local branch.
- **Paused** — say where you stopped in the PR description, or in
  `agent-system/WORK_LOG.md` if there is no PR yet. Branch and worktree stay.

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
