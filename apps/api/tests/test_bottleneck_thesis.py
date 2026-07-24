"""Tests for the bottleneck-thesis reasoning engine (Phase 3 / PRD-27).

All synthetic — no LLM, no network, no cost. Covers the code-computed fit score +
veto (the safety-critical property), the band thresholds, the cost gate, the
section mapping, and a persist -> read round-trip.
"""
from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.schemas.bottleneck_thesis import BottleneckThesisResponse, ChainHop
from app.services.bottleneck_thesis_service import BottleneckThesisService
from app.services.thesis_pipeline import _persist_thesis, read_thesis, thesis_enabled


# ── cost gate (safety-critical) ──────────────────────────────────────────────
def test_thesis_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SUPPLY_CHAIN_THESIS_ENABLED", raising=False)
    assert thesis_enabled() is False
    monkeypatch.setenv("SUPPLY_CHAIN_THESIS_ENABLED", "true")
    assert thesis_enabled() is True


# ── fit score + veto derived in CODE (never the model's number) ──────────────
def test_derive_computes_fit_score_and_veto_in_code():
    svc = BottleneckThesisService(gateway=object())
    payload = {
        "verdict": "chokepoint",
        "gates": [
            {"n": 1, "name": "Chokepoint", "score": "2", "tier": "A"},
            {"n": 2, "name": "Upstream", "score": "1"},
            {"n": 5, "name": "Contracts", "score": "2"},
            {"n": 99, "name": "clamp", "score": "5"},   # clamps to 2
            {"n": 7, "name": "Financing", "score": "VETO"},  # veto
        ],
        "invalidation_tests": ["a", "b", "c", "d", "e"],
    }
    t = svc.derive("axti", payload)
    assert t.fit_score == 7        # 2 + 1 + 2 + 2(clamped); VETO contributes 0
    assert t.veto is True
    assert t.band == "watch_item"  # any veto -> watch item regardless of total
    assert t.symbol == "AXTI"
    assert len(t.invalidation_tests) == 5


def test_derive_band_thresholds():
    svc = BottleneckThesisService(gateway=object())

    def band_for(n_twos):
        gates = [{"n": i, "name": str(i), "score": "2"} for i in range(n_twos)]
        return svc.derive("X", {"gates": gates})

    assert band_for(10).fit_score == 20 and band_for(10).band == "strong"
    assert band_for(7).fit_score == 14 and band_for(7).band == "partial"
    assert band_for(6).fit_score == 12 and band_for(6).band == "watch_item"


# ── map + evidence sections mapped faithfully ────────────────────────────────
def test_derive_maps_map_and_evidence_sections():
    svc = BottleneckThesisService(gateway=object())
    payload = {
        "verdict": "theme_exposure",
        "architecture_transition": {
            "from": "electrical interconnect", "to": "optical interconnect",
            "what_becomes_scarce": "InP substrates", "transition_exists": True,
        },
        "chain_map": [{"hop": 2, "layer": "substrate", "named_players": ["AXT"], "status": "constrained"}],
        "chokepoint_argument": {"if_stops": "x", "downstream_breaks": "y", "mechanism": "z",
                                "nearest_substitute": "GaAs", "substitute_status": "limited"},
        "evidence_table": [{"claim": "c", "tier": "A", "source": "8-K", "date": "2026-06", "falsifier": "f"}],
        "risk_profile": {"binariness": "low", "liquidity": "low", "crowding": "unknown", "factor_overlap": "low"},
        "could_not_verify": ["market share"],
        "gates": [],
    }
    t = svc.derive("AXTI", payload)
    assert t.architecture_transition.from_state == "electrical interconnect"
    assert t.architecture_transition.to_state == "optical interconnect"
    assert t.architecture_transition.transition_exists is True
    assert len(t.chain_map) == 1
    assert t.chain_map[0].status == "constrained" and t.chain_map[0].named_players == ["AXT"]
    assert t.chokepoint_argument.nearest_substitute == "GaAs"
    assert len(t.evidence_table) == 1 and t.evidence_table[0].tier == "A"
    assert t.risk_profile.binariness == "low" and t.could_not_verify == ["market share"]
    assert t.fit_score == 0 and t.band == "watch_item"  # no gates -> honest 0


