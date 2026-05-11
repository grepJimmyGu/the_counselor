from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

SENTIMENT_DISCLAIMER = (
    "This tool provides research candidates, not financial advice. "
    "News, social, and community sentiment data may be delayed, incomplete, biased, or noisy. "
    "Always verify important events with primary sources."
)


class ProviderStatus(str, Enum):
    active = "active"
    not_configured = "not_configured"
    rate_limited = "rate_limited"
    failed = "failed"
    unavailable = "unavailable"


# ── Raw provider records ──────────────────────────────────────────────────────

class NewsArticle(BaseModel):
    provider: str
    symbol: str
    title: str
    summary: Optional[str] = None
    source_name: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    topics: list[str] = []
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    relevance_score: Optional[float] = None


class CommunityMention(BaseModel):
    provider: str
    platform: str
    symbol: str
    title: Optional[str] = None
    text: str
    author: Optional[str] = None
    community_name: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    upvotes: Optional[int] = None
    downvotes: Optional[int] = None
    comments: Optional[int] = None
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    relevance_score: Optional[float] = None


# ── Four-section analysis output ─────────────────────────────────────────────

class NewsCatalystSection(BaseModel):
    main_catalyst_summary: Optional[str] = None
    catalyst_type: Optional[str] = None
    catalyst_scope: Optional[str] = None
    time_horizon: Optional[str] = None
    expected_business_impact: Optional[str] = None
    catalyst_materiality_label: Optional[str] = None
    information_source_quality_label: Optional[str] = None
    source_quality_notes: Optional[str] = None
    key_articles: list[dict] = []
    confidence: str = "partial"
    source_notes: list[str] = []


class NewsSentimentSection(BaseModel):
    news_sentiment_label: Optional[str] = None
    news_sentiment_trend: Optional[str] = None
    bullish_news_themes: list[str] = []
    bearish_news_themes: list[str] = []
    conflicting_news_signals: list[str] = []
    news_sentiment_score: Optional[float] = None
    source_diversity: Optional[str] = None
    confidence: str = "partial"
    source_notes: list[str] = []


class CommunityPulseSection(BaseModel):
    community_sentiment_label: Optional[str] = None
    community_attention_label: Optional[str] = None
    community_attention_trend: Optional[str] = None
    dominant_sources: list[str] = []
    bullish_community_themes: list[str] = []
    bearish_community_themes: list[str] = []
    representative_discussions: list[dict] = []
    internal_platform_stats: dict = {}
    external_social_stats: dict = {}
    confidence: str = "not_configured"
    source_notes: list[str] = []


class SignalQualityRiskSection(BaseModel):
    signal_quality_label: Optional[str] = None
    news_community_alignment: Optional[str] = None
    materiality_assessment: Optional[str] = None
    information_source_quality_assessment: Optional[str] = None
    crowding_risk: Optional[str] = None
    overreaction_risk: Optional[str] = None
    headline_risks: list[str] = []
    required_next_checks: list[str] = []
    confidence: str = "partial"
    source_notes: list[str] = []


class SentimentTakeaway(BaseModel):
    takeaway_label: str = "Too Unclear"
    takeaway_summary: Optional[str] = None
    suggested_user_action: Optional[str] = None


class SentimentScores(BaseModel):
    catalyst_score: int = 50
    catalyst_materiality_score: int = 50
    information_source_quality_score: int = 50
    news_sentiment_score: int = 50
    community_sentiment_score: int = 50
    attention_score: int = 50
    signal_quality_score: int = 50
    risk_score: int = 30
    overall_sentiment_signal_score: int = 50
    overall_label: str = "Too Unclear"


class SentimentSummaryResponse(BaseModel):
    symbol: str
    as_of_datetime: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    news_catalyst: NewsCatalystSection
    news_sentiment: NewsSentimentSection
    community_pulse: CommunityPulseSection
    signal_quality_risk: SignalQualityRiskSection
    takeaway: SentimentTakeaway
    scores: SentimentScores
    provider_status: dict[str, str] = {}
    warnings: list[str] = []
    disclaimer: str = SENTIMENT_DISCLAIMER


class ProvidersStatusResponse(BaseModel):
    alpha_vantage: str
    reddit: str
    x: str
    internal_community: str


class SentimentCandidateResult(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    overall_sentiment_signal_score: int
    overall_label: str
    takeaway_label: str
    takeaway_summary: Optional[str] = None
    catalyst_type: Optional[str] = None
    catalyst_materiality_label: Optional[str] = None
    news_sentiment_label: Optional[str] = None
    signal_quality_label: Optional[str] = None
    bullish_themes: list[str] = []
    bearish_themes: list[str] = []
    provider_status: dict[str, str] = {}


class SentimentAnalyzeRequest(BaseModel):
    symbols: list[str]
    toolkit_id: Optional[str] = None
    refresh: bool = False


class SentimentAnalyzeResponse(BaseModel):
    candidates: list[SentimentCandidateResult]
    provider_status: dict[str, str]
    warnings: list[str] = []
    toolkit_id: Optional[str] = None


class SentimentSandboxRequest(BaseModel):
    symbol: str
    sentiment_summary: dict


class SentimentSandboxResponse(BaseModel):
    review_verdict: str
    trust_score: int
    key_concerns: list[str] = []
    missing_data: list[str] = []
    noise_risks: list[str] = []
    source_limitations: list[str] = []
    required_next_checks: list[str] = []
    final_warning: Optional[str] = None
