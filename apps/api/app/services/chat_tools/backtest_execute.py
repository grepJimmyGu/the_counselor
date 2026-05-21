"""backtest_execute chat tool — run a backtest from chat.

Wraps the existing backtester pipeline (pre-flight + engine) and returns a
compact summary tuned for the LLM to weave into a chat response. The full
`BacktestResult` is too verbose for the chat context window; this tool
keeps only the headline metrics + the backtest_id so a follow-up turn can
fetch the full result via `backtest_explain`.

Stage 3 caps (universe, history, runs/week) are NOT enforced here — that
is the chat endpoint's job in ticket #5. This tool's contract is: "given
a valid strategy and an authorized request, run the backtest." If the
caller skips entitlement checks, the tool will happily run a 100-symbol
20-year backtest from a Scout user — by design, since the chat endpoint
owns auth.

Pre-flight is done in-tool (`validate_universe`, `ensure_data_available`,
`DataQualityService`). This mirrors what `/api/backtest/run` does so the
tool is self-sufficient — the chat endpoint just calls dispatch and
catches exceptions.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.db.session import SessionLocal
from app.schemas.strategy import StrategyJSON
from app.services.backtest_preflight import ensure_data_available, validate_universe
from app.services.backtester.engine import BacktestEngine
from app.services.data_quality_service import DataQualityService


class BacktestExecuteResponse(BaseModel):
    """Headline summary for the LLM. Full result is at `/api/backtest/{id}`.

    On failure, `error` is populated and other fields are None. The chat
    endpoint can decide whether to surface the error to the user verbatim
    or have the LLM phrase it.
    """

    success: bool
    backtest_id: Optional[str] = None
    strategy_name: Optional[str] = None
    total_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    n_trades: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    benchmark: Optional[str] = None
    benchmark_total_return: Optional[float] = None
    warnings: List[str] = []
    error: Optional[str] = None


async def execute_backtest(strategy_json: dict) -> BacktestExecuteResponse:
    """Run a backtest end-to-end. Returns a summary or an error payload.

    Errors are CAUGHT and returned in the response — the chat endpoint
    can choose to surface them as tool errors to the LLM rather than
    crashing the conversation. The endpoint owns retry / reprompt logic.

    Steps mirror `/api/backtest/run`:
      1. Validate strategy JSON shape
      2. Validate ticker existence
      3. Auto-fetch any missing price data
      4. Data quality gate
      5. engine.run
      6. Summarize
    """
    db = SessionLocal()
    try:
        try:
            strategy = StrategyJSON.model_validate(strategy_json)
        except Exception as exc:
            return BacktestExecuteResponse(
                success=False,
                error=f"Invalid strategy JSON: {exc}",
            )

        universe = [s.upper() for s in strategy.universe]
        all_symbols = universe + [strategy.benchmark]

        invalid = await validate_universe(db, universe)
        if invalid:
            return BacktestExecuteResponse(
                success=False,
                error=(
                    f"Unknown or unsupported ticker(s): {', '.join(invalid)}. "
                    "Check the symbols and try again."
                ),
            )

        required_from = strategy.start_date - timedelta(days=400)
        fetch_errors = await ensure_data_available(db, all_symbols, required_from)
        if fetch_errors:
            msgs = "; ".join(f"{sym}: {err}" for sym, err in fetch_errors.items())
            return BacktestExecuteResponse(
                success=False,
                error=f"Could not retrieve price data: {msgs}",
            )

        quality_service = DataQualityService()
        gate = quality_service.check_strategy(db, strategy)
        if gate.overall_status == "blocked":
            errors: List[str] = []
            for sym in gate.blocking_symbols:
                errors.extend(gate.reports[sym].blocking_errors)
            return BacktestExecuteResponse(success=False, error="; ".join(errors))

        engine = BacktestEngine()
        try:
            result = await engine.run(db, strategy)
        except Exception as exc:
            return BacktestExecuteResponse(
                success=False,
                error=f"Backtest engine failed: {exc}",
            )

        # Roll up quality-gate warnings into the response so the LLM can mention them
        warnings: List[str] = list(result.warnings or [])
        if gate.overall_status == "warning":
            for sym in gate.warning_symbols:
                warnings.extend(gate.reports[sym].warnings)

        return BacktestExecuteResponse(
            success=True,
            backtest_id=result.backtest_id,
            strategy_name=strategy.strategy_name,
            total_return=result.metrics.total_return,
            sharpe_ratio=result.metrics.sharpe_ratio,
            max_drawdown=result.metrics.max_drawdown,
            n_trades=result.metrics.number_of_trades,
            start_date=strategy.start_date.isoformat(),
            end_date=strategy.end_date.isoformat(),
            benchmark=strategy.benchmark,
            benchmark_total_return=result.metrics.benchmark_total_return,
            warnings=warnings,
        )
    finally:
        db.close()


BACKTEST_EXECUTE_DEF: Dict[str, Any] = {
    "name": "backtest_execute",
    "description": (
        "Run a backtest of a fully-specified strategy and return headline "
        "metrics. Use after `strategy_builder_iterate` has produced a "
        "complete strategy JSON and the user explicitly confirms they "
        "want to see the result. Returns total_return, sharpe_ratio, "
        "max_drawdown, n_trades, plus a backtest_id the user can ask "
        "you to explain or run robustness on. Tier caps (universe size, "
        "history window, weekly run quota) are enforced by the chat "
        "endpoint before this tool runs — if you see this tool fail with "
        "a quota error, the user needs to upgrade or wait."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "strategy_json": {
                "type": "object",
                "description": (
                    "The full strategy JSON object from "
                    "`strategy_builder_iterate`. Pass it through verbatim — "
                    "do not edit fields here."
                ),
            },
        },
        "required": ["strategy_json"],
        "additionalProperties": False,
    },
    "handler": execute_backtest,
}
