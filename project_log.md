# Project Log — Livermore (谋士)

## Overview
Natural-language investment strategy research tool. Users describe trading strategies conversationally; the backend converts them to validated JSON, runs a deterministic backtest, and returns explanation + critical review layers.

**Stack:** FastAPI (Python) + PostgreSQL + Next.js (TypeScript)
**Deployment:** Railway (backend) + Vercel (frontend)

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

