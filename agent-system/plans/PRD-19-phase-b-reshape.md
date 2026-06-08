# PRD-19: Phase B Re-shape — P0 Notifications & Execution Guidance

**Status**: Ready to build
**Phase**: Sprint A (notifications)
**Depends on**:
- **None on the notification side.** Phase A models (`SignalEvent`, `SignalAlertSubscription`, `SavedStrategySignalState`) and helper utilities (`signal_service.classify_change`) are already on `main`.
- **Soft dep on PRD-11** (Home page redesign) — both touch `apps/web/src/app/page.tsx`. If PRD-11 is in flight, coordinate banner placement via its PR; otherwise this PRD adds the banner first and PRD-11 builds around it.
- **Anti-dep on Phase B's original implementation** — `signal_alert.py` and `signal_jobs.py` were reverted by PR #101 and re-apply paused by PR #107. This PRD **does NOT** re-introduce that code as-is; it re-implements with the corrections in §6 of the notification framework doc.

**Blocks**: PRD-20 (Sprint B — milestone + maintenance) and PRD-21 (Sprint C — push + webhook) consume PRD-19's `ChannelDispatcher` protocol and `NotificationThrottle` engine.

**Effort**: 3–4 weeks, single owner (or 2 owners working backend/frontend in parallel)
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/livermore_notification_framework.html`](../../Quant%20Strategy/framework/livermore_notification_framework.html) — §1 decision tree (triggers 1 & 2 are P0), §2 per-trigger flows, §4 channel IA + throttling rules, §5 Surface 1, 2, 3, 5, 6 mockups

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded). Then read agent-system/plans/HANDOFF-livermore-notifications.md.

Goal: Re-shape Phase B (originally PR #88, reverted PR #101, paused PR #107)
with the corrections the original PR was missing — throttling layer, daily
digest as default, "Mark as executed" loop, settings page, in-app banner.

The two P0 triggers shipped by this PRD:

  1. Signal change — when a saved strategy's cron-computed signal flips.
     Email + in-app banner + (optional) Mark-as-Executed click.

  2. Daily digest — 9am ET summary across all of a user's saved strategies.
     Email only. Skipped on silent days.

PREREQUISITES (must be on main before starting):
  - Phase A models: SignalEvent, SignalAlertSubscription,
    SavedStrategySignalState. All shipped via PR #83. ✅
  - Phase A helpers: signal_service.{classify_change, signals_equal}. ✅
  - Phase A routes: GET/POST/DELETE /api/signals/{strategy_id}/*. ✅

OUT OF SCOPE for this PRD:
  - Milestone + maintenance triggers (Sprint B, PRD-20)
  - Web push + webhook dispatchers (Sprint C, PRD-21)
  - Regime/anomaly + educational nudge triggers (Sprint C, PRD-21)
  - Multi-channel orchestration beyond email + in-app (Sprint C adds push/webhook)
  - Per-user cadence customization beyond "daily/weekly digest" toggle (deferred)
  - Mark-as-Executed audit / reporting dashboard (PostHog event is enough for v1)

CRITICAL CONSTRAINT: do NOT re-introduce the PR #88 code as-is. PR #88 was
reverted because it had no throttling. The throttling engine in this PRD is
the FIRST thing to land — write it + tests, merge to your branch, THEN add
the cron job + email template on top.

Architecture rules (the four principles, see HANDOFF §2):
  1. Reuse — three signal models + helpers are on main; consume them.
  2. LEGO bricks — ChannelDispatcher protocol is the foundation Sprint B/C
     plug into. Don't shortcut it.
  3. FlowDefinition (where applicable) — Mark-as-Executed is a single-click
     button, not a flow. Don't over-engineer.
  4. UX rules — useFlowCopy('notifications', key) for all labels; <300ms
     perceived load with skeletons; optimistic UI for Mark-as-Executed.

Acceptance: the "Acceptance Checklist" section at the bottom of this PRD,
fully ticked. Branch as `<your-agent-name>/feat/phase-b-reshape`. Open one
PR; base=main. Do NOT split into stacked PRs.
```

