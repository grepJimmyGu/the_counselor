from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.sentiment import (
    SentimentAnalyzeRequest,
    SentimentAnalyzeResponse,
    SentimentCandidateResult,
)

# ── Toolkit definitions ──────────────────────────────────────────────────────

@dataclass
class ToolkitDefinition:
    id: str
    name: str
    description: str
    filter_keys: list[str] = field(default_factory=list)
    filter_values: dict[str, Any] = field(default_factory=dict)


TOOLKITS: dict[str, ToolkitDefinition] = {
    "positive_catalyst": ToolkitDefinition(
        id="positive_catalyst",
        name="Positive Catalyst Watchlist",
        description="Stocks with a meaningful positive catalyst (catalyst_score > 70 AND materiality_score > 60)",
    ),
    "news_community_confirmed": ToolkitDefinition(
        id="news_community_confirmed",
        name="News Confirmed by Community",
        description="News sentiment and community sentiment both positive (both > 65)",
    ),
    "rising_attention": ToolkitDefinition(
        id="rising_attention",
        name="Rising Attention Stocks",
        description="Stocks with above-average attention volume (attention_score > 75)",
    ),
    "sentiment_reversal": ToolkitDefinition(
        id="sentiment_reversal",
        name="Sentiment Reversal",
        description="News sentiment trending improving after prior bearish reading",
    ),
    "controversial": ToolkitDefinition(
        id="controversial",
        name="Controversial Stocks",
        description="Highly debated or meme-driven stocks (controversial label + attention_score > 60)",
    ),
    "headline_risk": ToolkitDefinition(
        id="headline_risk",
        name="Headline Risk Watchlist",
        description="Stocks at risk from adverse headlines or high risk_score",
    ),
    "community_hype": ToolkitDefinition(
        id="community_hype",
        name="Community Hype Watchlist",
        description="High community buzz but weak fundamental news support",
    ),
}


def list_toolkits() -> list[dict[str, str]]:
    return [{"id": tk.id, "name": tk.name, "description": tk.description} for tk in TOOLKITS.values()]


def _passes_toolkit(toolkit_id: str, scores: dict[str, int], labels: dict[str, str]) -> bool:
    cs = scores.get("catalyst_score", 0)
    mat = scores.get("catalyst_materiality_score", 0)
    news_s = scores.get("news_sentiment_score", 0)
    comm_s = scores.get("community_sentiment_score", 0)
    attn = scores.get("attention_score", 0)
    risk = scores.get("risk_score", 0)
    news_trend = labels.get("news_sentiment_trend", "")
    comm_label = labels.get("community_sentiment_label", "").lower()
    sig_label = labels.get("signal_quality_label", "").lower()
    overall_label = labels.get("overall_label", "")

    if toolkit_id == "positive_catalyst":
        return cs > 70 and mat > 60
    if toolkit_id == "news_community_confirmed":
        return news_s > 65 and comm_s > 65
    if toolkit_id == "rising_attention":
        return attn > 75
    if toolkit_id == "sentiment_reversal":
        return news_trend == "improving" and news_s < 50
    if toolkit_id == "controversial":
        return comm_label in ("highly controversial", "retail buzz") and attn > 60
    if toolkit_id == "headline_risk":
        return risk > 50 or sig_label == "headline risk"
    if toolkit_id == "community_hype":
        return comm_s > 70 and news_s < 40
    return False


class SentimentToolkitService:
    async def run(
        self,
        request: SentimentAnalyzeRequest,
        db: Session,
        sentinel_summaries: dict[str, Any],
    ) -> SentimentAnalyzeResponse:
        """
        sentinel_summaries: mapping symbol → SentimentSummaryResponse-like dict
        already fetched and scored by the caller (sentiment_service).
        """
        candidates: list[SentimentCandidateResult] = []
        warnings: list[str] = []
        provider_status: dict[str, str] = {}

        for symbol in request.symbols:
            summary = sentinel_summaries.get(symbol.upper())
            if not summary:
                continue

            scores_dict = summary.get("scores", {})
            scores: dict[str, int] = {
                k: v for k, v in (scores_dict.model_dump() if hasattr(scores_dict, "model_dump") else scores_dict).items()
                if isinstance(v, int)
            }

            labels: dict[str, str] = {}
            cat = summary.get("news_catalyst") or {}
            sent = summary.get("news_sentiment") or {}
            comm = summary.get("community_pulse") or {}
            sig = summary.get("signal_quality_risk") or {}
            if hasattr(cat, "model_dump"):
                cat = cat.model_dump()
            if hasattr(sent, "model_dump"):
                sent = sent.model_dump()
            if hasattr(comm, "model_dump"):
                comm = comm.model_dump()
            if hasattr(sig, "model_dump"):
                sig = sig.model_dump()

            labels["news_sentiment_trend"] = sent.get("news_sentiment_trend", "")
            labels["community_sentiment_label"] = comm.get("community_sentiment_label", "")
            labels["signal_quality_label"] = sig.get("signal_quality_label", "")
            labels["overall_label"] = scores_dict.overall_label if hasattr(scores_dict, "overall_label") else scores.get("overall_label", "")

            if request.toolkit_id and not _passes_toolkit(request.toolkit_id, scores, labels):
                continue

            overall = scores.get("overall_sentiment_signal_score", 50)
            takeaway = summary.get("takeaway") or {}
            if hasattr(takeaway, "model_dump"):
                takeaway = takeaway.model_dump()

            candidates.append(SentimentCandidateResult(
                symbol=symbol.upper(),
                overall_sentiment_signal_score=overall,
                overall_label=labels.get("overall_label") or "Too Unclear",
                takeaway_label=takeaway.get("takeaway_label", "Too Unclear"),
                takeaway_summary=takeaway.get("takeaway_summary"),
                catalyst_type=cat.get("catalyst_type"),
                catalyst_materiality_label=cat.get("catalyst_materiality_label"),
                news_sentiment_label=sent.get("news_sentiment_label"),
                signal_quality_label=sig.get("signal_quality_label"),
                bullish_themes=sent.get("bullish_news_themes", []) or comm.get("bullish_community_themes", []),
                bearish_themes=sent.get("bearish_news_themes", []) or comm.get("bearish_community_themes", []),
                provider_status=summary.get("provider_status", {}),
            ))
            provider_status.update(summary.get("provider_status", {}))

        # Sort descending by score
        candidates.sort(key=lambda c: c.overall_sentiment_signal_score, reverse=True)

        return SentimentAnalyzeResponse(
            candidates=candidates,
            provider_status=provider_status,
            warnings=warnings,
            toolkit_id=request.toolkit_id,
        )
