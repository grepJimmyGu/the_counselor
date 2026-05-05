from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class QAIssueSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class ReleaseRecommendation(str, Enum):
    SHIP = "ship"
    HOLD = "hold"
    SHIP_WITH_CAUTION = "ship_with_caution"


class QAIssue(BaseModel):
    severity: QAIssueSeverity
    title: str
    area: str
    is_confirmed: bool = Field(
        description="True = confirmed bug. False = hypothesis needing more evidence."
    )
    reproduction_steps: list[str]
    expected_behavior: str
    actual_behavior: str
    risk_to_user_trust: str
    suggested_fix: str


class QAReviewRequest(BaseModel):
    product: str = "Livermore Investment Analytics Tool"
    review_type: str = Field(..., min_length=3)
    area_to_review: str = Field(..., min_length=3)
    current_user_flow: str = Field(..., min_length=10)
    recent_change: Optional[str] = None
    known_concerns: Optional[str] = None
    available_evidence: Optional[str] = None
    locale: str = "en"


class QAReviewResponse(BaseModel):
    executive_verdict: str
    issues: list[QAIssue]
    regression_test_checklist: list[str]
    release_recommendation: ReleaseRecommendation
    release_recommendation_rationale: str
    missing_evidence: list[str] = Field(
        description="Evidence that would resolve open hypotheses or improve confidence."
    )
