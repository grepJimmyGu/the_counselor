from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.sentiment import (
    SENTIMENT_DISCLAIMER,
    CommunityMention,
    CommunityPulseSection,
    NewsArticle,
    NewsCatalystSection,
    NewsSentimentSection,
    ProvidersStatusResponse,
    SentimentScores,
    SentimentSummaryResponse,
    SentimentTakeaway,
    SignalQualityRiskSection,
)
from app.services.alpha_vantage_news_provider import AlphaVantageNewsProvider
from app.services.community_mention_cache_service import CommunityMentionCacheService
from app.services.internal_community_provider import InternalCommunityProvider
from app.services.news_article_cache_service import NewsArticleCacheService
from app.services.reddit_community_provider import RedditCommunityProvider
from app.services.sentiment_llm_service import SentimentLLMService
from app.services.sentiment_signal_scoring_service import compute_scores
from app.services.x_community_provider import XCommunityProvider

logger = logging.getLogger(__name__)

_LLM_CACHE_HOURS = 3


class SentimentService:
    def __init__(self) -> None:
        self._news_cache = NewsArticleCacheService()
        self._community_cache = CommunityMentionCacheService()
        self._llm = SentimentLLMService()
        self._news_providers = [AlphaVantageNewsProvider()]
        self._community_providers = [
            RedditCommunityProvider(),
            XCommunityProvider(),
            InternalCommunityProvider(),
        ]

    def get_provider_status(self) -> ProvidersStatusResponse:
        av_status = AlphaVantageNewsProvider().status().value
        reddit_status = RedditCommunityProvider().status().value
        x_status = XCommunityProvider().status().value
        internal_status = InternalCommunityProvider().status().value
        return ProvidersStatusResponse(
            alpha_vantage=av_status,
            reddit=reddit_status,
            x=x_status,
            internal_community=internal_status,
        )

    async def get_summary(
        self, symbol: str, db: Session, refresh: bool = False
    ) -> SentimentSummaryResponse:
        sym = symbol.upper()

        if not refresh:
            cached = _load_cached_summary(sym, db)
            if cached:
                return cached

        articles = await self._news_cache.get_articles(sym, db, limit=20)
        mentions = await self._community_cache.get_mentions(sym, db, limit=30)

        llm_output = await self._llm.analyze(sym, articles, mentions)
        scores = compute_scores(llm_output, len(articles), len(mentions))
        provider_status = {
            "alpha_vantage": AlphaVantageNewsProvider().status().value,
            "reddit": RedditCommunityProvider().status().value,
            "x": XCommunityProvider().status().value,
            "internal_community": InternalCommunityProvider().status().value,
        }

        warnings: list[str] = []
        if len(articles) < 3:
            warnings.append("Fewer than 3 articles found — analysis confidence is low.")
        confidence = llm_output.get("confidence", "partial")

        cat_data = llm_output.get("news_catalyst") or {}
        sent_data = llm_output.get("news_sentiment") or {}
        comm_data = llm_output.get("community_pulse") or {}
        sig_data = llm_output.get("signal_quality_risk") or {}
        take_data = llm_output.get("takeaway") or {}

        def _to_model(cls, data):
            if isinstance(data, dict):
                try:
                    return cls(**{k: v for k, v in data.items() if k in cls.model_fields})
                except Exception:
                    return cls()
            return data if isinstance(data, cls) else cls()

        news_catalyst = _to_model(NewsCatalystSection, cat_data)
        news_sentiment = _to_model(NewsSentimentSection, sent_data)
        community_pulse = _to_model(CommunityPulseSection, comm_data)
        signal_quality_risk = _to_model(SignalQualityRiskSection, sig_data)
        takeaway = _to_model(SentimentTakeaway, take_data)

        # Override takeaway_label from scores if LLM left it generic
        if takeaway.takeaway_label in ("Too Unclear", "") and scores.overall_label:
            takeaway = SentimentTakeaway(
                takeaway_label=scores.overall_label,
                takeaway_summary=takeaway.takeaway_summary,
                suggested_user_action=takeaway.suggested_user_action,
            )

        now = datetime.utcnow()
        expires_at = now + timedelta(hours=_LLM_CACHE_HOURS)

        summary = SentimentSummaryResponse(
            symbol=sym,
            as_of_datetime=now,
            expires_at=expires_at,
            news_catalyst=news_catalyst,
            news_sentiment=news_sentiment,
            community_pulse=community_pulse,
            signal_quality_risk=signal_quality_risk,
            takeaway=takeaway,
            scores=scores,
            provider_status=provider_status,
            warnings=warnings,
            disclaimer=SENTIMENT_DISCLAIMER,
        )

        _save_summary(sym, summary, confidence, provider_status, warnings, db)
        return summary

    async def get_raw_articles(
        self, symbol: str, db: Session
    ) -> list[NewsArticle]:
        return await self._news_cache.get_articles(symbol.upper(), db, limit=30)

    async def get_raw_mentions(
        self, symbol: str, db: Session
    ) -> list[CommunityMention]:
        return await self._community_cache.get_mentions(symbol.upper(), db, limit=50)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_cached_summary(symbol: str, db: Session) -> SentimentSummaryResponse | None:
    now = datetime.utcnow()
    row = db.execute(
        text(
            "SELECT symbol, as_of_datetime, expires_at, news_catalyst, news_sentiment,"
            " community_pulse, signal_quality_risk, takeaway,"
            " catalyst_score, catalyst_materiality_score, information_source_quality_score,"
            " news_sentiment_score, community_sentiment_score, attention_score,"
            " signal_quality_score, risk_score, overall_sentiment_signal_score, overall_label,"
            " provider_status, warnings"
            " FROM sentiment_signal_summaries"
            " WHERE symbol = :sym AND expires_at > :now"
            " ORDER BY as_of_datetime DESC LIMIT 1"
        ),
        {"sym": symbol, "now": now},
    ).fetchone()

    if not row:
        return None

    try:
        r = row._mapping  # type: ignore[attr-defined]

        def _j(val):
            if val is None:
                return {}
            if isinstance(val, str):
                return json.loads(val)
            return val

        def _jl(val):
            if val is None:
                return []
            if isinstance(val, str):
                return json.loads(val)
            return val

        expires_raw = r["expires_at"]
        as_of_raw = r["as_of_datetime"]
        if isinstance(expires_raw, str):
            expires_raw = datetime.fromisoformat(expires_raw)
        if isinstance(as_of_raw, str):
            as_of_raw = datetime.fromisoformat(as_of_raw)

        def _to_model(cls, data):
            d = _j(data)
            try:
                return cls(**{k: v for k, v in d.items() if k in cls.model_fields})
            except Exception:
                return cls()

        scores = SentimentScores(
            catalyst_score=r["catalyst_score"] or 50,
            catalyst_materiality_score=r["catalyst_materiality_score"] or 50,
            information_source_quality_score=r["information_source_quality_score"] or 50,
            news_sentiment_score=r["news_sentiment_score"] or 50,
            community_sentiment_score=r["community_sentiment_score"] or 50,
            attention_score=r["attention_score"] or 50,
            signal_quality_score=r["signal_quality_score"] or 50,
            risk_score=r["risk_score"] or 30,
            overall_sentiment_signal_score=r["overall_sentiment_signal_score"] or 50,
            overall_label=r["overall_label"] or "Too Unclear",
        )

        return SentimentSummaryResponse(
            symbol=r["symbol"],
            as_of_datetime=as_of_raw,
            expires_at=expires_raw,
            news_catalyst=_to_model(NewsCatalystSection, r["news_catalyst"]),
            news_sentiment=_to_model(NewsSentimentSection, r["news_sentiment"]),
            community_pulse=_to_model(CommunityPulseSection, r["community_pulse"]),
            signal_quality_risk=_to_model(SignalQualityRiskSection, r["signal_quality_risk"]),
            takeaway=_to_model(SentimentTakeaway, r["takeaway"]),
            scores=scores,
            provider_status=_j(r["provider_status"]),
            warnings=_jl(r["warnings"]),
            disclaimer=SENTIMENT_DISCLAIMER,
        )
    except Exception as exc:
        logger.warning("Failed to deserialize cached sentiment for %s: %s", symbol, exc)
        return None


