# Project Log — Livermore (谋士)

## Overview
Natural-language investment strategy research tool. Users describe trading strategies conversationally; the backend converts them to validated JSON, runs a deterministic backtest, and returns explanation + critical review layers.

**Stack:** FastAPI (Python) + PostgreSQL + Next.js (TypeScript)  
**Deployment:** Railway (backend) + Vercel (frontend)

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
