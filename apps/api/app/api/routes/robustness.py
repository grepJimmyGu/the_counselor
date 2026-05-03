from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.robustness_job import RobustnessJob
from app.schemas.robustness import (
    RobustnessJobResponse,
    RobustnessResults,
    RobustnessRunRequest,
)
from app.schemas.strategy import StrategyJSON
from app.services.robustness_service import robustness_service

router = APIRouter(prefix="/api/robustness", tags=["robustness"])


async def _execute_job(job_id: str, request: RobustnessRunRequest) -> None:
    """Background task: runs all requested robustness tests and saves results."""
    with SessionLocal() as db:
        job = db.get(RobustnessJob, job_id)
        if not job:
            return
        job.status = "running"
        db.commit()

        strategy = request.strategy_json
        tests = set(request.tests_to_run)
        results = RobustnessResults()
        warnings: list[str] = []

        try:
            # Run a quick baseline backtest to get sharpe/return for comparisons
            from app.services.backtester.engine import BacktestEngine
            baseline = await BacktestEngine().run(db, strategy)
            baseline_sharpe = baseline.metrics.sharpe_ratio
            baseline_return = baseline.metrics.total_return

            if "parameter_sensitivity" in tests:
                results.parameter_sensitivity = await robustness_service.run_parameter_sensitivity(
                    db, strategy, request.parameter_grid, baseline_sharpe
                )

            if "subperiod" in tests:
                results.subperiod = await robustness_service.run_subperiod(db, strategy)

            if "transaction_cost" in tests:
                results.transaction_cost = await robustness_service.run_transaction_cost(
                    db, strategy, baseline_return
                )

            if "benchmark_comparison" in tests:
                results.benchmark_comparison = await robustness_service.run_benchmark_comparison(
                    db, strategy, baseline_sharpe
                )

            if "peer_ticker" in tests:
                results.peer_ticker = await robustness_service.run_peer_ticker(
                    db, strategy, request.peer_tickers
                )

            results.warnings = warnings
            results.summary = _summarise(results, baseline_sharpe)

            job.status = "completed"
            job.results = results.model_dump(mode="json")
            job.completed_at = datetime.utcnow()
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.completed_at = datetime.utcnow()
        finally:
            db.commit()


def _summarise(results: RobustnessResults, baseline_sharpe: float) -> str:
    concerns: list[str] = []

    if results.parameter_sensitivity:
        worse = sum(1 for r in results.parameter_sensitivity if r.verdict == "worse")
        total = len(results.parameter_sensitivity)
        if worse / total > 0.5:
            concerns.append(f"{worse}/{total} parameter variants underperform — strategy is parameter-sensitive")

    if results.subperiod:
        weak = [r for r in results.subperiod if r.verdict in ("weak", "insufficient_data") and r.period != "Full Period"]
        if weak:
            concerns.append(f"Weak sub-periods: {', '.join(r.period for r in weak)}")

    if results.transaction_cost:
        breaks = [r for r in results.transaction_cost if r.verdict == "breaks_down"]
        if breaks:
            concerns.append(f"Strategy breaks down at {breaks[0].cost_bps} bps cost")

    if not concerns:
        return "No major robustness concerns detected. Continue with standard caution."
    return "Robustness concerns: " + "; ".join(concerns) + "."


@router.post("/run", response_model=RobustnessJobResponse, status_code=202)
async def run_robustness(
    payload: RobustnessRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> RobustnessJobResponse:
    job_id = str(uuid4())
    now = datetime.utcnow()
    job = RobustnessJob(
        id=job_id,
        status="pending",
        strategy_payload=payload.strategy_json.model_dump(mode="json"),
        tests_requested=payload.tests_to_run,
        peer_tickers=payload.peer_tickers or [],
        parameter_grid=payload.parameter_grid,
        created_at=now,
    )
    db.add(job)
    db.commit()

    background_tasks.add_task(_execute_job, job_id, payload)

    return RobustnessJobResponse(
        run_id=job_id,
        status="pending",
        created_at=now,
    )


@router.get("/{run_id}", response_model=RobustnessJobResponse)
async def get_robustness_job(
    run_id: str,
    db: Session = Depends(get_db),
) -> RobustnessJobResponse:
    job = db.get(RobustnessJob, run_id)
    if not job:
        raise HTTPException(status_code=404, detail="Robustness job not found")

    results = None
    if job.results:
        results = RobustnessResults.model_validate(job.results)

    return RobustnessJobResponse(
        run_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        results=results,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
