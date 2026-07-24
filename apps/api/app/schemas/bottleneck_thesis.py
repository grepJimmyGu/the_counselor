"""Response schema for the bottleneck-thesis reasoning engine (Phase 3 / PRD-27).

The thesis is a graded research artifact — structure + evidence, never a
recommendation. The LLM assesses each gate WITH an evidence tier; the fit-score
total and the two vetoes are derived in CODE (see bottleneck_thesis_service),
exactly like the chokepoint verdict.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ArchitectureTransition(BaseModel):
    from_state: str = ""
    to_state: str = ""
    what_becomes_scarce: str = ""
    transition_exists: bool = False


class ChainHop(BaseModel):
    hop: int
    layer: str
    named_players: list[str] = Field(default_factory=list)
    status: str = "unknown"  # abundant | constrained | unknown


class ChokepointArgument(BaseModel):
    if_stops: str = ""
    downstream_breaks: str = ""
    mechanism: str = ""
    nearest_substitute: str = ""
    substitute_status: str = ""


class ThesisEvidenceRow(BaseModel):
    claim: str
    tier: str
    source: str = ""
    date: str = ""
    falsifier: str = ""


class ThesisGate(BaseModel):
    n: int
    name: str
    score: str  # "0" | "1" | "2" | "PASS" | "VETO"
    tier: str = ""
    note: str = ""


class RiskProfile(BaseModel):
    binariness: str = "unknown"
    liquidity: str = "unknown"
    crowding: str = "unknown"
    factor_overlap: str = "unknown"


class FinancialDriver(BaseModel):
    driver: str
    low: str = ""
    base: str = ""
    high: str = ""
    source: str = ""


class ForwardFinancials(BaseModel):
    """Section 5 — a FORWARD unit-economics sensitivity, never a point estimate or
    a price target. Trailing revenue is flagged as (not) meaningful for pre-ramp
    names. The drivers vary by company; the LLM reasons low/base/high grounded in
    the supplied market cap, trailing revenue, and GAAP margin."""

    trailing_meaningful: bool = True
    trailing_note: str = ""
    drivers: list[FinancialDriver] = Field(default_factory=list)
    market_cap: str = ""
    trailing_revenue: str = ""
    gaap_gross_margin: str = ""
    contracted_forward_revenue: str = ""
    capital_required: str = ""
    funded_by: str = ""


class BottleneckThesisResponse(BaseModel):
    symbol: str
    # chokepoint | adjacent_supplier | theme_exposure | insufficient_evidence
    verdict: str = "insufficient_evidence"
    fit_score: int = 0          # 0-24, DERIVED IN CODE from the gate scores
    max_score: int = 24
    veto: bool = False          # gate 7 (financing) or gate 13 (factor overlap)
    band: str = "watch_item"    # strong | partial | watch_item
    architecture_transition: ArchitectureTransition = Field(default_factory=ArchitectureTransition)
    chain_map: list[ChainHop] = Field(default_factory=list)
    chokepoint_argument: ChokepointArgument = Field(default_factory=ChokepointArgument)
    evidence_table: list[ThesisEvidenceRow] = Field(default_factory=list)
    forward_financials: Optional[ForwardFinancials] = None
    gates: list[ThesisGate] = Field(default_factory=list)
    invalidation_tests: list[str] = Field(default_factory=list)
    risk_profile: RiskProfile = Field(default_factory=RiskProfile)
    could_not_verify: list[str] = Field(default_factory=list)
    computed_at: Optional[str] = None
    # Present when no thesis has been generated yet (honest, not an error).
    message: Optional[str] = None
