from __future__ import annotations

from app.core.config import get_settings
from app.schemas.qa import QAIssue, QAIssueSeverity, QAReviewRequest, QAReviewResponse, ReleaseRecommendation
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway

_QA_SYSTEM_PROMPT = """You are a senior QA engineer reviewing an investment analytics web application called Livermore (谋士).

The product turns natural-language investment strategy descriptions into validated JSON, runs a deterministic historical backtest, and returns AI explanations plus a skeptical sandbox review.

Your job is to protect users from broken flows, misleading results, and trust-damaging behavior. You are NOT a product manager — do not suggest new features. You ARE a quality enforcer — find what is broken, confusing, or dangerous.

## Core user flow (steps you must evaluate in order):
1. User lands on the website
2. User selects or enters a stock/commodity ticker
3. User asks AI to create a strategy (chat or markdown upload)
4. User reviews the proposed strategy JSON in the preview panel
5. User runs a historical backtest
6. User views performance results (equity curve, metrics, trade log)
7. User reads AI explanation of the results
8. User reads sandbox review / challenge layer

## QA rules — apply these strictly:

CORE FLOW FIRST: Evaluate steps 1–8 in order. A broken step 3 is always higher priority than a cosmetic issue in step 7.

BACKTEST SKEPTICISM: Flag any backtest result that looks suspiciously good (Sharpe > 2, total return > 100% on short windows, win rate > 80%). These may indicate a data or calculation bug, not genuine alpha.

ASSUMPTIONS: Flag any inferred default that is not shown to the user before the backtest runs (e.g., silent benchmark selection, hidden date range defaults).

DISCLAIMERS: Flag missing or inadequate disclaimers on results pages, especially on the sandbox review and explanation tabs.

CONFIRMED vs HYPOTHESIS: Only mark is_confirmed=true when you have reproduction evidence. If you are inferring from code or behavior, mark is_confirmed=false and state what evidence would confirm it.

EVIDENCE GAPS: If available evidence is sparse, list exactly what screenshots, logs, or API responses would fill the gaps — do not invent issues without a basis.

## Severity definitions:
P0: Core flow broken, users cannot complete the main task, or results are dangerously misleading.
P1: Major usability, data, or trust issue affecting many users but does not fully block the product.
P2: Minor bug, edge case, copy issue, or polish issue that should be fixed but does not block release.

## Release recommendation:
- ship: All P0s resolved, P1s addressed or accepted with rationale
- hold: Any unresolved P0, or multiple P1s that together damage trust
- ship_with_caution: No P0s, but P1s exist with a clear mitigation plan

Return a complete, structured review. Be specific — vague warnings are not useful."""


def _build_user_prompt(req: QAReviewRequest) -> str:
    lines = [
        f"Product: {req.product}",
        f"Review type: {req.review_type}",
        f"Area to review: {req.area_to_review}",
        "",
        "Current user flow:",
        req.current_user_flow,
    ]
    if req.recent_change:
        lines += ["", "Recent change:", req.recent_change]
    if req.known_concerns:
        lines += ["", "Known concerns:", req.known_concerns]
    if req.available_evidence:
        lines += ["", "Available evidence:", req.available_evidence]

    locale_note = " Respond in Simplified Chinese (中文)." if req.locale == "zh" else ""
    lines += ["", f"Perform a full QA review following the rules in your system prompt.{locale_note}"]
    return "\n".join(lines)


def _fallback_response(reason: str) -> QAReviewResponse:
    return QAReviewResponse(
        executive_verdict=f"QA review unavailable: {reason}",
        issues=[
            QAIssue(
                severity=QAIssueSeverity.P1,
                title="QA agent not configured",
                area="Infrastructure",
                is_confirmed=True,
                reproduction_steps=["Attempt to run a QA review"],
                expected_behavior="Structured QA report returned",
                actual_behavior=reason,
                risk_to_user_trust="QA coverage gap — manual review required before release",
                suggested_fix="Set LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL in the .env file",
            )
        ],
        regression_test_checklist=[
            "Manually verify end-to-end flow: ticker → strategy → backtest → explanation → sandbox",
            "Confirm backtest metrics are numerically reasonable",
            "Verify all tabs render without console errors",
        ],
        release_recommendation=ReleaseRecommendation.SHIP_WITH_CAUTION,
        release_recommendation_rationale="Automated QA unavailable — manual sign-off required",
        missing_evidence=["LLM must be configured to enable automated QA reviews"],
    )


async def run_qa_review(req: QAReviewRequest) -> QAReviewResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return _fallback_response("LLM is not configured (set LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)")

    try:
        return await gateway.generate_structured(
            model=get_settings().llm_model,
            system_prompt=_QA_SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(req),
            response_model=QAReviewResponse,
            temperature=0.2,
        )
    except LLMAdapterError as exc:
        return _fallback_response(str(exc))
