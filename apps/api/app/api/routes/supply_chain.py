"""Supply-chain lens endpoints (PRD-25/26), mounted at ``/api/supply-chain``.

  GET /{symbol}/summary   — verdict, layer, stage, evidence mix
  GET /{symbol}/graph     — nodes + edges with evidence
  GET /{symbol}/evidence  — the claim ledger

Pure read endpoints over public company data — no auth gate (matches the company
overview + asset-behavior read pattern). The summary path fetches FMP
fundamentals for the stage classifier; it reads sector/industry + any persisted
summary from the DB FIRST, releases the session, THEN awaits FMP — so the network
call never pins a pooled connection (trap #13).
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.schemas.bottleneck_thesis import BottleneckThesisResponse
from app.schemas.supply_chain import (
    ChainGraphResponse,
    EvidenceLedgerRow,
    SupplyChainSummaryResponse,
)
from app.services import supply_chain_service as scs
from app.services.chain_stage_service import ChainStageService
from app.services.fmp_client import FMPClient
from app.services.supply_chain_pipeline import extract_and_persist, extraction_enabled
from app.services.thesis_pipeline import (
    generate_and_persist_thesis,
    read_thesis,
    thesis_enabled,
)

router = APIRouter(prefix="/api/supply-chain", tags=["supply-chain"])

_stage_service = ChainStageService(FMPClient())


@router.get("/{symbol}/summary", response_model=SupplyChainSummaryResponse)
async def get_summary(symbol: str) -> SupplyChainSummaryResponse:
    symbol = symbol.upper()

    # Fast DB reads first, then release the session before any FMP await (trap #13).
    with SessionLocal() as db:
        sector, industry = scs.read_sector_industry(db, symbol)
        summary_row = scs.read_summary_row(db, symbol)

    # A persisted extraction summary already carries the stage — no FMP needed.
    if summary_row is not None:
        return scs.build_summary(symbol, sector, industry, summary_row=summary_row)

    # Financials: confident "doesn't apply here" without an FMP round-trip.
    if scs.is_no_chain_structure_sector(sector, industry):
        return scs.build_summary(symbol, sector, industry)

    # Everything else: the stage is real today (fixes the pre-ramp mis-ranking);
    # the verdict stays insufficient_evidence until extraction lands.
    stage = await _stage_service.get_stage(symbol)
    return scs.build_summary(
        symbol,
        sector,
        industry,
        stage=stage.stage,
        trailing_metrics_meaningful=stage.trailing_metrics_meaningful,
        stage_figures=stage.figures,
    )


@router.get("/{symbol}/graph", response_model=ChainGraphResponse)
def get_graph(symbol: str, db: Session = Depends(get_db)) -> ChainGraphResponse:
    return scs.read_graph(db, symbol)


@router.get("/{symbol}/evidence", response_model=list[EvidenceLedgerRow])
def get_evidence(
    symbol: str, db: Session = Depends(get_db)
) -> list[EvidenceLedgerRow]:
    return scs.read_evidence(db, symbol)


# On-demand extraction refresh. Gated (503 when extraction is disabled) and
# rate-limited to 1/hour/symbol so it can't be used to burn LLM cost.
_last_refresh: dict[str, float] = {}
_REFRESH_COOLDOWN_S = 3600.0


@router.post("/{symbol}/refresh")
async def refresh_supply_chain(symbol: str) -> dict:
    symbol = symbol.upper()
    if not extraction_enabled():
        raise HTTPException(status_code=503, detail="Supply-chain extraction is not enabled.")
    now = time.time()
    if now - _last_refresh.get(symbol, 0.0) < _REFRESH_COOLDOWN_S:
        raise HTTPException(
            status_code=429, detail="Refresh is rate-limited to once per hour per symbol."
        )
    _last_refresh[symbol] = now
    result = await extract_and_persist(symbol)
    return result or {"symbol": symbol, "ok": False, "detail": "extraction disabled"}


# ── Phase 3: bottleneck thesis (reasoning engine) ────────────────────────────
@router.get("/{symbol}/thesis", response_model=BottleneckThesisResponse)
def get_thesis(symbol: str, db: Session = Depends(get_db)) -> BottleneckThesisResponse:
    """Un-gated read of the persisted graded thesis (or an honest 'not generated
    yet' message). The thesis is authored by the gated refresh below."""
    return read_thesis(db, symbol)


# On-demand thesis generation. Gated (503 when the thesis engine is off) and
# rate-limited to 1/hour/symbol — reasoning is the most expensive LLM call.
_last_thesis: dict[str, float] = {}


@router.post("/{symbol}/thesis/refresh")
async def refresh_thesis(symbol: str) -> dict:
    symbol = symbol.upper()
    if not thesis_enabled():
        raise HTTPException(status_code=503, detail="Bottleneck thesis engine is not enabled.")
    now = time.time()
    if now - _last_thesis.get(symbol, 0.0) < _REFRESH_COOLDOWN_S:
        raise HTTPException(
            status_code=429, detail="Thesis refresh is rate-limited to once per hour per symbol."
        )
    _last_thesis[symbol] = now
    result = await generate_and_persist_thesis(symbol)
    return result or {"symbol": symbol, "ok": False, "detail": "thesis engine disabled"}
