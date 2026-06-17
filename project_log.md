# Project Log — Livermore (谋士)

## Overview
Natural-language investment strategy research tool. Users describe trading strategies conversationally; the backend converts them to validated JSON, runs a deterministic backtest, and returns explanation + critical review layers.

**Stack:** FastAPI (Python) + PostgreSQL + Next.js (TypeScript)
**Deployment:** Railway (backend) + Vercel (frontend)

---

## 2026-06-11 — active-execution-v2 (track real holdings) + Custom Mode reachability + the live intraday chart (#187 → #197)

A single long session. Started by answering "if I toggle execution on, what actually happens?" and ended with a usable live dashboard — including a price chart — plus a full data-source diagnosis that reframed the remaining work.

| PR | Scope |
|---|---|
| #187 | active-execution-v2 PR1 — cron **detects + notifies**, never auto-mutates (compliance: Livermore never simulates a fill) |
| #188 | PR2 — **declare a position you hold** (endpoint + UI); entry_price = the user's real cost basis |
| #189 | PR3 — **confirm-and-decrement**: user executes in their own brokerage, confirms, shares decrement |
| #190 | hotfix — pin `.python-version` to 3.13.13 (Railway `mise` couldn't build the just-published 3.13.14) |
| #191 | **the bridge** — an active-execution save now also creates the `SavedStrategy` the dashboard/cron key on; cron re-scoped to `PositionState WHERE is_open` (cost scales with open positions, not total saves) |
| #192 | **"My Strategies" repo** (`/account/strategies` + `/[id]` dashboard) + killed the post-save dead-end (explicit "View my strategies →" link) |
| #193 | persistent **nav entries** — account dropdown "My Strategies" + clickable home-tile heading (works in the empty state too) |
| #194 | composer **exit-ladder guard** — block "non-daily + no ladder" before save (the silent dead-end). Spawned as a background task, reviewed + merged |
| #195 | **live intraday chart** — owner-gated `/intraday-chart` endpoint + recharts component (price line + tier lines + trigger markers) |
| #196 | chart **ET axis** — normalize bars (naive ET) and events (naive UTC) to one ET-aware basis so markers align; format axis in `America/New_York` |
| #197 | **session-aware axis** — index-based x (collapse closed-market gaps), ET date+time tick labels, trigger dots snap to nearest bar |

### The architectural gap this closed
Composer **Save** wrote a `BacktestRecord` (slug-based, public); the entire active-execution system (cron, dashboard, declare/confirm) keys on the **`SavedStrategy`** table. They never connected. #191's bridge wires them: a non-daily save **with a non-empty exit ladder** now creates both. #192–#194 made that reachable + un-foot-gunnable from the UI.

### Operational: the missing-strategy incident + backfill
A real user (`jimmygu220@gmail.com`) reported a saved 15min strategy that never appeared in My Strategies. Live-DB diagnosis: **0 SavedStrategy rows** — all 9 saves predated the #191 bridge deploy, and only one (15min + 3-tier ladder) qualified. Authorized, previewed, then ran a one-row idempotent backfill (all-users scope; only that row qualified). The 5min strategies in the user's screenshots had **no exit ladder** → not active-execution by design.

