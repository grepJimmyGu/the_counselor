"""Tests for the supply-chain extraction pipeline (PRD-25, Slice 3).

All synthetic — no LLM call, no network, no cost. Covers the evidence gate, the
tier-in-code rule, the deterministic chokepoint verdict, the default-OFF cost
gate, and a persist -> Slice-2-read round-trip.
"""
from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.services import supply_chain_service as scs
from app.services.chokepoint_assessment_service import ChokepointAssessmentService
from app.services.chokepoint_assessment_service import (
    ChokepointAssessment,
    ChokepointTest,
)
from app.services.supply_chain_extraction_service import (
    ExtractedEdge,
    ExtractionResult,
    SupplyChainExtractionService,
    _norm_ws,
    assign_tier,
)
from app.services.supply_chain_pipeline import _persist, extraction_enabled


# ── cost gate (the safety-critical property) ────────────────────────────────
def test_extraction_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SUPPLY_CHAIN_EXTRACTION_ENABLED", raising=False)
    assert extraction_enabled() is False
    monkeypatch.setenv("SUPPLY_CHAIN_EXTRACTION_ENABLED", "true")
    assert extraction_enabled() is True


# ── evidence gate + tier-in-code ────────────────────────────────────────────
def test_admit_gates_on_verbatim_quote_and_assigns_tier_in_code():
    svc = SupplyChainExtractionService(fmp_client=object(), gateway=object())
    full = _norm_ws(
        "We source InP substrates from Sumitomo, a named supplier, under a "
        "multi-year agreement disclosed in this report."
    )
    raw = [
        # verifies verbatim -> admitted; named + 10-K -> Tier A (assigned in code)
        {
            "counterparty_name": "Sumitomo", "counterparty_symbol": None,
            "relationship": "supplies",
            "quote": "We source InP substrates from Sumitomo", "is_named": True,
        },
        # quote absent from the filing -> dropped (anti-hallucination gate)
        {
            "counterparty_name": "Ghost Corp", "relationship": "supplies",
            "quote": "This sentence is nowhere in the filing.", "is_named": True,
        },
        # missing counterparty name -> dropped
        {"counterparty_name": "", "relationship": "supplies", "quote": "x", "is_named": True},
    ]
    res = svc.admit("AXTI", raw, full, "https://sec.gov/x", "2026-03-14")

    assert len(res.edges) == 1
    assert res.dropped_edge_count == 2
    e = res.edges[0]
    assert e.evidence_tier == "A"  # named + filing, computed in code — not from the model
    # "supplies" => counterparty is the source, the filing company is the target
    assert e.source_name == "Sumitomo"
    assert e.target_symbol == "AXTI"


def test_assign_tier_never_launders_inference_up():
    assert assign_tier(True, "10-K") == "A"
    assert assign_tier(True, "partner page") == "C"
    assert assign_tier(False, "10-K") == "D"  # inferred is D even from a filing


# ── chokepoint verdict derived in code ──────────────────────────────────────
def test_three_unknown_forces_insufficient_evidence():
    svc = ChokepointAssessmentService(gateway=object())
    payload = {
        "tests": [
            {"test": "supply_concentration", "verdict": "yes", "rationale": "x"},
            {"test": "substitution_difficulty", "verdict": "unknown"},
            {"test": "qualification_cycle", "verdict": "unknown"},
            {"test": "capacity_allocation", "verdict": "unknown"},
            {"test": "bom_share", "verdict": "partial"},
        ],
        "break_statement": "should be dropped when insufficient",
    }
    a = svc.derive(payload, edges=[{"evidence_tier": "A"}])
    assert a.verdict == "insufficient_evidence"
    assert a.confidence == "insufficient_evidence"
    assert a.break_statement is None


def test_three_yes_is_chokepoint_with_break_statement():
    svc = ChokepointAssessmentService(gateway=object())
    payload = {
        "tests": [
            {"test": "supply_concentration", "verdict": "yes"},
            {"test": "substitution_difficulty", "verdict": "yes"},
            {"test": "qualification_cycle", "verdict": "yes"},
            {"test": "capacity_allocation", "verdict": "no"},
            {"test": "bom_share", "verdict": "partial"},
        ],
        "break_statement": "If SUP stops shipping, AXTI breaks.",
    }
    a = svc.derive(payload, edges=[{"evidence_tier": "A"}])
    assert a.verdict == "chokepoint"
    assert a.break_statement == "If SUP stops shipping, AXTI breaks."
    assert len(a.tests) == 5


# ── persist -> Slice-2 read round-trip (conftest `db` fixture) ───────────────
def test_persist_round_trip(db):
    factory = sessionmaker(bind=db.bind, autoflush=False, future=True)
    extraction = ExtractionResult(
        edges=[
            ExtractedEdge(
                source_symbol="SUP", source_name="Supplier Inc",
                target_symbol="AXTI", target_name="AXTI", relationship="supplies",
                evidence_tier="A", source_url="https://sec.gov/x",
                source_doc_type="10-K", quote="Supplier Inc supplies InP to AXTI.",
                as_of_date="2026-03-14", is_named=True,
            )
        ],
        dropped_edge_count=2,
        source_url="https://sec.gov/x",
        as_of_date="2026-03-14",
    )
    assessment = ChokepointAssessment(
        verdict="chokepoint", confidence="moderate",
        break_statement="If SUP stops, AXTI breaks.",
        tests=[
            ChokepointTest(
                test="supply_concentration", verdict="yes", evidence_tier="A",
                rationale="sole source", source_urls=["https://sec.gov/x"],
            )
        ],
    )
    _persist(
        "AXTI", extraction, assessment,
        stage="pre_ramp", trailing_metrics_meaningful=False, session_factory=factory,
    )

    row = scs.read_summary_row(db, "AXTI")
    assert row is not None
    summary = scs.build_summary("AXTI", "Technology", "Semiconductors", summary_row=row)
    assert summary.verdict == "chokepoint"
    assert summary.dropped_edge_count == 2
    assert summary.stage == "pre_ramp"
    assert summary.trailing_metrics_meaningful is False
    assert len(summary.tests) == 1 and summary.tests[0].evidence_tier == "A"

    graph = scs.read_graph(db, "AXTI")
    assert len(graph.edges) == 1 and graph.edges[0].evidence_tier == "A"
    assert scs.read_evidence(db, "AXTI")  # ledger populated


# ── dedicated supply-chain LLM gateway ──────────────────────────────────────
def test_gateway_falls_back_to_app_default_without_dedicated_config(monkeypatch):
    from app.services import supply_chain_llm
    from app.services.llm_adapter import get_llm_gateway

    monkeypatch.delenv("SUPPLY_CHAIN_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SUPPLY_CHAIN_LLM_API_KEY", raising=False)
    # No dedicated provider set → reuse the app's default gateway (same object).
    assert supply_chain_llm.get_supply_chain_gateway() is get_llm_gateway()


def test_gateway_routes_to_dedicated_provider_when_both_vars_set(monkeypatch):
    from app.services import supply_chain_llm

    monkeypatch.setenv("SUPPLY_CHAIN_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("SUPPLY_CHAIN_LLM_API_KEY", "sk-test-deepseek-key")
    gw = supply_chain_llm.get_supply_chain_gateway()
    assert gw.settings.llm_base_url == "https://api.deepseek.com/v1"
    assert gw.settings.llm_api_key == "sk-test-deepseek-key"
    assert gw.settings.llm_provider == "openai_compatible"
    assert gw.is_enabled  # a provider was built against the dedicated endpoint
