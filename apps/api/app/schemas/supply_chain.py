"""Response schemas for the supply-chain lens (PRD-25/26)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChokepointTestResult(BaseModel):
    test: str
    verdict: str  # yes | partial | no | unknown
    evidence_tier: str
    rationale: str
    source_urls: list[str] = Field(default_factory=list)


class SupplyChainSummaryResponse(BaseModel):
    symbol: str
    # chokepoint | adjacent_supplier | theme_exposure | no_chain_structure | insufficient_evidence
    verdict: str
    layer: Optional[str] = None
    layer_ambiguous: bool = False
    vertical: Optional[str] = None
    stage: Optional[str] = None  # pre_ramp | ramping | mature | declining | unknown
    trailing_metrics_meaningful: bool = True
    confidence: str = "insufficient_evidence"  # high | moderate | low | insufficient_evidence
    break_statement: Optional[str] = None
    tests: list[ChokepointTestResult] = Field(default_factory=list)
    dropped_edge_count: int = 0
    fallback_role: Optional[str] = None
    message: Optional[str] = None
    stage_figures: dict = Field(default_factory=dict)
    computed_at: Optional[str] = None


class ChainNode(BaseModel):
    symbol: Optional[str] = None
    name: str
    layer: Optional[str] = None
    is_listed: bool = True


class ChainEdgeOut(BaseModel):
    source_symbol: Optional[str] = None
    source_name: str
    target_symbol: Optional[str] = None
    target_name: str
    relationship: str
    evidence_tier: str
    source_url: str
    source_doc_type: str
    quote: str
    as_of_date: str
    is_named: bool = False
    stale: bool = False


class ChainGraphResponse(BaseModel):
    symbol: str
    nodes: list[ChainNode] = Field(default_factory=list)
    edges: list[ChainEdgeOut] = Field(default_factory=list)
    dropped_edge_count: int = 0


class EvidenceLedgerRow(BaseModel):
    symbol: str
    claim: str
    evidence_tier: str
    source_url: Optional[str] = None
    source_doc_type: Optional[str] = None
    quote: Optional[str] = None
    as_of_date: Optional[str] = None
    falsifier: Optional[str] = None
