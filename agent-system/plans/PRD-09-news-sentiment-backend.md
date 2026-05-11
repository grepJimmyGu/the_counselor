# PRD-09: News & Community Sentiment Module — Backend

**Status:** Not started  
**Date:** 2026-05-11  
**Depends on:** None (Alpha Vantage already integrated)  
**Followed by:** PRD-10 (frontend)  
**Branch naming:** `feat/prd-09-news-sentiment-backend`

---

## Goal

Build the backend data pipeline, provider system, AI analysis chain, and API endpoints for the News & Community Sentiment module. The module helps users answer one core question per stock:

> "Is this stock getting attention for a real reason, and is that attention likely useful or dangerous?"

---

## Aligned Decisions

| Decision | Value |
|---|---|
| LLM for analysis | Claude Haiku 4.5 (fast, cheap: ~$0.004/ticker) |
| LLM for sandbox | Claude Sonnet 4.6 (quality: ~$0.01/review) |
| Cache TTL — LLM output | **3 hours** |
| Cache TTL — raw articles | 15 minutes |
| Cache pre-warming | Top 100 S&P 500 tickers every 3h via background job |
| News provider MVP | Alpha Vantage `NEWS_SENTIMENT` (already integrated) |
| Reddit | Active if `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` set; `not_configured` otherwise |
| X (Twitter) | Interface only, `not_configured` by default — actual integration deferred (requires $100/mo API) |
| Internal community | Interface only, `not_configured` until Phase 3 (PRD-11–14) |
| Sandbox review | On-demand only — never auto-triggered |
| Thinly covered stocks | Skip LLM if < 3 articles; return `confidence: "too_few_articles"` |
| No buy/sell language | Use: research candidate, catalyst candidate, watchlist candidate |

---

## Architecture

```
Alpha Vantage NEWS_SENTIMENT
         ↓
news_article_cache_service.py
(raw articles, 15min TTL)
         ↓
news_catalyst_service.py          ← LLM (Haiku), 3h TTL
news_sentiment_service.py         ← LLM (Haiku), 3h TTL
         ↓
Reddit Provider (if configured)
         ↓
community_mention_cache_service.py
(raw mentions, 15min TTL)
         ↓
community_pulse_service.py        ← LLM (Haiku), 3h TTL
         ↓
signal_quality_risk_service.py    ← LLM (Haiku), 3h TTL
         ↓
sentiment_signal_scoring_service.py (deterministic formulas)
         ↓
sentiment_signal_summaries (DB, 3h TTL)
```

---

## Provider System

### Provider interface

```python
# apps/api/app/services/sentiment_provider_interface.py

from enum import Enum
from typing import Protocol

class ProviderStatus(str, Enum):
    active = "active"
    not_configured = "not_configured"
    rate_limited = "rate_limited"
    failed = "failed"
    unavailable = "unavailable"

class NewsProviderRecord(TypedDict):
    provider: str
    source_type: Literal["news"]
    symbol: str
    title: str
    summary: str
    source_name: str
    url: str
    published_at: str
    topics: list[str]
    sentiment_score: float | None
    sentiment_label: str
    relevance_score: float | None
    raw_json: dict

class CommunityProviderRecord(TypedDict):
    provider: str
    source_type: Literal["community"]
    platform: str
    symbol: str
    text: str
    title: str
    author: str
    url: str
    published_at: str
    engagement: dict  # upvotes, downvotes, comments, reposts, likes, views
    community_name: str
    sentiment_score: float | None
    sentiment_label: str
    relevance_score: float | None
    raw_json: dict

class NewsProvider(Protocol):
    def status(self) -> ProviderStatus: ...
    async def fetch(self, symbol: str, limit: int = 20) -> list[NewsProviderRecord]: ...

class CommunityProvider(Protocol):
    def status(self) -> ProviderStatus: ...
    async def fetch(self, symbol: str, limit: int = 30) -> list[CommunityProviderRecord]: ...
```

### News providers

**1. Alpha Vantage News Provider (active in MVP)**
```python
# apps/api/app/services/alpha_vantage_news_provider.py
# Calls: GET /query?function=NEWS_SENTIMENT&tickers={symbol}&limit=50
# Returns: normalized NewsProviderRecord list with pre-computed sentiment from AV
# Status: active (AV key already configured)
```

**2. Finnhub News Provider (future)**
```python
# Placeholder class, status = not_configured
# Endpoint: GET /api/v1/company-news?symbol={symbol}&from={date}&to={date}
```

### Community providers

**1. Reddit Provider (active if env vars set)**
```python
# apps/api/app/services/reddit_community_provider.py
# Library: praw (pip install praw)
# Env: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
# Subreddits (configurable): r/wallstreetbets, r/investing, r/stocks, r/SecurityAnalysis
# Search: posts mentioning ticker cashtag or company name, last 7 days
# Status: active if env vars set, not_configured otherwise
```