def _save_summary(
    symbol: str,
    summary: SentimentSummaryResponse,
    confidence: str,
    provider_status: dict,
    warnings: list[str],
    db: Session,
) -> None:
    s = summary.scores
    try:
        db.execute(
            text(
                "INSERT INTO sentiment_signal_summaries"
                " (symbol, as_of_datetime, expires_at,"
                "  news_catalyst, news_sentiment, community_pulse, signal_quality_risk, takeaway,"
                "  catalyst_score, catalyst_materiality_score, information_source_quality_score,"
                "  news_sentiment_score, community_sentiment_score, attention_score,"
                "  signal_quality_score, risk_score, overall_sentiment_signal_score, overall_label,"
                "  confidence, provider_status, warnings)"
                " VALUES"
                " (:symbol, :as_of, :expires,"
                "  :news_catalyst, :news_sentiment, :community_pulse, :signal_quality_risk, :takeaway,"
                "  :cat_score, :mat_score, :src_score,"
                "  :news_sent_score, :comm_score, :attn_score,"
                "  :sig_score, :risk_score, :overall, :overall_label,"
                "  :confidence, :provider_status, :warnings)"
            ),
            {
                "symbol": symbol,
                "as_of": summary.as_of_datetime,
                "expires": summary.expires_at,
                "news_catalyst": json.dumps(summary.news_catalyst.model_dump()),
                "news_sentiment": json.dumps(summary.news_sentiment.model_dump()),
                "community_pulse": json.dumps(summary.community_pulse.model_dump()),
                "signal_quality_risk": json.dumps(summary.signal_quality_risk.model_dump()),
                "takeaway": json.dumps(summary.takeaway.model_dump()),
                "cat_score": s.catalyst_score,
                "mat_score": s.catalyst_materiality_score,
                "src_score": s.information_source_quality_score,
                "news_sent_score": s.news_sentiment_score,
                "comm_score": s.community_sentiment_score,
                "attn_score": s.attention_score,
                "sig_score": s.signal_quality_score,
                "risk_score": s.risk_score,
                "overall": s.overall_sentiment_signal_score,
                "overall_label": s.overall_label,
                "confidence": confidence,
                "provider_status": json.dumps(provider_status),
                "warnings": json.dumps(warnings),
            },
        )
        db.commit()
    except Exception as exc:
        logger.warning("Failed to save sentiment summary for %s: %s", symbol, exc)
        db.rollback()
