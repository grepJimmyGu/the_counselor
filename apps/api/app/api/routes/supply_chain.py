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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.schemas.supply_chain import (
    ChainGraphResponse,
    EvidenceLedgerRow,
    SupplyChainSummaryResponse,
)
from app.services import supply_chain_service as scs
from app.services.chain_stage_service import ChainStageService
from app.services.fmp_client import FMPClient

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
