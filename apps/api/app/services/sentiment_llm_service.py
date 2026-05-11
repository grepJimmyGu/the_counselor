from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings
from app.schemas.sentiment import (
    CommunityMention,
    CommunityPulseSection,
    NewsCatalystSection,
    NewsSentimentSection,
    NewsArticle,
    SentimentTakeaway,
    SignalQualityRiskSection,
)

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MIN_ARTICLES = 3

_SYSTEM_PROMPT = """You are a financial news and sentiment analyst. Analyze news articles and community discussions about a stock ticker.

Return ONLY a valid JSON object — no preamble, no explanation, no markdown fences.

Use these EXACT labels (case-sensitive):

catalyst_materiality_label: "Highly Material" | "Moderately Material" | "Low Materiality" | "Unclear Materiality" | "Risk Event"
information_source_quality_label: "High Quality Sources" | "Moderate Quality Sources" | "Low Quality Sources" | "Unverified Sources" | "Single Source"
news_sentiment_label: "Strong Positive" | "Positive" | "Mixed Positive" | "Neutral" | "Mixed Negative" | "Negative" | "Deteriorating"
news_sentiment_trend: "improving" | "deteriorating" | "stable" | "unclear"
community_sentiment_label: "Strong Bullish" | "Bullish" | "Mixed Bullish" | "Neutral" | "Mixed Bearish" | "Bearish" | "Strong Bearish" | "Highly Controversial" | "Retail Buzz" | "Not Configured"
community_attention_trend: "rising" | "falling" | "stable" | "unclear"
signal_quality_label: "High Quality Catalyst" | "News Confirmed" | "Mixed Signals" | "Mostly Noise" | "Headline Risk"
confidence in each section: "high" | "partial" | "low" | "not_available"
takeaway_label: "Strong Positive Catalyst" | "News Confirmed by Community" | "Improving Sentiment Candidate" | "Rising Attention Candidate" | "Highly Debated Candidate" | "Community Hype Risk" | "Headline Risk Candidate" | "Mostly Noise" | "Too Unclear"

Rules:
- Only use information from the provided articles/mentions. Do not invent events.
- Lists (themes, risks, checks) should have 2–5 items max.
- key_articles: pick up to 3 titles + urls from the actual input.
- If community data is absent, set community_sentiment_label to "Not Configured" and confidence to "not_available".

Return JSON with exactly this shape:
{
  "news_catalyst": {
    "main_catalyst_summary": "",
    "catalyst_type": "",
    "catalyst_scope": "company_specific|sector_wide|macro_driven|unclear",
    "time_horizon": "short_term|medium_term|long_term|unclear",
    "expected_business_impact": "",
    "catalyst_materiality_label": "",
    "information_source_quality_label": "",
    "source_quality_notes": "",
    "key_articles": [{"title": "", "url": ""}],
    "confidence": "",
    "source_notes": []
  },
  "news_sentiment": {
    "news_sentiment_label": "",
    "news_sentiment_trend": "",
    "bullish_news_themes": [],
    "bearish_news_themes": [],
    "conflicting_news_signals": [],
    "source_diversity": "",
    "confidence": "",
    "source_notes": []
  },
  "community_pulse": {
    "community_sentiment_label": "",
    "community_attention_label": "",
    "community_attention_trend": "",
    "dominant_sources": [],
    "bullish_community_themes": [],
    "bearish_community_themes": [],
    "representative_discussions": [],
    "confidence": "",
    "source_notes": []
  },
  "signal_quality_risk": {
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
}"""


def _build_user_prompt(
    symbol: str,
    articles: list[NewsArticle],
    mentions: list[CommunityMention],
) -> str:
    lines = [f"# Stock: {symbol.upper()}", "", "## News Articles (latest first)"]
    for i, a in enumerate(articles[:20], 1):
        pub = a.published_at.strftime("%Y-%m-%d") if a.published_at else "unknown"
        lines.append(f"{i}. [{pub}] **{a.title}** — {a.source_name or 'unknown source'}")
        if a.summary:
            lines.append(f"   Summary: {a.summary[:200]}")
        if a.sentiment_label:
            lines.append(f"   AV Sentiment: {a.sentiment_label} (score={a.sentiment_score})")
        if a.url:
            lines.append(f"   URL: {a.url}")
    if mentions:
        lines += ["", "## Community Discussions"]
        for i, m in enumerate(mentions[:15], 1):
            pub = m.published_at.strftime("%Y-%m-%d") if m.published_at else "unknown"
            lines.append(f"{i}. [{pub}] r/{m.community_name or m.platform}: {m.title or m.text[:120]}")
            if m.upvotes is not None:
                lines.append(f"   Upvotes: {m.upvotes}, Comments: {m.comments or 0}")
    else:
        lines += ["", "## Community Discussions", "No community data available (providers not configured)."]
    lines += ["", "Analyze the above and return the JSON structure as instructed."]
    return "\n".join(lines)


