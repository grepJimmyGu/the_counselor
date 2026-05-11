# Work Log — Livermore Development

> **How to use this file:**
> At the start of every session, read this file first. It tells you exactly where work stopped
> and what to do next. Update it at every meaningful checkpoint — after each completed step,
> before stopping, and whenever a blocker is discovered.

---

## Current Session

**Status:** IDLE — ready to start PRD-06  
**Active PRD:** None  
**Active branch:** main  
**Last stable tag:** (none yet — tags created at PRD completion)  
**Last commit:** See `git log --oneline -3` on session start

**Next action:**
```
Start PRD-06: git checkout -b feat/prd-06-fmp-integration
Read: agent-system/plans/PRD-06 spec (not yet written — write it first from PRODUCT_PLAN.md PRD-06 section)
Then begin implementation per PRD-06 acceptance criteria
```

---

## Resumption Checklist

Run these at the start of every autonomous session:

```bash
# 1. Orient
git log --oneline -5
git branch
git status

# 2. Read the plan
cat agent-system/WORK_LOG.md          # this file — current state
cat agent-system/PRODUCT_PLAN.md      # full PRD queue and specs

# 3. If mid-PRD: read the specific PRD spec
# e.g. cat agent-system/plans/PRD-06-fmp-integration.md

# 4. Continue from "Next action" above
```

---

## How to Update This File

**Update after every completed implementation step:**
```
Active PRD: PRD-06
Step completed: 2/8 — FMPClient HTTP adapter done
Next action: Implement get_profile() method in FMPAdapter
Last commit: abc1234 — "feat: add FMPClient with auth and retry logic"
```

**Update before stopping (context limit or end of session):**
```
Stopped at: Halfway through financial_validation_service.py
Next action: Complete compute_profitability_metrics() method — line 87 of financial_validation_service.py
Blocker: None
```

**Update on blockers:**
```
BLOCKED: FMP API key not set in .env — need FINANCIAL_MODELING_PREP_API_KEY
```

---

## PRD Execution Queue

| Order | PRD | Status | Branch | Tag on complete |
|---|---|---|---|---|
| **1** | **PRD-06** | **Ready to start** | `feat/prd-06-fmp-integration` | `prd-06-complete` |
| 2 | PRD-07 | Blocked on PRD-06 | `feat/prd-07-stock-screener` | `prd-07-complete` |
| 3 | PRD-08a | Blocked on PRD-06 | `feat/prd-08a-fundamental-analysis` | `prd-08a-complete` |
| 4 | PRD-09 | Ready (AV already integrated) | `feat/prd-09-news-sentiment-backend` | `prd-09-complete` |
| 5 | PRD-10 | Blocked on PRD-09 | `feat/prd-10-news-sentiment-frontend` | `prd-10-complete` |
| 6 | PRD-11 | Start after Phase 1+2 done | `feat/prd-11-auth` | `prd-11-complete` |
| 7–9 | PRD-12–14 | Blocked on PRD-11 | — | — |
| — | PRD-08b | BLOCKED — 10-K model | — | — |

---

## Rollback Reference

**To roll back to a stable PRD tag:**
```bash
git log --oneline --decorate   # see all tags
git checkout prd-06-complete   # inspect that state
git checkout main              # return to main

# To revert a bad merge to main:
git revert <merge-commit-hash> --no-edit   # creates a revert commit, preserves history
# NEVER: git reset --hard (destroys history)
```

**To abandon a bad feature branch:**
```bash
git checkout main
git branch -D feat/prd-XX-bad-branch   # delete locally only
# The merge to main has NOT happened yet — branch is just discarded
```

**Safe merge to main procedure:**
```bash
# Always from the feature branch:
npm run build                        # must pass
python3 -m pytest apps/api/tests/   # must pass
git checkout main
git merge --no-ff feat/prd-XX-name -m "feat: merge PRD-XX description"
git tag prd-XX-complete              # tag immediately after merge
git push origin main                 # requires manual approval (not in auto-allow)
git push origin prd-XX-complete      # push tag
```

---

## Session History

### 2026-05-11 — Planning session
- Completed: PRODUCT_PLAN.md, PRD-08a spec, PRD-09 spec, PRD-10 spec
- Installed: 8 agent skills (.claude/skills/)
- Configured: settings.json permissions for autonomous development
- Created: WORK_LOG.md (this file)
- Last commit: see `git log --oneline -3`
- No code written yet — all planning/documentation

---

## Autonomous Development Rules

When working autonomously without explicit user input, follow these rules:

1. **One PRD at a time** — complete current PRD fully before starting the next
2. **Commit at every logical checkpoint** — after each service, each route, each component
3. **Run build + tests before every commit** — `npm run build` and `pytest` must pass
4. **Run `safe-migration` skill on every Alembic migration** before merging
5. **Update WORK_LOG.md before every commit** — keep "Next action" accurate
6. **Never push to main** — merge + push requires user confirmation
7. **Never `git reset --hard`** — use `git revert` to undo
8. **Stop and note a blocker if:** API key missing, dependency install fails, tests fail 3+ times
9. **Tag main after every PRD merge** — `git tag prd-XX-complete`
