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
| 6 | News/sentiment: Alpha Vantage NEWS_SENTIMENT + Finnhub free tier | 2026-05-11 | Both already budgeted |
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

#### PRD-08 · Company Overview Page (`/stocks/[ticker]`)
**Status:** Not started  
**Branch naming:** `feat/prd-08-company-overview`

**Scope:**
- New dynamic route `/stocks/[ticker]`
- Sections: Company header (name, price, % change, sector/industry tags) · Key metrics panel · Revenue & earnings chart (last 8 quarters) · Description · Earnings calendar (upcoming + historical) · "Run a Backtest" CTA → `/workspace?prompt=...`
- AI company health summary (LLM via Claude Haiku): "AAPL has grown revenue 8% YoY, maintains strong margins, P/E of 28 is elevated vs sector median..."
- `GET /api/fundamental/overview/{symbol}` — aggregates profile + metrics + earnings into one response

**Skills to activate:**
- `earnings-calendar` — surface upcoming earnings with EPS/revenue estimates
- `us-stock-analysis` — generate AI company summary
- `ui-ux-pro-max` — company page design

**GitHub resources:**
- `ranaroussi/yfinance` — supplement FMP with extended quarterly history when needed

**Acceptance criteria:**
- [ ] `/stocks/AAPL` renders without error, all sections populated
- [ ] Earnings calendar shows next 4 upcoming + last 8 historical
- [ ] AI summary is 3–5 sentences, clearly labelled as AI-generated, includes disclaimer
- [ ] "Run a Backtest on AAPL" CTA navigates to workspace with prompt pre-filled
- [ ] Page handles unknown ticker gracefully (404 with search suggestion)

---

### Phase 2 — News & Sentiment

#### PRD-09 · News & Sentiment Service (Backend)
**Status:** Not started  
**Branch naming:** `feat/prd-09-news-sentiment-service`

**Scope:**
- `NewsService` — fetch and cache news per ticker (TTL: 15min)
  - Primary: Alpha Vantage `NEWS_SENTIMENT` endpoint (already have premium key)
  - Secondary: Finnhub company news endpoint (free tier, 60 req/min)
- `SentimentService` — aggregate sentiment scores per ticker
  - Composite score from Alpha Vantage sentiment + Finnhub buzz score
  - 7-day rolling sentiment trend
- Background refresh job: top-50 most-active tickers refreshed every 15min (Railway background worker)
- New schemas: `NewsItem`, `SentimentScore`, `TrendingTicker`
- New routes:
  - `GET /api/news/{symbol}` — latest 20 news items with sentiment
  - `GET /api/news/trending` — top 10 trending tickers by news volume
  - `GET /api/sentiment/{symbol}` — composite sentiment score + 7-day trend

**Skills to activate:**
- `market-news-analyst` — validate news quality and relevance scoring logic
- `safe-migration` — new news/sentiment cache tables

**Acceptance criteria:**
- [ ] `GET /api/news/AAPL` returns ≥ 5 articles within 24h, each with sentiment score
- [ ] Sentiment score: positive/negative/neutral with numeric confidence (0–1)
- [ ] `GET /api/news/trending` updates at most every 15min (cached)
- [ ] Background refresh does not block API responses
- [ ] Finnhub rate limit (60/min) respected with exponential backoff

---

#### PRD-10 · News Feed + Sentiment UI
**Status:** Not started  
**Branch naming:** `feat/prd-10-news-sentiment-ui`

**Scope:**
- News panel on company overview page (from PRD-08)
- `/news` page — full news feed, filterable by ticker/sector/sentiment polarity
- Sentiment badge component: `● Bullish 74%` / `● Bearish 31%` / `● Neutral`
- "Trending Now" strip on homepage (replaces or sits alongside Market Snapshot)
- AI news digest card: "3 key things happening with NVDA this week" (Claude Haiku, cached 3h)

**Skills to activate:**
- `market-news-analyst` — generates AI news digest summaries
- `ui-ux-pro-max` — news feed layout, sentiment badge design

**Acceptance criteria:**
- [ ] Sentiment badge updates without full page reload
- [ ] News feed shows article title, source, time, sentiment, 1-line summary
- [ ] "Trending Now" strip shows 6 tickers with 24h sentiment direction
- [ ] AI news digest clearly labelled as AI-generated, cached per ticker per 3h

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

| PRD | Title | Merged | Notes |
|---|---|---|---|
| PRD-01 | Research Templates | ✅ 2026-05-08 | 5 templates, available/unavailable split |
| PRD-02 | Strategy Storage + Shareable URLs | ✅ 2026-05-08 | Slug-based public URLs |
| PRD-03 | Personal Strategy Library | ✅ 2026-05-08 | localStorage, comparison tab |
| PRD-04 | Interactive Clarification + Capability Glossary | ✅ 2026-05-11 | ClarificationState enum, amber chat bubbles, quick-reply chips, glossary on homepage + workspace sidebar |
| PRD-05 | `not_supported` Strategy Handling | 🔲 In discussion | Honest redirect with closest supported reformulation |

---

## Open / In-Discussion PRDs

| PRD | Title | Status |
|---|---|---|
| PRD-05 | `not_supported` strategy handling | Needs discussion — how to redirect users |

---

## Deferred / Out of Scope

- Live trade execution (permanent constraint)
- Intraday / minute-level data
- Options, futures, margin trading
- Community Phase 4 (cross-device sync, advanced curation) — post Phase 3
- Fundamental data for A-shares (FMP doesn't cover well; deferred)
