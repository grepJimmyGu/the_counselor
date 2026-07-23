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


# ── extract() end-to-end glue (regression for the has_content property bug) ──
def test_extract_reaches_admit_via_has_content_property(monkeypatch):
    """`FilingSections.has_content` is a @property; the extract() glue called it
    as `has_content()` → `TypeError: 'bool' object is not callable`, crashing
    BEFORE the LLM ran so every live /refresh returned ok:false. This drives the
    real extract() with mocked boundaries — it raised pre-fix, passes post-fix.
    """
    import asyncio

    from app.services import supply_chain_extraction_service as mod
    from app.services.filing_section_parser import FilingSections

    sentence = (
        "We source InP substrates from Sumitomo, a named supplier, under a "
        "multi-year agreement disclosed in this report."
    )

    class _FMP:
        async def get_sec_filings(self, symbol, form_type, limit):
            return [{"finalLink": "https://sec.gov/x", "fillingDate": "2026-03-14"}]

    class _GW:
        async def generate_json(self, **kwargs):
            return {
                "edges": [
                    {
                        "counterparty_name": "Sumitomo", "counterparty_symbol": None,
                        "relationship": "supplies",
                        "quote": "We source InP substrates from Sumitomo", "is_named": True,
                    }
                ]
            }

    async def _fake_fetch(url):
        return f"<html><body>{sentence}</body></html>"

    monkeypatch.setattr(mod, "fetch_filing_html", _fake_fetch)
    monkeypatch.setattr(mod, "parse_10k_sections", lambda h: FilingSections(item1_business=sentence))
    monkeypatch.setattr(mod, "_html_to_text", lambda h: sentence)

    svc = mod.SupplyChainExtractionService(fmp_client=_FMP(), gateway=_GW())
    res = asyncio.run(svc.extract("AXTI"))

    assert res.source_url == "https://sec.gov/x"
    assert len(res.edges) == 1  # got past has_content, through the LLM, into admit()
    e = res.edges[0]
    assert e.source_name == "Sumitomo" and e.target_symbol == "AXTI"
    assert e.evidence_tier == "A"  # named + 10-K, assigned in code


# ── 8-K ingestion (Phase 2a): material-agreement edges are Tier A filings ────
def test_admit_tiers_an_8k_relationship_as_tier_a():
    svc = SupplyChainExtractionService(fmp_client=object(), gateway=object())
    full = _norm_ws("We entered a multi-year supply agreement with Sumitomo, a named supplier.")
    raw = [{
        "counterparty_name": "Sumitomo", "counterparty_symbol": None,
        "relationship": "supplies",
        "quote": "We entered a multi-year supply agreement with Sumitomo", "is_named": True,
    }]
    res = svc.admit("AXTI", raw, full, "https://sec.gov/8k", "2026-07-01", doc_type="8-K")
    assert len(res.edges) == 1
    e = res.edges[0]
    assert e.evidence_tier == "A"  # 8-K is a filing -> A, computed in code
    assert e.source_doc_type == "8-K"
    assert e.source_name == "Sumitomo" and e.target_symbol == "AXTI"


