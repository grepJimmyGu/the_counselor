# Project Log — Livermore (谋士)

## Overview
Natural-language investment strategy research tool. Users describe trading strategies conversationally; the backend converts them to validated JSON, runs a deterministic backtest, and returns explanation + critical review layers.

**Stack:** FastAPI (Python) + PostgreSQL + Next.js (TypeScript)  
**Deployment:** Railway (backend) + Vercel (frontend)

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
