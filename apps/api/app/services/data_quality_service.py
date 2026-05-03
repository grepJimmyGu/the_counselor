from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.schemas.data_quality import BacktestQualityGate, DataQualityReport
from app.schemas.market_data import WarmupResponse
from app.schemas.strategy import StrategyJSON
from app.services.price_data_service import PriceDataService

# A backtest with fewer than this many trading days is not credible
_MIN_ROWS = 30
# Warn if latest data is older than this many calendar days
_STALE_DAYS = 7
# Block if adjusted_close coverage drops below this
_MIN_ADJUSTED_CLOSE_COVERAGE = 0.95
# Warn if volume coverage drops below this
_MIN_VOLUME_COVERAGE = 0.90
# Warn if any single-day price move exceeds this
_SUSPICIOUS_JUMP_THRESHOLD = 0.50


class DataQualityService:
    def __init__(self) -> None:
        self.price_data = PriceDataService()

    # ------------------------------------------------------------------
    # Warmup (existing behaviour, unchanged)
    # ------------------------------------------------------------------

    async def warmup(
        self,
        db: Session,
        symbols: list[str],
        lookback_days: int = 252,
    ) -> WarmupResponse:
        queued: list[str] = []
        already_fresh: list[str] = []
        errors: dict[str, str] = {}

        required_from = date.today() - timedelta(days=lookback_days + 10)

        for sym in symbols:
            try:
                cache = self.price_data.cache_svc
                latest = cache.get_latest_date(db, sym)
                earliest = cache.get_earliest_date(db, sym)
                not_stale = not cache.is_stale(latest, date.today())
                has_lookback = earliest is not None and earliest <= required_from

                if not_stale and has_lookback:
                    already_fresh.append(sym)
                else:
                    await cache.ensure_history(db, sym, required_from)
                    queued.append(sym)
            except Exception as exc:
                errors[sym] = str(exc)

        return WarmupResponse(queued=queued, already_fresh=already_fresh, errors=errors)

    # ------------------------------------------------------------------
    # Data quality checks
    # ------------------------------------------------------------------

    def check_symbol(
        self,
        db: Session,
        symbol: str,
        required_from: Optional[date] = None,
        required_through: Optional[date] = None,
        required_lookback_days: int = 0,
    ) -> DataQualityReport:
        cache = self.price_data.cache_svc
        earliest = cache.get_earliest_date(db, symbol)
        latest = cache.get_latest_date(db, symbol)
        row_count = cache.get_bar_count(db, symbol)

        warnings: list[str] = []
        blocking_errors: list[str] = []

        # No data at all
        if row_count == 0 or earliest is None or latest is None:
            return DataQualityReport(
                symbol=symbol,
                status="blocked",
                warnings=[],
                blocking_errors=[f"No price data available for {symbol}. The ticker may be invalid or the data provider could not be reached."],
                earliest_available_date=None,
                latest_available_date=None,
                row_count=0,
                missing_date_count=None,
                adjusted_close_coverage=0.0,
                volume_coverage=0.0,
            )

        # Staleness
        days_since_latest = (date.today() - latest).days
        if days_since_latest > _STALE_DAYS:
            warnings.append(
                f"Latest cached date is {latest} ({days_since_latest} days ago). "
                "Data may be stale — results will not reflect recent price action."
            )

        # Insufficient history
        if row_count < _MIN_ROWS:
            blocking_errors.append(
                f"Only {row_count} trading days cached for {symbol}. "
                f"Minimum required: {_MIN_ROWS}."
            )

        # Lookback window check
        if required_from is not None and earliest > required_from:
            gap_days = (earliest - required_from).days
            blocking_errors.append(
                f"Strategy requires data from {required_from} for indicator warmup, "
                f"but earliest cached date is {earliest} ({gap_days} days short)."
            )

        # Date range coverage
        if required_from and required_through:
            if earliest > required_from:
                blocking_errors.append(
                    f"Cached data starts {earliest}, but strategy starts {required_from}."
                )
            if latest < required_through:
                warnings.append(
                    f"Cached data ends {latest}, but strategy requests through {required_through}. "
                    "Backtest will be truncated."
                )

        # Coverage checks (adjusted_close, volume)
        coverage = self._compute_coverage(db, symbol)
        adj_coverage = coverage["adjusted_close"]
        vol_coverage = coverage["volume"]
        missing_date_count = coverage["missing_date_count"]

        if adj_coverage < _MIN_ADJUSTED_CLOSE_COVERAGE:
            blocking_errors.append(
                f"Adjusted close coverage is {adj_coverage:.1%} — too many missing values to backtest reliably."
            )
        if vol_coverage < _MIN_VOLUME_COVERAGE:
            warnings.append(
                f"Volume coverage is {vol_coverage:.1%}. Volume-based checks may be unreliable."
            )
        if missing_date_count and missing_date_count > 0:
            warnings.append(
                f"Approximately {missing_date_count} expected trading days have no price bar (gaps in data)."
            )

        # Suspicious price jumps
        jump_warning = self._check_price_jumps(db, symbol)
        if jump_warning:
            warnings.append(jump_warning)

        status: str
        if blocking_errors:
            status = "blocked"
        elif warnings:
            status = "warning"
        else:
            status = "ready"

        return DataQualityReport(
            symbol=symbol,
            status=status,  # type: ignore[arg-type]
            warnings=warnings,
            blocking_errors=blocking_errors,
            earliest_available_date=earliest,
            latest_available_date=latest,
            row_count=row_count,
            missing_date_count=missing_date_count,
            adjusted_close_coverage=adj_coverage,
            volume_coverage=vol_coverage,
        )

    def check_strategy(self, db: Session, strategy: StrategyJSON) -> BacktestQualityGate:
        """Run quality checks on every symbol in the strategy universe + benchmark."""
        lookback_days = self._estimate_lookback(strategy)
        required_from = strategy.start_date - timedelta(days=lookback_days + 10)
        required_through = strategy.end_date

        all_symbols = list(strategy.universe) + [strategy.benchmark]
        reports: dict[str, DataQualityReport] = {}
        for symbol in all_symbols:
            reports[symbol] = self.check_symbol(
                db, symbol,
                required_from=required_from,
                required_through=required_through,
                required_lookback_days=lookback_days,
            )

        # Benchmark-starts-later-than-strategy check
        benchmark_report = reports[strategy.benchmark]
        for sym in strategy.universe:
            universe_report = reports[sym]
            if (
                universe_report.earliest_available_date
                and benchmark_report.earliest_available_date
                and benchmark_report.earliest_available_date > universe_report.earliest_available_date
            ):
                benchmark_report.warnings.append(
                    f"Benchmark {strategy.benchmark} data starts {benchmark_report.earliest_available_date}, "
                    f"later than {sym} data starting {universe_report.earliest_available_date}. "
                    "Benchmark comparison will only cover the overlapping period."
                )
                if benchmark_report.status == "ready":
                    benchmark_report.status = "warning"  # type: ignore[assignment]

        blocking = [s for s, r in reports.items() if r.status == "blocked"]
        warning = [s for s, r in reports.items() if r.status == "warning"]

        if blocking:
            overall = "blocked"
        elif warning:
            overall = "warning"
        else:
            overall = "ready"

        return BacktestQualityGate(
            overall_status=overall,  # type: ignore[arg-type]
            reports=reports,
            blocking_symbols=blocking,
            warning_symbols=warning,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_coverage(self, db: Session, symbol: str) -> dict:
        total = db.scalar(
            select(func.count()).select_from(PriceBar).where(PriceBar.symbol == symbol)
        ) or 0
        if total == 0:
            return {"adjusted_close": 0.0, "volume": 0.0, "missing_date_count": 0}

        missing_adj = db.scalar(
            select(func.count()).select_from(PriceBar).where(
                PriceBar.symbol == symbol,
                PriceBar.adjusted_close.is_(None),
            )
        ) or 0
        missing_vol = db.scalar(
            select(func.count()).select_from(PriceBar).where(
                PriceBar.symbol == symbol,
                PriceBar.volume.is_(None),
            )
        ) or 0

        # Estimate missing date gaps (expected trading days vs actual rows)
        earliest = db.scalar(
            select(func.min(PriceBar.trading_date)).where(PriceBar.symbol == symbol)
        )
        latest = db.scalar(
            select(func.max(PriceBar.trading_date)).where(PriceBar.symbol == symbol)
        )
        missing_date_count: Optional[int] = None
        if earliest and latest:
            calendar_days = (latest - earliest).days
            expected_trading_days = math.ceil(calendar_days * 5 / 7)
            missing_date_count = max(0, expected_trading_days - total)

        return {
            "adjusted_close": (total - missing_adj) / total,
            "volume": (total - missing_vol) / total,
            "missing_date_count": missing_date_count,
        }

    def _check_price_jumps(self, db: Session, symbol: str) -> Optional[str]:
        rows = db.execute(
            select(PriceBar.trading_date, PriceBar.adjusted_close)
            .where(PriceBar.symbol == symbol, PriceBar.adjusted_close.isnot(None))
            .order_by(PriceBar.trading_date.asc())
        ).fetchall()
        if len(rows) < 2:
            return None
        for i in range(1, len(rows)):
            prev = rows[i - 1].adjusted_close
            curr = rows[i].adjusted_close
            if prev and prev > 0:
                change = abs(curr / prev - 1.0)
                if change > _SUSPICIOUS_JUMP_THRESHOLD:
                    return (
                        f"Suspicious price move detected on {rows[i].trading_date}: "
                        f"{change:.1%} change. This may indicate a data error, split, or corporate action."
                    )
        return None

    @staticmethod
    def _estimate_lookback(strategy: StrategyJSON) -> int:
        rules = strategy.rules
        stype = strategy.strategy_type
        if stype == "moving_average_filter":
            w = rules[0].lookback_days or 200 if rules else 200
            return int(w * 1.5) + 5
        if stype == "moving_average_crossover":
            w = rules[0].slow_window or 200 if rules else 200
            return int(w * 1.5) + 5
        if stype == "rsi_mean_reversion":
            w = rules[0].lookback_days or 14 if rules else 14
            return int(w * 1.5) + 5
        if stype == "breakout":
            w = rules[0].entry_window or 60 if rules else 60
            return int(w * 1.5) + 5
        if stype == "momentum_rotation":
            w = rules[0].ranking_lookback_days or 126 if rules else 126
            return int(w * 1.5) + 5
        return 252