def test_derive_maps_forward_financials():
    svc = BottleneckThesisService(gateway=object())
    payload = {
        "forward_financials": {
            "trailing_meaningful": False,
            "trailing_note": "pre-ramp; trailing revenue near-meaningless",
            "drivers": [
                {"driver": "Capacity allocation %", "low": "10%", "base": "25%", "high": "40%", "source": "assumption"},
                {"driver": "Revenue", "low": "$50M", "base": "$120M", "high": "$200M", "source": "derived"},
            ],
            "market_cap": "$2.45B", "trailing_revenue": "$100M", "gaap_gross_margin": "12%",
            "contracted_forward_revenue": "unknown", "capital_required": "$150M", "funded_by": "cash + ATM",
        },
        "gates": [],
    }
    ff = svc.derive("AXTI", payload).forward_financials
    assert ff is not None and ff.trailing_meaningful is False
    assert len(ff.drivers) == 2
    assert ff.drivers[0].driver == "Capacity allocation %" and ff.drivers[0].base == "25%"
    assert ff.market_cap == "$2.45B" and ff.gaap_gross_margin == "12%" and ff.funded_by == "cash + ATM"


def test_derive_without_forward_financials_is_none():
    t = BottleneckThesisService(gateway=object()).derive("AXTI", {"gates": []})
    assert t.forward_financials is None


def test_derive_maps_catalyst_calendar():
    svc = BottleneckThesisService(gateway=object())
    payload = {
        "catalyst_calendar": [
            {"date": "2027", "event": "Casela InP purchase commitment", "confirms_or_breaks": "confirms demand ramp"},
            {"date": "Q4 2026", "event": "gross-margin inflection", "confirms_or_breaks": "breaks distress narrative"},
        ],
        "gates": [],
    }
    t = svc.derive("AXTI", payload)
    assert len(t.catalyst_calendar) == 2
    assert t.catalyst_calendar[0].date == "2027" and "Casela" in t.catalyst_calendar[0].event
    assert t.catalyst_calendar[1].confirms_or_breaks == "breaks distress narrative"


def test_assemble_context_is_pure_and_uppercases():
    ctx = BottleneckThesisService.assemble_context(
        "axti", business={"sector": "Tech"}, edges=[{"source": "AXT"}],
        chokepoint_verdict="insufficient_evidence",
    )
    assert ctx["symbol"] == "AXTI"
    assert ctx["business"] == {"sector": "Tech"}
    assert ctx["extracted_edges"] == [{"source": "AXT"}]
    assert ctx["current_chokepoint_verdict"] == "insufficient_evidence"


# ── persist -> read round-trip (conftest `db` fixture) ───────────────────────
def test_persist_and_read_round_trip(db):
    factory = sessionmaker(bind=db.bind, autoflush=False, future=True)
    thesis = BottleneckThesisResponse(
        symbol="AXTI", verdict="chokepoint", fit_score=7, veto=True, band="watch_item",
        chain_map=[ChainHop(hop=2, layer="substrate", named_players=["AXT"], status="constrained")],
        invalidation_tests=["a", "b"],
    )
    _persist_thesis("AXTI", thesis, session_factory=factory)

    got = read_thesis(db, "AXTI")
    assert got.verdict == "chokepoint" and got.fit_score == 7 and got.veto is True
    assert got.band == "watch_item"
    assert len(got.chain_map) == 1 and got.chain_map[0].layer == "substrate"
    assert got.chain_map[0].named_players == ["AXT"]
    assert got.computed_at is not None


def test_read_thesis_absent_is_honest_not_error(db):
    t = read_thesis(db, "NOBODY")
    assert t.message is not None
    assert t.verdict == "insufficient_evidence" and t.fit_score == 0
