from __future__ import annotations

from pydantic import BaseModel, Field


class UXReviewRequest(BaseModel):
    product_context: str = Field(default="")
    current_ui: str = Field(..., description="Description of the current UI state or component")
    proposed_change: str = Field(..., description="What you are considering changing or adding")
    question: str = Field(..., description="The specific UX question you want answered")
    locale: str = "en"


class UXIssue(BaseModel):
    issue: str
    why_it_matters: str
    severity: str       # High / Medium / Low
    suggested_fix: str


class MissingStates(BaseModel):
    empty_state: str = ""
    loading_state: str = ""
    error_state: str = ""
    invalid_ticker: str = ""
    failed_backtest: str = ""
    no_data: str = ""


class DesignBrief(BaseModel):
    goal: str
    scope: str
    components_affected: list[str]
    acceptance_criteria: list[str]
    what_not_to_change: list[str]


class UXReviewResponse(BaseModel):
    ux_verdict: str             # Strong / Usable but needs improvement / Risky / Not ready
    biggest_confusion_risk: str
    biggest_trust_risk: str
    top_issues: list[UXIssue]
    layout_changes: list[str]
    copy_changes: list[str]
    missing_states: MissingStates
    mobile_concerns: str
    design_brief: DesignBrief
    what_not_to_change: list[str]
