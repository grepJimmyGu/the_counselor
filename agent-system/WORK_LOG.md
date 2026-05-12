# Work Log — Livermore Development

> **How to use this file:**
> At the start of every session, read this file first. It tells you exactly where work stopped
> and what to do next. Update it at every meaningful checkpoint — after each completed step,
> before stopping, and whenever a blocker is discovered.

---

## Current Session

**Status:** Phases 1 + 2 + PRD-08b COMPLETE — 20 commits ready to push to origin/main  
**Active branch:** main  
**Last stable tag:** `prd-08b-complete`  
**Tests:** 106 backend passing · frontend build clean

**Next action:**
```bash
# Deploy (Option 1 — platform rollback)
# 1. Set env var on Railway FIRST (before pushing):
#    FINANCIAL_MODELING_PREP_API_KEY = <your FMP Starter key>
#
# 2. Push:
git push origin main
git push origin --tags
#
# 3. Verify (wait ~3 min for Railway to build):
curl https://thecounselor-production.up.railway.app/health
curl https://thecounselor-production.up.railway.app/api/sentiment/providers/status
curl https://thecounselor-production.up.railway.app/api/screener/filters
#
# 4. Run symbol seed (one-time, after backend is live):
#    Railway → your service → Shell tab:
#    python -m app.scripts.seed_symbols
#
# 5. If anything breaks — Railway: Deployments tab → previous deploy → Redeploy
```

**After deploy — immediate to-dos:**
- [ ] Add `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` when Reddit API approved
- [ ] Run `python -m app.scripts.seed_symbols` in Railway shell (one-time symbol seed)
- [ ] Verify `/stocks` screener has data after seed
- [ ] Start PRD-11: `git checkout -b feat/prd-11-auth`

---

## PRD Execution Queue

| Order | PRD | Status | Branch | Tag |
|---|---|---|---|---|
| 1 | PRD-06 | ✅ DONE | `feat/prd-06-fmp-integration` | `prd-06-complete` |
| 2 | PRD-07 | ✅ DONE | `feat/prd-07-stock-screener` | `prd-07-complete` |
| 3 | PRD-08a | ✅ DONE | `feat/prd-08a-fundamental-analysis` | `prd-08a-complete` |
| 4 | PRD-08b | ✅ DONE | `feat/prd-08b-business-intelligence` | `prd-08b-complete` |
| 5 | PRD-09 | ✅ DONE | `feat/prd-09-news-sentiment-backend` | `prd-09-complete` |
| 6 | PRD-10 | ✅ DONE | `feat/prd-10-news-sentiment-frontend` | `prd-10-complete` |
| **7** | **PRD-11** | **Ready to start** | `feat/prd-11-auth` | `prd-11-complete` |
| 8 | PRD-12 | Blocked on PRD-11 | — | — |
| 9 | PRD-13 | Blocked on PRD-12 | — | — |
| 10 | PRD-14 | Blocked on PRD-13 | — | — |
| — | PRD-05 | In discussion | — | — |

---

## Open To-Dos (non-PRD)

| # | Item | Priority | Notes |
|---|---|---|---|
| 1 | Reddit API credentials | High | Waiting for approval; add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` to Railway |
| 2 | Run `seed_symbols.py` in production | High | One-time; fills `symbols` table with ~8,000 US equities for screener |
| 3 | Market snapshot staleness bug | Medium | `fix/market-snapshot-staleness` branch — `is_stale` +3 day buffer issue |
| 4 | PRD-05: `not_supported` strategy handling | Medium | Redirect UX for strategies the engine can't support — needs design decision |
| 5 | Sentiment pre-warmer background job | Low | APScheduler top-100 S&P 500 every 3h; toggle via `PREWARM_ENABLED` |
| 6 | Update PRODUCT_PLAN.md (done this session) | Done | — |

---

## Session History

### 2026-05-12 — Phases 1 + 2 + PRD-08b build session
**Commits pushed to local main: 20**

| Commit | What |
|---|---|
| PRD-06 | FMPClient, DataSourceAdapter, yfinance fallback, FundamentalService, 3 API routes, seed script |
| PRD-07 | `/stocks` screener page, sector strip, filter panel, sortable results, screener backend |
| PRD-08a | `/stocks/[ticker]` deep-dive, Business Map (partial), Market Position (peers), Financial Check (full), scoring |
| PRD-09 | Sentiment provider system, Haiku LLM chain, 9-score framework, 7 toolkits, Sonnet sandbox, 5 DB tables, 7 API routes |
| PRD-10 | `/sentiment` hub, toolkit cards, provider status panel, sentiment tab on ticker page |
| UI integration | Homepage redesigned (3-pillar hero), Market Snapshot → stock page navigation, Asset Explorer cross-links |
| LLM refactor | Sentiment now uses existing OpenAI gateway — no Anthropic key required |
| PRD-08b | SEC EDGAR 10-K fetcher, section parser (Items 1/1A/7), LLM business intelligence, 90-day cache, company page enriched |
| Docs | This WORK_LOG rewrite |

**Test counts:** 63 → 106 backend tests across sessions  
**New DB tables:** 9 new tables total (Phase 1+2+08b)  
**New API routes:** 15 new routes across all PRDs

### 2026-05-11 — Planning session
- Completed: PRODUCT_PLAN.md, PRD-08a/09/10 specs
- Installed: 8 agent skills
- Configured: settings.json autonomous dev permissions
- No code written — all planning/documentation

---

## Rollback Reference

```bash
# View all stable tags
git log --oneline --decorate | grep "tag:"

# Platform rollback (fastest — 30 seconds):
# Railway: Dashboard → service → Deployments tab → previous deploy → Redeploy
# Vercel:  Dashboard → project → Deployments → previous deploy → Instant Rollback

# Code-level rollback to a known-good tag:
git revert --no-commit prd-10-complete..HEAD   # stage all reverts
git commit -m "revert: roll back to prd-10-complete"
git push origin main                            # triggers redeploy

# Nuclear option (only if revert commits won't work):
git push origin prd-10-complete:main --force    # ⚠ destroys intervening history
```

**Stable rollback points:**
| Tag | What's in it |
|---|---|
| `prd-10-complete` | Phase 1 + Phase 2 frontend (no PRD-08b, no UI integration) |
| `prd-09-complete` | Phase 1 + Sentiment backend only |
| `prd-08a-complete` | Phase 1 only (no sentiment) |

---

## Resumption Checklist

```bash
# 1. Orient
cd /Users/jimmygu/the_counselor
git log --oneline -5
git branch

# 2. Read the plan
cat agent-system/WORK_LOG.md
cat agent-system/PRODUCT_PLAN.md

# 3. Continue from "Next action" above
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