**2. X Provider (placeholder, not_configured)**
```python
# apps/api/app/services/x_community_provider.py
# Status: always not_configured until integration PRD approved
# Reason: requires $100/mo API subscription
# Interface complete so activation is a future config change, not a code change
```

**3. Internal Community Provider (placeholder, not_configured)**
```python
# apps/api/app/services/internal_community_provider.py
# Status: not_configured until Phase 3 (PRD-11-14)
# Will read from strategy_comments, user_votes, user_watchlists tables when available
```

---

## LLM Analysis Chain

For each ticker, when cache is stale (> 3 hours old):

```python
# Input to Haiku:
# - Last 20 articles (title + summary) from Alpha Vantage
# - AV pre-computed sentiment scores per article
# - Community mention summaries (if Reddit active)

# Step 1: Extract structured analysis (single LLM call)
# Returns: News Catalyst + News Sentiment + Community Pulse + Signal Quality + Takeaway
# Cost: ~$0.004 per ticker
# Latency: 1–3s (Haiku is fast)

# If < 3 articles available:
# Skip LLM, return: {confidence: "too_few_articles", all sections: null}
```

**LLM output schema (single call returns all four sections):**
```json
{
  "business_map": null,
  "news_catalyst": {
    "section_name": "News Catalyst",
    "main_catalyst_summary": "",
    "catalyst_type": "",
    "catalyst_scope": "company_specific | sector_wide | macro_driven | unclear",
    "time_horizon": "short_term | medium_term | long_term | unclear",
    "expected_business_impact": "",
    "catalyst_materiality_label": "",
    "information_source_quality_label": "",
    "source_quality_notes": "",
    "key_articles": [],
    "confidence": "",
    "source_notes": []
  },
  "news_sentiment": {
    "section_name": "News Sentiment",
    "news_sentiment_label": "",
    "news_sentiment_trend": "improving | deteriorating | stable | unclear",
    "bullish_news_themes": [],
    "bearish_news_themes": [],
    "conflicting_news_signals": [],
    "news_sentiment_score": null,
    "source_diversity": "",
    "confidence": "",
    "source_notes": []
  },
  "community_pulse": {
    "section_name": "Community Pulse",
    "community_sentiment_label": "",
    "community_attention_label": "",
    "community_attention_trend": "rising | falling | stable | unclear",
    "dominant_sources": [],
    "bullish_community_themes": [],
    "bearish_community_themes": [],
    "representative_discussions": [],
    "internal_platform_stats": {
      "post_count": null, "comment_count": null,
      "upvote_count": null, "downvote_count": null,
      "save_count": null, "clone_count": null
    },
    "external_social_stats": {
      "reddit_post_count": null, "reddit_comment_count": null,
      "x_post_count": null, "engagement_count": null
    },
    "confidence": "",
    "source_notes": []
  },
  "signal_quality_risk": {
    "section_name": "Signal Quality & Risk",
    "signal_quality_label": "",
    "news_community_alignment": "",
    "materiality_assessment": "",
    "information_source_quality_assessment": "",
    "crowding_risk": "",
    "overreaction_risk": "",
    "headline_risks": [],
    "required_next_checks": [],
    "confidence": "",
    "source_notes": []
  },
  "takeaway": {
    "takeaway_label": "",
    "takeaway_summary": "",
    "suggested_user_action": ""
  }
}
```

**Disclaimer appended to every response:**
> "This tool provides research candidates, not financial advice. News, social, and community sentiment data may be delayed, incomplete, biased, or noisy. Always verify important events with primary sources."

---

## Scoring Framework (deterministic, computed after LLM output)

All scores 0–100. Higher = more positive signal, except `risk_score` (higher = more risk).

| Score | Weight in overall | How computed |
|---|---|---|
| `catalyst_score` | 20% | Catalyst type × materiality label → lookup table |
| `catalyst_materiality_score` | 20% | Highly Material=100, Moderately=65, Low=30, Unclear=15, Risk=20 |
| `information_source_quality_score` | 15% | High Quality=100, Moderate=65, Low=30, Unverified=10, Single-Source=25 |
| `news_sentiment_score` | 15% | Strong Positive=100, Positive=75, Mixed Positive=55, Neutral=50, Mixed Negative=35, Negative=15, Deteriorating=10 |
| `community_sentiment_score` | 10% | Strong Bullish=100 → Not Configured=50 (neutral default) |
| `attention_score` | 10% | Based on article count + community volume vs. 30-day baseline |
| `signal_quality_score` | 10% | High Quality Catalyst=100, News Confirmed=90, Mixed=50, Mostly Noise=10 |
| `risk_score` | negative | Crowded Trade=−30, Headline Risk=−20, Meme/Hype=−25, Overreaction=−15 |

