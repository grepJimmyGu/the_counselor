from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backtest import BacktestRecord
from app.schemas.backtest import BacktestResult, BacktestRunRequest
from app.services.alpha_vantage import AlphaVantageClient
from app.services.backtester.engine import BacktestEngine
from app.services.symbol_service import SymbolService

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
engine = BacktestEngine()
_symbol_service = SymbolService(AlphaVantageClient())


async def _validate_universe(db: Session, symbols: list[str]) -> list[str]:
    invalid: list[str] = []
    for symbol in symbols:
        cached = _symbol_service.get_by_symbol(db, symbol)
        if cached:
            continue
        results = await _symbol_service.search(db, symbol)
        exact = next((r for r in results if r.symbol == symbol), None)
        if not exact:
            invalid.append(symbol)
    return invalid


@router.post("/run", response_model=BacktestResult)
async def run_backtest(payload: BacktestRunRequest, db: Session = Depends(get_db)) -> BacktestResult:
    universe = [s.upper() for s in payload.strategy_json.universe]
    invalid = await _validate_universe(db, universe)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or unsupported ticker(s): {', '.join(invalid)}. "
                   "Please check the symbols and try again.",
        )
    try:
        return await engine.run(db, payload.strategy_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{backtest_id}", response_model=BacktestResult)
async def get_backtest(backtest_id: str, db: Session = Depends(get_db)) -> BacktestResult:
    record = db.scalar(select(BacktestRecord).where(BacktestRecord.id == backtest_id))
    if not record:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return BacktestResult.model_validate(record.result_payload)
