from __future__ import annotations

from app.schemas.sentiment import SentimentScores

# ── Label → score lookup tables ─────────────────────────────────────────────

_MATERIALITY = {
    "highly material": 100,
    "moderately material": 65,
    "low materiality": 30,
    "unclear materiality": 15,
    "risk event": 20,
}

_SOURCE_QUALITY = {
    "high quality sources": 100,
    "moderate quality sources": 65,
    "low quality sources": 30,
    "unverified sources": 10,
    "single source": 25,
}

_NEWS_SENTIMENT = {
    "strong positive": 100,
    "positive": 75,
    "mixed positive": 55,
    "neutral": 50,
    "mixed negative": 35,
    "negative": 15,
    "deteriorating": 10,
}

_COMMUNITY_SENTIMENT = {
    "strong bullish": 100,
    "bullish": 80,
    "mixed bullish": 65,
    "neutral": 50,
    "mixed bearish": 35,
    "bearish": 20,
    "strong bearish": 10,
    "highly controversial": 45,
    "retail buzz": 55,
    "not configured": 50,
}

_SIGNAL_QUALITY = {
    "high quality catalyst": 100,
    "news confirmed": 90,
    "mixed signals": 50,
    "mostly noise": 10,
    "headline risk": 20,
}

# Catalyst type bonus — applied on top of materiality
_CATALYST_TYPE_BONUS: dict[str, int] = {
    "earnings beat": 15,
    "earnings miss": -10,
    "product launch": 10,
    "regulatory approval": 15,
    "regulatory risk": -15,
    "merger & acquisition": 12,
    "analyst upgrade": 8,
    "analyst downgrade": -8,
    "macro trend": 5,
    "sector rotation": 5,
    "insider buying": 10,
    "insider selling": -5,
}

_OVERALL_LABELS = [
    (80, "Strong Positive Catalyst"),
    (70, "News Confirmed by Community"),
    (60, "Improving Sentiment Candidate"),
    (50, "Rising Attention Candidate"),
    (40, "Highly Debated Candidate"),
    (30, "Community Hype Risk"),
    (20, "Headline Risk Candidate"),
    (10, "Mostly Noise"),
    (0, "Too Unclear"),
]


def _lookup(table: dict[str, int], label: str | None, default: int = 50) -> int:
    if not label:
        return default
    return table.get(label.lower().strip(), default)


def _clamp(val: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(val))))


def compute_scores(
    llm_output: dict,
    article_count: int,
    mention_count: int,
) -> SentimentScores:
    cat_section = llm_output.get("news_catalyst") or {}
    sent_section = llm_output.get("news_sentiment") or {}
    comm_section = llm_output.get("community_pulse") or {}
    sig_section = llm_output.get("signal_quality_risk") or {}

    # catalyst_materiality_score
    mat_score = _lookup(_MATERIALITY, cat_section.get("catalyst_materiality_label"))

    # catalyst_score: materiality + type bonus
    catalyst_type = (cat_section.get("catalyst_type") or "").lower()
    bonus = 0
    for k, v in _CATALYST_TYPE_BONUS.items():
        if k in catalyst_type:
            bonus = v
            break
    catalyst_score = _clamp(mat_score + bonus)

    # information_source_quality_score
    src_score = _lookup(_SOURCE_QUALITY, cat_section.get("information_source_quality_label"))

    # news_sentiment_score: prefer LLM label, fall back to AV average
    news_sent_raw = sent_section.get("news_sentiment_label")
    news_sent_score = _lookup(_NEWS_SENTIMENT, news_sent_raw)

    # community_sentiment_score
    comm_label = comm_section.get("community_sentiment_label") or "not configured"
    comm_score = _lookup(_COMMUNITY_SENTIMENT, comm_label, default=50)

    # attention_score: simple article + mention volume heuristic
    # 20+ articles → 100, 10 → 70, 5 → 50, 3 → 30, <3 → 10
    attn_raw = min(100, int((article_count / 20) * 80 + (mention_count / 10) * 20))
    attention_score = max(10, attn_raw)

    # signal_quality_score
    sig_label = sig_section.get("signal_quality_label")
    sig_score = _lookup(_SIGNAL_QUALITY, sig_label)

    # risk_score: accumulate from flags
    risk = 0
    crowding = (sig_section.get("crowding_risk") or "").lower()
    if any(w in crowding for w in ("high", "crowded", "meme", "hype")):
        risk += 30
    elif any(w in crowding for w in ("moderate", "medium")):
        risk += 15
    overreaction = (sig_section.get("overreaction_risk") or "").lower()
    if any(w in overreaction for w in ("high", "significant")):
        risk += 20
    elif any(w in overreaction for w in ("moderate", "possible")):
        risk += 10
    if sig_section.get("headline_risks"):
        risk += 10 * min(len(sig_section["headline_risks"]), 2)
    risk_score = _clamp(risk)

    # overall = weighted sum − risk penalty
    overall_raw = (
        catalyst_score * 0.20
        + mat_score * 0.20
        + src_score * 0.15
        + news_sent_score * 0.15
        + comm_score * 0.10
        + attention_score * 0.10
        + sig_score * 0.10
        - risk_score * 0.30
    )
    overall = _clamp(overall_raw)

    # overall label
    overall_label = "Too Unclear"
    for threshold, label in _OVERALL_LABELS:
        if overall >= threshold:
            overall_label = label
            break

    return SentimentScores(
        catalyst_score=catalyst_score,
        catalyst_materiality_score=mat_score,
        information_source_quality_score=src_score,
        news_sentiment_score=news_sent_score,
        community_sentiment_score=comm_score,
        attention_score=attention_score,
        signal_quality_score=sig_score,
        risk_score=risk_score,
        overall_sentiment_signal_score=overall,
        overall_label=overall_label,
    )
