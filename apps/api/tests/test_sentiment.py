from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.sentiment import (
    NewsArticle,
    CommunityMention,
    ProviderStatus,
    SentimentScores,
)
from app.services.sentiment_signal_scoring_service import compute_scores
from app.services.sentiment_toolkit_service import (
    SentimentToolkitService,
    list_toolkits,
    _passes_toolkit,
)
from app.services.alpha_vantage_news_provider import AlphaVantageNewsProvider
from app.services.reddit_community_provider import RedditCommunityProvider
from app.services.x_community_provider import XCommunityProvider
from app.services.internal_community_provider import InternalCommunityProvider


# ── Provider status tests ─────────────────────────────────────────────────────

def test_x_provider_always_not_configured():
    p = XCommunityProvider()
    assert p.status() == ProviderStatus.not_configured


def test_internal_provider_always_not_configured():
    p = InternalCommunityProvider()
    assert p.status() == ProviderStatus.not_configured


def test_reddit_not_configured_without_env():
    with patch("app.services.reddit_community_provider.get_settings") as mock_s:
        mock_s.return_value = MagicMock(reddit_client_id="", reddit_client_secret="")
        p = RedditCommunityProvider()
        assert p.status() == ProviderStatus.not_configured


def test_av_not_configured_without_key():
    with patch("app.services.alpha_vantage_news_provider.get_settings") as mock_s:
        mock_s.return_value = MagicMock(alpha_vantage_api_key="", api_timeout_seconds=20)
        p = AlphaVantageNewsProvider()
        assert p.status() == ProviderStatus.not_configured


def test_av_active_with_key():
    with patch("app.services.alpha_vantage_news_provider.get_settings") as mock_s:
        mock_s.return_value = MagicMock(alpha_vantage_api_key="TESTKEY", api_timeout_seconds=20)
        p = AlphaVantageNewsProvider()
        assert p.status() == ProviderStatus.active


# ── Scoring tests ─────────────────────────────────────────────────────────────

def _make_llm_output(
    materiality="Moderately Material",
    source_quality="Moderate Quality Sources",
    news_label="Positive",
    news_trend="improving",
    community_label="Neutral",
    sig_quality="News Confirmed",
) -> dict:
    return {
        "news_catalyst": {
            "catalyst_materiality_label": materiality,
            "information_source_quality_label": source_quality,
            "catalyst_type": "earnings beat",
        },
        "news_sentiment": {
            "news_sentiment_label": news_label,
            "news_sentiment_trend": news_trend,
        },
        "community_pulse": {
            "community_sentiment_label": community_label,
        },
        "signal_quality_risk": {
            "signal_quality_label": sig_quality,
            "crowding_risk": "low",
            "overreaction_risk": "low",
            "headline_risks": [],
        },
        "takeaway": {"takeaway_label": ""},
        "confidence": "partial",
    }


def test_scoring_happy_path():
    output = _make_llm_output()
    scores = compute_scores(output, article_count=15, mention_count=5)
    assert isinstance(scores, SentimentScores)
    assert 0 <= scores.overall_sentiment_signal_score <= 100
    assert scores.catalyst_score > 0
    assert scores.news_sentiment_score == 75  # "Positive"


def test_scoring_strong_positive():
    output = _make_llm_output(
        materiality="Highly Material",
        source_quality="High Quality Sources",
        news_label="Strong Positive",
        community_label="Strong Bullish",
        sig_quality="High Quality Catalyst",
    )
    scores = compute_scores(output, article_count=25, mention_count=20)
    assert scores.overall_sentiment_signal_score >= 70
    assert scores.overall_label in (
        "Strong Positive Catalyst", "News Confirmed by Community", "Improving Sentiment Candidate"
    )


def test_scoring_risk_accumulation():
    output = _make_llm_output(sig_quality="Mostly Noise")
    output["signal_quality_risk"]["crowding_risk"] = "high crowded meme"
    output["signal_quality_risk"]["overreaction_risk"] = "high significant"
    output["signal_quality_risk"]["headline_risks"] = ["risk1", "risk2"]
    scores = compute_scores(output, article_count=5, mention_count=30)
    assert scores.risk_score >= 70

