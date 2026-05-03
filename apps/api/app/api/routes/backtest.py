from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backtest import BacktestRecord
from app.schemas.backtest import BacktestResult, BacktestRunRequest
from app.services.alpha_vantage import AlphaVantageClient
from app.services.backtester.engine import BacktestEngine
from app.services.data_quality_service import DataQualityService
from app.services.symbol_service import SymbolService

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
engine = BacktestEngine()
_symbol_service = SymbolService(AlphaVantageClient())
_quality_service = DataQualityService()


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
    strategy = payload.strategy_json
    universe = [s.upper() for s in strategy.universe]

    # Symbol existence check
    invalid = await _validate_universe(db, universe)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or unsupported ticker(s): {', '.join(invalid)}. "
                   "Please check the symbols and try again.",
        )

    # Data quality gate — runs only on cached data (no extra API calls)
    gate = _quality_service.check_strategy(db, strategy)
    if gate.overall_status == "blocked":
        errors = []
        for sym in gate.blocking_symbols:
            errors.extend(gate.reports[sym].blocking_errors)
        raise HTTPException(
            status_code=400,
            detail=f"Data quality check failed: {'; '.join(errors)}",
        )

    try:
        result = await engine.run(db, strategy)
        # Attach data quality warnings to result
        if gate.overall_status == "warning":
            quality_warnings = []
            for sym in gate.warning_symbols:
                quality_warnings.extend(gate.reports[sym].warnings)
            result.warnings = quality_warnings + result.warnings
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{backtest_id}", response_model=BacktestResult)
async def get_backtest(backtest_id: str, db: Session = Depends(get_db)) -> BacktestResult:
    record = db.scalar(select(BacktestRecord).where(BacktestRecord.id == backtest_id))
    if not record:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return BacktestResult.model_validate(record.result_payload)
