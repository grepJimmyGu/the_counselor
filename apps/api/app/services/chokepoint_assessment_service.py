"""Chokepoint assessment (PRD-25, Slice 3) — the five tests.

The LLM authors each test's verdict + rationale from the ADMITTED edges; the
overall verdict and confidence are derived in CODE, never taken from the model.
`unknown` is a first-class answer — the model is told not to guess to fill the
table, and ">=3 unknown" deterministically forces `insufficient_evidence`.

Gated OFF by default with the rest of the pipeline (no LLM call until enabled).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from app.services.llm_adapter import LLMAdapterError
from app.services.supply_chain_llm import get_supply_chain_gateway

logger = logging.getLogger("livermore.supply_chain")

_TESTS = [
    "supply_concentration",
    "substitution_difficulty",
    "qualification_cycle",
    "capacity_allocation",
    "bom_share",
]
_VERDICTS = {"yes", "partial", "no", "unknown"}


@dataclass
class ChokepointTest:
    test: str
    verdict: str
    evidence_tier: str
    rationale: str
    source_urls: list[str] = field(default_factory=list)


@dataclass
class ChokepointAssessment:
    verdict: str  # chokepoint | adjacent_supplier | theme_exposure | insufficient_evidence
    tests: list[ChokepointTest] = field(default_factory=list)
    break_statement: Optional[str] = None
    confidence: str = "insufficient_evidence"


_SYSTEM = (
    "You assess whether a company is a supply-chain CHOKEPOINT, using ONLY the "
    "provided sourced relationships. Run these five tests: supply_concentration "
    "(monopoly/duopoly vs many qualified sources), substitution_difficulty (is a "
    "second source qualified TODAY), qualification_cycle (long cycles are a moat), "
    "capacity_allocation (holding multi-year allocation at a contract manufacturer "
    "IS being the bottleneck — the most-missed test, judge it explicitly), "
    "bom_share (small % of the bill of materials + no substitute = pricing power). "
    "For each test return verdict yes|partial|no|unknown and a one-line rationale. "
    "Return 'unknown' whenever the evidence is silent — unknown is a valid, "
    "expected, NON-penalized answer; never guess to fill the table. Also return a "
    "one-line break_statement like 'If X stops shipping, Y breaks; nearest "
    "substitute is Z' ONLY if the evidence supports it, else null. Never output an "
    "opinion on the stock. JSON: {\"tests\":[{\"test\":string,\"verdict\":string,"
    "\"rationale\":string,\"source_urls\":[string]}],\"break_statement\":string|null}"
)


def _tier_of(edge) -> Optional[str]:
    if isinstance(edge, dict):
        return edge.get("evidence_tier")
    return getattr(edge, "evidence_tier", None)


class ChokepointAssessmentService:
    def __init__(self, gateway=None) -> None:
        self._gateway = gateway or get_supply_chain_gateway()

    @staticmethod
    def _model() -> Optional[str]:
        return os.environ.get("SUPPLY_CHAIN_CHOKEPOINT_MODEL") or None

    async def assess(self, symbol: str, edges: list) -> ChokepointAssessment:
        if not edges:
            return ChokepointAssessment("insufficient_evidence")

        def _f(e, attr):
            return (e.get(attr) if isinstance(e, dict) else getattr(e, attr, "")) or ""

        blob = "\n".join(
            f'[{_f(e, "evidence_tier")}] {_f(e, "source_name")} --{_f(e, "relationship")}--> '
            f'{_f(e, "target_name")} | "{_f(e, "quote")}" | {_f(e, "source_url")}'
            for e in edges
        )
        try:
            payload = await self._gateway.generate_json(
                system_prompt=_SYSTEM,
                user_prompt=f"Company: {symbol}\n\nSourced relationships:\n{blob}",
                temperature=0.2,
                model=self._model(),
            )
        except LLMAdapterError:
            logger.exception("chokepoint: LLM failed for %s", symbol)
            return ChokepointAssessment("insufficient_evidence")

        return self.derive(payload if isinstance(payload, dict) else {}, edges)

    def derive(self, payload: dict, edges: list) -> ChokepointAssessment:
        """Overall verdict + confidence derived in CODE — never from the model."""
        raw = payload.get("tests")
        by_name = {
            t["test"]: t
            for t in (raw if isinstance(raw, list) else [])
            if isinstance(t, dict) and t.get("test") in _TESTS
        }
        supporting_tier = self._best_tier(edges)
        tests: list[ChokepointTest] = []
        for name in _TESTS:
            t = by_name.get(name, {})
            verdict = (t.get("verdict") or "unknown").strip().lower()
            if verdict not in _VERDICTS:
                verdict = "unknown"
            tests.append(
                ChokepointTest(
                    test=name,
                    verdict=verdict,
                    evidence_tier=supporting_tier,
                    rationale=(t.get("rationale") or "").strip(),
                    source_urls=[u for u in (t.get("source_urls") or []) if isinstance(u, str)],
                )
            )

        unknown = sum(1 for t in tests if t.verdict == "unknown")
        yes = sum(1 for t in tests if t.verdict == "yes")
        partial = sum(1 for t in tests if t.verdict == "partial")

        if unknown >= 3:
            return ChokepointAssessment("insufficient_evidence", tests, None, "insufficient_evidence")

        break_stmt = payload.get("break_statement")
        break_stmt = break_stmt.strip() if isinstance(break_stmt, str) and break_stmt.strip() else None

        if yes >= 3:
            verdict, conf = "chokepoint", ("high" if yes >= 4 else "moderate")
        elif yes + partial >= 3:
            verdict, conf = "adjacent_supplier", "moderate"
        else:
            verdict, conf = "theme_exposure", ("moderate" if (yes + partial) >= 1 else "low")

        return ChokepointAssessment(
            verdict, tests, break_stmt if verdict == "chokepoint" else None, conf
        )

    @staticmethod
    def _best_tier(edges: list) -> str:
        order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
        tiers = [t for t in (_tier_of(e) for e in edges) if t]
        return min(tiers, key=lambda t: order.get(t, 9)) if tiers else "D"