```python
overall = (
    catalyst_score * 0.20
    + catalyst_materiality_score * 0.20
    + information_source_quality_score * 0.15
    + news_sentiment_score * 0.15
    + community_sentiment_score * 0.10
    + attention_score * 0.10
    + signal_quality_score * 0.10
    - risk_score * 0.30  # risk reduces overall score
)
# Clamped 0–100
```

**Overall labels:**
| Score | Label |
|---|---|
| 80–100 | Strong Positive Catalyst |
| 70–79 | News Confirmed by Community |
| 60–69 | Improving Sentiment Candidate |
| 50–59 | Rising Attention Candidate |
| 40–49 | Highly Debated Candidate |
| 30–39 | Community Hype Risk |
| 20–29 | Headline Risk Candidate |
| 10–19 | Mostly Noise |
| 0–9 | Too Unclear |

---

## Pre-built Toolkits

Each toolkit runs `POST /api/sentiment/analyze` with a standard symbol universe and filter set.

| ID | Name | Selection logic |
|---|---|---|
| `positive_catalyst` | Positive Catalyst Watchlist | `catalyst_score > 70` AND `catalyst_materiality_score > 60` |
| `news_community_confirmed` | News Confirmed by Community | `news_sentiment_score > 65` AND `community_sentiment_score > 65` |
| `rising_attention` | Rising Attention Stocks | `attention_score > 75` (attention trending up) |
| `sentiment_reversal` | Sentiment Reversal | `news_sentiment_trend = "improving"` AND prior `news_sentiment_score < 40` |
| `controversial` | Controversial Stocks | `community_sentiment_label` in `["Highly Controversial", "Retail Buzz"]` AND `attention_score > 60` |
| `headline_risk` | Headline Risk Watchlist | `risk_score > 50` OR `signal_quality_label = "Headline Risk"` |
| `community_hype` | Community Hype Watchlist | `community_sentiment_score > 70` AND `news_sentiment_score < 40` |

---

## Database Tables

```sql
-- news_articles: raw cache from Alpha Vantage + Finnhub (future)
CREATE TABLE news_articles (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(40) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    source_name VARCHAR(120),
    url TEXT,
    published_at TIMESTAMPTZ,
    topics JSONB DEFAULT '[]',
    ticker_sentiment_score FLOAT,
    ticker_sentiment_label VARCHAR(30),
    overall_sentiment_score FLOAT,
    overall_sentiment_label VARCHAR(30),
    relevance_score FLOAT,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (provider, url)
);
CREATE INDEX idx_news_articles_symbol_published ON news_articles (symbol, published_at DESC);

-- community_mentions: Reddit (active), X (future), internal (Phase 3)
CREATE TABLE community_mentions (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(40) NOT NULL,
    platform VARCHAR(40) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    title TEXT,
    text TEXT,
    author VARCHAR(120),
    community_name VARCHAR(120),
    url TEXT,
    published_at TIMESTAMPTZ,
    upvotes INT,
    downvotes INT,
    comments INT,
    reposts INT,
    likes INT,
    views INT,
    sentiment_score FLOAT,
    sentiment_label VARCHAR(30),
    relevance_score FLOAT,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (provider, url)
);
CREATE INDEX idx_community_mentions_symbol ON community_mentions (symbol, published_at DESC);

-- sentiment_signal_summaries: LLM output + scores, 3h TTL
CREATE TABLE sentiment_signal_summaries (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    as_of_datetime TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,  -- as_of_datetime + 3 hours
    news_catalyst JSONB,
    news_sentiment JSONB,
    community_pulse JSONB,
    signal_quality_risk JSONB,
    takeaway JSONB,
    catalyst_score SMALLINT,
    catalyst_materiality_score SMALLINT,
    information_source_quality_score SMALLINT,
    news_sentiment_score SMALLINT,
    community_sentiment_score SMALLINT,
    attention_score SMALLINT,
    signal_quality_score SMALLINT,
    risk_score SMALLINT,
    overall_sentiment_signal_score SMALLINT,
    overall_label VARCHAR(60),
    confidence VARCHAR(20),
    provider_status JSONB,   -- which providers were active during this run
    warnings JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_sentiment_summaries_symbol_expires ON sentiment_signal_summaries (symbol, expires_at DESC);

-- sentiment_toolkit_runs: for bulk analyze / toolkit results
CREATE TABLE sentiment_toolkit_runs (
    id SERIAL PRIMARY KEY,
    toolkit_id VARCHAR(40),
    query JSONB,          -- symbols + filters used
    provider_status JSONB,
    result_summary JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- sentiment_toolkit_candidates: ranked results per run
CREATE TABLE sentiment_toolkit_candidates (
    id SERIAL PRIMARY KEY,
    run_id INT REFERENCES sentiment_toolkit_runs(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    rank SMALLINT,
    overall_sentiment_signal_score SMALLINT,
    labels_json JSONB,
    takeaway_json JSONB,
    key_news JSONB DEFAULT '[]',
    key_community_mentions JSONB DEFAULT '[]',
    bullish_themes JSONB DEFAULT '[]',
    bearish_themes JSONB DEFAULT '[]',
    risks JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Backend Services

```
apps/api/app/services/
├── sentiment_provider_interface.py      # Protocol classes + ProviderStatus enum
├── alpha_vantage_news_provider.py       # AV NEWS_SENTIMENT, active
├── finnhub_news_provider.py             # Placeholder, not_configured
├── reddit_community_provider.py         # Active if env vars set (praw)
├── x_community_provider.py             # Placeholder, not_configured
├── internal_community_provider.py      # Placeholder, not_configured until Phase 3
├── news_article_cache_service.py        # Fetch + cache raw articles (15min TTL)
├── community_mention_cache_service.py   # Fetch + cache raw mentions (15min TTL)
├── news_catalyst_service.py             # LLM extraction of catalyst section
├── news_sentiment_service.py            # LLM extraction of sentiment section
├── community_pulse_service.py           # LLM extraction of community section
├── signal_quality_risk_service.py       # LLM extraction of signal quality section
├── sentiment_signal_scoring_service.py  # Deterministic scoring (no LLM)
├── sentiment_toolkit_service.py         # Run toolkit queries across symbol universe
└── sentiment_sandbox_reviewer.py        # On-demand Sonnet review
```

---

## API Endpoints

```
GET  /api/sentiment/{symbol}/summary
     → all four sections + scores + labels + provider_status + warnings
     → returns cached if expires_at > now(), otherwise triggers fresh analysis
     → always async: returns job_id if analysis is running, poll for result

