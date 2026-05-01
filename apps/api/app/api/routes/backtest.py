from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backtest import BacktestRecord
from app.schemas.backtest import BacktestResult, BacktestRunRequest
from app.services.backtester.engine import BacktestEngine

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
engine = BacktestEngine()


@router.post("/run", response_model=BacktestResult)
async def run_backtest(payload: BacktestRunRequest, db: Session = Depends(get_db)) -> BacktestResult:
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