class SentimentLLMService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _is_configured(self) -> bool:
        return bool(self._settings.anthropic_api_key)

    async def analyze(
        self,
        symbol: str,
        articles: list[NewsArticle],
        mentions: list[CommunityMention],
    ) -> dict[str, Any]:
        if len(articles) < _MIN_ARTICLES:
            return _too_few_articles_result(symbol)

        if not self._is_configured():
            return _llm_disabled_result(symbol, articles)

        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)
            user_prompt = _build_user_prompt(symbol, articles, mentions)
            message = await client.messages.create(
                model=_HAIKU_MODEL,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.1,
            )
            raw = message.content[0].text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Haiku returned non-JSON for %s: %s", symbol, exc)
            return _llm_disabled_result(symbol, articles)
        except Exception as exc:
            logger.warning("Haiku analysis failed for %s: %s", symbol, exc)
            return _llm_disabled_result(symbol, articles)

        return _normalize_payload(payload)


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for section in ("news_catalyst", "news_sentiment", "community_pulse", "signal_quality_risk"):
        if section not in payload:
            payload[section] = {}
    if "takeaway" not in payload:
        payload["takeaway"] = {}
    payload["confidence"] = "partial"
    return payload


def _too_few_articles_result(symbol: str) -> dict[str, Any]:
    note = [f"Fewer than {_MIN_ARTICLES} articles found — LLM analysis skipped."]
    empty_cat = NewsCatalystSection(confidence="low", source_notes=note)
    empty_sent = NewsSentimentSection(confidence="low", source_notes=note)
    empty_comm = CommunityPulseSection(confidence="not_available")
    empty_sig = SignalQualityRiskSection(confidence="low", source_notes=note)
    take = SentimentTakeaway(
        takeaway_label="Too Unclear",
        takeaway_summary="Insufficient news coverage to form a view.",
        suggested_user_action="Check back when more articles are available.",
    )
    return {
        "news_catalyst": empty_cat.model_dump(),
        "news_sentiment": empty_sent.model_dump(),
        "community_pulse": empty_comm.model_dump(),
        "signal_quality_risk": empty_sig.model_dump(),
        "takeaway": take.model_dump(),
        "confidence": "too_few_articles",
    }


def _llm_disabled_result(symbol: str, articles: list[NewsArticle]) -> dict[str, Any]:
    note = ["LLM analysis unavailable — raw provider data only."]
    # Best-effort from AV pre-computed scores
    scores = [a.sentiment_score for a in articles if a.sentiment_score is not None]
    avg = sum(scores) / len(scores) if scores else None
    sent_label = "Neutral"
    if avg is not None:
        if avg >= 0.35:
            sent_label = "Positive"
        elif avg <= -0.35:
            sent_label = "Negative"
        elif avg > 0:
            sent_label = "Mixed Positive"
        elif avg < 0:
            sent_label = "Mixed Negative"
    return {
        "news_catalyst": NewsCatalystSection(confidence="low", source_notes=note).model_dump(),
        "news_sentiment": NewsSentimentSection(
            news_sentiment_label=sent_label,
            confidence="low",
            source_notes=note,
        ).model_dump(),
        "community_pulse": CommunityPulseSection(confidence="not_available").model_dump(),
        "signal_quality_risk": SignalQualityRiskSection(confidence="low", source_notes=note).model_dump(),
        "takeaway": SentimentTakeaway(
            takeaway_label="Too Unclear",
            takeaway_summary="LLM not configured — using raw provider scores only.",
        ).model_dump(),
        "confidence": "partial",
    }