---

## Design Constraints (the four principles)

Same four principles as the product flow v2 HANDOFF and the notification HANDOFF. Re-stated here so the agent doesn't have to cross-reference mid-implementation.

### 1. Reuse, don't replicate

The codebase already has:
- 3 signal-related tables (don't add a fourth)
- `signal_service.classify_change` and friends (don't reimplement)
- Existing SMTP path for transactional emails (use it)
- Existing PostHog `capture` (use it for analytics)
- Existing `useEntitlements` hook for tier gating (use it)
- Existing `Skeleton`, `Button`, `Card`, `Badge` UI primitives (use them)
- Existing `ChatWidget` `openChatWidget` pattern (mirror it for `<NotificationBanner>`)

The genuinely novel work is: throttling engine, dispatcher protocol, two email templates, daily-digest composer, in-app banner, Mark-as-Executed endpoint + button, notification settings page.

### 2. LEGO bricks

`ChannelDispatcher` is the bedrock brick that PRD-20 + PRD-21 will plug into. Get the protocol right; the implementations are secondary.

```python
class ChannelDispatcher(Protocol):
    name: str  # 'email' | 'in_app' | 'push' | 'webhook'

    async def dispatch(
        self,
        user: User,
        notification: Notification,
        idempotency_key: str,  # for retry-safe redelivery
    ) -> DispatchResult:
        ...
```

If a future channel needs different fields (e.g., webhook needs HMAC signing), extend the protocol with optional fields; don't fork the bricks.

### 3. Mode = `FlowDefinition` (where applicable)

Mark-as-Executed is **not** a flow. It's a single button → POST → toast. No need to define a `FlowDefinition`. Same for the Settings page — it's a form, not a multi-step flow.

If a future PRD adds a "Trade execution wizard" that walks the user through copying trade lists, placing orders, and confirming each — that becomes a `FlowDefinition` per PRD-13a's runtime.

### 4. UX consistency + sub-300ms perceived load

- **`useFlowCopy('notifications', key)`** for every label in: banner, settings form, email templates' English text (templates are server-side rendered; the lexicon is shared with frontend).
- **Skeleton** on the settings page while preferences load. **Optimistic update** when the user toggles a setting.
- **Optimistic UI** for Mark-as-Executed: button updates immediately; API confirms in background; revert + error toast on failure.
- **Email rendering tested in 3 clients minimum**: Gmail web, Outlook web, Apple Mail. Send a test email to a dedicated test account during PR review.

---

## Problem

The notification framework doc identified six trigger types across four channels. Today, Livermore has the Phase A foundation (3 tables, helpers, routes, opt-in CTA) but **no cron that actually fires notifications**.

Phase B (PR #88) tried to ship the cron + email but had two structural flaws:
1. **No throttling** — fired one email per signal change with no per-strategy or per-user caps, which research and our own intuition both flag as the #1 alert-fatigue killer.
2. **No engagement signal** — emails were one-way; we couldn't measure whether they led to action. Without that signal, we couldn't tell what was working.

PR #101 reverted the implementation. PR #107 paused the re-apply pending design work — which the notification framework doc now provides.

**This PRD ships the corrected Phase B.** Two P0 triggers (signal change + daily digest), two P0 channels (email + in-app banner), a settings page, and the Mark-as-Executed loop. Sprint B and Sprint C add the rest.

## Goals

1. **Cron `compute_current_signal` job runs end-of-day** and detects changes against `SavedStrategySignalState`.
2. **Throttling engine** caps per-strategy (1/day) and per-user (3/day across all triggers).
3. **Signal change email** rendered with all 8 info-architecture fields from notification framework §2 trigger 1.
4. **Daily digest email** at 9 AM ET (user timezone-aware), skipped on silent days.
5. **In-app banner** on Home + Strategy Builders shows pending signals; clickable into strategy detail.
6. **Mark-as-Executed endpoint + button** instruments the retention metric.
7. **Notification settings page** at `/account/notifications` with per-trigger × per-channel toggles.
8. **Compliance hygiene**: every email has "Not investment advice" footer, one-click unsubscribe, no buy/sell verbs in subject lines.

## Non-Goals

- **No web push channel** (Sprint C / PRD-21).
- **No webhook channel** (Sprint C / PRD-21).
- **No milestone or maintenance triggers** (Sprint B / PRD-20).
- **No regime/anomaly or educational nudge triggers** (Sprint C / PRD-21).
- **No broker integration** — Livermore doesn't execute trades. Ever.
- **No Mark-as-Executed admin dashboard** — PostHog event is enough for v1.
- **No timezone-aware cadence beyond digest hour** — user picks digest hour, that's it. Per-trigger cadence customization is a v2 polish.
- **No SMS** — adds telecom integration complexity and regulatory load; defer to v3 at earliest.
- **No emails to anonymous (non-logged-in) users** — all notifications require an authenticated `User` with a verified email.

## User stories

1. **As Jimmy (signed-in user with 5 saved strategies)**, I want to get a single morning email at 9 AM ET that tells me which of my strategies need attention today, so I can read 30 seconds and decide whether to dig in.
2. **As Jimmy**, I want a real-time email the moment one of my strategies changes signal, so I can act before market close — but I want at most one such email per strategy per day, even if the strategy fires multiple sub-rules.
3. **As Jimmy**, when I land on Home, I want to see a colored banner if any of my strategies have pending signals so I don't have to remember to check email.
4. **As Jimmy**, when I open a strategy from a notification, I want to see a clear "I executed this" button so I can log that I acted on the signal.
5. **As Jimmy**, I want a settings page where I can choose which triggers fire on which channels, so I can tune the notification volume to my tolerance.
6. **As any user receiving emails**, I want a one-click unsubscribe link that actually unsubscribes me from the relevant trigger, not just hides emails in spam.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│ CRON JOBS (apps/api/app/jobs/signal_jobs.py)                           │
│                                                                        │
│   nightly_compute_signals_job  (runs after market close)              │
│     ├─ For each SavedStrategy with active subscription:                │
│     │   1. Compute current signal (BacktestEngine or signal_service)  │
│     │   2. classify_change vs cached SavedStrategySignalState         │
│     │   3. If changed: write SignalEvent + dispatch                    │
│     │                                                                  │
│   daily_digest_job  (runs 9 AM in each user's timezone)               │
│     └─ For each user with digest enabled:                              │
│         1. Compose per-user digest from today's SignalEvents          │
│         2. If no changes AND user picked "silent days skip": skip     │
│         3. Else: dispatch via EmailDispatcher                          │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ THROTTLING ENGINE (apps/api/app/services/notification_throttle.py)     │
│                                                                        │
│   check_and_record(user_id, strategy_id, channel, trigger_type)       │
│     ├─ Per-strategy daily cap: 1 signal-change per strategy per day   │
│     ├─ Per-user daily cap: 3 across all triggers                       │
│     ├─ Returns: (allowed: bool, reason: str)                           │
│     └─ Backed by Redis (or a small `notification_throttle` table)      │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ CHANNEL DISPATCHER (apps/api/app/services/notification_dispatcher.py)  │
│                                                                        │
│   class ChannelDispatcher(Protocol): dispatch(user, notification, key) │
│                                                                        │
│   ┌──────────────────────┐         ┌──────────────────────┐            │
│   │ EmailDispatcher       │         │ InAppDispatcher       │           │
│   │ (existing SMTP)       │         │ (writes BannerEntry)  │           │
│   └──────────────────────┘         └──────────────────────┘            │
│                                                                        │
│   PushDispatcher and WebhookDispatcher land in PRD-21.                 │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ USER SURFACES                                                          │
│                                                                        │
│   1. Inbox: signal_change.html + daily_digest.html email templates    │
│   2. Home page banner (<NotificationBanner /> brick)                  │
│   3. Strategy detail: <MarkAsExecutedButton /> brick                  │
│   4. Settings: /account/notifications page                             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Backend changes

### 1. New service: `NotificationThrottle`

`apps/api/app/services/notification_throttle.py` (new file)

Per-strategy and per-user rate-limiting. **Lands first**, before any cron job.

```python
class NotificationThrottle:
    """Per-strategy and per-user notification rate limits.

    The #1 cause of alert fatigue. Caps:
      - 1 signal-change notification per (user, strategy) per day
      - 3 notifications total per user per day across all triggers + channels

    Backed by Redis if available; falls back to a small `notification_throttle`
    table for environments without Redis.

    The 'key' for throttling is (user_id, strategy_id, channel, trigger_type).
    Same notification on same day = throttled. Different channel = NOT
    throttled (so email + in-app for the same event both fire).
    """

    async def check_and_record(
        self,
        user_id: str,
        strategy_id: Optional[str],   # None for triggers that aren't strategy-scoped (e.g. digest)
        channel: str,                  # 'email' | 'in_app' | 'push' | 'webhook'
        trigger_type: str,             # 'signal_change' | 'digest' | 'milestone' | ...
    ) -> ThrottleResult: ...
```

**Decision: Redis or DB-backed?**

- Use Redis if `REDIS_URL` env var is set (matches `live_quote_service.py` pattern).
- Otherwise fall back to a new `notification_throttle` table (small; auto-purged via TTL job).
- Either way, the API surface is identical from the dispatcher's perspective.

### 2. New service: `ChannelDispatcher` + `EmailDispatcher` + `InAppDispatcher`

`apps/api/app/services/notification_dispatcher.py` (new file)

```python
class ChannelDispatcher(Protocol):
    name: str

    async def dispatch(
        self,
        user: User,
        notification: Notification,
        idempotency_key: str,
    ) -> DispatchResult: ...


class EmailDispatcher(ChannelDispatcher):
    """Renders the trigger's email template + sends via existing SMTP."""
    name = "email"

class InAppDispatcher(ChannelDispatcher):
    """Writes a BannerEntry row consumed by <NotificationBanner /> frontend."""
    name = "in_app"


# Registry
def get_dispatcher(name: str) -> ChannelDispatcher: ...
```

`Notification` is a Pydantic model carrying the trigger type, payload, and rendered fields.

`DispatchResult` carries success/failure + error message (for retry / logging).

### 3. New table: `notification_banner_entry`

`apps/api/app/models/notification_banner_entry.py` (new file)

For the in-app banner. Cron writes here when `InAppDispatcher.dispatch` fires.

```python
class NotificationBannerEntry(Base):
    __tablename__ = "notification_banner_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(32))  # 'signal_change' | 'milestone' | ...
    saved_strategy_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(280))
    body: Mapped[str] = mapped_column(String(560))
    action_url: Mapped[str] = mapped_column(String(500))    # deep link target
    severity: Mapped[str] = mapped_column(String(16))       # 'info' | 'warning' | 'success'
    is_dismissed: Mapped[bool] = mapped_column(default=False)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

### 4. New table: `mark_as_executed_event` (or reuse `SignalEvent`?)

**Decision: new table.** `SignalEvent` is system-emitted; `MarkAsExecutedEvent` is user-emitted. Mixing them muddles the schema. Both reference `signal_event_id` so we can compute "time from notification to action."

```python
class MarkAsExecutedEvent(Base):
    __tablename__ = "mark_as_executed_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    signal_event_id: Mapped[str] = mapped_column(String(36), ForeignKey("signal_events.id"))
    executed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    # Optional free-text note from user ("filled at 4:05 ET via Schwab")
    user_note: Mapped[Optional[str]] = mapped_column(String(560), nullable=True)
```

### 5. New endpoint: `POST /api/strategies/{slug}/mark-executed`

`apps/api/app/api/routes/saved_strategies.py` (extend existing)

```python
@router.post("/{slug}/mark-executed")
async def mark_executed(
    slug: str,
    payload: MarkAsExecutedRequest,
    user: User = Depends(get_current_user),
) -> MarkAsExecutedResponse:
    # 1. Resolve strategy + verify ownership
    # 2. Find latest SignalEvent for this strategy
    # 3. Write MarkAsExecutedEvent
    # 4. PostHog capture('notification_executed', { latency_seconds, strategy_type, ... })
    # 5. Return {ok: true, latency_seconds: ...}
```

### 6. New endpoint: `GET/PUT /api/me/notification-preferences`

`apps/api/app/api/routes/me.py` (extend existing)

```python
class NotificationPreferences(BaseModel):
    digest_enabled: bool = True
    digest_hour_utc: int = 13  # 9am ET ≈ 13 UTC; user-overridable
    digest_skip_silent_days: bool = True
    triggers: dict[str, list[str]]  # trigger_type -> list of enabled channels
    # e.g. { "signal_change": ["email", "in_app"], "milestone": ["in_app"] }

@router.get("/notification-preferences")
async def get_preferences(user = Depends(get_current_user)) -> NotificationPreferences: ...

@router.put("/notification-preferences")
async def update_preferences(payload: NotificationPreferences, user = Depends(get_current_user)) -> NotificationPreferences: ...
```

Stored in a new column on `users` table OR in a separate `user_notification_preferences` table — implementer's call; new table is cleaner if we plan to add more pref fields in PRD-20/21.

### 7. Cron jobs

`apps/api/app/jobs/signal_jobs.py` (new file — recreating what PR #88 deleted)

```python
async def nightly_compute_signals_job():
    """Runs after market close (e.g. 5pm ET).

    For each SavedStrategy with at least one active SignalAlertSubscription:
      1. Compute current signal via BacktestEngine (using latest end-of-day data)
      2. classify_change vs cached SavedStrategySignalState
      3. If changed:
         a. Write SignalEvent row
         b. Update SavedStrategySignalState
         c. For each subscription (user, channel):
            - throttle.check_and_record(user, strategy, channel, 'signal_change')
            - if allowed: dispatcher.dispatch(user, notification, idempotency_key)
    """

async def daily_digest_job():
    """Runs every hour; for each user whose digest_hour_utc == current hour,
    compose and send their daily digest.

    Skip if:
      - User has digest_enabled = False
      - No SignalEvents in last 24h AND digest_skip_silent_days = True
    """
```

Cron registration: extend `apps/api/app/jobs/__init__.py` or whatever scheduling pattern exists (likely APScheduler).

### 8. Email templates

`apps/api/app/emails/signal_change.html` (new file)
`apps/api/app/emails/daily_digest.html` (new file)

Renders the framework doc's Surface 1 and Surface 2 mockups. Use Jinja2 (existing pattern in `apps/api/app/emails/welcome.py`).

### 9. Test plan

`apps/api/tests/`

- `test_notification_throttle.py` — per-strategy cap, per-user cap, multi-channel non-collision
- `test_channel_dispatcher.py` — registry lookup, EmailDispatcher mock SMTP, InAppDispatcher writes BannerEntry
- `test_nightly_compute_signals.py` — synthetic strategy fixture, signal change detection, dispatcher invocation
- `test_daily_digest_job.py` — silent-day skip, multi-strategy digest composition
- `test_mark_as_executed.py` — ownership check, latency computation, PostHog event
- `test_notification_preferences.py` — GET/PUT round-trip, default values

---

## Frontend changes

### 1. New bricks

`apps/web/src/components/notifications/notification-banner.tsx`

```tsx
export function NotificationBanner() {
  // Fetches GET /api/notification-banner-entries (active, not dismissed)
  // Renders 1-3 most recent in colored pill format (matches Surface 3 mockup)
  // Each entry links to its action_url (typically strategy detail page)
  // Dismiss button → PATCH /api/notification-banner-entries/{id}/dismiss
  // Skeleton state while loading; null when nothing pending
}
```

`apps/web/src/components/notifications/mark-as-executed-button.tsx`

```tsx
export function MarkAsExecutedButton({ strategySlug, signalEventId }: Props) {
  // Optimistic: click → state changes immediately → POST in background
  // On success: toast "Recorded — thanks for the feedback"
  // On failure: revert + error toast
  // Disabled if user already marked this signal as executed
}
```

`apps/web/src/components/notifications/notification-settings-form.tsx`

```tsx
export function NotificationSettingsForm() {
  // Lives on /account/notifications page
  // Fetches GET /api/me/notification-preferences
  // 6-row grid: trigger × {email, in_app, push, webhook} toggles
  // Save button (or auto-save on toggle) → PUT
  // Optimistic update on toggle; revert on API failure
}
```

`apps/web/src/components/notifications/not-investment-advice-footer.tsx`

```tsx
export function NotInvestmentAdviceFooter() {
  // Standardized footer used in every email template
  // Renders both: server-side (in Jinja templates) and client-side (in
  // notification settings preview)
  // Plain text version available for accessibility
}
```

### 2. Home page surgery

`apps/web/src/app/page.tsx`

Add `<NotificationBanner />` at the top (above PRD-11's entry-mode picker for signed-in users). **Coordinate with PRD-11 owner** if both are in flight.

### 3. Strategy detail page extension

`apps/web/src/app/strategies/[slug]/page.tsx`

Add the `<MarkAsExecutedButton />` to the Execute panel (per Surface 6 mockup in framework doc).

### 4. New page

`apps/web/src/app/account/notifications/page.tsx` (new file)

Renders `<NotificationSettingsForm />`. Server Component for the page wrapper; the form is a Client Component.

### 5. Test plan

- `apps/web/src/components/notifications/__tests__/notification-banner.test.tsx`
- `apps/web/src/components/notifications/__tests__/mark-as-executed-button.test.tsx`
- `apps/web/src/components/notifications/__tests__/notification-settings-form.test.tsx`
- E2E: `e2e/notification-banner.spec.ts` — banner appears for user with pending signal; click navigates to strategy detail; Mark-as-Executed button records and updates UI.

### 6. Manual email testing

During PR review, send each template to a test account and verify rendering in:
- Gmail web
- Outlook web
- Apple Mail (macOS or iOS)

Document any rendering quirks in the PR description. (Email-client rendering is the #1 source of post-merge bugs in transactional-email PRs.)

---

## Reusable LEGO bricks created by this PRD

### Backend

| Brick | Path | Used by |
|---|---|---|
| `NotificationThrottle.check_and_record` | `services/notification_throttle.py` | This PRD; PRD-20, PRD-21 |
| `ChannelDispatcher` protocol | `services/notification_dispatcher.py` | This PRD; PRD-20, PRD-21 |
| `EmailDispatcher` | `services/notification_dispatcher.py` | Every email-sending trigger |
| `InAppDispatcher` | `services/notification_dispatcher.py` | Every banner-eligible trigger |
| `NotificationBannerEntry` table | `models/notification_banner_entry.py` | Banner-eligible triggers across all PRDs |
| `MarkAsExecutedEvent` table | `models/mark_as_executed_event.py` | Retention metric; future Execute-related features |
| `POST /api/strategies/{slug}/mark-executed` | `api/routes/saved_strategies.py` | Mark-as-Executed button + (future) admin reporting |
| `GET/PUT /api/me/notification-preferences` | `api/routes/me.py` | Settings form + (future) onboarding-based defaults |
| `nightly_compute_signals_job`, `daily_digest_job` | `jobs/signal_jobs.py` | This PRD; new triggers add new cron functions but reuse the throttle + dispatcher |
| Email templates (Jinja): `signal_change.html`, `daily_digest.html` | `emails/` | This PRD; future PRDs add `milestone.html`, `maintenance.html`, etc. |

### Frontend

| Brick | Path | Used by |
|---|---|---|
| `<NotificationBanner>` | `components/notifications/notification-banner.tsx` | Home, Strategy Builders; future re-engagement modals |
| `<MarkAsExecutedButton>` | `components/notifications/mark-as-executed-button.tsx` | Strategy detail; future order-confirmation surfaces |
| `<NotificationSettingsForm>` | `components/notifications/notification-settings-form.tsx` | `/account/notifications`; future onboarding-flow setting steps |
| `<NotInvestmentAdviceFooter>` | `components/notifications/not-investment-advice-footer.tsx` | Every email template; future legal-required surfaces |
| `useFlowCopy('notifications', key)` lexicon | `lib/flows/copy.ts` (extended) | All notification UI |

---

## Acceptance checklist

A PR is accepted when **all of the following are true**. Claude Code should self-verify against this list before opening the PR.

### Backend

- [ ] `NotificationThrottle` service implemented; throttle table OR Redis backing in place; per-strategy and per-user caps tested.
- [ ] `ChannelDispatcher` protocol defined; `EmailDispatcher` and `InAppDispatcher` implementations shipped.
- [ ] `NotificationBannerEntry` model + migration added.
- [ ] `MarkAsExecutedEvent` model + migration added.
- [ ] `POST /api/strategies/{slug}/mark-executed` endpoint live; ownership check enforced; PostHog event captured with `latency_seconds`.
- [ ] `GET/PUT /api/me/notification-preferences` endpoint live; defaults applied for users without preferences set.
- [ ] `nightly_compute_signals_job` registered in scheduler; idempotent (safe to re-run).
- [ ] `daily_digest_job` registered; respects user timezone + silent-day skip.
- [ ] `signal_change.html` and `daily_digest.html` Jinja templates exist.
- [ ] Both templates include `NotInvestmentAdviceFooter` content + one-click unsubscribe link.
- [ ] Subject lines pass the "no buy/sell verbs" lint (a CI grep check is a nice-to-have but not required for this PR).
- [ ] No `X | None` syntax (Python 3.9 compat).
- [ ] All 6 new backend tests pass: throttle, dispatcher, nightly compute, digest, mark-executed, preferences.
- [ ] Full backend suite passes: `cd apps/api && python3 -m pytest -q`.

### Frontend

- [ ] `<NotificationBanner>` brick exists; fetches active entries; dismissible; renders Surface 3 mockup.
- [ ] `<MarkAsExecutedButton>` brick exists; optimistic UI; renders on strategy detail page.
- [ ] `<NotificationSettingsForm>` brick exists; renders 6-row trigger × channel toggles.
- [ ] `<NotInvestmentAdviceFooter>` brick exists; matches the footer in `signal_change.html` email template.
- [ ] `/account/notifications` route renders the settings form.
- [ ] Home page adds `<NotificationBanner>` above the entry-mode picker (coordinate with PRD-11 if in flight).
- [ ] Strategy detail page adds `<MarkAsExecutedButton>` to the Execute panel.
- [ ] All 3 frontend unit tests pass: banner, button, settings form.
- [ ] 1 Playwright E2E test passes: banner-to-mark-executed loop.
- [ ] `cd apps/web && npm run build` clean.
- [ ] `cd apps/web && npm run test` green.

### Compliance

- [ ] Every email template has "Not investment advice" footer.
- [ ] Every email template has CAN-SPAM-compliant one-click unsubscribe link.
- [ ] No "buy" or "sell" verbs in email subject lines.
- [ ] Mark-as-Executed event is user-attested only (not a Livermore claim of trade placement).
- [ ] Numeric claims in emails sourced to the originating `SignalEvent` row (auditable provenance).

### Manual smoke

- [ ] Send `signal_change.html` to a test account; renders correctly in Gmail web, Outlook web, Apple Mail.
- [ ] Send `daily_digest.html` to a test account; same.
- [ ] Trigger a synthetic signal change on a test strategy; verify email sent, banner appears, Mark-as-Executed records.
- [ ] Test throttling: trigger 2 signal changes for the same strategy on the same day → only 1 email.
- [ ] Test silent-day skip: user with digest enabled but no SignalEvents in 24h → no digest email.

### Telemetry

- [ ] PostHog events: `notification_dispatched` (with `trigger_type`, `channel`), `notification_throttled` (with `reason`), `notification_executed` (with `latency_seconds`).

### Documentation

- [ ] Update HANDOFF-livermore-notifications.md §5 Brick inventory: mark all PRD-19 bricks as ✅.
- [ ] Update `agent-system/WORK_LOG.md` with the PR summary.
- [ ] PR title: `feat(notifications): Phase B re-shape — signal change + digest + mark-as-executed (PRD-19)`.

---

## Out of scope (do not build in this PRD)

- **Performance milestone trigger** → PRD-20.
- **Maintenance review trigger** → PRD-20.
- **Per-user cadence customization** (weekly vs daily, timezone offsets beyond digest hour) → PRD-20.
- **Web push channel** → PRD-21.
- **Webhook channel** → PRD-21.
- **Regime / anomaly trigger** → PRD-21.
- **Educational nudge trigger** → PRD-21.
- **SMS channel** → never (regulatory + cost overhead not worth it).
- **Mark-as-Executed admin reporting dashboard** → maybe in PRD-22; for now the PostHog event is enough.
- **Auto-execute / broker integration** → never; Livermore is signal-only.

---

## Why this is one PRD, not a split

PRD-13 was split into 13a (runtime) + 13b (portfolio) because the runtime was a foundation other PRDs (PRD-11, etc.) needed independently. **The notification work isn't like that.** The throttle + dispatcher are foundation, but no other PRD needs them before PRD-19 ships in full. Splitting would just add coordination overhead.

If you find PRD-19 is too big to land as one PR, the natural split is **backend (services + cron + endpoints + email templates)** ahead of **frontend (banner + settings + Mark-as-Executed UI)**. But ship them in the same week — a half-shipped notification system (cron firing emails without a settings page) is worse than no notifications.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_notification_framework.html` §§ 1, 2, 4, 5
- Sprint plan: `agent-system/plans/HANDOFF-livermore-notifications.md`
- PR #88 commit (`9eeb3a9`): the original Phase B implementation — reference for what was tried.
- PR #101 commit (`d1c6c1a`): the revert — reference for what to avoid.
- PR #107 commit (`814dd31`): the pause — read this to understand why this re-shape is needed.
- Phase A models + helpers: `apps/api/app/models/{signal_event,saved_strategy_signal_state,signal_alert_subscription}.py`, `apps/api/app/services/signal_service.py`
- Existing frontend opt-in CTA: PR #91 — already on `main`.
- Repo conventions: `CLAUDE.md` (auto-loaded), `agent-system/PARALLEL_WORK.md`
- Related PRDs: PRD-11 (Home page — coordinate banner placement), PRD-20 (Sprint B — consumes throttle + dispatcher), PRD-21 (Sprint C — adds push + webhook dispatchers)

---

*Drafted 2026-05-26. PRD-19 is the corrected Phase B — re-shapes what PR #88 tried with the throttling layer + Mark-as-Executed loop that the original was missing. Sprint B (PRD-20) and Sprint C (PRD-21) get their own PRDs when scheduled; they will plug into the bricks this PRD ships.*
