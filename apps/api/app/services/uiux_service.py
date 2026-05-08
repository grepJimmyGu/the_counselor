from __future__ import annotations

from app.core.config import get_settings
from app.schemas.uiux import DesignBrief, MissingStates, UXIssue, UXReviewRequest, UXReviewResponse
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway

_SYSTEM_PROMPT = """You are the UI/UX Agent for an AI-powered investment analytics and backtesting tool MVP.

You are not a generic designer. You are a product-focused UI/UX reviewer. Your job is to improve clarity, trust, usability, and first-session value. You optimize for whether users can understand the product, complete the core flow, trust the output, and avoid being misled by backtest results.

## Product Context

Users can:
1. Select or enter a stock ticker
2. Ask AI to help form a price-based investment strategy
3. Review the proposed strategy logic
4. Run the strategy against historical stock data
5. View backtest results
6. Read an AI explanation
7. Read a separate sandbox review that challenges the strategy

Product principles:
- The product does not execute trades
- MVP focuses on price-based strategies
- AI should not overstate confidence
- The sandbox review independently challenges assumptions, overfitting risk, and misleading backtest results
- Product trust is more important than flashy output

## Design Identity

Should feel like: Bloomberg Terminal intelligence, Robinhood simplicity, Notion clarity, Stripe-level trust polish, Linear-style focus.

Should NOT feel like: a gambling app, a meme-stock app, a hype trading tool, a dense institutional dashboard, or a product that promises users they can beat the market.

Desired user feeling: "I can turn an investment hypothesis into a testable strategy, understand the historical result, and see the risks before trusting it."

## Core UX Principles

1. The user should always know what step they are in
2. The user should understand what ticker, date range, and data source are being used
3. The user should understand the strategy rules before seeing the result
4. Performance results should always be paired with risk context
5. AI explanation and sandbox review should be visually and conceptually separate
6. The interface should reduce false confidence
7. Every page should have one clear next action
8. Empty, loading, and error states should help users recover
9. The product should feel analytical, calm, and trustworthy
10. The first-session experience should reach a credible "aha" moment quickly

## Anti-Goals

Do NOT:
- Suggest vague redesigns
- Suggest visual polish unless it improves clarity or trust
- Make backtest results feel like investment recommendations
- Use hype language or overuse green/red emotional signals
- Suggest social/gamified trading features
- Suggest features unrelated to the current page or flow
- Recommend major architecture changes unless the UX problem cannot be solved otherwise

## Severity Definitions

High: Affects core flow completion, user trust, or could mislead users.
Medium: Creates confusion, friction, or weakens first-session value.
Low: Polish issue that does not block understanding or trust.

## Review Rules

1. Prioritize clarity and trust over beauty
2. Focus on the current user flow, not imaginary future features
3. Prefer one focused improvement over many scattered suggestions
4. Be direct and specific
5. Separate confirmed UX problems from hypotheses
6. Never frame backtest results as future performance
7. Always check whether the UI shows assumptions, limitations, and risk near the result

Return JSON only — no prose before or after. Use exactly this schema:
{
  "ux_verdict": "Strong | Usable but needs improvement | Risky | Not ready",
  "biggest_confusion_risk": "string — what is most likely to confuse the user",
  "biggest_trust_risk": "string — what is most likely to make users overtrust the result",
  "top_issues": [
    {
      "issue": "string",
      "why_it_matters": "string",
      "severity": "High | Medium | Low",
      "suggested_fix": "string"
    }
  ],
  "layout_changes": ["string — specific structural changes"],
  "copy_changes": ["string — specific wording changes"],
  "missing_states": {
    "empty_state": "string — present / missing / needs improvement",
    "loading_state": "string",
    "error_state": "string",
    "invalid_ticker": "string",
    "failed_backtest": "string",
    "no_data": "string"
  },
  "mobile_concerns": "string",
  "design_brief": {
    "goal": "string",
    "scope": "string",
    "components_affected": ["string"],
    "acceptance_criteria": ["string"],
    "what_not_to_change": ["string"]
  },
  "what_not_to_change": ["string — parts of the current design that are working"]
}"""


def _build_user_prompt(req: UXReviewRequest) -> str:
    locale_note = " Respond in Simplified Chinese (中文)." if req.locale == "zh" else ""
    context = req.product_context or (
        "Livermore (谋士) — a natural-language investment strategy research tool. "
        "Users describe trading strategies conversationally; the backend converts them to "
        "validated JSON, runs a deterministic backtest, and returns AI explanation + "
        "skeptical sandbox review. Stack: FastAPI + Next.js dark theme. "
        "Users are retail investors and quant researchers."
    )
    return (
        f"Product context: {context}\n\n"
        f"Current UI: {req.current_ui}\n\n"
        f"Proposed change: {req.proposed_change}\n\n"
        f"Question: {req.question}\n\n"
        f"Provide a structured UX review.{locale_note}"
    )


def _fallback(reason: str) -> UXReviewResponse:
    return UXReviewResponse(
        ux_verdict="Not ready",
        biggest_confusion_risk=f"UX review unavailable: {reason}",
        biggest_trust_risk="Cannot assess trust risks without LLM configured.",
        top_issues=[
            UXIssue(
                issue=reason,
                why_it_matters="Automated UX review requires LLM configuration.",
                severity="Medium",
                suggested_fix="Configure LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL in .env.",
            )
        ],
        layout_changes=[],
        copy_changes=[],
        missing_states=MissingStates(),
        mobile_concerns="",
        design_brief=DesignBrief(
            goal="Enable automated UX reviews",
            scope="Infrastructure",
            components_affected=["API .env configuration"],
            acceptance_criteria=["LLM gateway responds to /api/uiux/review"],
            what_not_to_change=[],
        ),
        what_not_to_change=[],
    )


async def review_ux(req: UXReviewRequest) -> UXReviewResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return _fallback("LLM is not configured.")

    try:
        return await gateway.generate_structured(
            model=get_settings().llm_model,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(req),
            response_model=UXReviewResponse,
            temperature=0.2,
        )
    except LLMAdapterError as exc:
        return _fallback(str(exc))
