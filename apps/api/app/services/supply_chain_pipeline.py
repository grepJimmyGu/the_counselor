"""Supply-chain extraction pipeline (PRD-25, Slice 3) — orchestrator + persist.

`extract_and_persist(symbol)` runs the whole cold path: extraction -> chokepoint
-> stage, then persists edges + the evidence ledger + the summary row that the
Slice-2 read endpoints already consume. The async LLM/FMP work runs first with NO
DB session held; the persist opens its own session and is fully synchronous
(trap #13).

GATED OFF by default: `extract_and_persist` no-ops unless
`SUPPLY_CHAIN_EXTRACTION_ENABLED` is set — so nothing calls an LLM (and nothing
costs money) until that flag is flipped. Same self-gating convention as the
screener snapshot cron.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.chain_stage_service import ChainStageService
from app.services.chokepoint_assessment_service import (
    ChokepointAssessment,
    ChokepointAssessmentService,
)
from app.services.supply_chain_extraction_service import (
    ExtractionResult,
    SupplyChainExtractionService,
)

logger = logging.getLogger("livermore.supply_chain")

_TRUTHY = ("1", "true", "yes", "on")


def extraction_enabled() -> bool:
    """Cost gate. Default OFF — no LLM call until this is set."""
    return os.environ.get("SUPPLY_CHAIN_EXTRACTION_ENABLED", "").lower() in _TRUTHY


def _persist(
    symbol: str,
    extraction: ExtractionResult,
    assessment: ChokepointAssessment,
    stage: str,
    trailing_metrics_meaningful: bool,
    session_factory=SessionLocal,
) -> None:
    """Synchronous persist in its own session (no async awaits inside)."""
    now = datetime.utcnow()
    tests_payload = json.dumps(
        [
            {
                "test": t.test,
                "verdict": t.verdict,
                "evidence_tier": t.evidence_tier,
                "rationale": t.rationale,
                "source_urls": t.source_urls,
            }
            for t in assessment.tests
        ]
    )
    with session_factory() as db:
        is_sqlite = db.bind.dialect.name == "sqlite"

        db.execute(
            text("DELETE FROM supply_chain_edges WHERE source_symbol = :s OR target_symbol = :s"),
            {"s": symbol},
        )
        for e in extraction.edges:
            db.execute(
                text(
                    "INSERT INTO supply_chain_edges (source_symbol, source_name,"
                    " target_symbol, target_name, relationship, evidence_tier,"
                    " source_url, source_doc_type, quote, as_of_date, is_named,"
                    " stale, extracted_at) VALUES (:ss,:sn,:ts,:tn,:rel,:tier,:url,"
                    ":dt,:q,:d,:named,:stale,:ext)"
                ),
                {
                    "ss": e.source_symbol, "sn": e.source_name,
                    "ts": e.target_symbol, "tn": e.target_name,
                    "rel": e.relationship, "tier": e.evidence_tier,
                    "url": e.source_url, "dt": e.source_doc_type, "q": e.quote,
                    "d": e.as_of_date, "named": e.is_named, "stale": False,
                    "ext": now,
                },
            )

        db.execute(text("DELETE FROM evidence_ledger WHERE symbol = :s"), {"s": symbol})
        for e in extraction.edges:
            db.execute(
                text(
                    "INSERT INTO evidence_ledger (symbol, claim, evidence_tier,"
                    " source_url, source_doc_type, quote, as_of_date, falsifier,"
                    " created_at) VALUES (:s,:c,:tier,:url,:dt,:q,:d,:f,:ca)"
                ),
                {
                    "s": symbol,
                    "c": f"{e.source_name} {e.relationship.replace('_', ' ')} {e.target_name}",
                    "tier": e.evidence_tier, "url": e.source_url,
                    "dt": e.source_doc_type, "q": e.quote, "d": e.as_of_date,
                    "f": None, "ca": now,
                },
            )

        db.execute(text("DELETE FROM supply_chain_summaries WHERE symbol = :s"), {"s": symbol})
        tests_bind = ":tests_json" if is_sqlite else "CAST(:tests_json AS jsonb)"
        db.execute(
            text(
                "INSERT INTO supply_chain_summaries (symbol, vertical, layer,"
                " layer_ambiguous, chokepoint_verdict, confidence, break_statement,"
                f" tests_json, stage, trailing_metrics_meaningful, dropped_edge_count,"
                f" computed_at) VALUES (:sym, NULL, NULL, :amb, :verdict, :conf,"
                f" :brk, {tests_bind}, :stage, :tmm, :dropped, :ca)"
            ),
            {
                "sym": symbol, "amb": False, "verdict": assessment.verdict,
                "conf": assessment.confidence, "brk": assessment.break_statement,
                "tests_json": tests_payload, "stage": stage,
                "tmm": trailing_metrics_meaningful,
                "dropped": extraction.dropped_edge_count, "ca": now,
            },
        )
        db.commit()


async def extract_and_persist(
    symbol: str,
    *,
    fmp=None,
    gateway=None,
    session_factory=SessionLocal,
) -> Optional[dict]:
    """Run the cold path for one symbol and persist. Returns a small status dict,
    or None when extraction is disabled. Never raises for a single symbol — logs
    and returns a status so a batch warm can continue.
    """
    if not extraction_enabled():
        logger.info("supply-chain extraction disabled — skipping %s", symbol)
        return None

    symbol = symbol.upper()
    try:
        extraction = await SupplyChainExtractionService(fmp_client=fmp, gateway=gateway).extract(symbol)
        assessment = await ChokepointAssessmentService(gateway=gateway).assess(symbol, extraction.edges)
        stage_result = await ChainStageService(fmp or _default_fmp()).get_stage(symbol)
    except Exception:
        logger.exception("extract_and_persist: cold path failed for %s", symbol)
        return {"symbol": symbol, "ok": False}

    try:
        _persist(
            symbol,
            extraction,
            assessment,
            stage_result.stage,
            stage_result.trailing_metrics_meaningful,
            session_factory=session_factory,
        )
    except Exception:
        logger.exception("extract_and_persist: persist failed for %s", symbol)
        return {"symbol": symbol, "ok": False}

    return {
        "symbol": symbol,
        "ok": True,
        "verdict": assessment.verdict,
        "edges": len(extraction.edges),
        "dropped": extraction.dropped_edge_count,
    }


def _default_fmp():
    from app.services.fmp_client import FMPClient

    return FMPClient()
