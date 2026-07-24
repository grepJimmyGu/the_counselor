"""Bottleneck-thesis reasoning engine (Phase 3 / PRD-27).

Turns the ingested evidence (supply-chain edges + chokepoint verdict + stage +
business intelligence + FMP financials) into the bottleneck skill's graded thesis
— architecture transition, chain map, chokepoint argument, tiered evidence,
gate scorecard, invalidation tests. NEVER a recommendation.

Discipline (mirrors chokepoint_assessment_service):
- The LLM assesses each gate WITH an evidence tier and reasons the MAP (transition
  + chain) from the company's business; but the fit-score total and the two vetoes
  are DERIVED IN CODE in ``derive`` — never taken from the model.
- The MAP (sections 1-2) is inference (allowed); the EVIDENCE (tiers, gates) is
  strictly gated to the supplied hard evidence. Inference generates the hypothesis;
  documents confirm it. The two are never blurred.

Gated OFF by default (see thesis_pipeline.thesis_enabled) — no LLM call, no cost,
until SUPPLY_CHAIN_THESIS_ENABLED is set.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.schemas.bottleneck_thesis import (
    ArchitectureTransition,
    BottleneckThesisResponse,
    CatalystEvent,
    ChainHop,
    ChokepointArgument,
    FinancialDriver,
    ForwardFinancials,
    RiskProfile,
    ThesisEvidenceRow,
    ThesisGate,
)
from app.services.llm_adapter import LLMAdapterError
from app.services.supply_chain_llm import get_supply_chain_gateway

logger = logging.getLogger("livermore.supply_chain")

_REASONING_SYSTEM = (
    "You are a supply-chain bottleneck research analyst. From the SUPPLIED EVIDENCE "
    "and the company's disclosed business ONLY, produce a structured research "
    "artifact. This is NEVER a recommendation, price target, or entry; never output "
    "buy/sell/hold.\n\n"
    "Non-negotiable rules:\n"
    "- Every claim carries an evidence tier. Ladder: A=SEC filing (can validate/kill); "
    "B=named commercial commitment (disclosed agreement/PO/design win); C=reference "
    "design / qualified-supplier listing; D=partner-page/inference/BOM (the map, not a "
    "commercial claim); E=peer transcripts/sell-side; F=social/LLM. Assign tier by "
    "SOURCE TYPE; never launder an inference up to a fact.\n"
    "- 'unknown' is a valid, expected answer. NEVER guess to fill a table. A gate scored "
    "from 'unknown' scores 0, not partial.\n"
    "- The fit score is an ARCHETYPE-FIT score (0-24), NOT a buy signal. Gate 7 "
    "(financing quality) and Gate 13 (factor overlap) are VETOES.\n"
    "- Provide >= 5 specific, checkable invalidation tests, each with a trigger/date. "
    "A drawdown is not an invalidation; a rally is not a confirmation.\n"
    "- Architecture-transition gate: if the thesis survives with the transition removed, "
    "it is a THEME, not a bottleneck — say so.\n\n"
    "MAP vs EVIDENCE (critical): inference generates the hypothesis; documents confirm "
    "it.\n"
    "- Sections 1 (architecture transition) and 2 (chain map) are THE MAP. REASON from "
    "the company's disclosed business + sector to name the OLD->NEW transition and the "
    "multi-hop chain (raw material -> substrate -> epiwafer -> device/laser -> module -> "
    "system). Inference is EXPECTED — name the plausible transition and layers even "
    "without hard evidence; mark a layer's status 'unknown' when you cannot verify it, "
    "but do NOT leave the transition/chain blank if the business implies one.\n"
    "- Sections 3-6, the evidence table, and the gates use ONLY the supplied hard "
    "evidence with strict tiers; unknown scores 0. Never promote a mapped inference to a "
    "gate score.\n\n"
    "Section 5 (forward financials): a FORWARD unit-economics sensitivity, NOT a "
    "point estimate and NEVER a price target. For a pre-ramp company trailing revenue "
    "is near-meaningless — say so in trailing_note. Give low/base/high for the drivers "
    "that actually move THIS company's revenue (e.g. capacity allocation %, yield %, "
    "ASP, addressable share), then the derived revenue + gross-profit bands as driver "
    "rows. Anchor market_cap, trailing_revenue, and gaap_gross_margin to the SUPPLIED "
    "financials; state each assumption's basis in its source field.\n\n"
    "Gate 7 (financing quality — VETO): judge from the supplied financing_signals "
    "(share dilution YoY, cash runway, debt). Heavy open-market dilution into weak cash "
    "with negative operating cash flow is toxic -> VETO; a one-time strategic / funded "
    "raise is constructive -> PASS. Gate 13 (factor overlap — VETO) is assessed "
    "PER-PORTFOLIO (whether the READER holds other names sharing this driver); at the "
    "company level note the shared driver but mark PASS unless the evidence itself shows "
    "crowding. Section 7 (catalyst calendar): list DATED events already implied by the "
    "evidence (contract/commitment dates, ramp milestones, qualification decisions) that "
    "would confirm or break the thesis.\n\n"
    "Return ONLY JSON:\n"
    "{\n"
    '  "verdict": "chokepoint|adjacent_supplier|theme_exposure|insufficient_evidence",\n'
    '  "architecture_transition": {"from": str, "to": str, "what_becomes_scarce": str, "transition_exists": bool},\n'
    '  "chain_map": [{"hop": int, "layer": str, "named_players": [str], "status": "abundant|constrained|unknown"}],\n'
    '  "chokepoint_argument": {"if_stops": str, "downstream_breaks": str, "mechanism": str, "nearest_substitute": str, "substitute_status": str},\n'
    '  "evidence_table": [{"claim": str, "tier": str, "source": str, "date": str, "falsifier": str}],\n'
    '  "forward_financials": {"trailing_meaningful": bool, "trailing_note": str, "drivers": [{"driver": str, "low": str, "base": str, "high": str, "source": str}], "market_cap": str, "trailing_revenue": str, "gaap_gross_margin": str, "contracted_forward_revenue": str, "capital_required": str, "funded_by": str},\n'
    '  "gates": [{"n": int, "name": str, "score": "0|1|2|VETO|PASS", "tier": str, "note": str}],\n'
    '  "catalyst_calendar": [{"date": str, "event": str, "confirms_or_breaks": str}],\n'
    '  "invalidation_tests": [str],\n'
    '  "risk_profile": {"binariness": str, "liquidity": str, "crowding": str, "factor_overlap": str},\n'
    '  "could_not_verify": [str]\n'
    "}\n"
    "The 14 gates in order: 1 Chokepoint, 2 Upstream+BOM share, 3 Chain fluency, "
    "4 Architecture transition, 5 Contracts+counterparty, 6 GAAP margins, 7 Financing "
    "quality (VETO), 8 Pre-ramp stage, 9 Dated catalyst, 10 Market-cap headroom, "
    "11 Coverage still behind, 12 Binariness+structure, 13 Factor overlap (VETO), "
    "14 Macro regime. Score each 0/1/2 (unknown=0); gates 7 & 13 are PASS or VETO."
)


class BottleneckThesisService:
    def __init__(self, gateway=None) -> None:
        self._gateway = gateway or get_supply_chain_gateway()

    @staticmethod
    def _model() -> Optional[str]:
        # Reasoning is harder than extraction; allow a dedicated (e.g. reasoning)
        # model, falling back to the chokepoint / extract model, then the default.
        return (
            os.environ.get("SUPPLY_CHAIN_THESIS_MODEL")
            or os.environ.get("SUPPLY_CHAIN_CHOKEPOINT_MODEL")
            or os.environ.get("SUPPLY_CHAIN_EXTRACT_MODEL")
            or None
        )

    @staticmethod
    def assemble_context(symbol: str, **parts) -> dict:
        """Pure — build the evidence context the reasoner sees. ``parts`` carries
        business, financials, stage, chokepoint_verdict, chokepoint_tests, edges,
        evidence (all already gathered by the caller; no DB / network here)."""
        return {
            "symbol": symbol.upper(),
            "business": parts.get("business") or {},
            "financials": parts.get("financials") or {},
            "supply_chain_stage": parts.get("stage"),
            "trailing_metrics_meaningful": parts.get("trailing_metrics_meaningful"),
            "current_chokepoint_verdict": parts.get("chokepoint_verdict"),
            "chokepoint_tests": parts.get("chokepoint_tests") or [],
            "extracted_edges": parts.get("edges") or [],
            "evidence_ledger": parts.get("evidence") or [],
        }

    async def reason(self, context: dict) -> dict:
        import json

        symbol = context.get("symbol", "?")
        payload = await self._gateway.generate_json(
            system_prompt=_REASONING_SYSTEM,
            user_prompt=f"Company: {symbol}\n\nEVIDENCE:\n{json.dumps(context, default=str)}",
            temperature=0.2,
            model=self._model(),
        )
        return payload if isinstance(payload, dict) else {}

    def derive(self, symbol: str, payload: dict) -> BottleneckThesisResponse:
        """Build the response; the fit-score TOTAL, the vetoes, and the band are
        computed HERE in code — never taken from the model."""
        payload = payload if isinstance(payload, dict) else {}

        gates: list[ThesisGate] = []
        numeric_total = 0
        veto = False
        for g in payload.get("gates") or []:
            if not isinstance(g, dict):
                continue
            score = str(g.get("score", "")).strip().upper()
            gates.append(
                ThesisGate(
                    n=_int(g.get("n")),
                    name=str(g.get("name") or ""),
                    score=score,
                    tier=str(g.get("tier") or ""),
                    note=str(g.get("note") or ""),
                )
            )
            if score.isdigit():
                numeric_total += min(max(int(score), 0), 2)  # clamp 0-2
            elif score == "VETO":
                veto = True

        fit = min(numeric_total, 12) if veto else min(numeric_total, 24)
        if veto or fit < 14:
            band = "watch_item"
        elif fit < 20:
            band = "partial"
        else:
            band = "strong"

        t = payload.get("architecture_transition") or {}
        transition = ArchitectureTransition(
            from_state=str(t.get("from") or t.get("from_state") or ""),
            to_state=str(t.get("to") or t.get("to_state") or ""),
            what_becomes_scarce=str(t.get("what_becomes_scarce") or ""),
            transition_exists=bool(t.get("transition_exists")),
        )

        chain: list[ChainHop] = []
        for h in payload.get("chain_map") or []:
            if not isinstance(h, dict):
                continue
            chain.append(
                ChainHop(
                    hop=_int(h.get("hop")),
                    layer=str(h.get("layer") or ""),
                    named_players=[str(p) for p in (h.get("named_players") or []) if p],
                    status=str(h.get("status") or "unknown"),
                )
            )

        ca = payload.get("chokepoint_argument") or {}
        choke = ChokepointArgument(
            if_stops=str(ca.get("if_stops") or ""),
            downstream_breaks=str(ca.get("downstream_breaks") or ""),
            mechanism=str(ca.get("mechanism") or ""),
            nearest_substitute=str(ca.get("nearest_substitute") or ""),
            substitute_status=str(ca.get("substitute_status") or ""),
        )

        evidence: list[ThesisEvidenceRow] = []
        for e in payload.get("evidence_table") or []:
            if not isinstance(e, dict):
                continue
            evidence.append(
                ThesisEvidenceRow(
                    claim=str(e.get("claim") or ""),
                    tier=str(e.get("tier") or ""),
                    source=str(e.get("source") or ""),
                    date=str(e.get("date") or ""),
                    falsifier=str(e.get("falsifier") or ""),
                )
            )

        rp = payload.get("risk_profile") or {}
        risk = RiskProfile(
            binariness=str(rp.get("binariness") or "unknown"),
            liquidity=str(rp.get("liquidity") or "unknown"),
            crowding=str(rp.get("crowding") or "unknown"),
            factor_overlap=str(rp.get("factor_overlap") or "unknown"),
        )

        ff = payload.get("forward_financials")
        forward = None
        if isinstance(ff, dict) and ff:
            forward = ForwardFinancials(
                trailing_meaningful=bool(ff.get("trailing_meaningful", True)),
                trailing_note=str(ff.get("trailing_note") or ""),
                drivers=[
                    FinancialDriver(
                        driver=str(d.get("driver") or ""), low=str(d.get("low") or ""),
                        base=str(d.get("base") or ""), high=str(d.get("high") or ""),
                        source=str(d.get("source") or ""),
                    )
                    for d in (ff.get("drivers") or []) if isinstance(d, dict)
                ],
                market_cap=str(ff.get("market_cap") or ""),
                trailing_revenue=str(ff.get("trailing_revenue") or ""),
                gaap_gross_margin=str(ff.get("gaap_gross_margin") or ""),
                contracted_forward_revenue=str(ff.get("contracted_forward_revenue") or ""),
                capital_required=str(ff.get("capital_required") or ""),
                funded_by=str(ff.get("funded_by") or ""),
            )

        catalysts = [
            CatalystEvent(
                date=str(c.get("date") or ""),
                event=str(c.get("event") or ""),
                confirms_or_breaks=str(c.get("confirms_or_breaks") or ""),
            )
            for c in (payload.get("catalyst_calendar") or []) if isinstance(c, dict)
        ]

        return BottleneckThesisResponse(
            symbol=symbol.upper(),
            verdict=str(payload.get("verdict") or "insufficient_evidence"),
            fit_score=fit,
            veto=veto,
            band=band,
            architecture_transition=transition,
            chain_map=chain,
            chokepoint_argument=choke,
            evidence_table=evidence,
            forward_financials=forward,
            gates=gates,
            catalyst_calendar=catalysts,
            invalidation_tests=[str(x) for x in (payload.get("invalidation_tests") or []) if x],
            risk_profile=risk,
            could_not_verify=[str(x) for x in (payload.get("could_not_verify") or []) if x],
        )

    async def generate(self, symbol: str, **parts) -> BottleneckThesisResponse:
        context = self.assemble_context(symbol, **parts)
        try:
            payload = await self.reason(context)
        except LLMAdapterError:
            logger.exception("thesis: LLM failed for %s", symbol)
            return BottleneckThesisResponse(
                symbol=symbol.upper(),
                message="Thesis reasoning failed — the model call did not complete.",
            )
        return self.derive(symbol, payload)


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0
