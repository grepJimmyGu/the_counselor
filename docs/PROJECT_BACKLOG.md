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
| Set `SCREENER_SNAPSHOT_ENABLED=true` on Railway | When PRD-23b ships the screener UI (or to run the real live-data S&P demo). The 23:00 UTC `signal_snapshot_warm` cron is registered but no-ops until this is set, so it adds zero load pre-launch. First enable warms ~52 primitives × 525 S&P symbols ≈ 27k rows daily from cached bars. | Railway env var (PRD-23a slice 2b) | 1 min |

---

## 3. Git / branch hygiene

| Item | Why it's here | Disposition |
|---|---|---|
| Stale `railway/fix-deploy-b1c14b` on remote | Auto-PR from Railway, merged but not deleted | Delete: `gh api -X DELETE repos/grepJimmyGu/the_counselor/git/refs/heads/railway/fix-deploy-b1c14b` |
| Stale `railway/fix-deploy-bce8d1` on remote | Same | Same |
| `codex/improve-chat-builder` branch (local worktree) | Codex agent's parallel chat-builder work from May 19-20 (Episode 17), never merged | Decide: merge, rebase + merge, or close. Likely superseded by [build_specs/research_chat_v2.md](../build_specs/research_chat_v2.md) — review before discarding. |

---

## 4. Open product decisions