### The data-freshness finding (reframes the open work)
The dashboard's "No recent bar" + ~1-day-stale chart is **not** our cron/cache — it faithfully serves what AlphaVantage returns. Direct API test with the prod key: `entitlement=realtime` and `entitlement=delayed` are **both rejected** — the key is **not entitled to real-time or 15-min-delayed US equities** (AV's general "premium" raises rate limits; realtime is a separate entitlement). Market Pulse looks live because it uses a **different provider** (FMP `/stable/quote`, daily granularity). Confirmed **FMP also serves intraday** (`/stable/historical-chart/15min` returned today's bars, minutes-fresh). **Decision (Mr Gu): don't swap now** — the chart honestly labels stale data; the FMP-intraday switch is the clean future fix.

**Verification:** every PR's full CI green before merge (CodeQL ×4 + Postgres smoke + Vercel); backend chart/route suites + frontend active-exec/account suites green throughout; `tsc` clean each time.

---

## 2026-06-09 (late) — PRD-16c (intraday + active execution) complete + Custom Mode end-to-end wired in 10 sequential PRs (#171 → #180)

Same continuous session as the PRD-16a + PRD-16b closeouts below. After Mr Gu directed "finish PRD-16 entirely," the full PRD-16c was shipped across 8 slices, then a UX audit revealed two reachability gaps (no Home tile + no dashboard render) and 2 more PRs closed them.

| Slice | PR | Scope | New tests |
|---|---|---|---|
| 16c-1 | #171 | `IntradayBarService` + `intraday_bars` cache + AV `fetch_intraday_bars` | +12 backend |
| 16c-2 | #172 | Engine `bar_resolution=…` parameter + `ExitTier` schema + multi-tier ladder evaluator | +22 backend |
| 16c-3a | #173 | `PositionState` ORM + migration + FK + compound index | +8 backend |
| 16c-3b | #174 | `monitor_active_positions` cron + per-position throttle | +13 backend |
| 16c-3c | #175 | 3 owner-only dashboard endpoints (universe-state / positions / trade-log) | +14 backend |
| 16c-4 | #176 | `render_position_event` single-renderer template + catalog `resolution=["daily","intraday"]` whitelist | +24 backend |
| 16c-5 | #177 | `<BarResolutionPicker>` + `<ExitLadderEditor>` + canvas wiring | +19 frontend |
| 16c-6 | #178 | `<UniverseWatchPanel>` + `<PositionCardsGrid>` + `<TradeLogTable>` + composition wrapper | +11 frontend |
| UX-1 | #179 | Replaced Chat-builder tile → **Build from scratch** + extended `custom_build_mode` chain + Run-backtest CTA | +1 net (test rewrites) |
| UX-2 | #180 | `/api/strategies/{slug}` exposes `saved_strategy_id` so dashboard renders on strategy detail | +4 backend |

Cumulative: **1334 → 1431 backend tests**, **151 → 182 frontend tests**, 0 regressions on the 22 existing strategy_types across the entire 10-PR run.

### Architecture decisions worth recording

**`exit_ladder` is engine-evaluated, not cron-only.** Backtests of intraday strategies with a multi-tier ladder produce equity curves that already account for the ladder firing. The `_apply_exit_ladder` post-processor runs between `_generate_weights` and the returns computation — tracks entry price per symbol, fires each tier AT MOST ONCE per entry, scales weight cumulatively on `sell_fraction`, zeros forward on `sell_all`, resets state when the strategy itself closes a position. This means the user gets one consistent picture: the backtest result and the live execution path obey the same exit rules.

**Cron uses `IntradayBarService`, NOT `live_quote_service` (trap #22).** The monitor cron runs on APScheduler's worker thread with its own event loop. `live_quote_service` is a module-level singleton that caches `asyncio.Lock` instances bound to whichever loop touches them first. Using it from the cron would either (a) race the main loop to bind the lock and then RuntimeError on user requests, or (b) leave the locks wedged after an early-return exception. `IntradayBarService` is pure SQLAlchemy + httpx with no asyncio primitives — safe to use from any loop. This is a permanent architectural rule for any background task that touches market-data services.

**The slug ↔ UUID bridge is one optional field.** PRD-16c-3c dashboard endpoints are owner-only on the SavedStrategy UUID, but the strategy-detail page surfaces a public BacktestRecord by slug. Rather than building a parallel `/saved-strategies/[id]` page, #180 added a single `Optional[str] = None` field on `SavedStrategyResponse` that looks up `SavedStrategy.id WHERE backtest_record_id = record.id`. Frontend conditional render: `data.saved_strategy_id && bar_resolution !== "daily" && <ActiveExecutionDashboard strategyId={...} />`. Non-owners hitting the dashboard polls 404 → the brick's built-in error state. No leakage. No new page.

**Single-renderer email template instead of three files.** `render_position_event` handles `stop_hit / tp1_hit / tp2_hit` (plus unknown trigger names via fallback) through a `_TRIGGER_META` table. Same visual style across all three, no copy drift, future tier names render with neutral copy until promoted to the table. Mirrors `signal_change.py`'s shape exactly so PR-19's ChannelDispatcher integration is mechanical (deferred — trade_log is the DB source of truth today).

**Editorial intraday whitelist on the catalog.** `_INTRADAY_ELIGIBLE_IDS` in `signal_primitives.py` is a deliberate frozenset of ~35 ids, not a `data_source == "price"` auto-classifier. Each id is in the set because (a) the provider works on intraday bars without semantic change AND (b) the signal is useful at that timescale. KAMA and SAR are mechanically eligible but tuned for daily — left out. Fundamentals + sentiment + cross-sectional rankings stay daily-only by intent. Tests verify the whitelist + the "daily always first in resolution list" invariant that keeps PRD-16a-1's ETag cache stable.

### Reachability audit caught two gaps before they shipped

The 8 backend + frontend slices were technically complete after #178. A user-experience audit before declaring it done found two reachability gaps that the per-slice tests wouldn't have caught:

1. **No Home tile for Custom Mode.** The `<EntryModePicker>` shipped three CTAs (Pick asset / Upload portfolio / Chat builder) — Custom Build wasn't one of them. The flow definition's `triggers` array referenced `"strategy_builders/custom_build_cta"` but no component called `startFlow("custom_build_mode", …)` anywhere in the codebase. The only way to reach the composer was typing `/flow/custom_build_mode` into the URL bar.

2. **`<ActiveExecutionDashboard>` not wired into any page.** The brick + its tests existed; nothing imported it.

PR #179 closed (1) — and along the way replaced the dead-end `compose_signals → null` terminal step with a proper chain (`compose_signals → backtest → review → save`) reusing the mode-agnostic `<FlowBacktest>` / `<FlowReview>` / `<FlowSave>` bricks that `one_asset_mode` already uses. The canvas got an explicit "Run backtest →" CTA that synthesizes the StrategyJson and advances the flow.

PR #180 closed (2) by exposing the slug ↔ UUID bridge described above.

The pattern lesson: **per-slice tests verify the brick renders; end-to-end audit verifies a user can actually reach it.** Same principle from PRD-19 Step 5/6 ("the banner deep-links to the settings page, so a 2-PR stack would require typed-route casts only to remove them"). When the work crosses many bricks, the integration layer between them is its own surface area.

### Custom Mode packet — complete

Three PRDs, eight months of design, ten PRs in one continuous session, end-to-end usable. User journey:

```
Home → "Build from scratch" tile
     ↓
/flow/custom_build_mode (canvas)
     ↓ pick primitives + thresholds + (optional) active execution + ladder
     ↓ click "Run backtest →"
FlowBacktest → FlowReview → FlowSave
     ↓
/strategies/{slug} (public detail page)
     ↓ if intraday strategy:
<ActiveExecutionDashboard>
     ↓ polls every 30s while open
intraday monitor cron → mutates PositionState → dashboard reflects
```

PRD-19 (notifications) + PRD-16a (catalog) + PRD-16b (composer) + PRD-16c (intraday + active execution) all on main. Operational follow-ups in WORK_LOG.md "Current Session" → "Operational follow-ups."

---

## 2026-06-09 (evening, continued) — PRD-16b (Custom Build composer) complete in three sequential PRs (#167 → #168 → #169)

Same continuous session as the PRD-16a closeout below. Three slices, all base=main:

| Slice | PR | Scope | New tests |
|---|---|---|---|
| 16b-1 | #167 | Backend `StrategyRule` additive fields (`primitive_id`, `primitive_params`, `logic_with_prior`) + `custom_build` strategy_type + `_evaluate_custom_build_block` engine path + backwards-compat tests | +18 backend |
| 16b-2 | #168 | `<CustomBuildCanvas>` + `<CustomBuildRuleCard>` + `<CustomBuildRuleComposer>` + `<CustomBuildActiveExecutionScaffold>` (pitfall B) + `custom_build_mode` FlowDefinition | +15 frontend |
| 16b-3 | #169 | `buildCustomBuildStrategyJson` converter + `applyTemplateThresholdsToRules` + symbol picker + canvas "Use these defaults" wiring | +15 frontend |

Cumulative: **1334 backend tests** (was 1316), **151 frontend tests** (was 121), **0 regressions** on 22 existing strategy types (pitfall C verified).

### Architecture decisions worth recording

**The synchronous-engine constraint.** PRD-16a-2's `SignalProvider` impls are async (they fetch price data via `PriceDataService.get_price_frame`). The backtest engine is synchronous. For v1, `_compute_primitive_on_close_matrix` calls `TechnicalSignalProvider._compute` directly with a frame synthesized from the close_matrix (close-only; OHLCV approximated). AV-endpoint primitives explicitly raise — out of scope for v1's synchronous engine. Test `test_av_endpoint_primitive_raises_in_custom_build_v1` pins the documented limitation.

**First-rule contract has a UX consequence.** When the user removes the first rule, the new `rules[0]` must have its `logic_with_prior` cleared to null. The canvas's `removeRule` handles this. Tested.

**Lenient threshold-key mapper.** `applyTemplateThresholdsToRules` doesn't strictly enumerate which keys are threshold-shaped — it uses a regex (`enter_*` / `exit_*` / `upper` / `lower` / `threshold` / `min` / `max` / `strong_buy` / `positive` / `breakout` / `trending`). The lenience is intentional: PRD-16a-3's per-template metadata is editorial copy, and a strict mapper would couple this code to copy choices in another file. First match wins for the threshold; other keys become `primitive_params`.

### Cross-cutting trap surfaced

**Test pollution via `getByText` ambiguity.** Initial canvas tests used `screen.getByText("rsi")` to wait for the catalog to render — but the SignalPrimitiveCard renders the primitive name in both the catalog browser and the (newly added) rule card on the right. Switched to `screen.getByTestId("primitive-card-rsi")` for unambiguous waits. Same lesson as earlier in the session: prefer test IDs over text matchers when the same string appears in multiple surfaces.

### PRD-16b status: complete

PRD-16c (intraday + active execution) remains in the packet. PRD-19 (notifications) + PRD-16a (catalog) + PRD-16b (composer) — all three prerequisites — are now on main.

---

## 2026-06-09 (very late) — PRD-16a (Signal Library) complete in four sequential PRs (#161 → #163 → #164 → #165)

Same continuous session as the PRD-19 closeout below. After Mr Gu queued the Custom Mode 3-PRD packet in PROJECT_BACKLOG (#159) and landed the spec docs in git (#160), we executed PRD-16a end-to-end in four sequential slices, each base=main, no stacked PRs.

### What landed

| Slice | PR | Scope | New tests |
|---|---|---|---|
| 16a-1 | #161 | Schema + 55-entry hand-authored catalog + `GET /api/signal-primitives` with ETag | +297 backend |
| 16a-2 | #163 | 46 new `SignalProvider` impls (38 local pandas + 8 AV-endpoint + 4 stubs + 1 placeholder) + `GET /preview` endpoint | +63 backend |
| 16a-3 | #164 | KB matcher service + 19-template metadata + `POST /api/signal-combos/match-templates` | +72 backend |
| 16a-4 | #165 | 4 frontend bricks + localStorage cache + types + standalone `/signal-library` page | +22 frontend |

Cumulative: **1316 backend tests** (was 884), **121 frontend tests** (was 99), **114 routes** (was 111), 0 regressions, 0 outages.

### Architecture decisions worth recording

**Lazy registry registration to avoid circular imports.** `technical_signal_providers.py` imports `SignalProvider` from `signal_provider.py`. If `signal_provider.py` tried to import + register the technical providers at module-top, we'd get a partial-init `ImportError`. Solution: `_ensure_technical_providers_registered()` is called on the first `get_signal_provider()` lookup, with a module-level flag short-circuiting subsequent calls. Tests trigger it via the new `all_registered_provider_names()` helper.

**Hand-authored catalog is the editorial product.** The 55 primitive descriptions are intentionally **not LLM-generated free text**. The voice rule — descriptive ("Measures overbought/oversold extremes…") not prescriptive ("Buy when RSI < 30") — is enforced by `test_no_prescriptive_language_in_description`, which fails CI on word-list matches like `buy when` / `sell when` / `enter when`. PR review is the editorial gate; the test is the safety net.

**Two-layer test-pollution fix for the preview endpoint.** `Depends(get_db)` fires real `SessionLocal()` in TestClient. Override via `app.dependency_overrides[get_db]` to short-circuit the dep. But the registry instantiates providers at module load, so an import-level patch of `PriceDataService` never reaches them — instead, `patch.object(PriceDataService, "get_price_frame", fake_get)` at the class level so already-constructed instances pick up the stub.

**Standalone `/signal-library` page** ships for marketing/SEO and pre-composer browsing. The composer (PRD-16b) will wrap `<SignalCatalogBrowser>` with its own `onPick` callback; standalone mode passes no callback and clicks no-op.

### Cross-cutting traps surfaced

- **Python 3.9 `str | None` syntax** — same trap as PRD-19 Step 3a's `ph_capture` import error a few hours earlier. Caught pre-commit by the static-import smoke test (pre-push #6).
- **Merge-conflict-rebase scenario** — PR #162 was opened from a branch carrying the pre-squash 16a-1 commit (`d81c767`); main had the squashed version (`ab761aa`). CLAUDE.md "Force-push blocked by classifier → fresh-branch rebase" recipe applied verbatim: cherry-pick onto a fresh branch, close #162, open #163. Third or fourth time this codebase has used this pattern.
- **recharts Tooltip formatter generic constraint** — annotating `(v: number | string)` violates the `Formatter<ValueType, NameType>` constraint; letting TS infer compiles.

### PRD-16a status: complete

PRD-16b (composer UI + multi-rule fold) + PRD-16c (intraday + active execution) remain in the packet. Specs already in `agent-system/plans/`; PRD-16a's bricks are reusable verbatim. PRD-16c blocks on PRD-16b + PRD-19 (done).

---

## 2026-06-09 (late) — PRD-19 frontend: closing the loop in one PR (PR #157)

Same session as the backend complete entry below — the natural follow-up. Step 5 + Step 6 bundled into one PR because the banner's overflow counter deep-links to `/account/notifications` (Step 6 territory); a 2-PR stack would have needed `as Route` casts to remove in the follow-up.

### What landed

Four new frontend bricks under `apps/web/src/components/notifications/`:

| Brick | Purpose |
|---|---|
| `NotificationBanner` | Polls `GET /api/me/notifications/pending` every 60s; renders amber-pill rows with inline `MarkAsExecutedButton`. Auto-hides for anonymous. |
| `MarkAsExecutedButton` | `POST /api/saved-strategies/{id}/mark-executed` with optimistic UI. Idempotent re-clicks render "Already marked at HH:MM" (backed by Step 3a's UNIQUE index). |
| `NotInvestmentAdviceFooter` | Reusable disclaimer; full + compact variants; copy mirrors the server-rendered footers in `signal_change.py` + `daily_digest.py`. |
| `NotificationSettingsForm` | `GET/PATCH /api/me/email-preferences` with optimistic toggles for the 3 PRD-19 flags + the legacy Stage 6a 3 (collapsed). |

Integration: `<NotificationBanner />` above PRD-11's entry-mode picker on Home; new `/account/notifications` page sibling to `/account/email` (both target the same endpoint).

### The interesting decision: where to put MarkAsExecutedButton

The PRD spec originally said "Strategy detail page — Execute panel." But `/strategies/[slug]` serves **legacy `BacktestRecord`** rows (slug-based) while the mark-executed endpoint takes **`SavedStrategy.id`** (new table). Two different ID surfaces. Threading both through would have required either a slug-to-id resolver call on page load or denormalizing `SavedStrategy.id` onto the BacktestRecord — both ugly.

Cleaner: inline the button directly on each banner row. The banner's `strategy_slug` field actually carries `SavedStrategy.id` per Step 3b's `dispatch_in_app_banner` (the field name is historical baggage). The retention loop closes without ever touching the legacy detail page. Same UX; better architecture.

### Numbers

- **Backend tests**: unchanged at 884 (frontend-only PR).
- **Frontend tests**: 75 → **99** (+24 component tests across 4 test files).
- Vitest suite green; `npm run build` clean.
- Next 16 typed routes used `as Route` casts on 3 sites where the URL is runtime-built — each commented inline.

### Session totals (2026-06-08 → 2026-06-09)

| | Count |
|---|---|
| PRs shipped | 9 (PRD-19 backend + frontend + 2 docs) |
| Backend tests | 855 → 884 (+29) |
| Frontend tests | 75 → 99 (+24) |
| Production outages | 0 |
| Regressions | 0 |
| Latent bugs caught pre-merge | 5 |

### Remaining for PRD-19 (operational)

- PostHog Sprint A retention dashboard (events fire; just configs)
- Email-client rendering QA: Gmail web, Outlook web, Apple Mail
- `CAN_SPAM_ADDRESS` + `EMAIL_UNSUB_SIGNING_KEY` env vars on Railway before launch

---

## 2026-06-08 → 2026-06-09 — PRD-19 backend complete: the reverted feature shipped end-to-end in five clean slices (PRs #150 / #152 / #153 / #154 / #155)

Six weeks after PR #88 (Signals v0 Phase B — daily cron + alerts + unsub) was reverted during the May 26 16-hour outage and then paused for reshape, this session executed PRD-19's revised plan in five sequential single-PR slices. Backend retention-metric loop is now closed end-to-end and the user-facing controls (3 EmailPreference flags + daily digest + signed per-strategy unsub) are all wired and tested. **Test count: 855 → 884 (+29). Zero regressions across the sequence.** Three latent bugs from the original PR #88 reshape caught pre-merge.

### The session shape — single-PR slices, single master merger

The session opened with two pieces of cleanup from a prior Sonnet 4.6 session: PR #146 (the missed `git add` of `notifications.py` that broke CI for 38 minutes) and PR #147 (codifying the static-import smoke test as pre-push checklist item #6 + the "Mr Gu" master-merger verbal handshake convention).

Then PRD-19, in this order:

| # | PR | Slice | Lines | Tests added | Key bug caught pre-merge |
|---|---|---|---|---|---|
| 1 | [#150](https://github.com/grepJimmyGu/the_counselor/pull/150) | 3a — Mark-as-Executed model + endpoint | 628 + 7 fix-up | +12 | `ph_capture` vs `capture` import (test passed via monkeypatch, prod would silently swallow ImportError) |
| 2 | [#152](https://github.com/grepJimmyGu/the_counselor/pull/152) | 3b — dispatcher wiring + email render + throttle | 797 | +4 integration | (a) wrong `send_email` signature → every cron tick swallows TypeError; (b) literal `{{unsubscribe_url}}` tokens in body; (c) in-memory throttle counters reset across cron ticks |
| 3 | [#153](https://github.com/grepJimmyGu/the_counselor/pull/153) | 4a — preference flags + UTC drive-by fix | 353 | +12 | trap #16 in signal_cron (`date.today()` local vs `utcnow()` UTC) |
| 4 | [#154](https://github.com/grepJimmyGu/the_counselor/pull/154) | 4b — daily digest job + render + cron | 802 | +8 integration | `DigestEvent` missing `cash_count` (bucketing test caught it) |
| 5 | [#155](https://github.com/grepJimmyGu/the_counselor/pull/155) | 4c — signal_alerts_<id> + daily_digest unsub | 299 | +9 | — (clean ship) |

### The retention metric loop, end-to-end

1. User subscribes to a strategy → `SignalAlertSubscription`
2. Cron flips signal → `SignalEvent` + `dispatch_signal_change_email` + `dispatch_in_app_banner` + PostHog `notification_dispatched`
3. User clicks "Mark as executed" in the email or banner → `MarkAsExecutedEvent` + PostHog `notification_executed`
4. Sprint A dashboard joins them on `signal_event_id` for `latency_seconds`

Plus the user-facing controls Step 4 added:
- `GET/PATCH /api/me/email-preferences` with 3 new boolean flags (`signal_alerts_enabled`, `daily_digest_enabled`, `silent_days_enabled`)
- Daily digest cron at 13:00 UTC respecting `daily_digest_enabled` + `silent_days_enabled`
- Per-strategy unsub via signed `signal_alerts_<id>` token → flips `SignalAlertSubscription.email_enabled = False`
- Global digest unsub via signed `daily_digest` token → flips `daily_digest_enabled = False`
- "Unsubscribe from all marketing" now also flips both PRD-19 flags

### The cross-cutting lesson

Every reshape that defines NEW categories / templates / token shapes has to grow every GATE / SWITCH / RENDER that handled the OLD shapes. If a new branch is missing, the new shapes silently fall through to a no-op or a default — and "no-op" looks identical to "shipped" until a user clicks.

The three latent bugs in PRD-19 weren't independent. They all came from the same reshape-without-following-through pattern:

- The dispatcher had been reshaped to take a new event type but kept the old `send_email(to=..., body_html=...)` call signature
- The email body had been reshaped from inline template to placeholder tokens but no one wrote the substitution code
- The throttle counters had been reshaped to be in-memory dicts but no one wrote the DB seeding

Codified in `docs/LEARNINGS.md` as "Template literals that look like substituted strings — grep them BEFORE shipping" and "Tests in CI containers (UTC) silently pass code that breaks in local TZ — and vice versa."

### Remaining (frontend, separate sessions)

- **Step 5** — `NotificationBanner`, `MarkAsExecutedButton`, `NotInvestmentAdviceFooter` bricks + Home / Strategy-detail integration. Notification-banner endpoints shipped in PR #146.
- **Step 6** — `NotificationSettingsForm` brick + `/account/notifications` page. Calls `GET/PATCH /api/me/email-preferences` from this session.

Resumption checklist lives in `agent-system/WORK_LOG.md` "Current Session."

---

## 2026-05-27 — Portfolio Mode diagnose: a triple-bug fix worth three new CLAUDE.md traps (PR #132)

Jimmy hit the Portfolio Mode flow and got **"We couldn't diagnose your portfolio. Try again."** Same error for anonymous AND signed-in users. Different copy than the one PR #126 fixed (that was a pool-saturation issue under load); this was an auth-and-error-mapping problem.

Investigation found three distinct bugs compounding into one indistinguishable failure mode. Each is now a CLAUDE.md trap so the next agent touching this surface doesn't have to re-derive any of them.

### Bug 1 (backend) — route shipped sign-in-only

`POST /api/portfolio/diagnose` used `require_entitlement(needs_run_quota=False)` — the default `allow_anonymous=False`. The route fronts the Portfolio Mode upload step, which **anonymous users can reach by clicking "Upload portfolio" on Home before signing in**. Strict `get_current_user` 401'd every anonymous caller. Frontend's generic catch block mapped the 401 to "couldn't diagnose."

**Fix:** `allow_anonymous=True`, plus a synthetic-user early-return in `_enforce_diagnose_rate_limit` (all anonymous callers share one `WeeklyUsage` row, so the standard Scout 5/hr cap would gate the 6th anonymous visitor sitewide). Counter increment also skipped for the synthetic user to avoid contention.

**Codified as `apps/api/CLAUDE.md` trap #18**: `require_entitlement` defaults to `allow_anonymous=False`. Pre-sign-in flows must opt in. Rate-limit caveat for the shared synthetic-user row spelled out.

### Bug 2 (frontend) — bricks calling authed endpoints must read `backendToken`

`<PortfolioDiagnosis>` never read `backendToken` off `useSession()` and never passed an `Authorization` header. Signed-in users called the endpoint as if anonymous → also 401 → same generic error copy.

**Fix:** mirror the `getEntitlements` pattern — pull `backendToken` from `useSession()`, gate the diagnose call on `sessionStatus !== "loading"`, add both to the effect's deps so it re-fires after NextAuth resolves. Without the gate, signed-in users would fire one anonymous request during NextAuth's boot window before the authenticated retry.

**Codified as `apps/api/CLAUDE.md` trap #19**: frontend bricks calling authed endpoints must read `backendToken` from `useSession()`. Two non-obvious bits: the `sessionStatus !== "loading"` gate and the effect-deps requirement.

### Bug 3 (subtle ORM) — intermediate commit expires `user` mid-route

This is the most insidious of the three. Inside the route:

```python
async def diagnose_portfolio(payload, auth, db):
    user, ent = auth
    _enforce_diagnose_rate_limit(db, user.id, ent.tier)  # ← creates WeeklyUsage row + commits
    # ... later, after db.close() and the slow await ...
    _ph_capture(user.id, "portfolio_diagnosed", {"current_tier": ent.tier, ...})  # ← DetachedInstanceError
```

The rate-limit check calls `get_or_create_current_weekly_usage(...)`, which **creates a fresh row + commits when no row exists for the user × week**. SQLAlchemy's default behaviour after `commit()` is to expire all instances bound to the session. The `user` ORM object is now in expired state; downstream reads of `user.id` / `ent.tier` trigger a lazy-refresh that fails after `db.close()` with `DetachedInstanceError`.

**Why this is insidious — the bug doesn't trip in tests or for existing users.** A user whose `WeeklyUsage` row already exists for the current week doesn't trigger the create-and-commit path; their attribute reads stay live because `db` doesn't commit. Tests use a fixture that pre-populates the row. So the bug ships green and explodes on the first NEW user's first diagnose call — exactly the failure mode every production debug already warns about.

**Fix:** snapshot `user.id` and `ent.tier` to plain `user_id: str` / `tier: str` locals at the top of the route. Use the locals everywhere downstream. ORM-bound reads happen exactly once, before any commit can fire.

**Codified as `apps/api/CLAUDE.md` trap #17**: intermediate commits expire ORM instances — snapshot scalars at route entry. Anchored to PR #132 (this bug) and PR #53 (the same class in the chat-hang fix from 2026-05-22).

### Test plan + regression coverage

- 6 new backend pytest cases (`tests/test_portfolio_diagnose_anonymous.py`):
  - Anonymous calls succeed (synthetic user, no 401)
  - Anonymous rate-limit skip across 50 simulated bursts (no spurious gate)
  - Scout cap still gates for signed-in users (regression bar)
  - Counter does NOT pollute the shared anonymous row
  - Counter DOES increment for signed-in users
  - Static introspection: FastAPI dep resolves to `get_current_user_or_anonymous` (catches an accidental future re-tighten without needing a live request)
- 3 new frontend vitest cases (`portfolio-diagnosis.test.tsx`):
  - Anonymous (token undefined): endpoint called without `Authorization` header
  - Signed-in (token present): endpoint called with `Authorization: Bearer <token>`
  - Loading: endpoint NOT called yet (waits for NextAuth to resolve)

Test count: backend **790 → 796**, frontend vitest **55 → 58**.

### The pattern this completes

Three traps in CLAUDE.md now cover the full "async route + auth + slow await" surface:

| Trap | Lesson | Born from |
|---|---|---|
| #13 | Async routes can't hold `db: Session = Depends(get_db)` across slow external HTTP awaits — pool drains. Close + re-acquire via `SessionLocal()`. | PR #104 (`dunning_expiry_job`) + PR #126 (`portfolio_diagnose`) |
| #17 | Intermediate commits expire ORM instances — snapshot scalars at route entry. | PR #53 (chat hang) + PR #132 (portfolio diagnose) |
| #18 | `require_entitlement(...)` defaults to `allow_anonymous=False`. Pre-sign-in flows must opt in. | PR #132 |
| #19 (frontend) | Bricks calling authed endpoints must read `backendToken` from `useSession()` + gate on `sessionStatus !== "loading"`. | PR #132 |

Together they describe everything an async route handler needs to think about. New routes that touch DB + external HTTP + auth should pass all four checks.

### What it reinforces

- **Insidious-bug heuristic**: when a backend path includes `commit()` inside a sub-helper, ask *"would this fire for an existing user vs. a new user differently?"* If yes, the new-user path is the one that ships green and breaks in production.
- **Indistinguishable-failure heuristic**: when two different root causes produce the same error string, the user-facing error is too generic. Future polish: the frontend catch block in `<PortfolioDiagnosis>` should at minimum log the underlying status so debugging session-zero issues like this doesn't require reading server logs blind.
- **Same-day discovery → same-day codification**: the bug got reported, diagnosed across three layers, fixed with regression tests, and the lessons written into CLAUDE.md within hours. This is the loop that lets sprint velocity stay high without losing institutional knowledge.

---

## 2026-05-26 (late) — Sprint 1 (Livermore Product Flow v2) shipped end-to-end

Late on the 30-PR Tuesday, Sprint 1 of the **Livermore Product Flow v2** rewrite closed out. The whole spec (HANDOFF doc + 5 PRDs) was drafted, scoped, executed, and merged in a single day across parallel agent sessions.

### What the sprint delivered

The product is restructured around **six user entry modes** (One Asset / Portfolio / Thesis / Custom / Idea / Discovery). Sprint 1 shipped the two highest-priority modes (Mode 1 secondary trigger + Mode 2 full flow), their trigger surfaces (Home picker + stock-page CTA + Strategy Builders integration), and the foundational LEGO architecture (`FlowDefinition` runtime + brick library) that Sprint 2 will compose against.

| PRD | What | PR(s) |
|---|---|---|
| **PRD-12** | Asset Behavior Fingerprint service + `<AssetBehaviorFingerprintCard>` | #97 / #106 |
| **PRD-13a** | Flow runtime infrastructure (`lib/flows/{types,runtime,registry,copy}.ts`) + universal `/flow/[flowId]` shell route + mock-flow dev fixture | #117 + #122 (brick tests) + #123 (`useFlowCopy` lexicon) + #124 (`schemaVersion` + dev-gate hardening) |
| **PRD-13b** | Portfolio Mode + engine extension (`inherited_universe` field, 3 overlay strategy_types, `PortfolioDiagnosisService`, `POST /api/portfolio/diagnose` cached + rate-limited, `weekly_usage.portfolio_diagnose_runs_hourly` migration, 3 portfolio bricks + 4 adapter bricks + first concrete `FlowDefinition`) | #125 + #126 (trap-#13 pool-safety fix) |
| **PRD-14** | Stock-page "⚡ Apply a strategy" CTA brick + fingerprint card render | #120 |
| **PRD-11** | Home page entry picker (3 CTAs) + saved-strategies tile | #127 |
| Sprint closeout | HANDOFF + 5 PRDs committed to `main`; brick inventory flipped ⏳→✅; acceptance checklist ticked; WORK_LOG refreshed | #128 (this entry) |

### Tests

Backend: **763 → 790** (+27 across the 5 PRDs).
Frontend vitest: **0 → 55** (the runner itself was new in PRD-13a; 4 brick test suites + the runtime suite).

### The four principles, in practice

The HANDOFF doc named four principles that every Sprint 1 PRD enforced:

1. **Reuse, don't replicate** — verified across PR reviews: backtest / save / result paths were never re-implemented per mode; PRD-13b's adapter bricks wrap the existing `/api/backtest/run` + `/api/strategies/save` instead of forking them.
2. **LEGO bricks** — every Sprint 1 brick lives at `apps/web/src/lib/flows/bricks/` (or `components/strategy-picker/` for PRD-12's pre-existing card). Sprint 2 modes plug in without touching `lib/flows/runtime.ts`.
3. **Mode = `FlowDefinition`, not a route** — `portfolio-mode.ts` is the first concrete proof. 7 steps, pure data, self-registers on import. PRD-11's "Upload portfolio" CTA is one line: `startFlow('portfolio_mode', { fromTrigger: 'home/upload_portfolio' })`.
4. **UX consistency + sub-300ms perceived load** — `useFlowCopy(modeId, key)` lexicon used everywhere; skeleton states on every blocking call > 200ms; `router.prefetch` on hover/focus for the EntryModePicker CTAs.

### The discipline that made it possible

- **Chip-driven parallel agent sessions.** PRD-13b, PRD-14, PRD-11, the 3 runtime-hardening chips, and the trap-#13 follow-up all ran in their own worktrees on their own branches; `claude-main` reviewed + merged sequentially. Zero cross-session contamination.
- **One PR per PRD, base=main.** Avoided the stacked-PR-loses-CI trap. Every PR ran the full backend pytest + frontend build + CodeQL + Postgres smoke before merge.
- **End-to-end audits beat unit tests.** PRD-13b's `test_engine_cross_sectional` regression check confirmed the `inherited_universe` field is truly additive (existing 22 strategy_types unaffected).
- **Trap-class follow-ups same day.** PRD-13b shipped with the known trap-#13 risk (DB session held across slow FMP HTTP); review flagged it; chip queued; PR #126 fixed it within hours, mirroring PR #104's pattern. The whole 2026-05-26 trap class is now closed at the application layer.

### What's next

- **Sprint 2** (per HANDOFF §10): PRD-15 Thesis Mode, PRD-16 Custom Build (closes the read-only WHEN IN / WHEN OUT gap), PRD-17 Saved-strategies surface, PRD-18 Community thesis cards, PRD-19 per-holding signal extension (un-defer after Phase B reshape).
- Each Sprint 2 PRD should be <1 week because the architecture is in place — that's the explicit promise of the runtime + brick library investment.

---

## 2026-05-26 — The 30-PR Tuesday: strategy builder, production outage, market-pulse live-data saga

Calendar count for the day: **PRs #86 through #118**, plus reverts, plus
one 16-hour production outage misdiagnosed at the start and a market-pulse
saga that took 8 PRs to converge.

### Morning — strategy builder rebuild (PRs #86–#96)

Reviewing the post-rebuild strategy builder with Jimmy surfaced a coherent
set of polish items that shipped across seven PRs:

| What | PR |
|---|---|
| Animated single-question wizard (fade-in/out, summary chips for answered Qs, auto-advance) | #91 |
| Rich template comparison cards (inline `StrategyBriefCard` expansion + "bump-out" animation on pick) | #91 |
| WHEN IN / WHEN OUT detailed copy for 11 templates, synthesized from `Livermore_Strategy_Library_v2.html` + framework docs | #92 |
| Lock unavailable templates + skip preview step + free-form capital input | #96 |
| Signals v0 Phase B (daily cron + email alerts + signal-unsub) | #88 |
| Spinner decouple — "Generating report" unstuck (LLM calls fire in background) | #98 |
| Module 2 — Asset Behavior Fingerprint (backend service + frontend card) | #97 |

### Midday — the 16-hour Railway outage (misdiagnosed)

Production wedged at "Waiting for application startup." The earliest failed
deploy ID was `11686d26`. The string was mistaken for a git SHA and traced
(incorrectly) to PR #88. Three PRs got reverted (#88, #99, #100, #97) and
re-deployed, each failing with the same hang — because the real culprit was
a **Postgres process-level socket wedge**, not any code change. Postgres
queries from the dashboard worked fine; new app containers couldn't
connect.

**The 15-second fix:** Railway → Postgres service → Deployments → Restart.

**Codified in `apps/api/CLAUDE.md` trap #11**: always disambiguate a suspect
hash with `git cat-file -t <hash>` before treating it as a git SHA. If it
errors, it's a Railway deployment ID, not a commit.

Full post-mortem: `docs/KNOWN_ISSUES.md` (entry 2026-05-26).

### Afternoon — recovery + the real conn-leak culprit (PRs #103–#107)

Once the restart confirmed no code was at fault:
- Jimmy decided to **pause PR #88 (Signals Phase B)** for reshape — full
  context in `docs/PROJECT_BACKLOG.md` §4. Original revert commit stays on
  main; the work itself is preserved on the GitHub remote branch and
  documented for resumption.
- **PR #104** moved `cancel_subscription()` (Stripe API call) outside the
  open DB transaction in `dunning_expiry_job`. This was the actual
  amplifier of the outage — slow Stripe calls held DB connections
  idle-in-tx, draining the pool. Worth fixing regardless of whether
  Postgres restart "solved" the immediate symptom.
- **PRs #105, #106** re-applied PR #99 (`:bind::type` → `CAST(:bind AS type)`)
  and PR #97 (Module 2 Asset Behavior Fingerprint) as clean re-PRs after
  the rollbacks.
- **PR #103** documented the outage post-mortem in `docs/KNOWN_ISSUES.md`.

### Evening — the market-pulse live-data saga (PRs #108–#118)

Eight PRs to converge on a working live-quote overlay. Each iteration
taught something worth keeping in CLAUDE.md.

| # | What | Result |
|---|---|---|
| #108 | Codex's first cut — live overlay path + 3 invented FMP batch endpoints (`/stable/batch-quote`, `/batch-etf-quotes`, `/batch-index-quotes`) | All batch calls 404'd silently → 0 live overlay applied, but the architecture was correct |
| #109 | Wire `get_live_pulse()` into the route (fixed the dead-code path) | Overlay code now runs, but still no quotes from #108's invented endpoints |
| #110 | Codex's batch implementation, same invented endpoints + chunking + concurrent gather | Same outcome — 0/497 live; tests mocked `client._get` so the broken URL strings never failed |
| #112 | Replace invented endpoints with `/stable/quote?symbol=A,B,C` (comma-separated query param) | **Wrong** — FMP `/stable/quote` is single-symbol only in query mode. Returned only the one symbol that was already cached individually. |
| #113 | Switch to concurrent individual `get_quote(sym)` calls at Semaphore(50) | Worked for the first 50 symbols, then hit FMP burst limits — late-alphabet (M-Z) silently 429'd inside `try/except Exception` |
| #114 | **Real batch convention is path-based**: `/stable/quote/SYM1,SYM2,...` (same as fmpsdk / fmp_py against v3) + individual fallback at Semaphore(10) | Coverage jumped to 496/497 |
| #115 | BRK.B normalization (FMP returns class shares as BRK-B, not BRK.B) — translate dot↔hyphen in both `_get_quote_batch_path` and `get_quote` | 497/497 in the warm case; ~88% on cold cache due to remaining burst-rate-limit hits |
| #116 | Throttle path-batch to `BATCH_CONCURRENT_CHUNKS=2` (Semaphore-bounded gather) | Cold-cache still ~88% — even 2 concurrent chunks triggered FMP's burst window |
| #118 | Strict serial: `BATCH_CONCURRENT_CHUNKS=1` | **100% cold-cache coverage**, ~2.5s latency for the first user after each 5-min cache expiry |

Parallel-session note: PRs #116 and #118 were written by a sibling Claude
session while the primary session was waiting for user input. Both fixes
landed cleanly because each agent worked in its own worktree per the
`PARALLEL_WORK.md` discipline.

**Plus PR #111** (independent of the saga): real FRED data for the last two
mock macro signals — CFNAI (Growth) and BAMLH0A0HYM2 (Stress / HY OAS).
Drops the last two `Mock` pills from the Market Pulse table. Note: ISM PMI
was the original Growth signal candidate but is no longer FRED-hosted
(post-2017 licensing); CFNAI is the documented alternative.

### What this day codified in `apps/api/CLAUDE.md`

- **Trap #11** — production hang at "Waiting for application startup": diagnose
  with `railway deployment list`, restart Postgres add-on first, treat the
  symptom-time hash as a deploy ID until proven otherwise.
- **Trap #12** — SQLAlchemy `text()` doesn't parse `:bind::type` (PR #99 / #105).
- **Trap #13** — async routes holding DB sessions across slow external HTTP
  awaits drain the connection pool under load (the conn-leak amplifier).
- **Trap #14** — don't hallucinate API endpoints; verify against existing
  in-repo working calls, real curls, or vendor docs before shipping.
- **Trap #15** — FMP-specific patterns: path-based batch convention,
  class-share dot↔hyphen normalization, strict-serial batch concurrency to
  avoid burst rate limits.
- **Trap #16** — UTC date rollover in freshness verification: compute the
  comparison date in the same TZ the backend writes (UTC on Railway). The
  saga had a 30-minute panic when my hard-coded date string flagged 497/497
  as "stale" right after UTC midnight passed.

### Production state at end of day

- Market Pulse `/stocks`: 497/497 S&P 500 symbols live on every cold-cache
  request (verified via `market-pulse-audit`)
- Sector Rotation re-sorted by live CMF
- All four macro signals real (Inflation, Rates via Alpha Vantage; Growth,
  Stress via FRED) — the four "Mock" pills are gone
- Backend test suite: 761 + new tests for #114-#118 / #115 normalization
- Frontend build clean

### Test suite growth across the day

737 → 761 → 763. Each market-pulse PR carried at least one regression test.
The `market-pulse-audit` skill (added 2026-05-23) was the integration-level
guard that caught every wrong fix before users would have.

---

## 2026-05-23 — Market Pulse accuracy + latency sprint (9 PRs)

Jimmy's first manual production review of the Market Pulse v2 redesign
surfaced four data-accuracy bugs plus a missing transparency piece
(narrative date stamp). Today shipped the bug fixes, the latency
report, an audit script + Claude skill for ongoing verification, and
an operational backfill that grew the Top Movers candidate pool from
30 SPX names to 497.

### Bugs Jimmy flagged + fixed

| # | Bug | Fix | PR |
|---|---|---|---|
| 1 | `510300.SH` (Shanghai A-share fund) leaking into US Top Movers | Region filter + suffix exclusion; later superseded by SP500 universe filter (PR-8) | [#68](https://github.com/grepJimmyGu/the_counselor/pull/68) |
| 2 | "Top losers" sort showing AMD +3.99% as worst loser | Widen candidate pool — backend stops pre-sorting by CMF, frontend client-side sorts the wider pool | [#69](https://github.com/grepJimmyGu/the_counselor/pull/69) |
| 3 | Sector chart label "vs S&P 500" but data was SPY ETF | Swap to `^GSPC` index with transparent SPY fallback; operational FMP backfill ingests 4y of ^GSPC bars | [#73](https://github.com/grepJimmyGu/the_counselor/pull/73) |
| 4 | CN toggle leaves US-only sections visible | Gate MacroPulseTable + HistoryRhymes on `market === "US"`; Screener stays visible | [#71](https://github.com/grepJimmyGu/the_counselor/pull/71) |

Plus Jimmy's two explicit asks:

| Ask | Fix | PR |
|---|---|---|
| "I suggest adding a date in the narrative section claiming which date it is summarizing" | Add `as_of` to MarketNarrative; render as newspaper-byline above the headline (was a 9px footer in the original PR-3 attempt — Jimmy couldn't see it) | [#70](https://github.com/grepJimmyGu/the_counselor/pull/70), [#77](https://github.com/grepJimmyGu/the_counselor/pull/77) |
| "I suggest we build a data latency report" | `GET /api/market/data-latency` + `<DataFreshnessFooter />` with per-group breakdown | [#74](https://github.com/grepJimmyGu/the_counselor/pull/74) |
| "Build an agent to check calculation accuracy + data latency" (the umbrella ask) | `apps/api/scripts/audit_market_pulse.py` + `.claude/skills/market-pulse-audit/SKILL.md` | [#75](https://github.com/grepJimmyGu/the_counselor/pull/75) |
| "Top Movers pool should be the entire S&P 500 list" | Switch `_build_top_assets` to filter against `SP500_TICKERS` (~525); operational AV backfill ingests the missing ~470 SPX names | [#77](https://github.com/grepJimmyGu/the_counselor/pull/77), [#78](https://github.com/grepJimmyGu/the_counselor/pull/78) |

### Plus two PRs from Jimmy's other Claude session

| PR | Subject |
|---|---|
| [#72](https://github.com/grepJimmyGu/the_counselor/pull/72) | chat anon cookie propagation + stock_lookup date coercion |
| [#79](https://github.com/grepJimmyGu/the_counselor/pull/79) (was #76) | chat-tool production-shape gate + nightly error auditor |

#76 had to be closed + reopened as #79 because #72 shipped the exact
same `stock_lookup.py` date-coercion fix in parallel — content-identical
conflict. Used the fresh-branch rebase pattern from CLAUDE.md.

### Test suite

**Backend grew 630 → 696** across today's PRs (+38 from the Market
Pulse sprint, +28 from the chat-side PRs).

### Production state at end of day

Final `/market-pulse-audit` against production: **11 OK · 0 WARN · 0 ERROR**:
- All data groups fresh (oldest source: 2026-05-21)
- US Top Movers: 497 SPX symbols, 349 gainers + 145 losers (the "Top
  losers" sort now has real candidates to surface)
- ^GSPC backfilled — sector chart benchmarks against the actual index
- Inflation + Rates macro signals live via Alpha Vantage; Growth +
  Stress remain `mock_pending_fred`
- CN scope clean — no A-share leakage
- Narrative date stamped as newspaper-byline ("Saturday, May 23, 2026")
  above every LLM headline

### Operational events worth logging

- **`^GSPC` backfill (~1004 rows)** ran cleanly first try
- **SP500 universe backfill (~525 rows × 3y of daily bars)** ran in
  two passes: pass 1 loaded ~130 before Railway Postgres ran out of
  disk space mid-fetch (`DiskFull: could not extend file`). Killed
  the script; Jimmy expanded Railway storage from the dashboard;
  pass 2 idempotently completed — 517 loaded, 8 failed (delisted /
  renamed names like `ABC` → `COR`).
- **Force-push blocked by auto-mode classifier** twice today (PR-1e
  yesterday, PR-9-related rebase today). Both resolved via the
  "fresh-branch rebase" pattern — push the rebased commit under a
  `-rebased` suffix, close old PR with comment, open new PR. Codified
  in CLAUDE.md.

### New principle codified

**The stock universe is a STANDARD — can be expanded, must not shrink.**
Per Jimmy's end-of-day note. `SP500_TICKERS` is the canonical Top
Movers universe; any future change should be additive. Documented
in CLAUDE.md + the `sp500_tickers.py` docstring.

---

## 2026-05-22 (later) — Market Pulse v2 Phase 1c–1f shipped, redesign fully real-data backed

Four sub-phases of the Market Pulse v2 wire-up landed in one focused
afternoon, swapping the last of the mock surfaces inside `/stocks`
with real backend data. The full redesign that signed off on
2026-05-21 (Phase 0a) is now end-to-end real except for two macro
rows that are documented-as-pending a FRED API key.

### What shipped

| Sub-phase | Surface | PR |
|---|---|---|
| **1c — Macro signals** | New `macro_signals_service` (Alpha Vantage `TREASURY_YIELD` for the 10Y row, AV `CPI` index → YoY% derivation for the Inflation row). Growth (ISM PMI) + Stress (HY OAS) stay mock with `mock_pending_fred` source flag. Per-row `Live` / `Mock` pill in the table. | [#61](https://github.com/grepJimmyGu/the_counselor/pull/61) |
| **1d — Sector vs SPY chart** | `sector_comparison_service` aligns sector ETF + SPY `price_bars` by intersected date set, normalizes both series to 0% at window start, returns Day/YTD/1Y/3Y totals from full history (not just the windowed slice). Endpoint `/api/market/sector-comparison/{symbol}?range=1M|6M|YTD|1Y|3Y`. 5-min cache. | [#62](https://github.com/grepJimmyGu/the_counselor/pull/62) |
| **1e — History Rhymes** | `macro_similarity_service` — cosine similarity over a 6-dim 5-day return vector across TLT/VXX/UUP/HYG/GLD/USO against ~5y of `price_bars`. Top-3 matches with 14-day MIN_GAP_DAYS dedupe, each carrying the SPY 30-trading-day post-window outcome + a 30-point normalized sparkline. Heuristic regime label ("Vol spike · bonds rallying") from threshold-trip logic. 4h cache. | [#64](https://github.com/grepJimmyGu/the_counselor/pull/64) |
| **1f — Screener presets** | `screener_presets` registry of 9 declarative `PresetSpec` entries (6 Scout / 2 Strategist / 1 Quant). Two endpoints: `/api/screener/presets` (summary with real counts + sample tickers, no gating) and `/api/screener/preset/{slug}` (paginated results, tier-gated via 402). New `screener_preset_locked` entitlement code + `required_tier_override` parameter on `upgrade_error()` so one code can route to Strategist OR Quant correctly. | [#65](https://github.com/grepJimmyGu/the_counselor/pull/65) |
| docs | PROJECT_BACKLOG.md §4b refreshed; v1-approximation follow-ups recorded (FRED key swap, news-sentiment / community-vote / volume_ratio pipelines for the three Strategist+/Quant presets that use curated baskets today). | [#66](https://github.com/grepJimmyGu/the_counselor/pull/66) |

Test suite grew **580 → 614 (+34)** across 1c/1d/1e and another
**+11** for 1f → **625 backend tests** at end of session. Frontend
build clean throughout.

### The detour worth logging

PR #63 had to be closed and reopened as PR #64 because the auto-mode
classifier blocked the `git push --force-with-lease` needed to update
#63 in place after a rebase onto post-1d main. The "Stacked-PR cascade"
recipe from CLAUDE.md handled it cleanly — push the rebased commit
under a fresh branch name (`claude/feat/phase-1e-history-rhymes-rebased`),
close the old PR with a comment, open a new PR from the rebased
branch. Same content, new PR number, full CI fires. Force-push
gating works as designed — the workaround keeps history clean
without an explicit "yes, force-push" sign-off from the user.

### Files touched

```
apps/api/app/services/macro_signals_service.py        NEW (Phase 1c)
apps/api/app/services/sector_comparison_service.py    NEW (Phase 1d)
apps/api/app/services/macro_similarity_service.py     NEW (Phase 1e)
apps/api/app/services/screener_presets.py             NEW (Phase 1f)
apps/api/app/services/alpha_vantage.py                +fetch_treasury_yield, +fetch_cpi
apps/api/app/api/routes/market_data.py                +3 routes
apps/api/app/api/routes/screener.py                   +2 routes + gating
apps/api/app/api/entitlement_errors.py                +screener_preset_locked code + required_tier_override param
apps/api/tests/test_macro_signals.py                  NEW (12 cases)
apps/api/tests/test_sector_comparison.py              NEW (15 cases)
apps/api/tests/test_macro_similarity.py               NEW (19 cases)
apps/api/tests/test_screener_presets.py               NEW (11 cases)
apps/web/src/lib/contracts.ts                         +4 new types
apps/web/src/lib/api.ts                               +4 helpers
apps/web/src/components/market-pulse/MacroPulseTable.tsx       (signals prop + Live/Mock pill)
apps/web/src/components/market-pulse/SectorComparisonChart.tsx (full rewrite: real fetch)
apps/web/src/components/market-pulse/HistoryRhymes.tsx         (full rewrite: real fetch)
apps/web/src/components/market-pulse/Screener.tsx              (full rewrite: summary fetch + Live badge)
apps/web/src/app/stocks/_market-pulse.tsx                       (pass macro_signals)
apps/web/src/app/stocks/_page-inner.tsx                         (read ?preset= and route through preset endpoint)
docs/PROJECT_BACKLOG.md                                         (4b refresh + follow-ups)
```

### What backend CI verified

Every PR ran the full Postgres migration smoke test, the full pytest
suite, CodeQL Python/JS/Actions, and the Vercel preview build before
squashing to main. All five PRs landed clean — no rollbacks, no
follow-up hotfixes.

### Documented v1 approximations (so future-me doesn't forget)

Three of the screener presets and two of the macro signals ship as
documented v1 approximations. PROJECT_BACKLOG.md §4b's "Follow-ups
from the 1c–1f ship" table is the running list:

- Set `FRED_API_KEY` on Railway → swap Growth (ISM Services PMI) +
  Stress (HY OAS) macro signals from mock to real. ~2h backend (FRED
  client + signal builders) plus a 1-min env var set.
- Replace `positive-catalyst` curated basket with news-sentiment query
  when PRD-09 sentiment coverage is dense enough to be a useful screen.
- Replace `community-confirmed` curated basket with vote/watchlist
  rollup query when community engagement scales.
- Replace `rising-attention` curated basket with per-stock real-time
  `volume_ratio` (backend addition; small).

---

## 2026-05-22 — Stage 7 Chat v2 Phase 1 complete + production hang fix

All eight Phase 1 tickets of the Stage 7 chat-v2 build landed on `main`,
delivering an end-to-end conversational research surface — backend SSE
endpoints, 7 tool-calling chat tools, runtime guardrails, and a floating
widget mounted on `/workspace` + `/stocks/[ticker]`.

### What shipped

| Ticket | Surface | PR(s) |
|---|---|---|
| #1 — schema | `chat_conversations` + `chat_messages` + `AnonymousSession.chat_turns_used` | landed via #29's muddy bundle, ratified #43 |
| #2 — LLM adapter | `chat_completion_with_tools` async iterator over OpenAI streaming | #37 |
| #3 — light tools | `concept_explainer` (reads `apps/api/docs/chat_concepts.md` at runtime), `template_search`, `onboarding_tutor` stub + central registry + dispatcher | #38 |
| #4 — heavier tools | `strategy_builder_iterate`, `backtest_execute`, `stock_lookup`, `backtest_explain` — wraps existing services | #43 |
| #5 — authed endpoint | `POST /api/chat/conversations/{id}/messages` w/ SSE + tool loop + tier daily caps | #44 (recovery from stacked-PR cascade) |
| #6 — anonymous endpoint | `POST /api/anonymous/chat/{...}` w/ 5-turn lifetime cap, tool whitelist, signup-merge | #45 (same recovery flow) |
| #7 — frontend widget | `ChatWidget.tsx` floating panel + `useChatStream` hook + types-first contracts.ts additions | #50 |
| #9 — guardrails | Refusal classifier + structured event log + citation reprompt + nightly LLM-judge auditor + weekly digest | #48 |

Test suite grew **464 → 563** over the session. Schema-drift tripwire (built in the previous session) ran nightly with no new WARNs; new chat tables registered cleanly. Frontend `npm run build` green throughout.

### The deferred ticket

Ticket #8 (homepage / `/templates` / `/account` onboarding entry points + UpgradeModal wiring on 402 + 100-prompt adversarial refusal QA corpus) is the only remaining Phase 1 item. Not on the critical path for "can a user chat at all" — the widget is already discoverable via the floating launcher.

### The production hang (post-mortem in [KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md))

Within minutes of #50 deploying, Jimmy reported the widget hanging — 200 OK with `text/event-stream`, but zero body bytes. Root cause: every `event_stream()` generator in `chat.py` touched ORM attributes (`session.chat_turns_used`, `conv.id`, `user.plan.tier`) *after* the FastAPI-injected `Depends(get_db)` session had closed, raising `DetachedInstanceError`. Starlette's ASGI exception handler silently absorbed it inside a TaskGroup, leaving the SSE body empty forever.

Existing tests didn't catch it because they iterate the StreamingResponse synchronously while the test fixture's `db` is still live. PR #53 fixes by:
- Snapshotting all ORM attribute reads into plain locals before each generator's first yield
- Opening a fresh DB session inside `_run_tool_loop` bound to the SAME engine as the caller's `db` (`sessionmaker(bind=db.get_bind())`), so tests use their in-memory SQLite engine and production uses Postgres without monkey-patching
- A regression test (`test_streaming_survives_request_session_close`) that explicitly closes the test session between the route return and the SSE iteration — produces zero frames against the bug, three frames against the fix

### Process learnings logged elsewhere

- **Stacked-PR cascade on parent-delete** — when #38 squash-merged + auto-deleted `claude/feat/chat-v2-p1-3-tools-light`, the stacked #39/#40/#42 PRs went `state: CLOSED` immediately and `gh pr edit --base main` refused. Recovery via `git rebase --onto main <old-parent-tip>` then opening fresh PRs. Codified in `CLAUDE.md` PR mechanics section.
- **Stacked PRs lose backend CI** — `.github/workflows/backend-ci.yml` triggers only on `base: main`. Stacked PRs got Vercel preview but no pytest/Postgres-smoke. Codified same place.
- **Force-push auto-mode blocking** — the auto-mode classifier correctly blocked claude-main from force-pushing this session's branches during the rebase recovery. claude-main worked around by opening parallel `*-rebased` branches under their own prefix. Captured in feedback_livermore_workflow memory.

### Files touched (high level)

```
apps/api/app/api/routes/chat.py       (NEW + extended through 5 tickets)
apps/api/app/services/chat_tools/     (NEW package, 7 tools + registry)
apps/api/app/services/chat_guardrails.py  (NEW — ticket #9)
apps/api/app/jobs/qa_jobs.py          (extended — nightly auditor + digest)
apps/api/app/models/chat.py           (NEW — ticket #1 tables)
apps/api/app/models/anonymous_session.py  (added chat_turns_used)
apps/api/app/services/anonymous_service.py  (merge_anonymous_into_user now re-attributes chat_conversations)
apps/api/app/services/llm_adapter.py  (added ChatToken/ChatToolCall/ChatDone + chat_completion_with_tools)
apps/api/docs/chat_concepts.md        (NEW — 30 curated concept entries)
apps/api/tests/test_chat_{models,endpoint,tools_light,tools_heavy,guardrails,refusal_adversarial,anonymous_chat}.py
apps/web/src/components/ChatWidget.tsx     (NEW)
apps/web/src/lib/useChatStream.ts          (NEW)
apps/web/src/lib/contracts.ts              (chat event union + UI message types)
apps/web/src/app/{workspace,stocks/[ticker]}/page.tsx  (mount widget)
```

### What backend CI verified

Every merged PR ran the full Postgres migration smoke test, full pytest, CodeQL Python/JS/Actions, and Vercel preview build before squashing to main.

---

## 2026-05-21 — The Three-Bug Chain + Gate Hardening

A debugging session that started "Scout users are stuck on the upgrade modal"
and ended three bug fixes deep, with a gate-hardening PR to keep the bug class
from recurring.

### Bug 1 — Scout misrouting to /api/anonymous/backtest/run (PR #7)

**Symptom:** Signed-in Scout users see the "Sign up to build custom strategies"
modal when clicking Run in `/workspace`. The modal copy promises that signup
unlocks 5 weekly runs — but they were already signed up.

**Root cause:** During NextAuth's brief `loading` state on page mount,
`session.user.id` is undefined. The old check
`isAnonymous = !sessionUserId` therefore returned `true` for signed-in
users in that window, routing them to `/api/anonymous/backtest/run`.
That endpoint 402s with `anonymous_chat_locked` when `template_id ===
"custom"`, surfacing the wrong modal to signed-in users.

The code already self-diagnosed the bug at
[research-workspace.tsx:100](apps/web/src/components/workspace/research-workspace.tsx#L100)
as "the May 20 evening regression" — an earlier partial fix existed but
was incomplete.

**Fix:** Use `sessionStatus === "unauthenticated"` (NextAuth's
authoritative signal) as the source of truth. Add `isSessionLoading`
guard to handleRunBacktestWith so clicks during the loading window
get a clean retry message instead of misrouted 402s. Add
`needsSessionRefresh` for stale JWTs minted pre-9789974.

**Commit:** `0243e2d` (squash of branch `fix/scout-misrouting-anonymous-endpoint`)

### Bug 2 — sync-user 500 on orphaned User-without-Plan (PR #8)

**Symptom:** Post-PR-#7 deploy. Signed-in Scout sees "Your account session
is out of date" banner + falls back to anonymous quota display ("1 free
run left — sign up to save"). Browser console: `backendToken: null` in
the NextAuth session.

**Root cause:** `POST /api/auth/sync-user` crashes at
[auth.py:380](apps/api/app/api/routes/auth.py#L380) with
`AttributeError: 'NoneType' object has no attribute 'tier'`. The User row
existed but `user.plan` was `None` — orphaned by a partial-failure path
during the May 19/20 migration odyssey. Every subsequent sync-user call
(initial Google signin + self-healing branch at
[auth.ts:61](apps/web/src/auth.ts#L61) on every request) hit the same
crash; the catch silently swallowed it; user's JWT was stuck with
`backendToken=null` indefinitely.

**Fix:** Lazy-create a Scout `Plan` row when `user.plan is None` just
before reading `user.plan.tier`. Logs a WARN so we can measure how often
the heal fires.

**Commit:** `0128c32` (squash of branch `fix/sync-user-heal-orphaned-plan`)

### Bug 3 — History boundary off-by-one (today's PR)

**Symptom:** Post-PR-#8 deploy. Scout configures a normal 5-year custom
backtest (`2021-05-20 → 2026-05-21`); modal fires: *"Custom backtest
history exceeds your tier limit. Current: 5.0 yr · Limit: 5 yr"*.

**Root cause:** `(end - start).days / 365.25 = 1827 / 365.25 = 5.0027`,
which strictly exceeds the 5-year Scout cap. Display rounds to "5.0 yr"
so the modal looks visually wrong — same numbers either side of the
divider. Math is correct; UX is misleading. Surfaces because
`GATING_ENABLED=true` on Railway (intentional per env-var review today).

**Fix:** One-week tolerance constant
`_HISTORY_TOLERANCE_YEARS = 7 / 365.25` in
[deps_entitlement.py](apps/api/app/api/deps_entitlement.py) +
[backtest.py](apps/api/app/api/routes/backtest.py); applied to both
history checks. 5-year backtests pass; 5.5-year still blocks.

### Gate hardening

Plus three preventions targeting the *bug class*, not just the bugs:

| Prevention | What it catches |
|---|---|
| Boundary-trio tests for history_too_long (`apps/api/tests/test_gating_backtest.py`) | Future regressions when caps move; the 5.0027 case is now codified |
| Boundary-trio tests for runs_exhausted | Off-by-one bugs in the quota counter |
| Postgres invariant test `test_orphan_user_detection_query_works` | Codifies the SQL that finds orphan Users; if the heal in sync-user is ever removed, this stays as the canary |
| Standalone script `apps/api/scripts/check_orphan_users.py` | Operational mirror — run against any environment to confirm clean state |
| `apps/api/CLAUDE.md` rule #9 | Auto-loaded for any agent touching auth — documents the orphan pattern + heal recipe |
| `docs/SHADOW_MODE_REVIEW.md` | Pre-enforcement checklist; the `gate_event` log aggregation command would have surfaced Bug 3 days earlier |
| Console.log diagnostic removed from `research-workspace.tsx` | PR #7 cleanup — served its purpose |

### Architectural decisions

- **Tolerance lives in `deps_entitlement.py` as `_HISTORY_TOLERANCE_YEARS`**, imported by `backtest.py` so the two history checks stay in lockstep.
- **Heal logic stays in `sync_user`**, not in `_create_user_with_plan`. The atomic-create path already commits both rows in one transaction; the only way to get an orphan is legacy data, which the lazy-heal addresses.
- **`GATING_ENABLED=true` is the intended production state**; today's review (`railway variables --service the_counselor | grep GATING_ENABLED` → `true`) confirmed it. The shadow-mode soak we should have done was skipped — `SHADOW_MODE_REVIEW.md` is now the gate for future flag flips.

### Backend tests grew

`420 → 425+` (3 history boundary, 2 runs boundary, 1 Postgres invariant).

---

## 2026-05-20 — Stages 3, 4a/b, 5a, 6a in one day

The biggest shipping day in the project. 28+ commits, 411 backend tests
(up from 319), six stage milestones, plus a forget-proofing layer.

### What shipped

**Stage 3 — Endpoint Gating + Upgrade UX** (6 commits)
- `require_entitlement` FastAPI dep + GATING_ENABLED flag (default off /
  shadow mode; emits `gate_event` log lines instead of 402s)
- `/api/backtest/run` gates: runs quota (5 custom/wk for Scout), custom-strategy
  universe + history caps (templates exempt — central Stage 1a invariant
  retested at the route layer)
- `/api/robustness/run` gate: test-name whitelist (Strategist gets 2 of 5;
  Quant unlimited)
- Market Pulse S&P 500 scope check on 8 per-ticker routes
  (`/api/company/{symbol}/*`, `/api/fundamental/*`, `/api/sentiment/{symbol}/*`)
  with `allow_anonymous=True` so anon browsing still works (legacy-anon
  user → Scout-tier; 402 fires with `is_anonymous=True`)
- `UpgradeModal` (10 copy variants) + `SoftPaywall` + 402 interceptor wrapping
  `fetchApi` → dispatches to a global event bus
- Naming fix: TIER_CAPS `robustness_tests` used `param_sensitivity` /
  `sub_period` / `benchmark` — actual schema literals are
  `parameter_sensitivity` / `subperiod` / `benchmark_comparison`. Without
  this, every Strategist+ would have hit `robustness_test_locked`.
- 24 new gating tests across backtest, robustness, market pulse, shadow mode

**Stage 4a — Community publish + attribution** (6 commits)
- `published_strategies` table — frozen public snapshot of a saved strategy.
  Decoupled from `saved_strategies` so editing the saved version doesn't
  leak. Snapshot includes metrics, universe, benchmark, equity curve
  (downsampled to 150 points).
- `attribution_visits` table — one row per `/s/<slug>?via=<handle>` click.
  Three lifecycle columns: `landed_at`, `converted_to_user_id` (set on
  signup via `livermore_vsid` cookie), `converted_to_paid_at` (set on
  Stripe `customer.subscription.created`).
- New endpoints under `/api/community/strategies/*` (mounted there NOT
  `/api/strategies/*` to avoid colliding with legacy PRD-02
  `strategy_storage.py`) + `/api/community/attribution/track`.
- Scout auto-publish wired into `saved_strategy_service.save_strategy`
  (every Scout save also creates a `published_strategies` row, best-effort).
- `/s/[slug]` public page — anonymous-viewable, fires
  `trackAttributionVisit` on mount when `?via` present, persistent signup
  CTA preserving handle.
- `ShareButton` (clipboard + `?via=<handle>`), `VerifiedBadge` (Quant gets
  blue check), `PublishModal` (Strategist+ explicit publish flow).
- Webhook extension: `customer.subscription.created` calls
  `mark_paid_conversion` to stamp `converted_to_paid_at`. Stage 5's
  Creator Program reads this column.
- 23 new tests covering publish + attribution + self-attribution rejection
  + first-touch wins.

**Stage 4b — Discovery + Clone** (1 commit)
- `PublishedStrategiesFeed` component on `/community` (sort: Trending / Newest;
  3-column responsive cards) above the existing PRD-02 legacy "Public
  Strategies" section. Anonymous-viewable.
- "Clone to workspace" button on `/s/[slug]` for authed users — copies
  `strategy_json` from the published row into a new `SavedStrategy`,
  redirects to `/workspace`. UpgradeModal fires on save quota.

**Stage 5a — Creator data layer + revshare + SEO scaffolding** (5 commits)
- 4 new tables: `stripe_invoices` (paid invoice ledger keyed on
  `Stripe invoice_id` — idempotent on webhook replay), `creators`,
  `creator_applications`, `creator_payouts`. `Plan.comped` boolean column
  for free Strategist comp during Creator Program.
- Stripe webhook now writes `stripe_invoices` rows on
  `invoice.payment_succeeded` (resolves Stripe customer_id → plans →
  user_id via `stripe_customer_id`).
- `revshare_service.py` — `compute_creator_revshare(creator_user_id)` =
  10% of first-year MRR (365 days from each referred user's
  `converted_to_paid_at`); excludes refunded invoices + self-attribution.
  `compute_creator_balance` = earned − sum of `CreatorPayout`.
- `apps/web/src/app/sitemap.ts` (lists 6 marketing surfaces + all
  `SEO_TEMPLATES`), `apps/web/public/robots.txt` (allows /, disallows
  /workspace + /account + /api/ + /admin + /creators/*).
- Global `openGraph` + `twitter` meta in root layout (`metadataBase`,
  title template, keywords).
- `StructuredData.tsx` component: `SoftwareApplicationLd`, `FAQPageLd`,
  `HowToLd`, `BreadcrumbListLd`.
- `/templates/[slug]` dynamic route with `generateStaticParams` — 3 sample
  landing pages (NVDA 200-day MA, AAPL RSI mean reversion, Mag-7 momentum
  rotation) prerender as static HTML, each with 3 FAQs + HowTo JSON-LD.
- 8 revshare tests including the spec acceptance criterion: `$228 annual
  prepay → $22.80 in revshare`.

**Stage 6a — Analytics + email plumbing** (8 commits)
- `posthog_service.py` (backend) + `analytics.ts` (frontend) — both with
  the "safe no-op" pattern. Lazy init, cached client, silent when
  `POSTHOG_API_KEY` / `NEXT_PUBLIC_POSTHOG_KEY` is empty. All `track()`
  / `capture()` calls fire through these wrappers; production with no key
  set has zero analytics overhead.
- Wired 10 events: `signup_completed`, `trial_started`, `backtest_started`,
  `backtest_completed`, `paywall_hit`, `checkout_completed`,
  `strategy_published`, `referral_landed`, `share_clicked`,
  `paywall_cta_clicked`.
- `AnalyticsProvider` (frontend) wraps `useSession` + `useSearchParams` to
  fire `identify` on auth + `page_view` on every navigation. Mounted under
  `<Suspense>` at root because `useSearchParams` would otherwise crash
  prerender (KNOWN_ISSUES rule #7-equivalent).
- `email_service.py` (Resend wrapper, same no-op pattern). Plain HTML +
  text templates for v1 (defer React Email). `make_unsub_token` /
  `verify_unsub_token` (HMAC-signed `<user_id>.<category>.<sig>`).
- `EmailPreference` model (per-user marketing toggles + global
  unsubscribed_at). `welcome.py` template (HTML + text, CAN-SPAM footer).
  Wired into `password_signup` + `google_oauth_callback` + `sync_user`
  on new-user paths.
- `/api/me/email-preferences` GET/PATCH + `/api/email/unsub?token=` public
  HMAC endpoint (returns 200 + styled HTML page regardless of token
  validity to prevent enumeration).
- `/account/email` page — three category toggles, optimistic UI,
  transactional-email explainer.
- H1 paywall A/B feature flag stub in `get_entitlements`: reads PostHog
  flag `paywall_variant` for Scouts (default `"A"`). Variant B →
  `history_window_years_custom=3`. Variant C → `universe_size_max_custom=3`.
  When PostHog isn't configured, returns default and behaves exactly like
  pre-Stage-6a. 7 tests cover deterministic assignment + tier filtering +
  error fallback.

### The forget-proofing layer

**`docs/DEFERRED.md`** — canonical list of items cut from Stage 3 / 4 / 5 / 6
specs, grouped by source stage. Each has a concrete trigger condition,
detection method (grep, DB query, calendar), and rough effort. Also a
pre-grouped Stage 5b + Stage 6b bucket for catch-up sprints.

**Three tripwire log lines** emit `DEFERRED_TRIGGER: <name> — <why>` when
conditions become real:
- `trial_day_7_email` / `trial_day_13_email` in `expire_trials_job`
- `soft_upsell_candidate` in the gating dep (every Scout paywall hit)
- `zh_email_templates` on first locale=`zh` signup

Grep with `railway logs --service api | grep DEFERRED_TRIGGER` to surface
the catch-up backlog.

### Scope cuts taken to keep the day shipping

Each stage spec was 400–600 lines as written. Cut to the revenue/loop-blocking
core for each:

| Stage | Original | Shipped (a) | Deferred |
|---|---|---|---|
| 3 | 14 deliverables incl. API access, ZH copy, asset-class gates | Core gates only; ZH cut; API access cut | Tier-aware sandbox; symbol-search locked tickers; commodity gate; supply-chain gate |
| 4 | 50+ deliverables incl. comments, follows, likes, moderation, dynamic OG | Publish primitive + `/s/[slug]` + attribution | Comments/follows/likes/moderation/dynamic OG/profile pages |
| 5 | 50 landing pages + comparison pages + creator UI + cron jobs | Data layer + revshare math + SEO scaffolding + 3 sample pages | 47 landing pages (editorial), comparison pages (legal), creator UI, payout/gate crons |
| 6 | PostHog dashboards + 8 emails + ZH + scheduler + Resend webhook | Wrappers + 1 email + 10 events + A/B stub + preferences UI | Remaining 7 emails, ZH copy, 4 cron jobs, Resend webhook, dashboard configs |

### Migration adjustments + production deploy fixes

Mid-day Railway deploy crashed twice:

1. **FastAPI 0.115 `status_code=204` strictness** — `DELETE /api/saved-strategies/{id}`
   declared `-> None` + `status_code=204`. FastAPI asserts at import time
   that 204 routes cannot have a response body; the `-> None` annotation
   makes it try to serialize `null`. Fix: `response_class=Response` +
   return `Response(status_code=204)`.

2. **FK type mismatch** — new Stage 1a tables (`anonymous_sessions`,
   `weekly_usage`, `saved_strategies`) had `ForeignKey("users.id")` on
   their `user_id` columns. Production `users.id` may have been created
   as `UUID` (PR #5 era); a `VARCHAR(36)` FK to a `UUID` column makes
   `Base.metadata.create_all` fail at startup. Fix: drop the FK entirely
   on all 3 tables. App-layer enforces user identity (community-tables
   pattern from Stage 1a's earlier fix). Added the rule to `apps/api/CLAUDE.md`
   as trap #1.

Both got post-mortems added to `docs/KNOWN_ISSUES.md`.

### Backend tests grew

`319 → 349 → 358 → 373 → 396 → 404 → 411` across the day.
- +24 Stage 3 gating tests (gating_backtest, robustness, market_pulse, shadow_mode)
- +23 Stage 4a tests (publish, attribution)
- +8 Stage 5a tests (revshare)
- +7 Stage 6a tests (A/B feature flag)
- +2 app_invariants tests early in the day (route inspection for the 204 trap)

### Architectural decisions on file

- **Path A for SavedStrategy:** new table separate from PRD-02
  `backtests.slug != null` mechanism. Snapshot semantics. Documented
  reasoning in `BUILDING_LIVERMORE_JOURNAL.md`.
- **Mount Stage 4a CRUD at `/api/saved-strategies` and `/api/community/strategies`**
  (not `/api/strategies`) to avoid colliding with the legacy PRD-02 router.
- **Universe + history caps apply only to custom strategies.** Templates
  exempt by design (the central Stage 1a invariant).
- **`GATING_ENABLED` default off (shadow mode)** — production currently
  emits `gate_event` log lines but allows requests through. Flip to true
  via env var when ready.
- **PostHog & Resend wrappers are safe no-ops by default.** Lazy init,
  cached client, silent when keys missing. Code ships today; the day env
  vars are set, events / emails start flowing.
- **Static OG image (not dynamic per-strategy) for v1.** Will upgrade to
  `next/og` when sharing volume justifies.
- **Plain HTML email templates for v1** instead of React Email.
- **50 SEO landing pages reduced to 3 sample pages.** The remaining 47 are
  editorial work (real prose, real data); shipping the renderer + 3 seed
  pages proves the pattern.
- **6 of 17 declared analytics events wired.** Remaining 11 are
  one-line-additions in existing code; deferred until PostHog dashboards
  show gaps.

### Current deployment state

- 6 stages shipped end-to-end. `main` is at commit `ce5492d`.
- 411 backend tests pass.
- Frontend builds clean. `/sitemap.xml`, `/s/[slug]`, `/templates/[slug]`
  (3 entries) all SSG.
- Railway deploy: ✅ healthy.
- Vercel deploy: ✅ healthy.
- PostHog: no API key set — events queue silently.
- Resend: no API key set — emails log `email_noop` lines for visibility.
- `GATING_ENABLED`: false (shadow mode); flip when ready.

### What's actually NOT done

`docs/DEFERRED.md` has the full list with triggers. Top items by next-likely-trigger:

1. First trial expires → wake up `trial_day_7_email` + `trial_day_13_email`
2. First creator applies → wake up the creator application form + admin queue
3. First 100 SEO-driven visits → time to write more landing pages
4. First user with `locale='zh'` → translate welcome email
5. ≥1500 Scouts signed up → flip the H1 A/B test live in PostHog UI

---

## 2026-05-07 — Merge, Validation & Bug Fixes

### Branch merge
- `feature/commodity-trading` merged into `main` via no-ff merge commit (9 commits, 16 files, 1,135 insertions)
- Pre-push validation: 51/51 tests, frontend build clean, backend smoke test, Python 3.9 compat check, Railway env var audit

### Bugs found and fixed during validation

#### Bug 1 — momentum_rotation LLM returns empty rules
- **Symptom:** Parsing "rotate into top 2 commodities by 3-month return" produced `rules: []` and `max_positions: null`
- **Root cause:** LLM system prompt described strategy type mapping but never told the model what to put in `rules[]` for momentum_rotation
- **Fix 1:** Added explicit instruction + concrete example to `_CHAT_PARSE_SYSTEM_PROMPT`: "top 2 by 3-month → rules=[{top_n:2, ranking_measure:'total_return', ranking_lookback_days:63}]"
- **Fix 2:** `_fix_momentum_rules()` post-processor in `parse_strategy_message()` — if LLM still returns empty rules for momentum_rotation, fills in top_n / ranking_lookback_days / max_positions from regex on the user message

#### Bug 2 — multi-asset backtest crashes with shape mismatch
- **Symptom:** `ValueError: Array conditional must be same shape as self` on any strategy with >1 ticker in the universe
- **Root cause:** `engine.py` line 163 used `pd.DataFrame.where(numpy_col_vector[:, None])` — pandas `.where()` does not broadcast `(n, 1)` → `(n, k)` on multi-column DataFrames. Never hit before because all prior strategies were single-asset.
- **Fix:** Replaced `weights.where(mask[:, None])` with direct row assignment `weights.loc[non_rebalance_dates] = np.nan` — no broadcasting needed

### Test suite
- Regression test added for multi-asset momentum_rotation weight generation
- Suite: 52/52 passing (up from 51)

### Verified end-to-end
- Query: "Every month, rotate into the top 2 commodities by 3-month return from GLD, SLV, USO, UNG, DBA."
- Parses correctly: strategy_type=momentum_rotation, universe=[GLD,SLV,USO,UNG,DBA], benchmark=DBC, top_n=2, ranking_lookback_days=63
- Backtest result: 48.4% total return, Sharpe 1.29, max drawdown -30.9%, benchmark (DBC) 50.9%

---

## 2026-05-04 — Commodity Trading + QA Agent (branch: `feature/commodity-trading`)

### Commodity Trading Support
| Area | Change |
|---|---|
| `strategy_parser.py` | `COMMODITY_TICKERS` set (25 ETFs); auto-selects `DBC` benchmark when ≥50% of universe is commodity ETFs; commodity name→ETF mappings in LLM prompt (gold→GLD, crude→USO, natural gas→UNG, agriculture→DBA, etc.); seasonality/rotation/carry keyword detection in regex fallback |
| `insights.py` | Commodity-specific regime notes and roll-yield/contango caveats injected into LLM system prompts and fallback explanation/sandbox review |
| `contracts.ts` | `commodityDemoStrategies`: 3 pre-seeded strategies (GLD 200-day trend, commodity momentum rotation, diversified commodity allocation) |
| `research-workspace.tsx` | Demo picker now has Equities / Commodities subsections |
| `i18n.ts` | `chatSupported` and `demoPrompts` updated EN + ZH |

### Bugs Fixed
| Bug | Fix |
|---|---|
| `commodityDemoStrategies` exported but not rendered | Imported and wired into demo picker in `research-workspace.tsx` |
| `main.py` startup crash on fresh SQLite DB | `create_all()` must run before `run_startup_migrations()` — swapped order |
| Backend running old code after branch switch | Killed old PIDs, restarted uvicorn |
| Local LLM key 401 | Updated `apps/api/.env` with valid OpenAI key |
| `generate_structured` failing on complex QA schema | Added `response_format: {type: json_object}` to all OpenAI requests in `llm_adapter.py` |
| 4 pre-existing async/sync mismatches in `test_strategy_parser.py` | Tests now call `_fallback` functions directly |

### QA Agent (`POST /api/qa/review`)
| Area | Detail |
|---|---|
| Schema | `QAReviewRequest`, `QAReviewResponse`, `QAIssue` with P0/P1/P2 severity and release recommendation enum |
| Service | Uses existing `get_llm_gateway()` with structured output; graceful fallback if LLM not configured |
| System prompt | QA rules: core flow first, backtest skepticism, assumption flagging, confirmed vs hypothesis, evidence gaps; explicit JSON schema embedded |
| Frontend | `/qa` page with full form (review type, area, flow, recent change, concerns, evidence, locale) + report display (verdict badge, issue cards with repro steps / expected vs actual / fix, regression checklist, missing evidence) |

### Backtest Credibility Warnings
Three checks run after every backtest and prepend to `result.warnings`:
- Sharpe ratio > 2.0 → look-ahead bias / data error flag
- Win rate > 80% with ≥ 10 trades → overfitting / survivorship bias flag
- Total return > 100% on window < 1 year → short-window noise flag

8 new tests in `test_metrics.py` — suite now 44/44 passing (up from 37+4 broken).

### Trust & Transparency Improvements
| Area | Change |
|---|---|
| Explanation prompt | Rewritten to require thorough analysis: market regimes that help/hurt, 2–4 genuine strengths, honest weaknesses, 3–4 concrete next iterations, specific disclaimer naming data-snooping risk |
| Strategy Preview | Yellow "Review before running" callout shows benchmark, date range, and costs before first backtest run |
| Backtest tab | Persistent disclaimer banner below results: hypothetical nature, execution assumptions, research-only purpose |
| i18n | New keys for defaults callout and backtest disclaimer in EN + ZH |

### Architecture Decisions
- **Commodity benchmark threshold:** ≥50% of universe tickers in `COMMODITY_TICKERS` → auto-select DBC
- **QA agent uses existing LLM adapter** — no Anthropic SDK dependency; works with any OpenAI-compatible key
- **`response_format: json_object`** added to all `generate_structured` calls — prevents model from wrapping JSON in prose on complex schemas
- **Credibility warnings are non-strict** — Sharpe exactly 2.0 passes; only > 2.0 triggers

---

## 2026-05-03 — MVP Optimization (Areas 6–8)

### New Frontend Features
| Feature | Description |
|---|---|
| **Robustness Tab** | 5th tab in results; "Run All" button + peer tickers input; polls every 2s; shows up to 5 result tables |
| **Demo Picker** | 3 pre-seeded strategy cards above Chat Builder; loads strategy JSON + triggers quality fetch instantly |
| **VerdictBadge** | Color-coded: green=better/strong/robust, red=worse/weak/breaks_down, neutral=similar/acceptable |

### New / Changed Frontend Types (`contracts.ts`)
| Type | Added |
|---|---|
| `ParameterSensitivityRow` | New |
| `SubperiodRow` | New |
| `TransactionCostRow` | New |
| `BenchmarkComparisonRow` | New |
| `PeerTickerRow` | New |
| `RobustnessResults` | New |
| `RobustnessJobResponse` | New |
| `DemoStrategy` | New |
| `demoStrategies` | 3 pre-seeded strategies: NVDA MA filter, QQQ RSI, mega-cap momentum |

### New API Functions (`api.ts`)
| Function | Endpoint |
|---|---|
| `runRobustness()` | `POST /api/robustness/run` |
| `getRobustnessJob()` | `GET /api/robustness/{run_id}` |

### Tests Added
| File | Tests | Coverage |
|---|---|---|
| `tests/test_metrics.py` | 10 | compute_metrics, trade diagnostics, buy-and-hold |
| `tests/test_data_quality.py` | 7 | all DataQualityService check paths (mocked DB) |
| `tests/test_robustness.py` | 6 | output shapes for each robustness test type |
| **Total** | **24 passing** | |

### Bugs Fixed This Session
| Bug | Fix |
|---|---|
| Quality gate blocked before data fetch ("No cached data for MUA") | Backtest route now auto-fetches uncached tickers before quality gate |
| Quality badges never appeared after LLM parse | `fetchQualityForSymbols` called after every parse, not just manual universe edits |
| `iteration_count` never sent to sandbox reviewer | Added to `api.ts` `reviewSandbox()`, tracked in workspace state |
| `Mapped[str \| None]` syntax error on Python 3.9 | Changed to `Mapped[Optional[str]]` in `robustness_job.py` |
| Frontend page crash after sandbox schema change | Updated `contracts.ts` + `research-workspace.tsx` field references |

### Discipline Applied
- All TypeScript types defined before UI components — no schema drift
- `npm run build` verified before every commit — no broken builds pushed
- Backend tests run and pass before commit

---

## 2026-05-03 — MVP Optimization (Areas 1–4)

### New API Routes
```
GET  /api/data/quality/{symbol}     — DataQualityReport for a ticker
POST /api/robustness/run            — Launch async robustness job (202 + run_id)
GET  /api/robustness/{run_id}       — Poll robustness job status + results
```

### New / Changed Schemas
| Schema | Change |
|---|---|
| `DataQualityReport` | New — status, warnings, blocking_errors, coverage metrics |
| `BacktestQualityGate` | New — aggregated quality across universe + benchmark |
| `BacktestMetrics` | Added: profit_factor, avg_winner, avg_loser, median_trade_return, streaks, buy_and_hold_return |
| `BacktestResult` | Added: buy_and_hold_curve |
| `SandboxReviewResponse` | Added: confidence_level, overfitting_risk (enum), data_quality_concerns, main_reasons_to_trust/distrust, required_next_tests, suggested_next_experiments |
| `SandboxReviewRequest` | Added: iteration_count |
| `RobustnessRunRequest` | New |
| `RobustnessJobResponse` | New |

### New Services / Models
| File | Purpose |
|---|---|
| `app/models/robustness_job.py` | SQLAlchemy model for async job state |
| `app/services/robustness_service.py` | 5 robustness tests: parameter sensitivity, sub-period, transaction cost, benchmark comparison, peer ticker |
| `app/api/routes/robustness.py` | POST /run (202 + BackgroundTasks) and GET /{run_id} |

### Architecture Decisions
- **Robustness: async** — POST returns `run_id` immediately; FastAPI BackgroundTasks executes tests; frontend polls GET endpoint
- **Anti-overfitting memory** — no auth/user concept → frontend passes `iteration_count` to sandbox reviewer; LLM warns on count > 3
- **Data quality gate** — runs on cached data only (no extra API calls); blocks if any ticker has blocking errors; attaches warnings to BacktestResult

---

## 2026-04-30 — MVP Deployed

### Infrastructure
| Service | URL | Notes |
|---|---|---|
| Backend (Railway) | `https://thecounselor-production.up.railway.app` | FastAPI + PostgreSQL |
| Frontend (Vercel) | `https://the-counselor-web.vercel.app` | Next.js |

### Railway Environment Variables
| Variable | Value |
|---|---|
| `DATABASE_URL` | Railway internal PostgreSQL URL |
| `ALPHA_VANTAGE_API_KEY` | Set (rotate if sharing project access) |
| `ALLOWED_ORIGINS` | `https://the-counselor-web.vercel.app` |
| `NEXT_PUBLIC_API_BASE_URL` | `https://thecounselor-production.up.railway.app` *(remove — frontend-only var)* |

### Vercel Environment Variables
| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://thecounselor-production.up.railway.app` |

### API Routes
```
POST /api/chat/strategy
POST /api/backtest/run
GET  /api/backtest/{backtest_id}
POST /api/insights/explain
POST /api/review/sandbox
GET  /api/symbols/search
GET  /api/data/daily/{symbol}
GET  /health
```

---

---

## 2026-05-01 — LLM Integration + i18n + A-Share Support

### What shipped today

#### 1. LLM Gateway (branch `LLM_chatbot` → merged to `main`)
- `apps/api/app/services/llm_adapter.py` — OpenAI-compatible HTTP gateway with structured output validation, graceful fallback when LLM is disabled or fails
- `apps/api/app/services/strategy_parser.py` — LLM converts chat/markdown → strategy JSON; regex fallback always present
- `apps/api/app/services/insights.py` — LLM generates strategy explanation and skeptical sandbox review after each backtest

**Railway env vars required to activate LLM:**
| Variable | Value |
|---|---|
| `LLM_PROVIDER` | `openai_compatible` |
| `LLM_API_KEY` | OpenAI API key |
| `LLM_BASE_URL` | `https://api.openai.com/v1` |
| `LLM_MODEL` | `gpt-4o-mini` |

LLM is **opt-in** — if vars are absent, all endpoints fall back to deterministic regex/heuristic logic with no crash.

#### 2. Price Cache Fixes
- Upserts chunked to 1000 rows to stay under PostgreSQL's 65535 parameter limit
- `ensure_history` now falls back to cached data when Alpha Vantage refresh fails but cache covers the requested date range
- `price_bars.volume` widened from `INTEGER` to `BIGINT` via idempotent startup migration (A-shares trade billions of shares daily)

#### 3. Strategy Parser Improvements
- LLM prompt now uses sensible defaults (benchmark, dates, capital) so only `universe` and `strategy_type` trigger `needs_clarification`
- Indicator alias mapping: MACD → `moving_average_crossover`, golden cross, RSI, breakout, etc.
- Chinese indicator keywords added: 价格高于均线 → `moving_average_filter`, 均线交叉/金叉 → `moving_average_crossover`, etc.
- Index name → ETF ticker mapping: S&P 500 → SPY, Nasdaq → QQQ, A-shares default benchmark → `510300.SHH`
- Today's date injected into every chat prompt so LLM uses correct `end_date` instead of training cutoff
- Default window: `end_date = today`, `start_date = today - 1 year`

#### 4. Pre-Backtest Ticker Validation
- Backtest route validates all universe tickers against Alpha Vantage before running
- Returns a clear error message for unknown symbols instead of a cryptic mid-backtest crash

#### 5. Chinese/English i18n
- `apps/web/src/lib/i18n.ts` — ~120 strings in `en` and `zh` (Simplified Chinese)
- `LocaleProvider` React context backed by `localStorage`
- `LanguageSwitcher` toggle in the header
- All 5 frontend components updated to read from locale context
- Backend: `locale` field on all 4 LLM request schemas; LLM responds in Chinese when `locale=zh`

#### 6. A-Share Support
- Shanghai (`.SHH`) and Shenzhen (`.SHZ`) tickers work end-to-end
- Default benchmark auto-switches to `510300.SHH` (CSI 300 ETF) when A-share tickers detected
- Volume BIGINT migration handles high-volume Chinese stocks

#### 7. Rebrand
- App renamed from **StrategyLab AI** → **Livermore** (EN) / **谋士** (ZH)
- Git author fixed: `grepJimmyGu`

### Key bugs fixed today

#### Price data "No price data returned" (NVDA)
**Root cause:** Cache was stale (last data Dec 2025, today May 2026), refresh failed due to old free-tier API key, error re-raised unconditionally.  
**Fix:** `ensure_history` checks if cached data covers the requested date range before re-raising; upgraded Alpha Vantage to premium key.

#### PostgreSQL 65535 parameter limit
**Root cause:** Full history upsert (~6000 rows × 12 cols) exceeded limit in one statement.  
**Fix:** Chunked to 1000 rows per batch.

#### LLM always returning `needs_clarification`
**Root cause:** System prompt didn't tell LLM about default values for benchmark, dates, capital — LLM flagged everything as required.  
**Fix:** Explicit defaults listed in prompt; only `universe` and `strategy_type` are truly required.

#### Wrong end_date (Oct 2023 instead of today)
**Root cause:** LLM used its training cutoff as "today". Chat parse prompt didn't inject real date.  
**Fix:** `Today: {date.today()}` added to user prompt (markdown parser already had this).

#### A-share volume INTEGER overflow
**Root cause:** `price_bars.volume` was `INTEGER` (max ~2.1B); A-shares trade 3–8B+ shares/day.  
**Fix:** `ALTER TABLE price_bars ALTER COLUMN volume TYPE BIGINT` on startup.

#### CSI 300 index not fetchable
**Root cause:** `000300.SHH` is a raw index — Alpha Vantage only serves ETFs/stocks.  
**Fix:** Changed default A-share benchmark to `510300.SHH` (Huatai-PineBridge CSI 300 ETF).

---

## Key Bugs Fixed (2026-04-30)

### 1. `ALLOWED_ORIGINS` JSONDecodeError on startup
**Symptom:** Healthcheck failed — app crashed before binding to port.  
**Root cause:** pydantic-settings v2 JSON-parses `list`-typed fields before field validators run. `ALLOWED_ORIGINS` env var was a plain URL string, not valid JSON.  
**Fix:** Changed `allowed_origins: list[str]` → `allowed_origins: Union[str, list[str]]` in `apps/api/app/core/config.py`. This marks the field as non-complex, bypassing JSON parsing and passing the raw string to the existing `field_validator`.  
**Commit:** `d43352b`

### 2. CORS blocking frontend requests
**Symptom:** "Failed to fetch" on Vercel frontend.  
**Fix:** Added `https://the-counselor-web.vercel.app` to `ALLOWED_ORIGINS` in Railway variables.

### 3. Frontend pointing at localhost
**Symptom:** "Failed to fetch" — frontend fell back to `http://127.0.0.1:8001`.  
**Fix:** Set `NEXT_PUBLIC_API_BASE_URL=https://thecounselor-production.up.railway.app` in Vercel environment variables.

---

## 2026-05-13 to 2026-05-15 — Fundamental Analysis Overhaul (PRD-08c/d/e) + Evaluation Dashboard

### What shipped

#### PRD-08c → superseded by Evaluation Dashboard
Originally built Piotroski F-Score (9-signal), Altman Z-Score, QSV insight paragraphs, and industry percentile. Fully functional but replaced by the 3-question Evaluation Dashboard (Health / Valuation / Trend) which provides better UX. Redundant pipeline removed — 3 duplicate FMP API calls per page load eliminated. EV/EBITDA now sourced directly from `key_metrics_raw` into `FinancialCheckSection`.

#### PRD-08d — Business Model Section ✅
- `RevenueSegmentService`: fetches FMP `/stable/revenue-product-segmentation` + `/revenue-geographic-segmentation`, caches 24h in `revenue_segments` table. Handles both FMP flat and nested dict formats.
- Frontend: Recharts stacked `BarChart` (5yr product segments) + `PieChart` donut (geographic mix) + business characteristics chips (revenue model / customers / cyclicality / pricing power)
- Bug fixed: FMP stable returns nested `{"Apple": {"iPhone": ..., "Services": ...}}` format — parser now handles both.

#### PRD-08e — Market Position Section ✅ (partial)
- **Supply chain**: Extended 10-K LLM prompt to extract `upstream_suppliers` and `downstream_customers`. Fuzzy-match against `symbols` table for clickable badge links.
- **Competitor groups**: `CompetitorGroupService` — LLM filters FMP peers by segment, fetches 5yr revenues for each, computes relative revenue share, classifies Dominant/Market Leader/Major Participant/Niche. 7-day cache. Per-segment tab UI with sparkline.

#### Asset Evaluation Dashboard (replaces PRD-08c display)
Three-question framework: **Health** / **Valuation** / **Trend** scorecards.
- Health: scored from `financial_check` (revenue growth 20%, margins 20%, FCF 20%, ROE 20%, balance sheet 20%)
- Valuation: FCF yield 25%, EV/EBITDA 25%, P/E 20%, PEG 15%, neutral DCF placeholder 6%
- Trend: real Alpha Vantage price data — 3M/12M momentum 35%, MA50/MA200 position 30%, RS vs SPY 20%, neutral 15%
- Final score: Health 40%, Valuation 30%, Trend 30% → Attractive / Moderately Positive / Neutral / Caution / Avoid
- Rule-based analyst summary, bull/bear cases, contradiction warnings, key metrics to watch
- Lazy trend fetch — Health + Valuation render instantly, Trend loads after with skeleton

#### Commodity Evaluation Framework ✅ (mock physical data + real ETF prices)
- `CommodityMetricsInput` type with 30+ fields: inventory percentile, supply-demand balance, futures curve, CFTC positioning, macro drivers
- Scoring: Health (inventory 30% + supply-demand 25% + spare capacity 15% + cost curve 15% + disruption 15%), Valuation (futures curve 25% + marginal cost premium 25% + 10yr percentile 20% + inventory-adj 20% + ratio 10%), Trend (momentum 25% + futures curve 20% + CFTC 20% + ETF flows 15% + macro 20%)
- `/commodities/[symbol]` page: Gold, WTI, Copper, Wheat with tab selector
- Real price trend from Alpha Vantage ETF proxies: GLD (Gold), USO (WTI), COPX (Copper), WEAT (Wheat)
- Physical market data (inventory, CFTC, futures curve) is mock/estimated — noted clearly in UI

#### New backend endpoints
- `GET /api/company/{symbol}/trend` — price trend from `price_bars` (no FMP call, pure DB)
- `GET /api/commodities/{commodity}/trend` — maps GOLD→GLD, WTI→USO, etc.
- `GET /api/admin/health-scores/status` — prewarm progress monitoring
- `POST /api/admin/refresh-bi/{symbol}` — invalidate 10-K BI cache
- `POST /api/admin/warmup-commodity-etfs` — load GLD/USO/COPX/WEAT bars

#### Key bugs fixed in this sprint
| Bug | Fix |
|---|---|
| FMP `/profile` returns no price | Added `GET /stable/quote` live price fetch bypassing 24h cache |
| `symbol_health_scores` always 0 rows | `db.bind` deprecated in SQLAlchemy 2.0 → silent failures. Fixed: `engine.begin()` for all DB writes in health/segment/competitor services |
| Revenue segments showing `['fiscalYear']` | FMP stable API uses nested dict format. Parser now handles both flat and nested |
| `upstream_suppliers: [{name: "null"}]` | LLM extracted JSON string literal "null". Added filter for null/empty names |
| FMP peers include NXT, RIME, TBCH (wrong) | Filtered peers through `symbols` table — non-universe tickers dropped |
| `cash_quality` signal wrong for AAPL | FMP stable uses `netCashProvidedByOperatingActivities` not `operatingCashFlow` — added fallback key |
| Commodity ETFs COPX/WEAT not loaded | Added `_warmup_commodity_etfs()` startup background task |
| `useState` used before import | Fixed import order in `_market-position-section.tsx` |
| Missing `Suspense` on `useSearchParams` | Split `CompanyPage` into inner + Suspense wrapper |

### Current deployment state
- Frontend: Vercel (auto-deploy on push)
- Backend: Railway (PostgreSQL + FastAPI)
- `price_bars`: GLD (5,402 bars), USO (5,053 bars), COPX (4,043 bars), WEAT (3,685 bars)
- `symbol_health_scores`: being populated on-demand per page load (no prewarm — removed as redundant)
- `company_business_intelligence`: auto-invalidates stale rows (missing supply chain fields) on startup

### Architecture as of 2026-05-15

```
/stocks/[ticker] Overview tab
├── Company header + live price (FMP /stable/quote)
├── Evaluation Dashboard (Health / Valuation / Trend)
│   ├── Health score: from financial_check (revenue, margins, FCF, ROE, balance sheet)
│   ├── Valuation score: from financial_check (P/E, EV/EBITDA, FCF yield, PEG)
│   ├── Trend score: from Alpha Vantage price_bars (lazy fetch)
│   └── Final analyst summary, bull/bear, contradiction warning
├── Business Model (FMP revenue segments + geographic mix + characteristics chips)
├── Market Position (FMP peers + 10-K supply chain + competitor revenue share tabs)
└── News & Sentiment tab

/commodities/[symbol]
├── CommodityAssetCard (spot price via ETF proxy + snapshot metrics)
├── Three scorecards: Physical Market Health / Valuation / Market Trend
├── Metric detail panels (expandable)
└── Final analyst summary with bull/bear/contradiction

Data sources:
  FMP Starter plan: /profile, /quote, /income-statement, /cash-flow-statement,
    /balance-sheet-statement, /key-metrics-ttm, /revenue-product-segmentation,
    /revenue-geographic-segmentation, /stock-peers
  Alpha Vantage: price_bars (daily adjusted OHLCV) for stocks + ETF proxies
  SEC EDGAR: 10-K filings for business intelligence extraction
  LLM (gpt-4o-mini): 10-K extraction for business summary, supply chain,
    growth drivers, key risks, competitor segment filtering
```

---

## 2026-06-16 — Signal Catalog v2 backfill: MA/MACD + RSI/Stoch/ADX event primitives (PRD-22b slices 1-2)

> This chronological log skipped late-May → mid-June; that history lives in
> `agent-system/WORK_LOG.md` (session checkpoints) and
> `docs/BUILDING_LIVERMORE_JOURNAL.md` (Episodes 28-41 — Sprint 1 product
> flow, PRD-16a/b/c Custom Mode, PRD-19 notifications, PRD-23 Market
> Screener, the June outages). Resuming the chronological log here.

### What shipped (PR #215, catalog 69 → 87 primitives)

The Market Screener (PRD-23a/b) went live on a real S&P snapshot, lifting the
catalog freeze. These are the first two slices of the PRD-22b indicator-family
backfill — each turns a raw indicator *scalar* into the event/cross/level/regime
primitives the industry actually trades:

- **Slice 1 — MA + MACD events (9):** `price_above_ma` (LEVEL), `price_ma_cross_up`/`_down` (CROSS), `golden_cross`/`death_cross` (CROSS), `ma_slope_positive` (LEVEL); `macd_signal_cross` (CROSS), `macd_histogram_flip` (EVENT), `macd_zero_line_cross` (CROSS).
- **Slice 2 — RSI + Stochastic + ADX/DMI events (9):** `rsi_oversold`/`overbought` (LEVEL); `stoch_k_d_cross` (CROSS), `stoch_oversold_cross_up`/`overbought_cross_down` (EVENT); `adx_regime` (REGIME), `adx_rising` (LEVEL), `di_cross_bullish`/`bearish` (CROSS).

All 18 are local `TechnicalSignalProvider`s → auto-join the daily screener snapshot. Encoding matches the engine's `_apply_rule_threshold` (CROSS ±1/0, EVENT fires, LEVEL 1-while-true, REGIME discrete code via `equals`). Descriptions sourced from the v2 catalog spec's own prose (editorial gate = PR review). Extracted `_adx_components` as the single ADX source-of-truth for the `composes=["adx"]` contract. 22 new tests; **1796 backend tests green**.

### Key bugs fixed (build-time — correct providers, degenerate test fixtures)

- **Pure monotonic rally → RSI = NaN** (avg_loss = 0 → divide by zero), not 100. Fixture needs pullbacks.
- **Perfectly linear trend → ADX flatlines** (constant DX → `ewm(constant)` is flat) → `adx_rising` never True. Fixture needs a choppy→trend regime change.
- **Monotonic move with `high==low==close` → %K saturates 0/100** → stochastic cross never transitions. Fixture needs an oscillating (triangle) series.
- **Provider refinement:** stochastic zone-crosses now gate on the `%D` signal line, not `%K` (which whips out of the oversold/overbought zone off a sharp turn, silently never firing).

### Editorial follow-ups (carried to PROJECT_BACKLOG §4)

- `macd_histogram_flip` emits a **byte-identical** series to `macd_signal_cross` (kept distinct only by `output_kind`) — confirm or switch to a histogram-inflection detector.
- `intent_group` **auto-derives from category** on all new primitives (unused in UI), pending the intent-taxonomy deep research Mr Gu is running.

### Deferred

Slices 3-6 (Bollinger, Supertrend + Anchored VWAP, momentum z-scores + Heikin-Ashi, divergences via **numpy** peak/trough) scoped to the primitive in PROJECT_BACKLOG §4. Fundamental/events family parked pending an earnings-calendar source.

Docs: PR #216 (this log + LEARNINGS "Signal primitives + indicators" + Journal Episode 41).

---

## 2026-06-16 (cont.) — Signal Catalog v2 backfill: Bollinger / Supertrend+AVWAP / momentum+Heikin-Ashi / divergence primitives (PRD-22b slices 3-6)

### What shipped (PR #218, catalog 87 → 110 primitives)

The remaining four indicator-family slices, finishing the technical half of the
PRD-22b backfill. Same pattern as slices 1-2 — each raw indicator *scalar*
decomposes into the event/cross/level/regime/divergence primitives the industry
trades. All 23 new ones are local `TechnicalSignalProvider`s → auto-join the daily
screener snapshot + scan:

- **Slice 3 — Bollinger events (6), all `composes=["bbands"]`:** `bb_bandwidth` (VALUE), `bb_squeeze` (REGIME), `bb_squeeze_fire` (EVENT ±1), `bb_walk_upper` (EVENT), `bb_tag_upper`/`bb_tag_lower` (EVENT). %B is intentionally **not** re-added (the existing `bbands` primitive already emits it). Extracted a shared `_bollinger_bands` helper and refactored `bbands` onto it (the composes contract).
- **Slice 4 — Supertrend ×3 + Anchored VWAP ×3:** `supertrend` (VALUE), `supertrend_flip` (EVENT ±1), `supertrend_above_price` (LEVEL); `anchored_vwap` (VALUE), `distance_to_anchored_vwap` (DISTANCE), `price_above_anchored_vwap` (LEVEL). Supertrend uses a stateful O(n) carry-forward (`_supertrend` helper). AVWAP v1 anchors to a trailing window; the fixed-date / most-recent-earnings anchor is **deferred** (needs the earnings-calendar source).
- **Slice 5 — momentum_acceleration (VALUE) + Heikin-Ashi ×3:** `heikin_ashi_trend` (REGIME), `heikin_ashi_consecutive` (VALUE, signed run length), `heikin_ashi_color_flip` (EVENT ±1). `_heikin_ashi` helper; HA carries a `smoothing` param (the model requires ≥1 parameter, and "smoothed HA" is the spec's own variant). `momentum_12_1` was **skipped** (already ships as `time_series_momentum`).
- **Slice 6 — numpy peak/trough detector (`_pivot_indices`, `_divergence_signal`; NOT scipy, which isn't a pinned dep) + 7 DIVERGENCE primitives:** `macd_bullish_divergence`, `macd_bearish_divergence`, `rsi_bullish_divergence`, `rsi_bearish_divergence`, `rsi_hidden_bullish_div`, `obv_divergence_bullish`, `obv_divergence_bearish`. Each is unidirectional (+1 bullish / -1 bearish), held `order` bars from confirmation so the daily snapshot catches a recently-formed divergence.

Encoding still matches the engine (CROSS/EVENT ±1, LEVEL 1-while-true, REGIME discrete code). Descriptions sourced from the v2 catalog spec's own family prose (editorial gate = PR review); `intent_group` continues to auto-derive from category (unused in UI), pending the intent-taxonomy research. Helper extractions across the whole backfill for the composes contract: `_macd_lines`, `_adx_components`, `_bollinger_bands`, `_supertrend`, `_heikin_ashi`. 4 new test files (one per slice) — `test_bollinger_event_providers.py`, `test_supertrend_avwap_providers.py`, `test_momentum_heikin_ashi_providers.py`, `test_divergence_providers.py` (~39 new tests). **Full suite: 1965 passed, 20 skipped; static-import smoke: 123 routes OK.**

### Key bugs fixed (caught in pre-test smoke, not a test failure)

- **`momentum_acceleration` measured trend magnitude, not acceleration.** It first compared raw **cumulative** returns (`ret_3mo - ret_9mo`). That's biased: a 9-month cumulative return is mechanically larger than a 3-month one (compounding), so a strong *steady* uptrend read as ≈ -38. **Fix:** compare per-month return **rates** (`ret_3mo/3 - ret_9mo/9`) — accelerating → positive, steady → ~0, fading → negative.

### Deferred (remaining PRD-22b)

- **Fundamental + Events family** (PEAD, days-to/since-earnings, est-revision cross, insider surge) — needs an earnings-calendar data source.
- **2 cross-sectional momentum z-scores** (`momentum_12_1_zscore`, `momentum_composite_zscore`) — need universe standardization (MSCI-style, per-symbol snapshot can't compute).
- **2 RSI failure swings** — a distinct multi-point Wilder pattern, not a pivot divergence.

---

## 2026-06-17 — Market Screener: Discover → Track (PRD-23c PR1 + PR2)

### What shipped

Turns a one-time screener scan into a **standing screen**: save it, and the cron
alerts you when a NEW name enters the matched basket. Reuses the PRD-19
notification stack wholesale (no new machinery).

- **PR1 (#220) — backend core (save → track → notify):** `screen_basket_member`
  table (append-only membership → current basket + entrant/exit history);
  `saved_screen_service.rescan_and_diff()` (re-scans via the SAME `scan()` the
  live route uses; transition-only; idempotent per `as_of_date`);
  `POST /api/screen/save` (Strategist+ gated via the new `screen_tracking_locked`
  402; standing-universe only; seeds the initial basket silently);
  `monitor_saved_screens` cron (23:30 UTC, gated by `SCREENER_SNAPSHOT_ENABLED`;
  one `SignalEvent` + in-app banner + best-effort email per new entrant; sync
  def on APScheduler's threadpool — traps #21/#22 safe). 12 tests.
- **PR2 (#221) — the UI half:** `GET /api/screen/saved` + `/saved/{id}` (basket +
  entrant/exit history, owner-gated 404); the disabled "Coming soon" button →
  a working **"Save + track"** CTA (saves the composed screen, "✓ Tracking —
  watching N names" confirmation, Strategist+ gate for anonymous, Scout 402 →
  upgrade modal); `saveScreen`/`getSavedScreen`/`listSavedScreens` api + types.
  +5 backend e2e (incl. Scout→402, non-owner→404) + 2 vitest; full suite **1982
  passed**, 126 routes, `npm run build` clean.

### Known rough edge to fix next (PR2c)

A saved screen is a `SavedStrategy` (`kind="screen"`), and
`GET /api/strategies` returns ALL of a user's SavedStrategies with **no filter**
— so a saved screen currently **leaks into "My Strategies"** and would render
broken on the strategy-detail page (which expects a backtest). PR2c must filter
screens out of that list (or route them to their own view) AND ship the
standalone `/screens/[id]` dashboard + "My Screens" list. This is the next task
(see `agent-system/WORK_LOG.md`).

### Deferred

- **PR2c** — the screen dashboard/list + the rough-edge fix above (NOT optional;
  spec §3.3 DoD).
- **PR3** — intraday snapshot (`resolution='intraday'`), genuinely optional (the
  spec's "the option"); daily screening already works.