def test_extract_8k_admits_agreement_and_skips_non_agreements_before_llm(monkeypatch):
    import asyncio

    from app.services import supply_chain_extraction_service as mod

    agreement = (
        "On June 30, 2026, the Company entered into, under Item 1.01, a material "
        "definitive agreement: a multi-year supply agreement with Sumitomo."
    )
    earnings = "The Company announced quarterly results under Item 2.02 Results of Operations."
    htmls = {
        "https://sec.gov/8k-agreement": f"<html><body>{agreement}</body></html>",
        "https://sec.gov/8k-earnings": f"<html><body>{earnings}</body></html>",
    }

    class _FMP:
        async def get_sec_filings(self, symbol, form_type, limit):
            assert form_type == "8-K"
            return [
                {"finalLink": "https://sec.gov/8k-agreement", "dateFiled": "2026-06-30"},
                {"finalLink": "https://sec.gov/8k-earnings", "dateFiled": "2026-05-01"},
            ]

    class _GW:
        def __init__(self):
            self.calls = 0

        async def generate_json(self, **kwargs):
            self.calls += 1
            return {"edges": [{
                "counterparty_name": "Sumitomo", "counterparty_symbol": None,
                "relationship": "supplies",
                "quote": "a multi-year supply agreement with Sumitomo", "is_named": True,
            }]}

    async def _fake_fetch(url):
        return htmls[url]

    monkeypatch.setattr(mod, "fetch_filing_html", _fake_fetch)
    gw = _GW()
    svc = mod.SupplyChainExtractionService(fmp_client=_FMP(), gateway=gw)
    res = asyncio.run(svc.extract_8k("AXTI"))

    assert len(res.edges) == 1  # only the Item 1.01 8-K yields an edge
    assert res.edges[0].source_doc_type == "8-K" and res.edges[0].evidence_tier == "A"
    assert res.edges[0].source_name == "Sumitomo"
    assert gw.calls == 1  # the earnings 8-K was skipped BEFORE spending an LLM call


def test_merge_extractions_dedups_keeping_the_first_pass():
    from app.services.supply_chain_pipeline import _merge_extractions

    def _edge(src_name, tgt_name, rel, doc):
        return ExtractedEdge(
            source_symbol=None, source_name=src_name, target_symbol=None, target_name=tgt_name,
            relationship=rel, evidence_tier="A", source_url=f"u-{doc}", source_doc_type=doc,
            quote="q", as_of_date="2026-03-14", is_named=True,
        )

    ten_k = ExtractionResult(edges=[_edge("Sumitomo", "AXTI", "supplies", "10-K")], dropped_edge_count=1)
    eight_k = ExtractionResult(
        edges=[
            _edge("Sumitomo", "AXTI", "supplies", "8-K"),   # dup of the 10-K edge
            _edge("AXTI", "Coherent", "customer_of", "8-K"),  # new
        ],
        dropped_edge_count=2,
    )
    merged = _merge_extractions(ten_k, eight_k)

    assert len(merged.edges) == 2  # Sumitomo deduped, Coherent added
    sumitomo = [e for e in merged.edges if e.source_name == "Sumitomo"]
    assert len(sumitomo) == 1 and sumitomo[0].source_doc_type == "10-K"  # first pass wins
    assert merged.dropped_edge_count == 3


def test_extract_filings_generic_10q_is_tier_a(monkeypatch):
    """The generalized pass (no marker) admits a 10-Q relationship as Tier A —
    the same doc_type-driven tiering, covering 10-Q / S-1 / 20-F."""
    import asyncio

    from app.services import supply_chain_extraction_service as mod

    body = "We continue to purchase InP substrates from Sumitomo under our supply agreement."

    class _FMP:
        async def get_sec_filings(self, symbol, form_type, limit):
            assert form_type == "10-Q"
            return [{"finalLink": "https://sec.gov/10q", "dateFiled": "2026-05-10"}]

    class _GW:
        async def generate_json(self, **kwargs):
            return {"edges": [{
                "counterparty_name": "Sumitomo", "counterparty_symbol": None,
                "relationship": "supplies",
                "quote": "purchase InP substrates from Sumitomo", "is_named": True,
            }]}

    async def _fake_fetch(url):
        return f"<html><body>{body}</body></html>"

    monkeypatch.setattr(mod, "fetch_filing_html", _fake_fetch)
    svc = mod.SupplyChainExtractionService(fmp_client=_FMP(), gateway=_GW())
    res = asyncio.run(svc.extract_filings("AXTI", "10-Q", 2))

    assert len(res.edges) == 1
    assert res.edges[0].source_doc_type == "10-Q" and res.edges[0].evidence_tier == "A"
    assert res.edges[0].source_name == "Sumitomo"


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