def test_scoring_too_few_articles():
    from app.services.sentiment_llm_service import _too_few_articles_result
    result = _too_few_articles_result("TEST")
    assert result["confidence"] == "too_few_articles"
    scores = compute_scores(result, article_count=1, mention_count=0)
    assert scores.overall_sentiment_signal_score <= 60  # low confidence → mediocre score


# ── Toolkit tests ─────────────────────────────────────────────────────────────

def test_list_toolkits_returns_seven():
    tkts = list_toolkits()
    assert len(tkts) == 7
    ids = {t["id"] for t in tkts}
    assert "positive_catalyst" in ids
    assert "community_hype" in ids


def test_positive_catalyst_filter():
    scores = {"catalyst_score": 80, "catalyst_materiality_score": 70}
    assert _passes_toolkit("positive_catalyst", scores, {})
    scores2 = {"catalyst_score": 60, "catalyst_materiality_score": 70}
    assert not _passes_toolkit("positive_catalyst", scores2, {})


def test_news_community_confirmed_filter():
    s = {"news_sentiment_score": 70, "community_sentiment_score": 70}
    assert _passes_toolkit("news_community_confirmed", s, {})
    s2 = {"news_sentiment_score": 60, "community_sentiment_score": 70}
    assert not _passes_toolkit("news_community_confirmed", s2, {})


def test_headline_risk_filter():
    s = {"risk_score": 60}
    assert _passes_toolkit("headline_risk", s, {})
    s2 = {"risk_score": 30}
    labels = {"signal_quality_label": "Headline Risk"}
    assert _passes_toolkit("headline_risk", s2, labels)
    labels2 = {"signal_quality_label": "Mixed Signals"}
    assert not _passes_toolkit("headline_risk", s2, labels2)


def test_community_hype_filter():
    s = {"community_sentiment_score": 75, "news_sentiment_score": 35}
    assert _passes_toolkit("community_hype", s, {})
    s2 = {"community_sentiment_score": 75, "news_sentiment_score": 50}
    assert not _passes_toolkit("community_hype", s2, {})


# ── LLM service — too_few_articles guard ─────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_service_skips_llm_on_too_few_articles():
    from app.services.sentiment_llm_service import SentimentLLMService
    with patch("app.services.sentiment_llm_service.get_settings") as mock_s:
        mock_s.return_value = MagicMock(anthropic_api_key="KEY")
        svc = SentimentLLMService()
        result = await svc.analyze("AAPL", articles=[], mentions=[])
        assert result["confidence"] == "too_few_articles"


@pytest.mark.asyncio
async def test_llm_service_returns_fallback_when_not_configured():
    from app.services.sentiment_llm_service import SentimentLLMService
    with patch("app.services.sentiment_llm_service.get_settings") as mock_s:
        mock_s.return_value = MagicMock(anthropic_api_key="")
        svc = SentimentLLMService()
        articles = [
            NewsArticle(provider="alpha_vantage", symbol="AAPL", title=f"Article {i}",
                        sentiment_score=0.3, sentiment_label="Positive")
            for i in range(5)
        ]
        result = await svc.analyze("AAPL", articles=articles, mentions=[])
        assert result["confidence"] == "partial"
        assert result["news_sentiment"]["news_sentiment_label"] == "Mixed Positive"


# ── AV provider — rate limit graceful return ──────────────────────────────────

@pytest.mark.asyncio
async def test_av_fetch_returns_empty_on_http_error():
    with patch("app.services.alpha_vantage_news_provider.get_settings") as mock_s:
        mock_s.return_value = MagicMock(
            alpha_vantage_api_key="KEY", api_timeout_seconds=20
        )
        p = AlphaVantageNewsProvider()
        import httpx
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "429", request=MagicMock(), response=MagicMock(status_code=429)
                )
            )
            mock_client_cls.return_value = mock_client
            result = await p.fetch("AAPL")
            assert result == []
