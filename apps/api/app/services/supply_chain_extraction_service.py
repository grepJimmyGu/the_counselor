"""Evidence-gated supply-chain edge extraction (PRD-25, Slice 3).

Pull a company's latest 10-K, ask an LLM to surface customer/supplier
relationships, and admit ONLY edges whose quote verifies VERBATIM against the
full filing text. Tiers are assigned in CODE from the source type — never taken
from the model. Uncited / unverifiable edges are dropped and counted; a high
drop rate is a signal the model is confabulating, and we surface it, not hide it.

Gated OFF by default (see supply_chain_pipeline.extraction_enabled) — no LLM call
happens until SUPPLY_CHAIN_EXTRACTION_ENABLED is set, so deploying this costs $0.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.services.fmp_client import FMPClient
from app.services.filing_section_parser import _html_to_text, parse_10k_sections
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway
from app.services.sec_edgar_client import fetch_filing_html

logger = logging.getLogger("livermore.supply_chain")

# Source types that can carry a Tier A relationship (primary disclosure).
_FILING_DOC_TYPES = {"10-k", "10-q", "20-f", "8-k", "s-1", "annual report", "transcript"}
_RELATIONSHIPS = {"supplies", "customer_of", "partners_with", "competes_with"}


@dataclass
class ExtractedEdge:
    source_symbol: Optional[str]
    source_name: str
    target_symbol: Optional[str]
    target_name: str
    relationship: str
    evidence_tier: str
    source_url: str
    source_doc_type: str
    quote: str
    as_of_date: str
    is_named: bool


@dataclass
class ExtractionResult:
    edges: list[ExtractedEdge] = field(default_factory=list)
    dropped_edge_count: int = 0
    source_url: Optional[str] = None
    as_of_date: Optional[str] = None


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def assign_tier(is_named: bool, source_doc_type: str) -> str:
    """Tier by SOURCE TYPE, never from the model (the anti-laundering rule).

    A named relationship in a primary filing is Tier A; a named one from a
    weaker source is C; an inferred (not-named) relationship is at best D.
    """
    doc = (source_doc_type or "").strip().lower()
    if not is_named:
        return "D"
    if doc in _FILING_DOC_TYPES:
        return "A"
    return "C"


_EXTRACTION_SYSTEM = (
    "You map supply-chain relationships from SEC filings. You output STRUCTURE, "
    "never an opinion on the stock. For each customer or supplier relationship the "
    "filing explicitly states, return the counterparty, the relationship direction "
    "from the FILING COMPANY's perspective, and a VERBATIM quote (30-400 chars) "
    "copied exactly from the text that supports it. If the filing does not name a "
    "specific counterparty, do NOT invent one. Never assign an evidence tier — that "
    "is computed downstream. Return JSON: "
    '{"edges": [{"counterparty_name": string, "counterparty_symbol": string|null, '
    '"relationship": "supplies"|"customer_of"|"partners_with"|"competes_with", '
    '"quote": string, "is_named": boolean}]}. '
    'relationship="supplies" means the counterparty supplies the filing company. '
    "An empty list is a valid, expected answer — never pad it."
)


class SupplyChainExtractionService:
    """Fetches a filing and returns evidence-gated edges. Holds no DB session.

    The FMP client and the LLM gateway are injectable so the gate + admission
    logic can be unit-tested with a fake gateway and no network / no cost.
    """

    def __init__(self, fmp_client: Optional[FMPClient] = None, gateway=None) -> None:
        self._fmp = fmp_client or FMPClient()
        self._gateway = gateway or get_llm_gateway()

    @staticmethod
    def _model() -> Optional[str]:
        # Configured at enable-time; None falls back to the gateway's default.
        return os.environ.get("SUPPLY_CHAIN_EXTRACT_MODEL") or None

    async def extract(self, symbol: str) -> ExtractionResult:
        symbol = symbol.upper()
        try:
            filings = await self._fmp.get_sec_filings(symbol, "10-K", 1)
        except Exception:
            logger.exception("extraction: get_sec_filings failed for %s", symbol)
            return ExtractionResult()
        if not filings:
            return ExtractionResult()

        first = filings[0]
        url = first.get("finalLink") or first.get("link")
        as_of = str(
            first.get("fillingDate") or first.get("acceptedDate") or first.get("date") or date.today().isoformat()
        )[:10]
        if not url:
            return ExtractionResult(as_of_date=as_of)

        try:
            html = await fetch_filing_html(url)
        except Exception:
            logger.exception("extraction: fetch_filing_html failed for %s", symbol)
            return ExtractionResult(source_url=url, as_of_date=as_of)

        sections = parse_10k_sections(html)
        if not sections.has_content():
            return ExtractionResult(source_url=url, as_of_date=as_of)

        # Prompt from the (truncated) sections; verify quotes against the FULL text
        # so a legitimate quote past the 12k section boundary isn't wrongly dropped.
        full_text = _norm_ws(_html_to_text(html))
        prompt_text = sections.combined_for_llm()

        try:
            payload = await self._gateway.generate_json(
                system_prompt=_EXTRACTION_SYSTEM,
                user_prompt=f"Filing company: {symbol}\n\nFiling excerpts:\n{prompt_text}",
                temperature=0.1,
                model=self._model(),
            )
        except LLMAdapterError:
            logger.exception("extraction: LLM failed for %s", symbol)
            return ExtractionResult(source_url=url, as_of_date=as_of)

        raw = payload.get("edges") if isinstance(payload, dict) else None
        return self.admit(symbol, raw or [], full_text, url, as_of)

    def admit(
        self,
        symbol: str,
        raw_edges: list,
        full_text_normalized: str,
        source_url: str,
        as_of: str,
    ) -> ExtractionResult:
        """The evidence gate. Pure — unit-tested directly with fake LLM output."""
        result = ExtractionResult(source_url=source_url, as_of_date=as_of)
        for e in raw_edges:
            if not isinstance(e, dict):
                result.dropped_edge_count += 1
                continue
            name = (e.get("counterparty_name") or "").strip()
            quote = (e.get("quote") or "").strip()
            rel = (e.get("relationship") or "").strip().lower()
            is_named = bool(e.get("is_named"))

            # Required fields (source_url, quote, as_of are all mandatory).
            if not name or not quote or not source_url or not as_of or rel not in _RELATIONSHIPS:
                result.dropped_edge_count += 1
                continue
            # Anti-hallucination gate: the quote must appear verbatim in the full
            # filing text (whitespace-normalized). This is not optional.
            if _norm_ws(quote) not in full_text_normalized:
                result.dropped_edge_count += 1
                continue

            tier = assign_tier(is_named, "10-K")
            cp_sym = e.get("counterparty_symbol")
            cp_sym = cp_sym.upper() if isinstance(cp_sym, str) and cp_sym.strip() else None

            if rel == "supplies":
                # counterparty → filing company
                src_name, src_sym, tgt_name, tgt_sym = name, cp_sym, symbol, symbol
            else:
                # filing company → counterparty (customer_of / partners_with / competes_with)
                src_name, src_sym, tgt_name, tgt_sym = symbol, symbol, name, cp_sym

            result.edges.append(
                ExtractedEdge(
                    source_symbol=src_sym,
                    source_name=src_name,
                    target_symbol=tgt_sym,
                    target_name=tgt_name,
                    relationship=rel,
                    evidence_tier=tier,
                    source_url=source_url,
                    source_doc_type="10-K",
                    quote=quote[:400],
                    as_of_date=as_of,
                    is_named=is_named,
                )
            )
        return result
