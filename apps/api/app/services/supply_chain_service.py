"""Supply-chain summary / graph / evidence assembly (PRD-25/26).

Slice 2 (backend spine): the endpoints exist and return a real STAGE plus an
honest verdict. Until the extraction backend (Slice 3) fills ``supply_chain_edges``
/ ``supply_chain_summaries`` / ``evidence_ledger``:

- financial / real-estate / utilities / comm-services names read
  ``no_chain_structure`` (the lens genuinely doesn't apply — a confident, useful
  answer), with a ``fallback_role``;
- everything else reads ``insufficient_evidence`` — we simply haven't extracted
  yet, which is different from "no structure";
- the graph and evidence ledger are empty.

The full chokepoint verdict + populated graph arrive with extraction.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.supply_chain import (
    ChainEdgeOut,
    ChainGraphResponse,
    ChainNode,
    ChokepointTestResult,
    EvidenceLedgerRow,
    SupplyChainSummaryResponse,
)
from app.services.business_intelligence_service import load_cached_bi
from app.services.value_chain_classifier import get_value_chain_role

logger = logging.getLogger("livermore.supply_chain")

# Sectors whose economics are not driven by a physical input chain. Substring,
# case-insensitive — mirrors the health_score_service financial-sector idiom.
_NO_CHAIN_SECTORS = (
    "financial",  # "Financials" / "Financial Services"
    "bank",
    "insurance",
    "real estate",
    "utilities",
    "communication services",
)

# FMP returns "Financial Services"; value_chain_classifier keys on "Financials".
# Normalize before the fallback-role lookup so it doesn't return None (the P4 bug
# the PRD calls out).
_SECTOR_ALIASES = {
    "financial services": "Financials",
    "banking": "Financials",
    "insurance": "Financials",
}


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def is_no_chain_structure_sector(sector: Optional[str], industry: Optional[str]) -> bool:
    """Rule 1 of the ``no_chain_structure`` decision (deterministic, no LLM).

    Rule 2 — zero admitted Tier A–D edges after extraction — applies once the
    extraction backend has run; here (pre-extraction) only the sector rule fires,
    so a non-financial name with no edges reads ``insufficient_evidence``, not
    ``no_chain_structure``.
    """
    s = _norm(sector)
    if not s:
        return False
    return any(bucket in s for bucket in _NO_CHAIN_SECTORS)


def _fallback_role(sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    alias = _SECTOR_ALIASES.get(_norm(sector))
    return get_value_chain_role(alias or sector, industry)


def build_summary(
    symbol: str,
    sector: Optional[str],
    industry: Optional[str],
    *,
    stage: Optional[str] = None,
    trailing_metrics_meaningful: bool = True,
    stage_figures: Optional[dict] = None,
    summary_row: Optional[dict] = None,
) -> SupplyChainSummaryResponse:
    symbol = symbol.upper()
    stage_figures = stage_figures or {}

    # A persisted summary (Slice 3 extraction) wins.
    if summary_row:
        raw_tests = summary_row.get("tests_json") or "[]"
        try:
            tests = [ChokepointTestResult(**t) for t in json.loads(raw_tests)]
        except (json.JSONDecodeError, TypeError, ValueError):
            tests = []
        return SupplyChainSummaryResponse(
            symbol=symbol,
            verdict=summary_row.get("chokepoint_verdict") or "insufficient_evidence",
            layer=summary_row.get("layer"),
            layer_ambiguous=bool(summary_row.get("layer_ambiguous")),
            vertical=summary_row.get("vertical"),
            stage=summary_row.get("stage") or stage,
            trailing_metrics_meaningful=bool(
                summary_row.get("trailing_metrics_meaningful", True)
            ),
            confidence=summary_row.get("confidence") or "insufficient_evidence",
            break_statement=summary_row.get("break_statement"),
            tests=tests,
            dropped_edge_count=int(summary_row.get("dropped_edge_count") or 0),
            stage_figures=stage_figures,
            computed_at=(
                str(summary_row.get("computed_at"))
                if summary_row.get("computed_at")
                else None
            ),
        )

    # No extraction yet — financials get a confident "doesn't apply here".
    if is_no_chain_structure_sector(sector, industry):
        return SupplyChainSummaryResponse(
            symbol=symbol,
            verdict="no_chain_structure",
            confidence="high",
            fallback_role=_fallback_role(sector, industry) or "Financial Intermediary",
            stage=stage,
            trailing_metrics_meaningful=trailing_metrics_meaningful,
            stage_figures=stage_figures,
            message=(
                "No supply-chain bottleneck structure detected. This company's "
                "economics are not driven by a physical input chain."
            ),
        )

    # Everything else: extraction hasn't run — honest insufficient_evidence, but
    # the STAGE is real (that alone fixes the pre-ramp mis-ranking today).
    return SupplyChainSummaryResponse(
        symbol=symbol,
        verdict="insufficient_evidence",
        confidence="insufficient_evidence",
        stage=stage,
        trailing_metrics_meaningful=trailing_metrics_meaningful,
        stage_figures=stage_figures,
        message="Supply-chain evidence has not been extracted for this company yet.",
    )


def read_sector_industry(
    db: Session, symbol: str
) -> tuple[Optional[str], Optional[str]]:
    row = db.execute(
        text("SELECT sector, industry FROM symbols WHERE symbol = :s"),
        {"s": symbol.upper()},
    ).fetchone()
    if not row:
        return None, None
    m = row._mapping
    return m["sector"], m["industry"]


def read_summary_row(db: Session, symbol: str) -> Optional[dict]:
    row = db.execute(
        text(
            "SELECT symbol, vertical, layer, layer_ambiguous, chokepoint_verdict,"
            " confidence, break_statement, tests_json, stage,"
            " trailing_metrics_meaningful, dropped_edge_count, computed_at"
            " FROM supply_chain_summaries WHERE symbol = :s"
        ),
        {"s": symbol.upper()},
    ).fetchone()
    return dict(row._mapping) if row else None


def _seed_edges_from_bi(
    db: Session, symbol: str, existing_names: set
) -> list[ChainEdgeOut]:
    """Seed the inferred 'map' (Tier D) from the cached business-intelligence
    supplier/customer names.

    Those names are an LLM read of the 10-K — grounded in a primary document but
    NOT verbatim-verified — so they enter as Tier D with an empty quote, distinct
    from the Tier A edges the strict extraction produces. Cache-only: never
    triggers the BI analysis path (no LLM, no network). A counterparty already
    carried by an extracted edge (in ``existing_names``) is skipped, so the
    verbatim-quoted Tier A edge always wins the dedup.
    """
    # The seed is enrichment, never load-bearing: ANY failure degrades to [] so the
    # graph read still returns the extracted edges rather than 500ing.
    try:
        bi = load_cached_bi(symbol, db)
        if not bi:
            return []

        # The DB hands filing_date back as a date object, not a str; ChainEdgeOut
        # requires str fields, so coerce (a bare date here 500'd /graph for every
        # company with a populated BI cache).
        url = str(bi.filing_url or "")
        as_of = str(bi.filing_date or "")
        sym_l = symbol.lower()
        seeded: list[ChainEdgeOut] = []

        def _emit(name, relationship: str, upstream: bool) -> None:
            n = name.strip() if isinstance(name, str) else ""
            nl = n.lower()
            if not n or nl == sym_l or nl in existing_names:
                return
            existing_names.add(nl)
            if upstream:  # supplier -> company
                src_sym, src_name, tgt_sym, tgt_name = None, n, symbol, symbol
            else:  # company -> customer
                src_sym, src_name, tgt_sym, tgt_name = symbol, symbol, None, n
            seeded.append(
                ChainEdgeOut(
                    source_symbol=src_sym,
                    source_name=src_name,
                    target_symbol=tgt_sym,
                    target_name=tgt_name,
                    relationship=relationship,
                    evidence_tier="D",
                    source_url=url,
                    source_doc_type="10-K",
                    quote="",
                    as_of_date=as_of,
                    is_named=True,
                    stale=False,
                )
            )

        for s in bi.upstream_suppliers or []:
            _emit(s, "supplies", upstream=True)
        for c in bi.downstream_customers or []:
            _emit(c, "customer_of", upstream=False)
        return seeded
    except Exception:
        logger.exception("supply-chain seed: failed for %s (non-fatal)", symbol)
        return []


def read_graph(db: Session, symbol: str) -> ChainGraphResponse:
    symbol = symbol.upper()
    rows = db.execute(
        text(
            "SELECT source_symbol, source_name, target_symbol, target_name,"
            " relationship, evidence_tier, source_url, source_doc_type, quote,"
            " as_of_date, is_named, stale FROM supply_chain_edges"
            " WHERE source_symbol = :s OR target_symbol = :s"
        ),
        {"s": symbol},
    ).fetchall()

    edges: list[ChainEdgeOut] = []
    nodes: dict[str, ChainNode] = {}
    existing_names: set = set()

    def _add_node(sym, name) -> None:
        key = sym or name
        if key and key not in nodes:
            nodes[key] = ChainNode(symbol=sym, name=name, is_listed=bool(sym))

    for r in rows:
        m = r._mapping
        edges.append(
            ChainEdgeOut(
                source_symbol=m["source_symbol"],
                source_name=m["source_name"],
                target_symbol=m["target_symbol"],
                target_name=m["target_name"],
                relationship=m["relationship"],
                evidence_tier=m["evidence_tier"],
                source_url=m["source_url"],
                source_doc_type=m["source_doc_type"],
                quote=m["quote"],
                as_of_date=str(m["as_of_date"]),
                is_named=bool(m["is_named"]),
                stale=bool(m["stale"]),
            )
        )
        for sym, name in (
            (m["source_symbol"], m["source_name"]),
            (m["target_symbol"], m["target_name"]),
        ):
            _add_node(sym, name)
            if name:
                existing_names.add(name.strip().lower())

    # Phase 1: seed the inferred map (Tier D) from cached business intelligence,
    # skipping any counterparty already carried by an extracted (Tier A) edge.
    for edge in _seed_edges_from_bi(db, symbol, existing_names):
        edges.append(edge)
        _add_node(edge.source_symbol, edge.source_name)
        _add_node(edge.target_symbol, edge.target_name)

    return ChainGraphResponse(symbol=symbol, nodes=list(nodes.values()), edges=edges)


def read_evidence(db: Session, symbol: str) -> list[EvidenceLedgerRow]:
    rows = db.execute(
        text(
            "SELECT symbol, claim, evidence_tier, source_url, source_doc_type,"
            " quote, as_of_date, falsifier FROM evidence_ledger"
            " WHERE symbol = :s ORDER BY evidence_tier ASC"
        ),
        {"s": symbol.upper()},
    ).fetchall()
    out: list[EvidenceLedgerRow] = []
    for r in rows:
        m = r._mapping
        out.append(
            EvidenceLedgerRow(
                symbol=m["symbol"],
                claim=m["claim"],
                evidence_tier=m["evidence_tier"],
                source_url=m["source_url"],
                source_doc_type=m["source_doc_type"],
                quote=m["quote"],
                as_of_date=str(m["as_of_date"]) if m["as_of_date"] else None,
                falsifier=m["falsifier"],
            )
        )
    return out
