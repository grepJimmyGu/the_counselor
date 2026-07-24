"""Bottleneck-thesis pipeline (Phase 3 / PRD-27) — gated generate + persist + read.

Assembles the ingested evidence (supply-chain graph + chokepoint summary + evidence
ledger + business intelligence + FMP financials), runs the reasoning engine, and
persists the graded thesis. All DB reads happen first and the session is released
BEFORE any FMP / LLM await (trap #13); the persist opens its own session.

GATED OFF by default: `generate_and_persist_thesis` no-ops unless
SUPPLY_CHAIN_THESIS_ENABLED is set — no LLM call, no cost, until the flag flips.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.db.session import SessionLocal
from app.schemas.bottleneck_thesis import BottleneckThesisResponse
from app.services import supply_chain_service as scs
from app.services.bottleneck_thesis_service import BottleneckThesisService
from app.services.business_intelligence_service import load_cached_bi

logger = logging.getLogger("livermore.supply_chain")

_TRUTHY = ("1", "true", "yes", "on")


def thesis_enabled() -> bool:
    """Cost gate. Default OFF — no LLM reasoning call until this is set."""
    return os.environ.get("SUPPLY_CHAIN_THESIS_ENABLED", "").lower() in _TRUTHY


def _default_fmp():
    from app.services.fmp_client import FMPClient

    return FMPClient()


def _first(x):
    if isinstance(x, list):
        return x[0] if x else {}
    return x if isinstance(x, dict) else {}


async def _fetch_financials(fmp, symbol: str) -> tuple[dict, dict]:
    """Returns (fmp_business, financials). Each FMP call is guarded so one failure
    doesn't sink the thesis — the reasoner tolerates missing fields."""

    async def _safe(coro):
        try:
            return await coro
        except Exception:  # noqa: BLE001
            return None

    profile = _first(await _safe(fmp.get_profile(symbol)))
    income = await _safe(fmp.get_income_statement(symbol, limit=2))
    metrics = _first(await _safe(fmp.get_key_metrics(symbol, limit=1)))

    fmp_business = {
        "description": (profile.get("description") or "")[:1000],
        "market_cap": profile.get("mktCap") or profile.get("marketCap"),
    }
    financials = {
        "income_last2": [
            {"date": s.get("date"), "revenue": s.get("revenue"),
             "grossProfit": s.get("grossProfit"),
             "rnd": s.get("researchAndDevelopmentExpenses")}
            for s in (income if isinstance(income, list) else [])[:2]
        ],
        "market_cap": fmp_business["market_cap"],
        "key_metrics": metrics,
    }
    return fmp_business, financials


def _persist_thesis(symbol: str, thesis: BottleneckThesisResponse, session_factory=SessionLocal) -> None:
    now = datetime.utcnow()
    payload = thesis.model_dump_json()
    with session_factory() as db:
        is_sqlite = db.bind.dialect.name == "sqlite"
        db.execute(text("DELETE FROM bottleneck_theses WHERE symbol = :s"), {"s": symbol})
        json_bind = ":tj" if is_sqlite else "CAST(:tj AS jsonb)"
        db.execute(
            text(
                "INSERT INTO bottleneck_theses (symbol, verdict, fit_score, veto,"
                f" band, thesis_json, computed_at) VALUES (:sym, :v, :fit, :veto,"
                f" :band, {json_bind}, :ca)"
            ),
            {
                "sym": symbol, "v": thesis.verdict, "fit": thesis.fit_score,
                "veto": thesis.veto, "band": thesis.band, "tj": payload, "ca": now,
            },
        )
        db.commit()


def read_thesis(db, symbol: str) -> BottleneckThesisResponse:
    row = db.execute(
        text("SELECT thesis_json, computed_at FROM bottleneck_theses WHERE symbol = :s"),
        {"s": symbol.upper()},
    ).fetchone()
    if not row:
        return BottleneckThesisResponse(
            symbol=symbol.upper(),
            message="No bottleneck thesis has been generated for this company yet.",
        )
    m = row._mapping
    raw = m["thesis_json"]
    data = json.loads(raw) if isinstance(raw, str) else raw  # PG jsonb returns a dict
    thesis = BottleneckThesisResponse(**data)
    thesis.computed_at = str(m["computed_at"]) if m["computed_at"] else None
    return thesis


async def generate_and_persist_thesis(
    symbol: str,
    *,
    fmp=None,
    gateway=None,
    session_factory=SessionLocal,
) -> Optional[dict]:
    """Assemble evidence -> reason -> persist. Returns a status dict, or None when
    the thesis engine is disabled. Never raises for a single symbol."""
    if not thesis_enabled():
        logger.info("thesis disabled — skipping %s", symbol)
        return None

    symbol = symbol.upper()
    fmp = fmp or _default_fmp()

    # 1. All DB reads first, then release the session before any await (trap #13).
    with session_factory() as db:
        graph = scs.read_graph(db, symbol)
        summary_row = scs.read_summary_row(db, symbol) or {}
        evidence_rows = scs.read_evidence(db, symbol)
        bi = load_cached_bi(symbol, db)
        sector, industry = scs.read_sector_industry(db, symbol)

    business = {
        "sector": sector, "industry": industry,
        "one_line_summary": getattr(bi, "one_line_summary", None) if bi else None,
        "market_category": getattr(bi, "market_category", None) if bi else None,
        "revenue_model": getattr(bi, "revenue_model", None) if bi else None,
    }
    edges = [
        {"source": e.source_name, "rel": e.relationship, "target": e.target_name,
         "tier": e.evidence_tier, "doc": e.source_doc_type,
         "quote": (e.quote or "")[:200], "date": e.as_of_date}
        for e in graph.edges
    ]
    evidence = [
        {"claim": r.claim, "tier": r.evidence_tier, "source": r.source_doc_type, "date": r.as_of_date}
        for r in evidence_rows
    ]
    try:
        tests = json.loads(summary_row.get("tests_json") or "[]")
    except (TypeError, ValueError):
        tests = []

    # 2. Network (FMP) — no DB session held.
    fmp_business, financials = await _fetch_financials(fmp, symbol)
    business.update({k: v for k, v in fmp_business.items() if v})

    # 3. Reason.
    try:
        thesis = await BottleneckThesisService(gateway=gateway).generate(
            symbol,
            business=business,
            financials=financials,
            stage=summary_row.get("stage"),
            trailing_metrics_meaningful=summary_row.get("trailing_metrics_meaningful"),
            chokepoint_verdict=summary_row.get("chokepoint_verdict"),
            chokepoint_tests=tests,
            edges=edges,
            evidence=evidence,
        )
    except Exception:
        logger.exception("generate_and_persist_thesis: reasoning failed for %s", symbol)
        return {"symbol": symbol, "ok": False}

    # 4. Persist (own session, fully synchronous).
    try:
        _persist_thesis(symbol, thesis, session_factory=session_factory)
    except Exception:
        logger.exception("generate_and_persist_thesis: persist failed for %s", symbol)
        return {"symbol": symbol, "ok": False}

    return {
        "symbol": symbol, "ok": True, "verdict": thesis.verdict,
        "fit_score": thesis.fit_score, "veto": thesis.veto, "band": thesis.band,
    }
