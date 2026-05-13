# Work Log — Livermore Development

> **How to use this file:**
> At the start of every session, read this file first. It tells you exactly where work stopped
> and what to do next. Update it at every meaningful checkpoint — after each completed step,
> before stopping, and whenever a blocker is discovered.

---

## Current Session

**Status:** PRD-11 COMPLETE — Phase 3 community layer in progress  
**Active branch:** main  
**Last stable tag:** `prd-11-complete`  
**Tests:** 106 backend passing · frontend build clean  
**Deployed:** Railway + Vercel — all of Phase 1, 2, and PRD-11 live

**Next action:**
```bash
# Phase 3 — build PRD-12, PRD-13, PRD-14 in sequence
git checkout -b feat/prd-12-watchlists-profiles
# Build watchlists + user profiles first (required for community signal score)
# Then PRD-13 (votes + community signals) on same or new branch
# Then PRD-14 (strategy sharing + comments)
```

**Production env vars still needed (sign-in won't work until set):**
```
Vercel:  AUTH_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
         INTERNAL_API_KEY, INTERNAL_API_BASE_URL
Railway: INTERNAL_API_KEY (same value as Vercel)
```

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
| 7 | PRD-11 | ✅ DONE | `feat/prd-11-auth` | `prd-11-complete` |
| **8** | **PRD-12** | **In progress** | `feat/prd-12-watchlists-profiles` | `prd-12-complete` |
| 9 | PRD-13 | Next after PRD-12 | `feat/prd-13-community-signals` | `prd-13-complete` |
| 10 | PRD-14 | Next after PRD-13 | `feat/prd-14-community-page` | `prd-14-complete` |
| — | PRD-05 | In discussion | — | — |

---

## Open To-Dos (non-PRD)

| # | Item | Priority | Notes |
|---|---|---|---|
| 1 | Set production auth env vars | High | AUTH_SECRET, GOOGLE_CLIENT_ID/SECRET, INTERNAL_API_KEY on Vercel + Railway |
| 2 | Reddit API credentials | Medium | Add REDDIT_CLIENT_ID + SECRET to Railway when approved |
| 3 | Market snapshot staleness bug | Low | `fix/market-snapshot-staleness` branch |
| 4 | PRD-05: `not_supported` strategy handling | Low | Redirect UX — needs design decision |
| 5 | Sentiment pre-warmer background job | Low | Top-100 S&P 500 every 3h via APScheduler |

---

## Session History

### 2026-05-12 — Phase 3 start
- PRD-11 complete: Auth.js v5, Google OAuth, JWT sessions, NavHeader sign-in/avatar
- Adversarial audit run: 3 HIGH findings fixed (internal key bypass, open redirect, ownership check)
- UI/UX review: skip link, inputMode on search fields, accessibility improvements
- FMP stable API migration: /api/v3 → /stable, sec-filings via EDGAR CIK, field remapping
- 14,548 symbols seeded into production PostgreSQL

### 2026-05-12 — Phase 1+2 deploy
- All PRD-06 through PRD-10 + PRD-08b pushed and deployed to production
- FMP key issue discovered and fixed (stable API migration)
- Symbol seed run via Railway CLI

### 2026-05-11/12 — Phases 1 + 2 build
- PRD-06: FMP, FundamentalService, yfinance fallback, seed script
- PRD-07: Stock screener, sector strip, filters, URL state
- PRD-08a: Company deep-dive, Financial Check, scoring
- PRD-08b: SEC EDGAR 10-K fetch, section parser, LLM business intelligence, 90-day cache
- PRD-09: Sentiment provider system, Haiku LLM chain, 9 scores, 7 toolkits, Sonnet sandbox
- PRD-10: /sentiment hub, toolkit cards, sentiment tab on ticker page

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

## Resumption Checklist

```bash
cd /Users/jimmygu/the_counselor
git log --oneline -5
cat agent-system/WORK_LOG.md
cat agent-system/PRODUCT_PLAN.md
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