| Decision | Context | Status |
|---|---|---|
| Chat v2 (Research Partner) | [`build_specs/research_chat_v2.md`](../build_specs/research_chat_v2.md), 660 lines, Year-1 proposal | Awaiting go/no-go. Phasing in §6 — 3 phases × ~4 weeks. Untracked file; will need to be committed before Phase 1 starts. |
| PRD-05 `not_supported` strategy handling | Strategy parser returns `not_supported` when LLM can't map the request to a backend strategy type. UX redirect TBD. | Low priority, in discussion. No Stage equivalent yet. |
| Drop `robustness_jobs.user_id` zombie column | Schema drift item #10 above | Schedule when convenient; not urgent. |
| Live commodity spot prices on `/commodities/[symbol]` | Page displays $/oz, $/bbl (commodity spot units). FMP `useLiveQuotes` returns ETF share prices (GLD, USO, COPX, WEAT) — different scale. Overriding `spotPrice` with the ETF quote re-introduces the WTI $133 vs $83 bug fixed earlier. Deferred 2026-05-21 after the live-quote rollout. | Skip until a live commodity-spot data source exists (Alpha Vantage commodity API, FMP futures plan, or a backend conversion factor). Option B from the rollout — supplementary "ETF proxy: $X ▲%" chip alongside the spot — is still available if visual freshness becomes more important than data fidelity. |
| ~~Signals v0 Phase B (daily cron + email alerts + signal-unsub) — paused for reshape~~ | ✅ **Reshaped and shipped as PRD-19 Phase B on 2026-06-08/09** in 5 sequential PRs (#150 Mark-as-Executed → #152 dispatcher wiring → #153 prefs + UTC fix → #154 daily digest → #155 unsub webhook). End-to-end backend retention loop in place: cron flips signal → SignalEvent + dispatch → user clicks Mark-as-Executed → PostHog `notification_dispatched` joins against `notification_executed` on `signal_event_id` for latency_seconds. Three latent bugs from the original PR #88 caught pre-merge: wrong `send_email` signature in dispatcher, literal `{{unsubscribe_url}}` tokens in email body, in-memory throttle counters resetting across cron ticks. Plus drive-by trap #16 fix in signal_cron. | Done. See WORK_LOG.md "Current Session" + Episode 35 in BUILDING_LIVERMORE_JOURNAL.md. Frontend (Steps 5+6) remains — tracked separately below. |
| ~~**PRD-19 Phase B frontend (Steps 5+6)** — NotificationBanner + MarkAsExecutedButton + NotInvestmentAdviceFooter bricks; NotificationSettingsForm + `/account/notifications` page~~ | ✅ **Shipped 2026-06-09 in PR #157** as a single bundle (Step 5's banner deep-links to Step 6's settings page, so a 2-PR stack would need typed-route casts only to remove them in the follow-up). 4 new bricks + the page; 24 new component tests; 99 frontend tests total, build clean. Architectural note: inlining `<MarkAsExecutedButton />` on each banner row (instead of on `/strategies/[slug]`) avoids the legacy-`BacktestRecord` vs new-`SavedStrategy` ID-surface mismatch. | Done. Remaining operational follow-ups in WORK_LOG.md "Next session" block: PostHog dashboard, email-client QA, `CAN_SPAM_ADDRESS` + `EMAIL_UNSUB_SIGNING_KEY` env vars on Railway. |

### Queued PRD packets (not yet started)

| Packet | Scope | Status |
|---|---|---|
| ~~**Custom Mode (PRD-16a / 16b / 16c)** — Signal Library + Composer + Active Execution~~ | ~~3-PRD sequential packet, 5–7 weeks total.~~ | **PRD-16a shipped 2026-06-09** in 4 sequential PRs (#161 catalog + schema + GET endpoint → #163 46 SignalProvider impls + preview endpoint → #164 KB match-templates endpoint + per-template metadata → #165 frontend bricks). Backend: 55 catalog primitives, `GET /api/signal-primitives` + `GET /preview` + `POST /signal-combos/match-templates`, 1316 backend tests (+135). Frontend: 4 bricks + standalone `/signal-library` page, 121 vitest tests (+22). **PRD-16b (composer UI)** + **PRD-16c (intraday + active execution)** remain in the packet — see HANDOFF for sequencing. PRD-16c depends on PRD-19 (done) + PRD-16a (done) + PRD-16b on `main`. |
| ~~**PRD-16b — Custom Build composer UI + multi-rule fold**~~ | ~~Drag-and-combine canvas consuming PRD-16a's catalog.~~ | **PRD-16b shipped 2026-06-09** in 3 sequential PRs (#167 backend schema + engine fold → #168 canvas + FlowDefinition + 4 bricks → #169 converter + symbol picker + "Use these defaults" wiring). Backend: `StrategyRule.{primitive_id, primitive_params, logic_with_prior}` + `custom_build` strategy_type + `_evaluate_custom_build_block` with left-to-right AND/OR fold; 1316→1334 backend tests, 0 regressions on all 22 existing strategy types (pitfall C verified). Frontend: `custom_build_mode` FlowDefinition + `<CustomBuildCanvas>` (3-pane: catalog/rules/recommendations) + `<CustomBuildRuleCard>` + `<CustomBuildRuleComposer>` + `<CustomBuildActiveExecutionScaffold>` (pitfall B placeholder) + canvas→`StrategyJson` converter + `applyTemplateThresholdsToRules`; 121→151 vitest tests. |
| ~~**PRD-16c — Intraday + multi-tier exits + active execution + live dashboard**~~ | ~~Adds intraday data support (5/15/30/60-min bars), multi-tier exit ladder, per-position state tracking, intraday monitor cron, live dashboard.~~ | **PRD-16c shipped 2026-06-09 (late)** in 8 sequential PRs (#171 IntradayBarService + intraday_bars cache → #172 engine `bar_resolution` + `ExitTier` schema + multi-tier ladder evaluator → #173 PositionState model + migration → #174 monitor cron + per-position throttle → #175 3 dashboard endpoints → #176 position-event email + catalog intraday metadata → #177 composer `<BarResolutionPicker>` + `<ExitLadderEditor>` → #178 live dashboard bricks). Plus 2 UX wire-up PRs in the same session: #179 replaced Chat-builder tile with "Build from scratch" on `<EntryModePicker>` + extended `custom_build_mode` chain (compose → backtest → review → save), #180 bridged the slug ↔ SavedStrategy UUID gap on `/api/strategies/{slug}` so `<ActiveExecutionDashboard>` renders conditionally on the public strategy-detail page. Backend: 1334 → 1431 tests (+97). Frontend: 151 → 182 tests (+31). 0 regressions on all 22 existing strategy_types (pitfall C verified after every additive engine change). |

**Custom Mode packet status:** ✅ **all three PRDs (16a + 16b + 16c) complete and end-to-end wired.** Home tile → composer → backtest → save → strategy detail (with live dashboard for intraday strategies). See `agent-system/WORK_LOG.md` "Current Session" for the architectural patterns codified and the small operational follow-ups still owed.

### Active-execution follow-ups (active-execution-v2 era)

| Item | Why | Status |
|---|---|---|
| **Cap on declared positions per user** | The intraday monitor cron's cost scales with OPEN positions, not saved strategies (the cron is scoped to `position_states WHERE is_open`). A per-user cap on the number of strategies-with-open-positions (or total open positions) bounds the abuse/runaway case + the AV intraday call volume. Likely a tier-gated cap in `entitlements.py` (Scout small / Strategist mid / Quant large), enforced in `declare_position`. | **TODO** — backlog. Not blocking; the cron is already efficient (open-position-scoped), so this is an abuse/cost guard, not a correctness fix. |
| Signal-triggered ENTRY | Daily cron notifies "your strategy says enter X" → user buys + confirms a fill → declared position. The declare (PR2) + confirm (PR3) primitives make this a small follow-up. | TODO |
| Dashboard owner-gate on the frontend | The dashboard render gate (`saved_strategy_id != null`) doesn't check viewer ownership, so a non-owner viewing a public active-execution strategy sees the dashboard try to load + hit owner-only 404s → error state. Cosmetic. | TODO |

### Composer flexibility (custom_build expressiveness)

Surfaced 2026-06-12 by Mr Gu's hand-written SpaceX-ripple strategy — a real-world cross-sectional screen the composer can't yet express. **Parked** (Mr Gu, 2026-06-12) after the data-correctness fix landed.

| Item | Why / scope | Status |
|---|---|---|
| **Multi-asset "filter → rank → top-K" composer** | The composer is single-symbol + boolean rules; real screens rank a *universe* and hold top-K. The engine **already has** the hard part (`_generate_cross_sectional_weights`, `cross_sectional_momentum`/`momentum_rotation`, schema `top_n`/`ranking_*`). Remaining: multi-symbol picker (FE — was planned as "PRD-16b-3"), a "rank & hold top-K" rule card, converter, and a modest engine "boolean-filter → eligibility → rank survivors → top-K" glue path. **Tier 1** (rank whole universe by one factor, reuse existing rotation type) ≈ 1 PR, mostly FE. **Tier 2** (filter-then-rank — the actual screen) ≈ 2–3 PRs. See WORK_LOG / this session's analysis for the breakdown. | **PARKED** |
| **Composite ranking score** (e.g. `0.6·mom_1m + 0.4·mom_3m`) | `ranking_measure` is single-metric (`Literal["total_return"]`) today; a user-defined weighted blend of primitives as the rank score is the one genuinely-new modeling bit. Defer behind Tier 2; rank by a single primitive for MVP. | PARKED |
| **`pct_below_high` primitive** (% below rolling N-day high) | Needed for a "freshness band" filter (`2% < dist_from_52w_high < 25%`) — no current primitive gives distance-from-high as a value (`donchian_breakout` is boolean-only). Small add: one `TechnicalSignalProvider` + catalog entry → band becomes two AND'd rules. Unblocks the last *single-asset* filter in Mr Gu's screen. | TODO (small) |
| **Risk-based position sizing** (e.g. 1% risk ÷ stop-distance → shares) + **event/date exit tier** | His script also sizes by risk and has a hard calendar exit (IPO date). `ExitTier` is %-only today; sizing is engine-default. Each is incremental, lower priority than the multi-asset core. | TODO |

> Context: the 2026-06-12 real-OHLCV fix (#199) already unblocked the **volume + range** primitives (`avg_dollar_volume`, `obv`, `atr`, `stoch`, …) in the single-asset composer backtest — they now compute on real `price_bars` data instead of fabricated `volume=1.0`/`high=low=close`.

### Signal Catalog v2 → Market Screener sequencing (decided 2026-06-16)

The catalog v2 work (PRD-22) pivoted toward the **Market Screener** (PRD-23) — the productized form of the parked "multi-asset filter → rank → top-K composer" item above. Agreed plan (Mr Gu, 2026-06-16):

1. **Finish PRD-22c** (composer kind-dispatch) — the foundation the screener reuses. Scope-corrected to include the **engine operator-dispatch** (widen `StrategyRule.operator`/`threshold` + extend `_apply_rule_threshold` for `fires`/`crosses_up`/`in_range`/…) that 22c wrongly punted to 22b, plus the additive `reading` + `intent_group` catalog fields (intent-first composer). 4 slices: (a) engine foundation → (b) reading layer → (c) widgets → (d) kind-filter + `composes` drawer. **In progress.**
2. **Build the PRD-23 thin slice (23a)** on the frozen 72-primitive catalog — prove the universe → scan → ranked-basket loop works **end-to-end on live data** before expanding. DoD = a real working demo, not just unit tests (Mr Gu's bar).
3. **Backfill PRD-22b's remaining families incrementally** once the screener is live — each a small additive PR that immediately makes the live screener more powerful. Better feedback loop than 3 weeks of speculative editorial before the feature exists.

**Catalog freeze LIFTED 2026-06-16** — the screener loop is proven live (PRD-23a/b shipped, real S&P snapshot warmed), so step 3's incremental 22b backfill is underway. Shipped: PRD-22a semantics (#203), 22b 52-week-extrema (#204) + RVOL/Chandelier/TTM (#205), **MA/MACD events + RSI/Stoch/ADX events (#215, catalog 69→87)**. **Remaining 22b families** (spec'd in PRD-22b §3.1/§9 + the v2 catalog spec, resumable as 1-PR adds): Bollinger decomposition (%B/BBW/squeeze/fire/walk/tags), Anchored VWAP (user `anchor_date` param), Supertrend, Momentum z-score + acceleration, divergences (numpy peak/trough — NOT scipy, which isn't pinned in requirements), Heikin-Ashi, PEAD/insider (need new AV endpoints / earnings calendar), KB-lookup enrichment.

**PRD-22b catalog backfill — remaining slices (resume plan, 2026-06-16):** branch `claude/feat/prd-22b-catalog-families` shipped slices 1-2 (#215). Each remaining slice is a small additive PR (new `TechnicalSignalProvider` subclasses + catalog entries + `_READINGS` headlines + a mirror test file, no migrations). Build pattern is locked by the two shipped slices; descriptions sourced from the v2 spec prose (editorial gate = PR review). All-local primitives auto-join the daily screener snapshot.
  - **Slice 3 — Bollinger (+7):** `bb_percent_b`/`bb_bandwidth` (VALUE), `bb_squeeze` (REGIME), `bb_squeeze_fire` (EVENT, ±1 direction-aware), `bb_walk_upper` (EVENT), `bb_tag_upper`/`bb_tag_lower` (EVENT); compose `["bbands"]`.
  - **Slice 4 — Supertrend (×3) + Anchored VWAP (×3):** `supertrend` (VALUE), `supertrend_flip` (EVENT), `supertrend_above_price` (LEVEL); `anchored_vwap` (VALUE), `distance_to_anchored_vwap` (DISTANCE), `price_above_anchored_vwap` (LEVEL) — AVWAP v1 with a configurable `anchor_date`/lookback param.
  - **Slice 5 — Momentum + Heikin-Ashi:** `momentum_12_1`, `momentum_12_1_zscore`, `momentum_composite_zscore`, `momentum_acceleration` (VALUE); `heikin_ashi_trend` (REGIME), `heikin_ashi_consecutive` (VALUE), `heikin_ashi_color_flip` (EVENT).
  - **Slice 6 — Divergences + RSI failure swings:** a numpy peak/trough detector (NOT scipy), then `macd_bullish/bearish_divergence`, `rsi_bullish/bearish_divergence` (+ `rsi_hidden_bullish_div`), `obv_divergence_bullish/bearish` (DIVERGENCE, +1/-1/0), and `rsi_bullish/bearish_failure_swing` (EVENT, share the peak/trough machinery).
  - **Deferred — Fundamental + Events (+6):** `pead_signal`/`pead_drift_window`, `days_to_earnings`/`days_since_earnings`, `estimate_revision_positive_cross`, `insider_net_buy_surge` — need an earnings-calendar data source (est_rev/insider compose on existing `estimate_revision_3m`/`insider_net_buy`; the earnings-date ones need a new source). Build after the earnings-calendar ingest exists.
  - **Editorial follow-ups carried from #215:** (1) `macd_histogram_flip` emits a byte-identical series to `macd_signal_cross` (kept distinct only by `output_kind`) — confirm or switch to a histogram-inflection detector. (2) `intent_group` on all new primitives auto-derives from category (unused in UI) — gets corrected wholesale when the intent-taxonomy research lands.

**Why not finish all of 22b first:** the screener's risk is its new architecture/UX, not primitive count; new primitives are additive (no rework); finishing the catalog first front-loads the low-uncertainty work and defers validating the uncertain thing. **PRD-23 packet** (HANDOFF + sliced PRDs, mirroring the catalog-v2 packet): `agent-system/plans/HANDOFF-livermore-market-screener.md` + `PRD-23a-screener-backend-spine.md` (snapshot + scan + rank) + `PRD-23b-screener-mode-ui.md` (flow + composer + results) + `PRD-23c-screener-track-intraday.md` (save→notify + intraday). The §4 "Multi-asset filter → rank → top-K" parked item is now **superseded by PRD-23**.

**PRD-23a v1 follow-ups (deferred from the pre-merge review of PR #212):**
- **`/api/screen/rank` — trap #13 + run-quota** (deferred from review, not a blocker): rank backtests the matched subset sequentially while holding the request `db`; on a cold-cache symbol each `BacktestEngine.run` can `await` an AV fetch with the conn checked out. Bounded today by sign-in gating + `top_k<=200` + the warm-cache short-circuit, but before `/rank` is heavily trafficked: (a) use a fresh `SessionLocal()` per backtest (requires threading a sessionmaker so the in-memory e2e test still works), and (b) wire a per-tier run quota (Scout cap). Code comment marks the spot in `screen.py`.
- **Param-override screening**: the daily snapshot is default-param only; a rule overriding an indicator *period* is scanned at default and surfaced via `default_param_primitives` (the rank re-backtests precisely). To screen precisely, warm a snapshot column per distinct param-set (or compute on-the-fly for the matched subset).
- **Fundamental snapshot**: the 17 fundamental / AV-endpoint primitives are excluded from the daily price snapshot (would need the live fetch §3.3 forbids); a separate slower-cadence fundamental snapshot would let the screener filter on value/quality/sentiment.
- **Sector-label normalization**: `sector_<key>` matches `SymbolCache.sector` verbatim; provider sector strings (e.g. "Information Technology") may not match the US_SECTORS ETF labels — normalize before the sector tier ships in the UI.
- **Extensible prewarm-universe registry (+ Nasdaq-100 as the first add)** [Jimmy, 2026-06-16; live demo confirmed the S&P-only snapshot]: today the standing universe is **hardcoded to `SP500_TICKERS` in ~4 places** — the warm job (`signal_snapshot_job._warm_sp500`), the resolver (`universe_resolver.resolve_universe` + `is_standing_universe`), the scan-request validator (`screener_scan._FIXED_UNIVERSE_IDS`), and the UI (`universe-selector.tsx` `TIERS`). **Goal: collapse to ONE source of truth** — a `STANDING_UNIVERSES` registry (`universe_id -> ticker frozenset`, e.g. `app/data/standing_universes.py`) that the warm job (warm the **union** of all registered sets — the snapshot is keyed by symbol, universe-agnostic), resolver, validator, and a new `GET /api/screen/universes` endpoint all read; the UI fetches that list instead of hardcoding tiles. Then **adding a universe = (1) one registry entry + (2) make sure its `price_bars` stay warm** — not a multi-file edit.
  - **First instance — Nasdaq-100:** ~80–90% overlaps the S&P 500 (already warm), so the net-new work is only the **~15–25 NDX names not in SPX** — a `NASDAQ100_TICKERS` list, a one-time `price_bars` backfill for those names, and wiring them into the daily ingestion (else the daily snapshot warm live-fetches them → AV rate limits, exactly the ABC-style failures from the first warm).
  - **Market Pulse reuse:** the same registry backs a "Nasdaq-100 Top Movers" view (`_build_top_assets(NASDAQ100_TICKERS)` in `market_pulse_service.py`) — an **additive** tab; SPX untouched (respect the "expand only, never shrink" universe invariant in CLAUDE.md).
  - **Effort:** registry + screener `nasdaq100` tier ~1 day · NDX bars backfill + keep-warm ~½ day · a dedicated Market Pulse NDX surface +~1–1.5 day (data-coverage-only is ~free once the union is warmed). **Watch-outs:** daily-warm wiring for net-new names, AV rate limits on the one-time backfill, the expand-only invariant.

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
| ~~Set `FRED_API_KEY` on Railway → swap Growth + Stress macro signals to real FRED data~~ | ✅ Shipped — `FRED_API_KEY` env var set on Railway; `FREDClient` + builders for CFNAI (Growth, since ISM PMI is no longer FRED-hosted post-2017 licensing) and BAMLH0A0HYM2 (Stress / HY OAS) in `apps/api/app/services/`. Mock fallback preserved when key missing or FRED unreachable. | Done |
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
| Market Pulse cold-path opt — **batch `_load_bars`** | `_build_top_assets` (US) and `_build_cn_top_assets` (CN) in `apps/api/app/services/market_pulse_service.py` run a per-symbol `_load_bars()` query inside the loop — ~500 round-trips per cold compute. Replace with one batched `SELECT * FROM price_bars WHERE symbol IN (...) AND trading_date >= cutoff`, group in Python. Same pattern likely worth applying to `_build_sector_card`, `_build_index_card`, `_build_macro_card`. | ~2h | Railway bill estimate climbs past ~$7/mo OR a new caller of these functions appears that can't benefit from PR #138's pre-warm (e.g. per-user filtered Top Movers). See `docs/LEARNINGS.md` "N+1 queries are the dominant slow path." |
| Market Pulse cold-path opt — **cap CN candidate pool before N+1** | `_build_cn_top_assets` fetches market-cap-ranked symbols then computes CMF for ALL of them (~500), sorts, slices to top 10. Better: fetch market-cap-ranked, slice to top 50–100 in SQL, THEN compute CMF only for those. Smaller change than the batch fix above; complementary. | ~30 min | Same trigger as batch-`_load_bars` row above. |
| Market Pulse CN — **restore intraday freshness on US-listed China ETFs** (PR #138 "Option B") | PR #138 skipped the FMP live overlay for CN entirely. That removed wasted FMP calls for A-shares (`.SZ`/`.SS` — FMP doesn't have them) but also dropped intraday updates on the US-listed China ETF cards (FXI, KWEB, MCHI, CQQQ, FLCH, CHIE) and macro cards (VXX, UUP, TLT, HYG). The refined fix: filter `.SZ`/`.SS` out of the symbols passed to `live_quote_service.get_quotes`, keep the overlay for everything else. Restores intraday freshness on ~10 cards during US market hours while preserving the speed win. | ~15 min | When a CN user notices stale FXI/KWEB prices during US trading hours. Until then, the EOD-only display is acceptable since A-shares (the dominant CN signal) were always EOD anyway. |
| **Watch Railway monthly bill** — revisit Market Pulse perf debt if cost climbs | PR #138's pre-warm adds ~80s of background compute every 4 min. As of 2026-06-05 the bill is ~$2.97 spent / $5.10 estimated on the $5 Hobby plan — memory (93%) dominates, pre-warm contribution is negligible. If the estimate creeps past $7/mo, audit whether pre-warm overhead is responsible and consider the batch-`_load_bars` + candidate-cap fixes above. | 5-min dashboard check first; ~2.5h of code if action needed | Weekly review. Railway → Project → Usage → "View Cost by Service." |

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
