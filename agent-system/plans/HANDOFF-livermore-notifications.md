# HANDOFF: Livermore Notifications & Execution Guidance — Sprint A

> **You are a coding agent (Claude Code, Codex, or human). Read this doc first.** It is the entry point for the notification/execution-guidance build. After reading this (~5 minutes), `CLAUDE.md` is auto-loaded for branch/PR conventions; then pick your assigned PRD and start.

**Sprint window**: 3–4 weeks for Sprint A; Sprint B and Sprint C follow if/when scheduled.
**Total scope (Sprint A)**: 1 PRD — **PRD-19 (Phase B re-shape)**. Sprint B and Sprint C are queued as PRD-20/21 and will get their own PRDs when scheduled.
**Sprint goal**: Un-pause and re-shape Phase B (the P0 notification work originally shipped in PR #88, reverted in PR #101, paused in PR #107) with the additions called out in the notification framework doc — throttling layer, daily digest as default, "Mark as executed" loop, settings page, in-app banner.

---

## 1. TL;DR

The Livermore notification system needs to do one job well: **once a user adopts a saved strategy, tell them when something changes and help them act on it — without firing too often.** The framework doc (`/Quant Strategy/framework/livermore_notification_framework.html`) defines six trigger types across four channels. Sprint A ships the two P0 triggers (signal change + daily digest) over the two P0 channels (email + in-app banner), plus the settings page and "Mark as executed" loop.

Most of the foundation already exists in main (3 signal-related DB tables, helper utilities in `signal_service.py`, signal routes, frontend opt-in CTA). PR #88's original cron + email dispatch was reverted (PR #101) and the re-apply was paused (PR #107). **Sprint A re-shapes that work with the corrections the original PR was missing.**

The single retention metric this sprint instruments: **time from notification sent → user clicks "Mark as executed"**.

---

## 2. The four design principles (load-bearing)

Every PRD in this packet enforces these. They are the SAME four principles as the product flow v2 HANDOFF — kept identical on purpose so an agent moving between the product flow work and the notification work doesn't have to context-switch.

### Principle 1 — Reuse, don't replicate

Sprint A must not add: a new database table for signal state (already exists), a new signal-event model (already exists), a new subscription model (already exists), a new email-sending infra (existing emails use the same SMTP path), a new auth pattern, a new entitlement gate. All of those exist in main.

Novel work is: the throttling engine, the dispatcher abstraction, the two email templates (signal change + daily digest), the in-app banner, the settings page, the Mark-as-executed endpoint + button.

### Principle 2 — LEGO bricks

Every new component, hook, or service is either a **brick** (reusable across triggers/channels) or a **composer** (wires bricks for one trigger only).

PRD-19 creates these bricks that Sprint B and Sprint C will plug into:
- `NotificationThrottle` (per-strategy and per-user caps)
- `ChannelDispatcher` protocol with `EmailDispatcher` and `InAppDispatcher` impls
- `<NotificationBanner>` brick on Home/Builders
- `<NotificationSettingsForm>` brick
- `<MarkAsExecutedButton>` brick
- "Not investment advice" footer component (reused in every email template)

Brick inventory lives in §5 of this doc and is updated at PR close.

### Principle 3 — Mode = a `FlowDefinition` (where applicable)

PRD-19's Mark-as-Executed UI is a tiny flow — open from notification → confirm execution → record timestamp. If the implementation grows beyond ~3 user-visible steps, declare it as a `FlowDefinition` per PRD-13a's runtime; otherwise the existing strategy detail page is sufficient. (Default: don't over-engineer — Mark-as-Executed is currently a single click + toast, not a flow.)

### Principle 4 — UX consistency + sub-300ms perceived load

- **Centralized labels** via `useFlowCopy('notifications', key)`. Every label in the settings page, banner, and email templates comes from the same lexicon.
- **Skeleton states for all blocking calls > 200ms.**
- **Optimistic UI** for Mark-as-Executed: button updates immediately; API confirms in background; revert + toast on failure.
- **Email rendering tested in 3 clients minimum** (Gmail web, Outlook web, Apple Mail). The framework doc's mockup IS the design target.

---

## 3. Reading order (for a coding agent fresh to this work)

1. **`CLAUDE.md`** (repo root) — auto-loaded. Branch/PR/Python-3.9 conventions.
2. **`agent-system/PARALLEL_WORK.md`** — claim a row in the Active Sessions table.
3. **This file** — sprint plan + the four principles.
4. **`/Quant Strategy/framework/livermore_notification_framework.html`** — the design source. Read §1 (decision tree), §2 (info architecture for the trigger you're implementing), §4 (channel IA + throttling rules), §5 (mockups).
5. **PRD #88 commit (`9eeb3a9 feat(signals-v0): Phase B`)** — read this commit's diff to see what was originally tried, then reverted in PR #101.
6. **PR #107 commit (`814dd31 docs(backlog): pause Signals v0 Phase B re-apply for future reshape`)** — read this to understand WHY the re-apply was paused.
7. **Your assigned PRD** — `agent-system/plans/PRD-19-phase-b-reshape.md`.

---

## 4. The Sprint A PRD

| PRD | Title | Status | Owner | Effort | Depends on |
|-----|-------|--------|-------|--------|------------|
| **PRD-19** | Phase B re-shape — P0 signal change + daily digest + Mark-as-executed + settings | ✅ [Ready](PRD-19-phase-b-reshape.md) | TBD | ~3–4 weeks | None on the notification side (Phase A models already shipped). Soft dep: PRD-11 (Home page redesign) shouldn't conflict with the in-app banner; coordinate via PARALLEL_WORK.md. |

### Sprint B + Sprint C preview (not in this packet)

- **PRD-20 (Sprint B, ~2 weeks)** — performance milestone + maintenance review + per-user cadence + timezone prefs. Depends on PRD-19's dispatcher + throttle bricks.
- **PRD-21 (Sprint C, ~3 weeks)** — web push (PWA) + webhook dispatcher (Pro tier) + regime monitor + educational nudge library. Depends on PRD-19's dispatcher abstraction being shipped.

Don't write PRD-20/21 yet — wait until PRD-19 lands and we know the dispatcher API is solid in production.

---

## 5. Shared infra inventory (living document)

Bricks created across notification PRDs. Each PRD updates this section at PR close. Read this before writing new code — if the brick exists, reuse it.

### Backend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `SignalEvent`, `SignalAlertSubscription`, `SavedStrategySignalState` models | Phase A (PR #83) | ✅ | All notification triggers |
| `signal_service.classify_change`, `signals_equal`, `_basket_tickers` helpers | Phase A (PR #83) | ✅ | Cron compute job |
| `GET / POST / DELETE /api/signals/{strategy_id}/*` routes | Phase A (PR #83) | ✅ | Frontend opt-in CTA |
| Cron `compute_current_signal` job | PRD-19 | ⏳ | Re-applies paused PR #88 with throttling baked in |
| `NotificationThrottle` engine (per-strategy + per-user caps) | PRD-19 | ⏳ | Every trigger; PRD-20/21 reuse |
| `ChannelDispatcher` protocol | PRD-19 | ⏳ | Email + in-app initially; push + webhook later |
| `EmailDispatcher` (uses existing SMTP infra) | PRD-19 | ⏳ | Signal change + daily digest emails |
| `InAppDispatcher` (writes `NotificationBannerEntry`) | PRD-19 | ⏳ | Banner widget |
| Daily-digest composer + cron | PRD-19 | ⏳ | Daily digest trigger |
| `POST /api/strategies/{slug}/mark-executed` endpoint | PRD-19 | ⏳ | Mark-as-executed button; retention metric |
| `GET/PUT /api/me/notification-preferences` endpoint | PRD-19 | ⏳ | Settings page |
| Milestone detector job | PRD-20 | ⏳ | Performance milestone trigger |
| Maintenance reviewer job | PRD-20 | ⏳ | Maintenance review trigger |
| `PushDispatcher` (web push) | PRD-21 | ⏳ | Push trigger (Pro tier) |
| `WebhookDispatcher` (HMAC + retry) | PRD-21 | ⏳ | Webhook trigger (Pro tier) |

### Frontend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| Existing frontend opt-in CTA on save | PR #91 | ✅ | Subscription enrollment |
| `<NotificationBanner>` (lives on Home + Strategy Builders) | PRD-19 | ⏳ | Signal change + milestone in-app surface |
| `<MarkAsExecutedButton>` brick | PRD-19 | ⏳ | Strategy detail page; clickable from in-app and email-deep-link |
| `<NotificationSettingsForm>` brick | PRD-19 | ⏳ | `/account/notifications` page |
| `<NotInvestmentAdviceFooter>` brick | PRD-19 | ⏳ | All email templates; reused in PRD-20/21 |
| Email templates: `signal_change.html`, `daily_digest.html` | PRD-19 | ⏳ | Email channel |
| Email templates: `milestone.html`, `maintenance.html` | PRD-20 | ⏳ | Sprint B |
| Email template: `regime_anomaly.html`, `educational_nudge.html` | PRD-21 | ⏳ | Sprint C |
| PWA service worker for web push | PRD-21 | ⏳ | Push channel |

---

## 6. Common pitfalls (read this before your first commit)

These bit prior PRs. Don't let them bite yours.

### A. PR #88 fired too often

The original Phase B (PR #88) fired one email per signal change with no throttling. On a day where a multi-strategy user had two rebalances + a regime flip, they got 3 emails — past the alert-fatigue threshold. PR #107's pause note specifically called this out.

**The fix in PRD-19**: throttling engine is the *first* PR to land, before any email template ships. Per-strategy daily cap = 1; per-user daily cap across all triggers = 3.

### B. PR #88 didn't have "Mark as Executed"

The original Phase B shipped emails but had no way to measure whether they led to action. With no engagement signal, we couldn't tell which alerts worked and which didn't.

**The fix in PRD-19**: Mark-as-Executed lands in the same PR as the signal-change email. The button is on the strategy detail page and reachable from a deep-link in the email. Latency from sent → click is the retention metric (see §7).

### C. Stacked PRs lose backend CI

`.github/workflows/backend-ci.yml` only fires on `pull_request.branches: [main]`. A PR stacked on another branch gets no backend tests. **Always rebase your PR onto current `main` and set `base=main` before opening.** Full discussion in `CLAUDE.md` §"Stacked PRs lose backend CI".

### D. `X | None` syntax

CI runs on Python 3.9 even though Railway runs 3.13. Use `Optional[X]` not `X | None`. Grep your diff before pushing. This pattern bit PR #88's original Phase B (a follow-up commit had to rewrite all `| None` to `Optional[X]`).

### E. Compliance language is non-negotiable

Every email subject line: no "buy" or "sell" verbs. Subject previews are visible in the inbox and look like recommendations to regulators. Use "signal", "rebalance", "rotation", "alert".

Every email body: "Not investment advice" footer. CAN-SPAM-compliant one-click unsubscribe. These aren't optional and they're not a polish item — they ship in the first email template.

### F. Don't run `git add -A`

Explicit pathspecs only. The parallel-work setup means stray files from other agents can land in your commit. Run `git status --short` immediately before every `git add`.

### G. Coordinate with PRD-11 (Home page redesign) on banner placement

PRD-11 owns the Home page redesign. PRD-19 adds a `<NotificationBanner>` at the top of the Home page (above the entry-mode picker for signed-in users with pending alerts). If both PRDs are in flight, they share `apps/web/src/app/page.tsx`. **Claim the row in PARALLEL_WORK.md first**; if PRD-11 is already in progress, coordinate via comments on its PR before pushing.

---

## 7. The retention metric to watch

**"Time from notification sent → user clicks Mark-as-executed"**.

This is the single number Sprint A makes measurable. If it's short and rising over time, the notification loop works. If long or declining, either alerts aren't trusted (information architecture problem) or aren't actionable (signal quality problem). It's the cleanest health signal we can instrument without integrating with brokers.

The framework doc's Section 6 calls this out as the load-bearing metric; PRD-19 instruments it via:
1. Stamping every notification with a `sent_at` timestamp (already in `SignalEvent.created_at` schema).
2. Adding `POST /api/strategies/{slug}/mark-executed` that writes a `MarkAsExecutedEvent` row with the timestamp.
3. PostHog event `notification_executed` with computed latency.

After 4 weeks of data, we'll know if the median latency is under 24 hours (healthy) or over a week (broken loop).

---

## 8. When in doubt

- **Architecture question** → check §2 (four principles) and PRD-19's "Design Constraints" block. If still unclear, comment on the PR.
- **Branch / PR procedure** → `CLAUDE.md` (auto-loaded).
- **Brick already exists?** → check §5 of this doc.
- **What did PR #88 do that we're avoiding?** → check §6 above + `git show 9eeb3a9` diff.
- **Module already shipped?** → check the framework doc's §6 inventory.
- **Anything else** → escalate to Jimmy.

---

## 9. Final pre-flight checklist

Before you write your first line of code:

- [ ] You've read this doc end-to-end.
- [ ] `CLAUDE.md` auto-loaded (Claude Code) or you've read it manually (other agents).
- [ ] You've read `/Quant Strategy/framework/livermore_notification_framework.html` §§1, 2, 4, 5.
- [ ] You've git-shown PR #88 (`9eeb3a9`) and PR #107 (`814dd31`) to understand the prior attempt.
- [ ] You've claimed your row in `agent-system/PARALLEL_WORK.md` Active Sessions.
- [ ] You've spun up a worktree (`git worktree add ../the_counselor-<tag> -b <branch> main`).
- [ ] You've checked whether PRD-11 (Home redesign) is in flight — if yes, coordinate banner placement before pushing.

If all seven are checked, start. If any are unchecked, fix that first.

---

*Sprint A plan drafted 2026-05-26. Cross-reference: source design doc at `/Quant Strategy/framework/livermore_notification_framework.html`. Updates to this handoff doc require updating PRD-19's "Reading order" section to stay in sync.*