GET  /api/sentiment/{symbol}/news
     → raw cached news articles (last 15min fetch)

GET  /api/sentiment/{symbol}/community
     → raw cached community mentions (last 15min fetch)

GET  /api/sentiment/providers/status
     → {alpha_vantage: "active", reddit: "not_configured", x: "not_configured",
        internal: "not_configured"}

POST /api/sentiment/analyze
     → body: {symbols: [], toolkit_id?: string, refresh?: bool, enabled_providers?: []}
     → returns: ranked candidates list + provider_status + warnings
     → runs in background, returns run_id to poll

POST /api/sentiment/review
     → body: {symbol: string, sentiment_summary: object}
     → on-demand Sonnet sandbox review
     → NOT cached, runs on every call
```

---

## Environment Variables

```bash
# Already configured
ALPHA_VANTAGE_API_KEY=...

# Reddit (optional — provider active only if both set)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=livermore-research/1.0

# X (optional — deferred, requires $100/mo X API Basic subscription)
X_API_BEARER_TOKEN=
```

---

## Background Job — Cache Pre-warmer

```python
# Runs every 3 hours via Railway background worker (or APScheduler)
# Pre-analyses top 100 S&P 500 tickers so first-load latency is near-zero for popular stocks
# Cost: 100 tickers × $0.004 = $0.40 per run × 8 runs/day = $3.20/day = ~$96/month
# Can be toggled off via PREWARM_ENABLED=false env var

TOP_100_TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", ...]
```

---

## Skills to activate during build

| Skill | When |
|---|---|
| `market-news-analyst` | Reference when writing LLM system prompt for news catalyst + sentiment extraction |
| `data-quality-checker` | Validate Alpha Vantage NEWS_SENTIMENT response field coverage |
| `safe-migration` | Review all 5 new table Alembic migrations |

---

## Acceptance Criteria

- [ ] `GET /api/sentiment/AAPL/summary` returns all four sections with correct field population
- [ ] Alpha Vantage is `active` in provider_status; Reddit/X/Internal are `not_configured`
- [ ] LLM analysis is cached for 3 hours — second request within window hits DB, not LLM
- [ ] Tickers with < 3 articles return `confidence: "too_few_articles"` without LLM call
- [ ] `safe-migration` skill run confirms migrations are safe before merge
- [ ] Reddit provider returns `not_configured` gracefully when env vars absent
- [ ] `POST /api/sentiment/review` runs Sonnet review on-demand only
- [ ] Pre-warming background job runs every 3 hours without blocking API
- [ ] All new services have unit tests (happy path + AV rate-limit error + LLM failure fallback)
- [ ] Daily spend alert threshold documented: $20/day triggers monitoring notification
