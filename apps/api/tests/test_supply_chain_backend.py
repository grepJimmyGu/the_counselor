"""Backend-spine tests for the supply-chain lens (PRD-25/26, Slice 2).

Covers the deterministic logic (stage classifier, verdict rules) and the DB
layer against the real migrated schema. The HTTP endpoints are thin passthroughs
over these functions.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

from app.services import supply_chain_service as scs
from app.services.chain_stage_service import classify_stage


# ── stage classifier (pure) ──────────────────────────────────────────────────
def _inc(rev, rnd=None, d="2026-03-14"):
    row = {"revenue": rev, "date": d}
    if rnd is not None:
        row["researchAndDevelopmentExpenses"] = rnd
    return row


def test_stage_pre_ramp_low_revenue_high_rnd():
    r = classify_stage([_inc(30e6, rnd=20e6), _inc(25e6, rnd=18e6)], [{"freeCashFlow": -10e6}])
    assert r.stage == "pre_ramp"
    assert r.trailing_metrics_meaningful is False


def test_stage_ramping_high_growth():
    r = classify_stage([_inc(200e6), _inc(100e6)], [{"freeCashFlow": 5e6}])
    assert r.stage == "ramping"
    assert r.trailing_metrics_meaningful is True


def test_stage_declining_two_consecutive_years():
    r = classify_stage([_inc(80e6), _inc(100e6), _inc(120e6)], [{"freeCashFlow": 1e6}])
    assert r.stage == "declining"


def test_stage_mature_default():
    r = classify_stage([_inc(500e6), _inc(480e6)], [{"freeCashFlow": 50e6}])
    assert r.stage == "mature"
    assert r.trailing_metrics_meaningful is True


def test_stage_unknown_without_revenue():
    assert classify_stage([], []).stage == "unknown"
    assert classify_stage([{"date": "2026"}], []).stage == "unknown"


# ── no_chain_structure + build_summary (pure) ────────────────────────────────
def test_bank_is_no_chain_structure_with_nonnull_fallback_role():
    # PRD acceptance: a JPM-like financial returns no_chain_structure with a
    # NON-NULL fallback_role — which requires the "Financial Services" → the
    # classifier's "Financials" alias normalization.
    assert scs.is_no_chain_structure_sector("Financial Services", "Banks") is True
    s = scs.build_summary("JPM", "Financial Services", "Banks")
    assert s.verdict == "no_chain_structure"
    assert s.confidence == "high"
    assert s.fallback_role is not None


def test_non_financial_without_extraction_is_insufficient_not_no_structure():
    assert scs.is_no_chain_structure_sector("Technology", "Semiconductors") is False
    s = scs.build_summary(
        "AXTI", "Technology", "Semiconductors",
        stage="pre_ramp", trailing_metrics_meaningful=False,
    )
    assert s.verdict == "insufficient_evidence"
    assert s.stage == "pre_ramp"
    assert s.trailing_metrics_meaningful is False


def test_persisted_summary_row_wins():
    row = {
        "chokepoint_verdict": "chokepoint", "confidence": "moderate",
        "layer": "substrate", "vertical": "photonics", "layer_ambiguous": False,
        "stage": "pre_ramp", "trailing_metrics_meaningful": False,
        "break_statement": "If AXTI stops shipping InP, transceivers break.",
        "tests_json": json.dumps([{
            "test": "supply_concentration", "verdict": "yes",
            "evidence_tier": "A", "rationale": "sole source", "source_urls": ["u"],
        }]),
        "dropped_edge_count": 3, "computed_at": "2026-07-21",
    }
    s = scs.build_summary("AXTI", "Technology", "Semiconductors", summary_row=row)
    assert s.verdict == "chokepoint"
    assert s.layer == "substrate"
    assert s.dropped_edge_count == 3
    assert len(s.tests) == 1 and s.tests[0].evidence_tier == "A"


# ── DB layer against the migrated schema (conftest `db` fixture) ──────────────
def test_tables_exist_and_empty_reads(db):
    for t in ("supply_chain_edges", "supply_chain_summaries", "evidence_ledger"):
        assert db.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0
    g = scs.read_graph(db, "AXTI")
    assert g.nodes == [] and g.edges == []
    assert scs.read_evidence(db, "AXTI") == []
    assert scs.read_summary_row(db, "AXTI") is None


def test_read_graph_assembles_nodes_and_edges(db):
    db.execute(
        text(
            "INSERT INTO supply_chain_edges (source_symbol, source_name, target_symbol,"
            " target_name, relationship, evidence_tier, source_url, source_doc_type,"
            " quote, as_of_date, is_named, stale, extracted_at) VALUES"
            " (:ss,:sn,:ts,:tn,:rel,:tier,:url,:dt,:q,:d,:named,:stale,:ext)"
        ),
        {
            "ss": "AXTI", "sn": "AXT Inc", "ts": "AAOI",
            "tn": "Applied Optoelectronics", "rel": "supplies", "tier": "A",
            "url": "https://sec.gov/x", "dt": "10-K",
            "q": "We supply InP substrates to AAOI.", "d": "2026-03-14",
            "named": 1, "stale": 0, "ext": datetime.utcnow().isoformat(),
        },
    )
    db.commit()
    g = scs.read_graph(db, "AXTI")
    assert len(g.edges) == 1
    assert {n.symbol for n in g.nodes} == {"AXTI", "AAOI"}
    assert g.edges[0].evidence_tier == "A"


# ── Phase 1: seed the inferred map (Tier D) from cached business intelligence ──
def _cache_bi(db, symbol, suppliers, customers, url="https://sec.gov/x", date="2026-03-14"):
    from app.services.business_intelligence_service import BusinessIntelligence, _save_cache

    _save_cache(
        BusinessIntelligence(
            symbol=symbol, filing_type="10-K", filing_date=date, filing_url=url,
            upstream_suppliers=suppliers, downstream_customers=customers, confidence="high",
        ),
        db,
    )
    db.commit()


def test_read_graph_seeds_tier_d_edges_from_bi(db):
    _cache_bi(db, "AXTI", suppliers=["Sumitomo", "Freiberger"], customers=["Coherent"])
    g = scs.read_graph(db, "AXTI")

    assert {e.evidence_tier for e in g.edges} == {"D"}
    assert len(g.edges) == 3  # 2 suppliers + 1 customer
    # suppliers point INTO the company; customers point OUT of it
    assert {e.source_name for e in g.edges if e.relationship == "supplies"} == {
        "Sumitomo", "Freiberger",
    }
    assert {e.target_name for e in g.edges if e.relationship == "customer_of"} == {"Coherent"}
    assert {n.name for n in g.nodes} >= {"AXTI", "Sumitomo", "Freiberger", "Coherent"}
    # no verbatim quote — that is exactly what keeps a seeded edge Tier D, not A
    assert all(e.quote == "" for e in g.edges)


def test_extracted_tier_a_edge_wins_over_bi_seed(db):
    # An extracted (Tier A) edge for Sumitomo already exists...
    db.execute(
        text(
            "INSERT INTO supply_chain_edges (source_symbol, source_name, target_symbol,"
            " target_name, relationship, evidence_tier, source_url, source_doc_type,"
            " quote, as_of_date, is_named, stale, extracted_at) VALUES"
            " (:ss,:sn,:ts,:tn,:rel,:tier,:url,:dt,:q,:d,:named,:stale,:ext)"
        ),
        {
            "ss": None, "sn": "Sumitomo", "ts": "AXTI", "tn": "AXTI",
            "rel": "supplies", "tier": "A", "url": "https://sec.gov/x", "dt": "10-K",
            "q": "We source InP substrates from Sumitomo.", "d": "2026-03-14",
            "named": 1, "stale": 0, "ext": datetime.utcnow().isoformat(),
        },
    )
    db.commit()
    # ...and the BI cache lists Sumitomo (dup) plus a NEW name.
    _cache_bi(db, "AXTI", suppliers=["Sumitomo", "Freiberger"], customers=[])
    g = scs.read_graph(db, "AXTI")

    sumitomo = [e for e in g.edges if e.source_name == "Sumitomo"]
    assert len(sumitomo) == 1  # NOT duplicated by the seed
    assert sumitomo[0].evidence_tier == "A"  # the verbatim-quoted edge wins
    freiberger = [e for e in g.edges if e.source_name == "Freiberger"]
    assert len(freiberger) == 1 and freiberger[0].evidence_tier == "D"  # seeded name survives


def test_read_graph_without_bi_cache_is_unchanged(db):
    g = scs.read_graph(db, "NOBODY")
    assert g.edges == [] and g.nodes == []


def test_seed_survives_non_string_filing_date(db, monkeypatch):
    """Regression: Postgres hands filing_date back as a date object, not a str.
    ChainEdgeOut requires str fields, so read_graph 500'd for every company with a
    populated BI cache (AAPL/TSLA). The seed must coerce and never break the read.
    """
    import datetime as _dt

    from app.services import supply_chain_service as scs_mod
    from app.services.business_intelligence_service import BusinessIntelligence

    bi = BusinessIntelligence(
        symbol="AAPL", filing_type="10-K",
        filing_date=_dt.date(2026, 3, 14),  # a DATE object, not a string
        filing_url="https://sec.gov/x",
        upstream_suppliers=["TSMC"], downstream_customers=["Enterprise"],
    )
    monkeypatch.setattr(scs_mod, "load_cached_bi", lambda symbol, session: bi)

    g = scs_mod.read_graph(db, "AAPL")  # must NOT raise

    assert len(g.edges) == 2
    assert all(isinstance(e.as_of_date, str) for e in g.edges)  # coerced to str
    assert {e.as_of_date for e in g.edges} == {"2026-03-14"}


def test_read_sector_industry(db):
    from app.models.symbol import SymbolCache

    db.add(
        SymbolCache(
            symbol="JPM", name="JPMorgan Chase",
            sector="Financial Services", industry="Banks",
        )
    )
    db.commit()
    sector, industry = scs.read_sector_industry(db, "jpm")
    assert sector == "Financial Services"
    assert industry == "Banks"
