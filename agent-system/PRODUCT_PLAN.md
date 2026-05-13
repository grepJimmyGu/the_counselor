# Livermore — Product Plan

**Last updated:** 2026-05-11  
**Status:** Active  
**Product vision:** AI-driven stock research community where community discussion volume, watchlist activity, and votes surface buy/sell/hold signals — not AI recommendations.

---

## Decisions Log

| # | Decision | Date | Notes |
|---|---|---|---|
| 1 | Build order: Fundamental → News/Sentiment → Community | 2026-05-11 | Community requires auth; data lenses come first |
| 2 | No intraday data | 2026-05-11 | End-of-day only. "Day trading" lens = technical analysis tools for day traders, not real-time signals |
| 3 | Core value = community-driven signals | 2026-05-11 | Discussion volume + watchlist adds + votes surface sentiment. AI never says "buy X" |
| 4 | Auth: Google OAuth via Auth.js | 2026-05-11 | + optional GitHub OAuth. Required before Phase 3 |
| 5 | Primary fundamental data: FMP Starter ($14/mo) | 2026-05-11 | yfinance as dev/fallback only |
| 6 | News/sentiment: Alpha Vantage NEWS_SENTIMENT (primary), Reddit (if configured) | 2026-05-11 | X deferred — requires $100/mo API |
| 7 | LLM cache TTL: 3 hours for all AI analysis | 2026-05-11 | 3× cheaper than 1h; pre-warm top 100 S&P 500 every 3h |
| 8 | Sandbox reviews: on-demand only, never auto-run | 2026-05-11 | Sonnet ~$0.01/call |
| 9 | Daily spend alert: $20/day | 2026-05-11 | Scaling checkpoint — ~600 active users |
| 7 | Not building day trading / live execution | 2026-05-11 | Permanent constraint |
| 8 | PRD-first engineering process | 2026-05-11 | Every feature starts as PRD before code |

---

