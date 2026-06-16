# PRD-23c: Market Screener — Discover → Track + Intraday

**Status**: Ready to build (pending Jimmy's review of the packet)
**Phase**: Market Screener mode (PRD-23 packet) — phase 3 of 3
**Depends on** (on `main`): PRD-23a (snapshot + scan), PRD-23b (the "Save + track" handoff), PRD-19/16c (the notification dispatcher + active-execution cron + live dashboard).
**Blocks**: —
**Effort**: ~1 week, single owner.
**Owner**: TBD
**Read first**: `HANDOFF-livermore-market-screener.md`.

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md +
apps/api/CLAUDE.md (auto-loaded), then HANDOFF-livermore-market-screener.md.

Goal: close the screener loop — let a user SAVE a discovered screen and get notified
when NEW names enter the basket, and add the intraday snapshot option. Two parts:

  1. Discover -> track: a saved screen becomes a SavedStrategy (rule + universe_id).
     The active-execution cron re-runs the scan on its cadence; when a NEW symbol
     enters the matched basket, dispatch the existing PRD-19 notification
     (SignalEvent + dispatcher + digest). Point the live dashboard's universe-watch
     panel at the saved screen.

  2. Intraday snapshot: warm a resolution='intraday' signal_snapshot on the PRD-16c
     intraday cadence (the FMP ~15-min-delayed path) so the screen can run during
     market hours. Daily already shipped in 23a; this is the option.

REUSE everything — PRD-19's dispatcher + SignalEvent, PRD-16c's intraday bars +
monitor cron + universe-watch panel. Add no new notification stack.

PREREQUISITES (on main): PRD-23a, PRD-23b, PRD-19/16c.

OUT OF SCOPE: net-new primitives (frozen at ~72); options/short-interest data.

DEFINITION OF DONE: see §6.
```

---

## 1. The problem

After 23a/b a user can *discover* a basket, but the value compounds when the screen keeps watching the market for them. This PRD turns a one-time scan into a standing screen: save it, and get pinged when a new name starts reading the same thing — and make the screen runnable intraday, not just at the close.

---

## 2. Design constraints

1. **Reuse the notification + active-execution stack** (Principle 1). A saved screen is a `SavedStrategy`; new-entrant alerts go through PRD-19's `SignalEvent` + dispatcher + digest. No new email/notification machinery.
2. **New-entrant semantics.** Notify only when a symbol is in today's matched basket and was NOT in the previous run's basket (a *transition into* the basket), not every day it stays in. Mirror the EVENT "fires on transition" discipline.
3. **Intraday reuses PRD-16c.** The intraday snapshot warms off the same FMP ~15-min-delayed intraday path (the source the PRD-16c monitor already uses). `resolution='intraday'` rows in `signal_snapshot`.
4. **Owner-gated.** The saved-screen dashboard + alerts are owner-scoped (don't leak a non-owner into owner-only loads — the existing dashboard owner-gate follow-up applies).
5. **No fabricated data; event-loop-safe cron** (same as 23a).

---

## 3. Implementation

### 3.1 Save a screen → `SavedStrategy`

The 23b "Save + track" CTA persists the composed rule + `universe_id` as a `SavedStrategy` (reuse the existing two-table model). The screen's "universe" is the chosen `universe_id` (resolved at run time), not a frozen symbol list — so the basket can gain/lose names as the market moves.

### 3.2 Cron re-scan + new-entrant notify

Extend the active-execution cron (or add a sibling job) to, per saved screen: resolve the universe → scan against the latest snapshot → diff today's matched basket vs the previous run's persisted basket → for each **new entrant**, dispatch a PRD-19 `SignalEvent` ("NVDA just entered your '<screen name>' screen") through the existing dispatcher + digest. Persist the current basket for the next diff.

### 3.3 Dashboard

Point the live dashboard's universe-watch panel (PRD-16c-6) at the saved screen — it already renders "which names in the universe are triggering." The saved-screen detail shows the current basket + the entrant/exit history.

### 3.4 Intraday snapshot

A `resolution='intraday'` warm path on the PRD-16c intraday cadence (FMP ~15-min-delayed). The scan service already keys on `resolution`; passing `resolution='intraday'` runs the screen against intraday values during market hours. Gate intraday screening behind the appropriate tier.

---

## 4. Testing

- Save → `SavedStrategy` round-trips the rule + `universe_id`.
- New-entrant diff: a symbol entering the basket fires exactly one `SignalEvent`; staying in fires none; re-entering after an exit fires again.
- Dispatch reuses PRD-19 (mock the dispatcher; assert the `SignalEvent` shape).
- Intraday snapshot: `resolution='intraday'` rows written off the intraday path; scan with `resolution='intraday'` reads them.
- Owner-gate: a non-owner cannot load the saved-screen dashboard.
- No-regression: full suite green; event-loop-safe cron audit.

---

## 5. Pre-merge checklist

1. `cd apps/api && python3 -m pytest -q` + `cd apps/web && npm run build` — green.
2. Static-import smoke (new job/route resolves).
3. Event-loop-safe cron (`_run_async_in_thread`; no shared asyncio primitives).
4. Env-var audit (intraday source already wired via PRD-16c/202).
5. Branch follows `claude/feat/prd-23c-screener-track-intraday`.

---

## 6. Definition of done

- [ ] Save a screen → `SavedStrategy` (rule + `universe_id`)
- [ ] Cron re-scans + dispatches a PRD-19 notification on each NEW basket entrant (transition-only)
- [ ] Saved-screen dashboard reuses the universe-watch panel; owner-gated
- [ ] Intraday snapshot (`resolution='intraday'`) on the PRD-16c cadence; tier-gated
- [ ] Tests per §4; no-regression green
- [ ] PR merged to `main` with green CI; brick inventory (HANDOFF §5) updated; the Market Screener packet marked complete

---

## 7. Hand-off / future (post-packet)

- **Saved screens as a library** — discovered baskets become shareable, like published strategies.
- **More universes** — Nasdaq-100, custom lists, multi-asset (once non-equity universes are defined).
- **Resume PRD-22b's deferred families** — each new primitive is now a small additive PR that immediately widens what's screenable (the better feedback loop the catalog freeze was for).

---

*PRD drafted 2026-06-16. Part of the Market Screener packet (`HANDOFF-livermore-market-screener.md`). Supersedes §3.7–3.8 of the single-doc draft.*
