"""onboarding_tutor chat tool — guided product demo (plumbing only).

Per build_specs/07_chat_v2_research_partner.md §7 D5: ticket #3 ships the
plumbing, Jimmy writes the final demo script (and optionally produces a
video creative). Until then this tool returns a structured placeholder
with the right shape so ticket #5's chat endpoint + ticket #7's frontend
widget can wire against a stable contract.

When Jimmy delivers the real script, swap `_PLACEHOLDER_SCRIPT` for the
actual content. No other code change required.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TutorStep(BaseModel):
    """One step of the guided demo. Frontend renders the body verbatim and
    highlights the named panel via the existing dashboard chrome."""

    title: str
    body: str
    highlight_panel: Optional[str]  # e.g., "equity_curve", "explainer", "sandbox_review"


class OnboardingTutorResponse(BaseModel):
    """Returned by `run_onboarding_tutor`. Frontend iterates `steps` and
    renders one at a time, advancing on user click."""

    demo_strategy_id: str
    steps: List[TutorStep]
    placeholder: bool  # True until Jimmy's script ships


# Placeholder script. The shape matches the planned final structure so the
# frontend renderer in ticket #7 can be built against a stable contract.
_PLACEHOLDER_SCRIPT: List[TutorStep] = [
    TutorStep(
        title="Welcome to Livermore",
        body=(
            "We just ran an NVDA 200-day moving-average filter backtest in "
            "the background. This is a real strategy on real data — let me "
            "walk you through how to read the result."
        ),
        highlight_panel=None,
    ),
    TutorStep(
        title="The equity curve",
        body=(
            "This is the strategy's cumulative return vs the buy-and-hold "
            "benchmark. Note the drawdowns in 2022 — the filter sidestepped "
            "the worst of the bear market by holding cash above the 200-day."
        ),
        highlight_panel="equity_curve",
    ),
    TutorStep(
        title="The explainer",
        body=(
            "Livermore writes a plain-English explanation of every result. "
            "It calls out what worked, what didn't, and where the strategy's "
            "edge is most uncertain. Read this before you trust any number."
        ),
        highlight_panel="explainer",
    ),
    TutorStep(
        title="The sandbox reviewer",
        body=(
            "A skeptical second opinion. The reviewer assumes you ARE going "
            "to make this trade and tries to talk you out of it. Pay closest "
            "attention to the 'weakest link' sections."
        ),
        highlight_panel="sandbox_review",
    ),
    TutorStep(
        title="Robustness — Strategist tier",
        body=(
            "Robustness suite tests how the strategy holds up under stress "
            "— transaction cost variations, sub-period analysis, benchmark "
            "comparison. Sample shown here; full suite available on the "
            "Strategist tier and above."
        ),
        highlight_panel="robustness",
    ),
    TutorStep(
        title="Try your own idea",
        body=(
            "Type any strategy idea into chat — 'momentum on tech', 'value "
            "factor on small caps' — and I'll help you build it. The first "
            "few turns are free even on the Scout tier."
        ),
        highlight_panel=None,
    ),
]


async def run_onboarding_tutor(step: Optional[int] = None) -> OnboardingTutorResponse:
    """Return the onboarding tutor script.

    If `step` is None (default), return the full script — the frontend
    renders one step at a time and tracks position locally. If `step` is
    provided (0-indexed), return only that step plus the surrounding context
    (length, prev/next exists) — used for direct deep-links.

    Note: the placeholder flag is True until the final script lands. The
    frontend can use this to render a "demo content in progress" badge
    during the placeholder window — see ticket #7 for the GA copy.
    """
    if step is not None:
        if step < 0 or step >= len(_PLACEHOLDER_SCRIPT):
            # Out-of-range step. Return the full script as a fallback rather
            # than raising — the LLM may have hallucinated a step number.
            return OnboardingTutorResponse(
                demo_strategy_id="nvda-200-ma-demo",
                steps=_PLACEHOLDER_SCRIPT,
                placeholder=True,
            )
        return OnboardingTutorResponse(
            demo_strategy_id="nvda-200-ma-demo",
            steps=[_PLACEHOLDER_SCRIPT[step]],
            placeholder=True,
        )

    return OnboardingTutorResponse(
        demo_strategy_id="nvda-200-ma-demo",
        steps=_PLACEHOLDER_SCRIPT,
        placeholder=True,
    )


ONBOARDING_TUTOR_DEF: Dict[str, Any] = {
    "name": "onboarding_tutor",
    "description": (
        "Start a guided product demo. Returns a pre-baked NVDA 200-day MA "
        "backtest plus a step-by-step walkthrough of the result panels "
        "(equity curve, explainer, sandbox reviewer, robustness sample). "
        "Use when a new user asks 'how does this work?', 'show me what I "
        "can do', or anything indicating they want an overview rather than "
        "a specific answer. First 3 invocations are exempt from Scout's "
        "daily turn cap (anti-friction on day 0)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "step": {
                "type": "integer",
                "description": (
                    "Optional 0-indexed step to deep-link into. Omit to "
                    "return the full script (the usual case)."
                ),
                "minimum": 0,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
    "handler": run_onboarding_tutor,
}