## Product Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Livermore Platform v2                         │
├─────────────────┬────────────────────┬──────────────────────────┤
│   FUNDAMENTAL   │  NEWS & SENTIMENT  │  TECHNICAL ANALYSIS      │
│   Phase 1       │  Phase 2           │  existing + expand       │
│                 │                    │                          │
│ Stock Screener  │ Per-ticker news    │ Strategy Builder         │
│ Company Page    │ AI sentiment score │ Backtesting Engine       │
│ Key metrics     │ Trending topics    │ Robustness Tests         │
│ Earnings cal.   │ Analyst ratings    │ Explanation + Review     │
│ Sector compare  │ Social buzz score  │ Run History              │
│ AI summary      │ AI news digest     │ Templates                │
├─────────────────┴────────────────────┴──────────────────────────┤
│                   COMMUNITY LAYER  Phase 3                       │
│                                                                  │
│  Auth + Profiles   Watchlists (personal)   Strategy Sharing     │
│  Comments + Votes  "Most Discussed" board   Bull/Bear Poll       │
│                                                                  │
│  Community Signal Score per ticker:                              │
│  (discussion × 1.0) + (watchlist_adds × 1.5)                   │
│  + (strategy_runs × 2.0) + (bull_votes - bear_votes × 0.8)     │
│  → normalised to "Community Sentiment" — never "AI says buy"    │
└─────────────────────────────────────────────────────────────────┘
```

---

## PRD Sequence

### Phase 1 — Fundamental Analysis

#### PRD-06 · FMP Data Integration + Fundamental Service
**Status:** Not started  
**Prerequisite for:** PRD-07, PRD-08a  
**Branch naming:** `feat/prd-06-fmp-integration`

**Scope:**
- Install Financial Modeling Prep (FMP) Starter plan ($14/mo)
- `FMPClient` HTTP adapter — mirrors existing `AlphaVantageClient` pattern
- `DataSourceAdapter` Protocol — abstract interface so FMP/yfinance are swappable
- `FundamentalService` — company profile, key metrics, income statement, balance sheet
- `apps/api/app/scripts/seed_symbols.py` — one-time seed from FinanceDatabase
- New API routes: `GET /api/fundamental/profile/{symbol}`, `GET /api/fundamental/metrics/{symbol}`
- New frontend type: `CompanyProfile`, `KeyMetrics` in `contracts.ts`

**Skills to activate:**
- `data-quality-checker` — validate FMP response fields before caching
- `safe-migration` — review any new Alembic migration (symbol metadata table)

**GitHub resources:**
- `ranaroussi/yfinance` — install as `pip install yfinance`; use as dev fallback adapter
- `OpenBB-finance/OpenBB` — reference `DataProvider` abstract class pattern for adapter design
- `JerBouma/FinanceDatabase` — install as `pip install financedatabase`; seed symbol universe

**New data table:**
```sql
symbols (
  symbol VARCHAR PRIMARY KEY,
  name VARCHAR, sector VARCHAR, industry VARCHAR,
  country VARCHAR, exchange VARCHAR, currency VARCHAR,
  market_cap_category VARCHAR,  -- micro/small/mid/large/mega
  last_synced_at TIMESTAMP
)
```

**Acceptance criteria:**
- [ ] `GET /api/fundamental/profile/AAPL` returns company name, sector, description, P/E, market cap, dividend yield
- [ ] `GET /api/fundamental/metrics/AAPL` returns revenue, earnings, profit margin, ROE, debt/equity
- [ ] FMP 429 → falls back to yfinance without error surfaced to frontend
- [ ] `seed_symbols.py` populates ~8,000 US equities with sector/industry metadata
- [ ] safe-migration skill run confirms no dangerous migration operations
- [ ] data-quality-checker confirms FMP field coverage ≥ 90% for S&P 500 symbols

---

#### PRD-07 · Stock Screener Page (`/stocks`)
**Status:** Not started  
**Branch naming:** `feat/prd-07-stock-screener`

**Scope:**
- New page `/stocks` — filterable stock screener
- Filter parameters: sector, industry, country, market cap range, P/E range, revenue growth %, dividend yield, exchange
- Results table: symbol, name, sector, price, P/E, market cap, revenue growth, dividend yield, % change today
- "Browse by Sector" navigation strip
- Screener state persists in URL query params (bookmarkable/shareable)
- `GET /api/screener/results?sector=Technology&min_pe=10&max_pe=30` backend endpoint
- `GET /api/screener/filters` — returns all valid filter options (sectors, industries, countries from FinanceDatabase seed)

**Skills to activate:**
- `sector-analyst` — power the sector rotation context panel alongside screener results
- `us-stock-analysis` — inline AI summary for selected screener result
- `ui-ux-pro-max` — screener page design (data-dense dashboard style)

**GitHub resources:**
- `xang1234/stock-screener` — reference filter parameter schema (80+ filters) and results table column spec
- `JerBouma/FinanceDatabase` — power sector/industry/country filter dropdown options

**Acceptance criteria:**
- [ ] Screener returns results within 2s for any single-filter query
- [ ] URL state: `/stocks?sector=Technology&min_pe=10` loads correct filtered results on page refresh
- [ ] "Browse by Sector" strip covers all 11 GICS sectors
- [ ] Results table sortable by any column
- [ ] Empty state when no results match filters

---

#### PRD-08a · Fundamental Analysis Module — Financial Check + Structured Company Data
**Status:** Not started  
**Depends on:** PRD-06  
**Full spec:** `agent-system/plans/PRD-08a-fundamental-analysis-financial-check.md`  
**Branch naming:** `feat/prd-08a-fundamental-analysis`

**Scope summary:**
- Company deep-dive page `/stocks/[ticker]` with three visual sections
- **Business Map (partial):** Description from FMP, value chain role from sector+industry rule-based lookup, margin/cyclicality implications derived. Customer types, revenue model, pricing power → blank ("Data pending — 10-K/10-Q model")
- **Market Position (partial):** Category from FinanceDatabase. Competitors from FMP peers when available, absent otherwise (no LLM fallback). Market size, growth, competitive position, share, drivers, risks → blank
- **Financial Check (complete):** Full deterministic metrics from FMP — growth, profitability, cash flow, balance sheet, valuation
- Scoring: `financial_validation_score` + `valuation_risk_score` only; Business Map + Market Position scores null
- 4 new DB tables, 5 new backend services, 6 API endpoints

**Skills:** `data-quality-checker`, `safe-migration`, `earnings-calendar`, `ui-ux-pro-max`  
**GitHub:** `JerBouma/FinanceDatabase`, `ranaroussi/yfinance`

---

#### PRD-08b · Fundamental Analysis — Full Business Map + Market Position
**Status:** BLOCKED — waiting on 10-K/10-Q data extraction model (Jimmy to build)  
**Branch naming:** `feat/prd-08b-fundamental-intelligence`

Adds: full Business Map fields, full Market Position fields, complete 4-component scoring, fundamental sandbox reviewer. **No timeline — explicitly gated on external model.**

---

### Phase 2 — News & Sentiment

#### PRD-09 · News & Community Sentiment — Backend
**Status:** Not started  
**Full spec:** `agent-system/plans/PRD-09-news-sentiment-backend.md`  
**Branch naming:** `feat/prd-09-news-sentiment-backend`

**Scope summary:**
- Provider-based architecture: `NewsProvider` + `CommunityProvider` Protocol interfaces
- Active MVP: Alpha Vantage `NEWS_SENTIMENT` (news), Reddit (if env vars set)
- Placeholder interfaces: X (`not_configured`, deferred — $100/mo), Internal Community (`not_configured` until Phase 3)
- LLM chain: Claude Haiku extracts News Catalyst + News Sentiment + Community Pulse + Signal Quality + Takeaway — **cached 3 hours**
- Raw article/mention cache: 15 min TTL
- Background pre-warmer: top 100 S&P 500 tickers every 3h (~$3.20/day, toggle via env var)
- 9-score framework (catalyst, materiality, source quality, news sentiment, community sentiment, attention, signal quality, risk, overall)
- 7 pre-built toolkits (Positive Catalyst, News Confirmed, Rising Attention, Reversal, Controversial, Headline Risk, Community Hype)
- Sandbox review: Claude Sonnet, on-demand only (~$0.01/call, never auto-run)
- 5 new DB tables: `news_articles`, `community_mentions`, `sentiment_signal_summaries`, `sentiment_toolkit_runs`, `sentiment_toolkit_candidates`

**Skills:** `market-news-analyst`, `data-quality-checker`, `safe-migration`

---

#### PRD-10 · News & Community Sentiment — Frontend
**Status:** Not started  
**Full spec:** `agent-system/plans/PRD-10-news-sentiment-frontend.md`  
**Depends on:** PRD-09  
**Branch naming:** `feat/prd-10-news-sentiment-frontend`

**Scope summary:**
- New nav section: `/sentiment` (Sentiment Hub)
- Hub page: 7 toolkit cards with source status badges + last run timestamp
- Provider status strip: active/not_configured for each data source
- Toolkit results page: ranked candidate cards with all labels, themes, takeaway, suggested action
- Deep-dive page `/sentiment/stock/[ticker]`: 4 visual sections (News Catalyst, News Sentiment, Community Pulse, Signal Quality & Risk)
- On-demand sandbox review panel (Sonnet, ~10s)
- "Publish to Community" + "Add to Watchlist": disabled until Phase 3
- Disclaimer on all pages

**Skills:** `ui-ux-pro-max`, `market-news-analyst`, `playwright-runner`

---

### Phase 3 — Community Layer

#### PRD-11 · Authentication (Google OAuth via Auth.js)
**Status:** Not started — blocked until Phases 1+2 complete  
**Branch naming:** `feat/prd-11-auth`

**Scope:**
- Auth.js (formerly NextAuth.js) with Google OAuth provider
- Optional GitHub OAuth provider
- New `users` table: `id`, `email`, `display_name`, `avatar_url`, `provider`, `created_at`
- Session management via JWT + HttpOnly cookies
- Protected routes: watchlist, vote, comment, profile
- Public routes: screener, company page, news, workspace (no auth required)
- Nav header: "Sign in with Google" button → profile avatar when logged in

**Skills to activate:**
- `safe-migration` — users table migration
- `adversarial-audit` — auth flow abuse cases (session hijacking, OAuth state validation)

**Acceptance criteria:**
- [ ] Google OAuth login/logout works end-to-end
- [ ] Session persists across page refresh (HttpOnly cookie)
- [ ] Unauthenticated users can use all Phase 1+2 features without being blocked
- [ ] `/api/auth/*` routes handled by Auth.js
- [ ] adversarial-audit skill run before merging

---

#### PRD-12 · Watchlists + User Profiles
**Status:** Not started  
**Branch naming:** `feat/prd-12-watchlists-profiles`

**Scope:**
- Watchlist: add/remove ticker, persist to `user_watchlists` table
- Watchlist contributes to community signal score (passive, not shown to user as influence)
- User profile page `/profile/[username]` — public: shared strategies, watchlist (optional public/private toggle)
- Watchlist-based personalisation: company pages show "X people watching this"
- `GET /api/watchlist` (auth required), `POST /api/watchlist/{symbol}`, `DELETE /api/watchlist/{symbol}`

**Skills to activate:**
- `safe-migration` — watchlist table
- `playwright-runner` — add workflow `.md` for "add to watchlist, view watchlist, remove from watchlist"

---

#### PRD-13 · Community Signals (Votes + Trending Board)
**Status:** Not started  
**Branch naming:** `feat/prd-13-community-signals`

**Scope:**
- Bull/Bear/Hold vote per ticker (one vote per user per ticker, updateable)
- `user_votes` table: `user_id`, `symbol`, `vote` (bull/bear/hold), `voted_at`
- Community Signal Score formula (see architecture section)
- "Most Discussed This Week" page at `/community` — ranked by signal score, not returns
- Trending bar on homepage driven by community score
- Explicit disclaimer: "Community sentiment reflects user activity, not investment advice"

**Skills to activate:**
- `adversarial-audit` — vote manipulation patterns (vote stuffing, coordinated pumping)
- `safe-migration` — votes table
- `playwright-runner` — vote submission + undo flow

---

#### PRD-14 · Strategy Sharing + Comments + Community Page
**Status:** Not started  
**Branch naming:** `feat/prd-14-community-page`

**Scope:**
- Public strategy gallery at `/community/strategies` — strategies shared by users (already have slug URLs)
- Comments on strategies: `strategy_comments` table with `user_id`, `slug`, `content`, `created_at`
- Upvote/downvote on strategies (not on individual stocks — avoids "recommending" framing)
- "Most upvoted this month" strategy leaderboard (sorted by upvotes, not by returns — critical)
- Community page links: most discussed stocks + top strategies + recent activity

**Skills to activate:**
- `adversarial-audit` — comment abuse, upvote manipulation, spam detection
- `playwright-runner` — full community flow E2E test
- `ui-ux-pro-max` — community page layout

---

## API Stack

| Data Need | Provider | Cost | Status |
|---|---|---|---|
| Price history (OHLCV) | Alpha Vantage | Already paid | ✅ Active |
| Company fundamentals | FMP Starter | $14/mo | 🔲 PRD-06 |
| News + AI sentiment | Alpha Vantage `NEWS_SENTIMENT` | Included in premium | 🔲 PRD-09 |
| Analyst ratings + earnings calendar | Finnhub free tier | $0 | 🔲 PRD-09 |
| Symbol metadata (sector/industry) | FinanceDatabase (Python lib) | Free | 🔲 PRD-06 |
| AI summaries (news digest, company health) | Claude Haiku API | ~$0.25/M tokens | 🔲 PRD-08 |

**Total new recurring cost: ~$14/mo**

---

## Installed Agent Skills

| Skill | Source | Activated for |
|---|---|---|
| `ui-ux-pro-max` | nextlevelbuilder | All phases — any UI/UX work |
| `earnings-calendar` | tradermonty/claude-trading-skills | PRD-08 company page |
| `market-news-analyst` | tradermonty/claude-trading-skills | PRD-09/10 news service |
| `sector-analyst` | tradermonty/claude-trading-skills | PRD-07 screener |
| `us-stock-analysis` | tradermonty/claude-trading-skills | PRD-07/08 company analysis |
| `data-quality-checker` | tradermonty/claude-trading-skills | PRD-06 FMP integration |
| `safe-migration` | gastonsalg/claude-skills | Every PRD with DB schema changes |
| `adversarial-audit` | neonwatty/qa-skills | PRD-11/12/13/14 community features |
| `playwright-runner` | neonwatty/qa-skills | End of each phase — E2E regression |

---

## GitHub Resources

| Repo | Type | Used in |
|---|---|---|
| `ranaroussi/yfinance` | Install: `pip install yfinance` | PRD-06 — dev fallback adapter, symbol validation |
| `OpenBB-finance/OpenBB` | Reference only — `DataProvider` pattern | PRD-06 — `DataSourceAdapter` interface design |
| `JerBouma/FinanceDatabase` | Install: `pip install financedatabase` | PRD-06 seed script + PRD-07 filter options |
| `xang1234/stock-screener` | Reference only — filter schema + column spec | PRD-07 screener filter design |
| `kernc/backtesting.py` | Reference only — commission/partial fill models | Future technical engine expansion |

---

## Engineering Process

### Per-PR checklist (mandatory from PRD-06 onward)

```
□ PRD written and linked in PR description
□ TypeScript types defined in contracts.ts before any component
□ safe-migration skill run on any Alembic migration file
□ pytest passes — new tests: happy path + min 2 error cases
□ npm run build clean (TypeScript zero errors)
□ data-quality-checker skill run on any new data ingestion
□ adversarial-audit skill run before any community/voting feature merge
□ playwright-runner: workflow .md added for any new user-facing flow
```

### Branch naming
```
feat/prd-XX-feature-name    new features
fix/short-description       bug fixes
data/source-name            data integration
infra/what-changed          Railway/Vercel/config
```

### Caching TTLs
```
Company profile / key metrics   24 hours
Earnings calendar               6 hours
News / sentiment                15 minutes
Screener results                1 hour
Price data (OHLCV)              24 hours (existing)
Community signal scores         5 minutes
```

### Data source adapter pattern
All new data sources implement `DataSourceAdapter` Protocol.
`FUNDAMENTAL_PROVIDER=fmp` in production, `yfinance` in local dev.
FMP 429/5xx → automatic fallback to yfinance, logged but not surfaced as error.

---

## Completed PRDs

| PRD | Title | Merged | Tag | Notes |
|---|---|---|---|---|
| PRD-01 | Research Templates | ✅ 2026-05-08 | — | 5 templates, available/unavailable split |
| PRD-02 | Strategy Storage + Shareable URLs | ✅ 2026-05-08 | — | Slug-based public URLs |
| PRD-03 | Personal Strategy Library | ✅ 2026-05-08 | — | localStorage, comparison tab |
| PRD-04 | Interactive Clarification + Capability Glossary | ✅ 2026-05-11 | — | ClarificationState enum, amber chat bubbles, quick-reply chips |
| PRD-06 | FMP Data Integration + Fundamental Service | ✅ 2026-05-11 | `prd-06-complete` | FMPClient, yfinance fallback, FundamentalService, seed script |
| PRD-07 | Stock Screener Page (`/stocks`) | ✅ 2026-05-11 | `prd-07-complete` | Sector strip, filter panel, sortable results, URL state |
| PRD-08a | Company Deep-Dive — Financial Check | ✅ 2026-05-11 | `prd-08a-complete` | Business Map (partial), Market Position (peers), full Financial Check + scoring |
| PRD-08b | Company Deep-Dive — 10-K Business Intelligence | ✅ 2026-05-12 | `prd-08b-complete` | SEC EDGAR fetch, section parser (Items 1/1A/7), LLM extraction, 90-day cache |
| PRD-09 | News & Community Sentiment — Backend | ✅ 2026-05-12 | `prd-09-complete` | 4-provider system, Haiku LLM chain, 9-score framework, 7 toolkits, Sonnet sandbox |
| PRD-10 | News & Community Sentiment — Frontend | ✅ 2026-05-12 | `prd-10-complete` | `/sentiment` hub, toolkit cards, provider status, sentiment tab on ticker page |
| PRD-11 | Authentication — Google OAuth via Auth.js v5 | ✅ 2026-05-12 | `prd-11-complete` | JWT sessions, NavHeader sign-in/avatar, /auth/signin, /auth/error, internal key BFF pattern, adversarial audit passed |

---

## Open / In-Discussion PRDs

| PRD | Title | Status |
|---|---|---|
| PRD-05 | `not_supported` strategy handling | Needs discussion — redirect UX not decided |

---

## PRD Execution Queue (next up)

| Order | PRD | Status | Blocker |
|---|---|---|---|
| **1** | **PRD-12** | **In progress** | None — PRD-11 complete |
| 2 | PRD-13 | Next after PRD-12 | Watchlists required for signal score |
| 3 | PRD-14 | Next after PRD-13 | Votes + signals required |
| — | PRD-05 | In discussion | Design decision needed |

---

## Unit Economics

*Last updated: 2026-05-12*

### LLM provider decision (updated)

All LLM calls (sentiment analysis, 10-K extraction, sandbox reviews, strategy builder) now route through a **single OpenAI-compatible gateway** (`LLMGateway` in `llm_adapter.py`). No Anthropic key required. Configured via `LLM_API_KEY` + `LLM_MODEL` on Railway.

Current production model: **`gpt-4o-mini`**  
*OpenAI pricing: $0.15/M input, $0.60/M output (gpt-4o-mini)*

### LLM cost per operation (revised for gpt-4o-mini)

| Operation | Tokens (in/out) | Cost per call | Cache TTL |
|---|---|---|---|
| News sentiment analysis (per ticker) | 3,000 / 800 | **~$0.001** | 3 hours |
| 10-K business intelligence (per company) | 6,000 / 800 | **~$0.002** | 90 days |
| Sentiment sandbox review (on-demand) | 2,000 / 500 | **~$0.001** | None (per call) |
| Strategy explanation | 1,500 / 500 | **~$0.001** | None |
| Strategy sandbox review | 1,200 / 400 | **~$0.001** | None |
| Full backtest session | ~4,000 / 1,200 | **~$0.001** | None |

*All costs ~3–5× lower than originally estimated (Haiku). Sentiment and 10-K extraction especially cheap with gpt-4o-mini.*

### Cache TTL decisions

| Data type | TTL | Reason |
|---|---|---|
| LLM sentiment analysis | **3 hours** | Balances freshness vs. cost |
| 10-K business intelligence | **90 days** | Annual filing; rarely changes |
| Raw news articles | 15 minutes | News is time-sensitive |
| Raw community mentions | 15 minutes | Social moves fast |
| Financial statements (FMP) | 24 hours | Quarterly data |
| Company profile/metrics | 24 hours | Structural data |
| Price data (OHLCV) | 24 hours | End-of-day |
| Community signal scores | 5 minutes | Phase 3 — real-time activity |

### Fixed monthly costs (current)

| Item | Cost | Status |
|---|---|---|
| Railway (backend + PostgreSQL) | $5–20 | Active |
| Vercel (frontend) | Free | Active |
| FMP Starter (fundamentals) | $14 | Active (key needed in Railway) |
| Alpha Vantage Premium (price + news) | $50–100 | Active |
| OpenAI API (all LLM) | Variable ~$2–10 | Active |
| Reddit API | Free | Pending approval |
| **Total fixed** | **~$70–150/month** | |

### Total platform cost by user scale (gpt-4o-mini, 3h TTL)

| Users | Unique tickers/day | LLM variable | Total/month | Per user/month |
|---|---|---|---|---|
| Solo | 20 | ~$0.60 | **~$100** | — |
| 50 users | 80 | ~$2 | **~$155** | $3.10 |
| 200 users | 200 | ~$6 | **~$165** | $0.83 |
| 1,000 users | 500 | ~$15 | **~$185** | $0.19 |
| 5,000 users | 1,500 | ~$45 | **~$220** | $0.04 |
| 20,000 users | 3,000 | ~$90 | **~$280** | $0.01 |

*LLM costs are 3–5× lower than original Haiku estimates. The platform is economically viable at small scale.*

### Cost optimisation levers

1. **Sentiment pre-warmer** (not yet built) — top-100 S&P 500 every 3h; ~$3/month at gpt-4o-mini rates
2. **Skip LLM for thin coverage** — already implemented; < 3 articles returns deterministic fallback
3. **Sandbox review on-demand only** — already implemented; never auto-runs
4. **10-K cache is 90 days** — one LLM call per company per quarter
5. **Daily spend alert at $20/day** — monitoring checkpoint for scaling

### Latency benchmarks

| Operation | First load (uncached) | Cached |
|---|---|---|
| News sentiment analysis | 2–4s (gpt-4o-mini is fast) | 50–100ms |
| 10-K business intelligence | 5–10s (EDGAR download + LLM) | 50ms |
| Fundamental / financial check | 1–2s (FMP API) | 50ms |
| Backtest + explanation | 8–15s | N/A |
| Sentiment sandbox review | 2–4s | N/A (on-demand) |

---

## Deferred / Out of Scope

- Live trade execution (permanent constraint)
- Intraday / minute-level data
- Options, futures, margin trading
- Community Phase 4 (cross-device sync, advanced curation) — post Phase 3
- Fundamental data for A-shares (FMP doesn't cover well; deferred)
- X (Twitter) API integration — deferred ($100/mo X API Basic subscription)
- Sentiment pre-warmer background job — low priority; toggle via `PREWARM_ENABLED` when needed
