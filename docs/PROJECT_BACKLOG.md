# Project Backlog

The single place to look for everything that's outstanding on Livermore but
not actively being worked on. Living document — add, update, prune.

**Not a duplicate of:**
- [`docs/DEFERRED.md`](DEFERRED.md) — items cut from each stage spec, gated
  on traffic events. Cross-linked below; don't restate the list here.
- [`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md) — post-mortems for shipped
  bugs. Items in this backlog should link there when relevant.
- GitHub issues — the canonical task tracker for actionable items. This
  doc points to the issue; the issue holds the conversation + spec.

**Last refreshed:** 2026-05-22 (post Phase 1c–1f ship)

---

## 1. Schema drift triage (10 items)

Surfaced by `apps/api/scripts/check_schema_drift.py` on 2026-05-21 (first
run, against prod via Railway). Each line is either a real drift (WARN)
or a benign artifact (DIFF/INFO). One issue per WARN; no issues for
DIFF/INFO unless they later cause real friction.

**Triage discipline:** one drift = one decision = one deploy. Do not
bundle into a sweep migration; each item carries its own risk profile
and wants isolated blame on rollback. See the rationale at the bottom of
this file under "Discipline notes."

### Real triage queue — 9 WARN items

| # | Drift | Triage | Backfill question | Issue |
|---|---|---|---|---|
| 1 | `backtests.is_public` nullable=YES prod, NO model | Fix | NULL → `false` (privacy-safe default) | [#TBD] |
| 2 | `users.email` varchar(255) prod, varchar(320) model | Fix | none — pure widening | [#TBD] |
| 3 | `users.last_login_at` tz-naive prod, tz-aware model | Fix carefully | `AT TIME ZONE 'UTC'` (Railway runs UTC) | [#TBD] |
| 4 | `users.email_verified_at` tz-naive prod, tz-aware model | Fix carefully | same as #3 | [#TBD] |
| 5 | `users.created_at` nullable=YES prod, NO model | Fix | `COALESCE(created_at, NOW() - INTERVAL '1 year')` OR derive from related row | [#TBD] |
| 6 | `users.updated_at` nullable=YES prod, NO model | Fix | same as #5 | [#TBD] |
| 7 | `users.locale` nullable=YES prod, NO model | Fix | NULL → `'en'` (Stage 1 default) | [#TBD] |
| 8 | `users.oauth_provider` varchar(20) prod, varchar(32) model | Update model | shrink `String(32)` → `String(20)`; no DB touch | [#TBD] |
| 9 | `users.oauth_subject` varchar(100) prod, varchar(255) model | Update model | shrink `String(255)` → `String(100)`; no DB touch | [#TBD] |

### Accept / defer — 1 INFO item

| # | Drift | Disposition |
|---|---|---|
| 10 | `robustness_jobs.user_id` exists in prod, not in model | Accept. Zombie column from PRD-04 era. Schedule a `ALTER TABLE DROP COLUMN` cleanup at next convenience; not urgent (column is unused; no FATAL behavior). |

### Noise (17 DIFF items)

All 17 are `model=float prod=double precision` — `SQLAlchemy Float` always
compiles to `FLOAT`, Postgres always stores as `double precision`. Numerically
equivalent, pure noise. Suppressed from exit code by design.

### Tripwire baseline

After all 9 WARN items resolve, the baseline becomes **17 DIFF + 1 INFO**.
Any future WARN line is a new bug; the daily `check_schema_drift_job`
already logs `INVARIANT_BROKEN: schema_drift WARN ...` so growth past
this baseline is visible without further infrastructure.

---

## 2. Pre-launch operational tasks

Things that must be done before specific real-world events (first email
send, first real customer, scaling marketing past ~100 users). None are
actively blocking development; all are gates on going-live activities.

| Item | Trigger | Where it lives | Effort |
|---|---|---|---|
| Set `EMAIL_UNSUB_SIGNING_KEY` on Railway | Before first real email send | `openssl rand -hex 32` → Railway env var | 1 min |
| Set `CAN_SPAM_ADDRESS` on Railway | Before the daily signal-alert cron first fires with any active subscriber (signal-alert email body interpolates this string — sharper trigger than the original "scaling past ~100 marketing users") | Railway env var, plain text address | 1 min |
| Ship Stage 8 v0 Phase C — `/account/saved/[id]` route | Before `SIGNAL_ALERTS_ENABLED=true` lets the cron actually dispatch an email. The all-scope unsub message in `apps/api/app/api/routes/email.py:184` tells users to "Re-enable per-strategy from /account/saved" — that route is Phase C work. Ship Phase C before the first signal email goes out or the link 404s. | Phase C frontend (`SignalPanel`, `SignalIntroModal`) | ~4-6h |
| `POSTHOG_API_KEY` + `NEXT_PUBLIC_POSTHOG_KEY` | When ready to collect analytics | Railway (backend) + Vercel (frontend) | 5 min |
| `RESEND_API_KEY` | When ready to send welcome email | Railway env var; safe no-op until set | 1 min |
| Verify `GATING_ENABLED=true` was intentional | Now (one-off) | Railway env var; confirmed 2026-05-21 ✓ | done |

---

## 3. Git / branch hygiene

| Item | Why it's here | Disposition |
|---|---|---|
| Stale `railway/fix-deploy-b1c14b` on remote | Auto-PR from Railway, merged but not deleted | Delete: `gh api -X DELETE repos/grepJimmyGu/the_counselor/git/refs/heads/railway/fix-deploy-b1c14b` |
| Stale `railway/fix-deploy-bce8d1` on remote | Same | Same |
| `codex/improve-chat-builder` branch (local worktree) | Codex agent's parallel chat-builder work from May 19-20 (Episode 17), never merged | Decide: merge, rebase + merge, or close. Likely superseded by [build_specs/research_chat_v2.md](../build_specs/research_chat_v2.md) — review before discarding. |
| Dormant `the_counselor-signals-v0` worktree | Phase A landed via PR #83; Phase B (PR #88) moved to `-signals-v0-phase-b`. The original worktree is no longer referenced by any session. | `git worktree remove ../the_counselor-signals-v0 --force` once PR #88 lands. |

---

## 4. Open product decisions

| Decision | Context | Status |
|---|---|---|
| Chat v2 (Research Partner) | [`build_specs/research_chat_v2.md`](../build_specs/research_chat_v2.md), 660 lines, Year-1 proposal | Awaiting go/no-go. Phasing in §6 — 3 phases × ~4 weeks. Untracked file; will need to be committed before Phase 1 starts. |
| PRD-05 `not_supported` strategy handling | Strategy parser returns `not_supported` when LLM can't map the request to a backend strategy type. UX redirect TBD. | Low priority, in discussion. No Stage equivalent yet. |
| Drop `robustness_jobs.user_id` zombie column | Schema drift item #10 above | Schedule when convenient; not urgent. |
| Live commodity spot prices on `/commodities/[symbol]` | Page displays $/oz, $/bbl (commodity spot units). FMP `useLiveQuotes` returns ETF share prices (GLD, USO, COPX, WEAT) — different scale. Overriding `spotPrice` with the ETF quote re-introduces the WTI $133 vs $83 bug fixed earlier. Deferred 2026-05-21 after the live-quote rollout. | Skip until a live commodity-spot data source exists (Alpha Vantage commodity API, FMP futures plan, or a backend conversion factor). Option B from the rollout — supplementary "ETF proxy: $X ▲%" chip alongside the spot — is still available if visual freshness becomes more important than data fidelity. |

---

## 4b. Market Pulse v2 — Phase 1 status

The Market Pulse v2 redesign shipped to `/stocks` via PRs #56–60, then
the four real-data sub-phases shipped 2026-05-22 (PRs #61–62, #64–65).
Phase 1 is essentially done — only 1g and the LLM prompt rewrite remain.

| Sub-phase | Scope | Status | PR |
|---|---|---|---|
| ✅ **1a** | Promote v2 → /stocks | shipped | #56 |
| ✅ **1b** | LLM narrative service | shipped | #57 |
| ✅ **1b-extra** | Real index values via FMP `^DJI`/`^IXIC`/`^GSPC`/`^RUT` | shipped | #58 |
| ✅ **decimal-fix** | Sentence-splitter regression | shipped | #59 |
| ✅ **2-col layout** | MarketBrief narrative on left, takeaways on right | shipped | #60 |
| ✅ **1c** | Real macro signals — CPI YoY + 10Y Treasury via AV; mock Growth + Stress pending FRED key | shipped | #61 |
| ✅ **1d** | Real sector ETF-vs-SPY comparison series in the click-expansion chart | shipped | #62 |
| ✅ **1e** | History Rhymes backend (`macro_similarity_service.py` — cosine over 5y of 5d return vectors across 6 macro ETFs) | shipped | #64 |
| ✅ **1f** | Screener preset filter logic — 9 presets, real counts + tier gating via 402 envelope | shipped | #65 |
| 🚧 **LLM prompt rewrite** | Replace generic system prompt with Jimmy-provided financial-news-summary prompt | ~30 min | **Waiting on Jimmy to share the prompt** (2026-05-22) |
| ⏳ **1g (new)** | Top news sidebar in MarketBrief right column (replaces the temporary 2-col layout that just shows watch_items there) | ~4-5h backend + ~1-2h frontend | Per 2026-05-22 feedback. Backend: news service (use `market-news-analyst` skill pattern OR extend PRD-09 sentiment provider). Frontend: 4-6 news headlines, refreshed hourly, linked to source. |

### Follow-ups from the 1c–1f ship

| Item | Trigger | Effort |
|---|---|---|
| Set `FRED_API_KEY` on Railway → swap Growth (ISM Services PMI) + Stress (HY OAS) macro signals to real FRED data | When you want to drop the last two `Mock` pills in the Macro Pulse table | 1 min env var + ~2h backend (FRED client + signal builders) |
| Replace `positive-catalyst` curated basket with news-sentiment query | When PRD-09 sentiment coverage is dense enough to be a useful screen | ~2-3h |
| Replace `community-confirmed` curated basket with vote/watchlist rollup query | When community engagement hits scale | ~2-3h |
| Replace `rising-attention` curated basket with real volume_ratio across the stocks universe | Backend addition; small | ~3-4h |

---

## 5. Engineering debt

| Item | Source | Effort | Trigger |
|---|---|---|---|
| Frontend lint debt (26 errors across 22 files) | [DEFERRED.md](DEFERRED.md) | ~1-2h batch | When touching one of the affected files for a real feature |
| Sentiment pre-warmer background job (Top-100 S&P 500 every 3h via APScheduler) | Was a "low" priority in WORK_LOG.md | ~2h | When sentiment dashboards show staleness in user-facing pages |
| Market snapshot staleness bug | `fix/market-snapshot-staleness` branch (does it still exist?) | Unknown | Low priority |
| Remove diagnostic console.log in `research-workspace.tsx` | PR #7 cleanup | done in PR #9 ✓ | — |
| Postgres migration smoke test in CI for Stage 4/5/6 tables | DEFERRED.md | ~30 min | Stage 4 OR 5 OR 6 production deploy regresses |
| HTML-escape user-controlled strings in email templates | `apps/api/app/emails/welcome.py` and `apps/api/app/emails/signal_alert.py` interpolate `user.display_name` and `saved_strategy.title` directly into the HTML body. Risk is bounded (modern mail clients sanitize XSS) but a malicious title could break layout. Surfaced by PR #88 master-merger review. | ~30 min for `html.escape()` wrappers, or systemic when the React Email migration happens | When template count grows past ~5 OR any rendered-email regression report |

---

## 6. Pending external dependencies

| Item | Blocking on | Effort once unblocked |
|---|---|---|
| Reddit API credentials (`REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET`) | Reddit approval (applied; awaiting response) | 1 min env var set on Railway |

---

## 7. Traffic-gated work (links only)

The full **~30 items** in [`docs/DEFERRED.md`](DEFERRED.md) are deferred
because they need real user traffic to validate. Don't duplicate the
list here. Top-of-list watchers — the moment any of these tripwire
log lines fires, the corresponding item moves from DEFERRED.md to this
file's relevant section:

```bash
railway logs --service the_counselor | grep -E "DEFERRED_TRIGGER|gate_event|email_noop"
```

Most-likely next trigger: `trial_day_7_email` (first user enters a 14-day
trial). When it fires, the corresponding email template moves out of
DEFERRED.md.

---

## Discipline notes

**Why one drift = one decision = one deploy.**
A single big ALTER transaction couples N independent risks. If the
timestamp-tz conversion (#3, #4) has a bug — and it has the most
surface area — it rolls back the safe varchar widening (#2) too. Each
fix wants its own commit + test + production deploy so blame is
isolated when something unexpected happens. The exception is items #8
and #9 (pure model edits, no DB touch) which can ship together; they
trivially can't fail in a way that requires rolling back the other.

**Why this doc exists at all.**
WORK_LOG.md describes "what we're doing now"; DEFERRED.md catalogs the
cut-from-stage items gated on traffic; KNOWN_ISSUES.md is the
post-mortem ledger. This doc is the catch-all for everything else that's
outstanding — schema drift, env vars, branch cleanup, pending
decisions — so it's never "where did I file that again?"

**How to grow this doc.**
When a new item surfaces in a session and isn't immediately actioned:
add a row here, link any context, optionally open a GitHub issue. When
the item ships: delete the row. The doc should always answer "what's
the open list?" in under a minute of scanning.
