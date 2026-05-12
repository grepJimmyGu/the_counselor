from __future__ import annotations

import logging

from app.schemas.sentiment import SentimentSandboxResponse
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a skeptical financial analyst reviewing an AI-generated sentiment analysis report.

Your job is to identify weaknesses, gaps, and risks in the analysis. Return ONLY a valid JSON object.

Return this JSON shape:
{
  "review_verdict": "trustworthy|promising|speculative|unreliable",
  "trust_score": <0-100 integer>,
  "key_concerns": ["..."],
  "missing_data": ["..."],
  "noise_risks": ["..."],
  "source_limitations": ["..."],
  "required_next_checks": ["..."],
  "final_warning": "..." or null
}

Criteria:
- review_verdict "trustworthy": multiple high-quality sources, consistent signals, material catalyst
- "promising": mostly good but some gaps
- "speculative": community-driven or thin news coverage
- "unreliable": mostly noise, unverified, or contradictory
- trust_score reflects overall reliability (0=noise, 100=fully trustworthy)
- Lists should have 2–4 items max; use null for final_warning if no critical warning.
- Be concise and specific — no generic statements."""


class SentimentSandboxReviewer:
    def __init__(self) -> None:
        self._gateway = get_llm_gateway()

    async def review(
        self, symbol: str, sentiment_summary: dict
    ) -> SentimentSandboxResponse:
        if not self._gateway.is_enabled:
            return SentimentSandboxResponse(
                review_verdict="speculative",
                trust_score=40,
                key_concerns=["Sandbox reviewer not configured (LLM provider disabled)."],
                required_next_checks=["Configure LLM_PROVIDER and LLM_API_KEY to enable review."],
            )

        import json
        user_prompt = (
            f"Review this sentiment analysis for {symbol.upper()}:\n\n"
            + json.dumps(sentiment_summary, indent=2, default=str)
        )

        try:
            payload = await self._gateway.generate_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.15,
            )
        except LLMAdapterError as exc:
            logger.warning("Sandbox review failed for %s: %s", symbol, exc)
            return SentimentSandboxResponse(
                review_verdict="speculative",
                trust_score=40,
                key_concerns=[f"Review failed: {type(exc).__name__}"],
            )

        return SentimentSandboxResponse(
            review_verdict=payload.get("review_verdict", "speculative"),
            trust_score=int(payload.get("trust_score", 40)),
            key_concerns=payload.get("key_concerns") or [],
            missing_data=payload.get("missing_data") or [],
            noise_risks=payload.get("noise_risks") or [],
            source_limitations=payload.get("source_limitations") or [],
            required_next_checks=payload.get("required_next_checks") or [],
            final_warning=payload.get("final_warning"),
        )
