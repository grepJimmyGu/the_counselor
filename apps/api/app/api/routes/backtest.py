import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from app.api.entitlement_errors import upgrade_error
from app.core.config import get_settings
from app.db.session import get_db
from app.models.backtest import BacktestRecord
from app.schemas.backtest import BacktestResult, BacktestRunRequest
from app.schemas.identity import Entitlements
from app.services.alpha_vantage import AlphaVantageClient
from app.services.backtester.engine import BacktestEngine
from app.services.data_quality_service import DataQualityService
from app.services.entitlements import increment_custom_backtest, increment_template_backtest
from app.services.price_cache_service import PriceCacheService
from app.services.symbol_service import SymbolService

_log = logging.getLogger("livermore.gating")

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
engine = BacktestEngine()
_symbol_service = SymbolService(AlphaVantageClient())
_quality_service = DataQualityService()
_cache_svc = PriceCacheService(AlphaVantageClient())


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


def _credibility_warnings(result: BacktestResult) -> list[str]:
    """Flag backtest metrics that are suspiciously outside reasonable ranges."""
    warnings: list[str] = []
    m = result.metrics
    days = (result.strategy_json.end_date - result.strategy_json.start_date).days

    if m.sharpe_ratio > 2.0:
        warnings.append(
            f"Sharpe ratio of {m.sharpe_ratio:.2f} is unusually high (> 2.0). "
            "Verify there is no look-ahead bias or data error before trusting this result."
        )
    if m.win_rate > 0.80 and m.number_of_trades >= 10:
        warnings.append(
            f"Win rate of {m.win_rate:.0%} is unusually high (> 80%). "
            "Check for overfitting or survivorship bias."
        )
    if m.total_return > 1.0 and days < 365:
        warnings.append(
            f"Total return of {m.total_return:.0%} over a {days}-day window is unusually high. "
            "Short windows with large returns are typically not reproducible."
        )
    return warnings


async def _ensure_data_available(db: Session, symbols: list[str], required_from: date) -> dict[str, str]:
    """
    For any symbol with no cached data, attempt a fetch before the quality gate runs.
    Returns a dict of symbol → error message for symbols that couldn't be fetched.
    """
    fetch_errors: dict[str, str] = {}
    for symbol in symbols:
        if _cache_svc.get_bar_count(db, symbol) == 0:
            try:
                await _cache_svc.ensure_history(db, symbol, required_from)
            except Exception as exc:
                fetch_errors[symbol] = str(exc)
    return fetch_errors


@router.post("/run", response_model=BacktestResult)
async def run_backtest(
    payload: BacktestRunRequest,
    auth: tuple = Depends(require_entitlement(
        needs_run_quota=True,
        template_id_field="template_id",
        # universe + history are nested in strategy_json — checked inline below
    )),
    db: Session = Depends(get_db),
) -> BacktestResult:
    user, ent = auth
    strategy = payload.strategy_json
    is_template = bool(payload.template_id)

    # Stage 3: custom-strategy universe + history caps (templates exempt).
    # Inline checks (not in the dep) because the values are nested inside strategy_json.
    if not is_template:
        _enforce_custom_caps(strategy, ent, user_id=user.id)

    universe = [s.upper() for s in strategy.universe]
    all_symbols = universe + [strategy.benchmark]

    # 1. Symbol existence check
    invalid = await _validate_universe(db, universe)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or unsupported ticker(s): {', '.join(invalid)}. "
                   "Please check the symbols and try again.",
        )

    # 2. Auto-fetch any symbols with no cached data before the quality gate
    required_from = strategy.start_date - timedelta(days=400)
    fetch_errors = await _ensure_data_available(db, all_symbols, required_from)
    if fetch_errors:
        msgs = "; ".join(f"{sym}: {err}" for sym, err in fetch_errors.items())
        raise HTTPException(
            status_code=400,
            detail=f"Could not retrieve price data: {msgs}",
        )

    # 3. Data quality gate — now runs on populated cache
    gate = _quality_service.check_strategy(db, strategy)
    if gate.overall_status == "blocked":
        errors = []
        for sym in gate.blocking_symbols:
            errors.extend(gate.reports[sym].blocking_errors)
        raise HTTPException(status_code=400, detail="; ".join(errors))

    try:
        result = await engine.run(db, strategy)
        if gate.overall_status == "warning":
            quality_warnings = []
            for sym in gate.warning_symbols:
                quality_warnings.extend(gate.reports[sym].warnings)
            result.warnings = quality_warnings + result.warnings
        result.warnings = _credibility_warnings(result) + result.warnings

        # Stage 3: stamp the run on the BacktestRecord + bump the weekly counter.
        bt = db.get(BacktestRecord, result.backtest_id)
        if bt is not None:
            bt.user_id = user.id
            db.commit()
        if is_template:
            increment_template_backtest(db, user.id)
        else:
            increment_custom_backtest(db, user.id)

        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _enforce_custom_caps(strategy, ent: Entitlements, *, user_id: str) -> None:
    """Stage 3: custom-strategy universe + history validators. Templates exempt
    (caller checks template_id before calling this). Either raises 402 or emits
    a shadow-mode log line depending on settings.gating_enabled."""
    settings = get_settings()
    universe_len = len(strategy.universe)
    if universe_len > ent.universe_size_max_custom:
        if settings.gating_enabled:
            raise upgrade_error(
                "universe_too_large",
                current_tier=ent.tier,
                current_value=str(universe_len),
                limit_value=str(ent.universe_size_max_custom),
            )
        _log.info(
            "gate_event code=universe_too_large tier=%s user_id=%s path=/api/backtest/run current=%s limit=%s shadow=true",
            ent.tier, user_id, universe_len, ent.universe_size_max_custom,
        )

    history_years = (strategy.end_date - strategy.start_date).days / 365.25
    if history_years > ent.history_window_years_custom:
        if settings.gating_enabled:
            raise upgrade_error(
                "history_too_long",
                current_tier=ent.tier,
                current_value=f"{history_years:.1f} yr",
                limit_value=f"{ent.history_window_years_custom} yr",
            )
        _log.info(
            "gate_event code=history_too_long tier=%s user_id=%s path=/api/backtest/run current=%.1f yr limit=%s yr shadow=true",
            ent.tier, user_id, history_years, ent.history_window_years_custom,
        )


@router.get("/{backtest_id}", response_model=BacktestResult)
async def get_backtest(backtest_id: str, db: Session = Depends(get_db)) -> BacktestResult:
    record = db.scalar(select(BacktestRecord).where(BacktestRecord.id == backtest_id))
    if not record:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return BacktestResult.model_validate(record.result_payload)
