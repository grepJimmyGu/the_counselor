from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.backtest import BacktestRecord
from app.schemas.backtest import (
    AnnualReturnItem,
    BacktestMetrics,
    BacktestResult,
    CurvePoint,
    MonthlyReturnItem,
    TradeLogItem,
)
from app.schemas.strategy import StrategyJSON
from app.services.backtester.metrics import compute_buy_and_hold, compute_drawdown, compute_metrics
from app.services.market_data import MarketDataService
from app.services.strategy_validator import validate_strategy


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0).rolling(window=window).mean()
    losses = (-delta.clip(upper=0)).rolling(window=window).mean()
    rs = gains / losses.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class BacktestEngine:
    def __init__(self) -> None:
        self.market_data = MarketDataService()

    def _compute_lookback(self, strategy: StrategyJSON) -> int:
        """Calendar days of pre-start history needed for indicator warmup."""
        stype = strategy.strategy_type
        rules = strategy.rules

        if stype == "moving_average_filter":
            window = rules[0].lookback_days or 200 if rules else 200
            return int(window * 1.5) + 5
        if stype == "moving_average_crossover":
            slow = rules[0].slow_window or 200 if rules else 200
            return int(slow * 1.5) + 5
        if stype == "rsi_mean_reversion":
            window = rules[0].lookback_days or 14 if rules else 14
            return int(window * 1.5) + 5
        if stype == "breakout":
            entry_w = rules[0].entry_window or 60 if rules else 60
            return int(entry_w * 1.5) + 5
        if stype == "momentum_rotation":
            lookback = rules[0].ranking_lookback_days or 126 if rules else 126
            return int(lookback * 1.5) + 5
        if stype == "static_allocation":
            return 5
        # ── New template types ────────────────────────────────────────────────
        if stype == "cross_sectional_momentum":
            rule0 = rules[0] if rules else None
            formation = (rule0.formation_period_days if rule0 else None) or 252
            skip = (rule0.skip_period_days if rule0 else None) or 21
            return int((formation + skip) * 1.4) + 10
        if stype == "time_series_momentum":
            rule0 = rules[0] if rules else None
            lookback = (rule0.lookback_days if rule0 else None) or 252
            return int(lookback * 1.4) + 10
        if stype == "short_term_reversal":
            rule0 = rules[0] if rules else None
            formation = (rule0.formation_period_days if rule0 else None) or 5
            return int(formation * 1.4) + 10
        if stype == "sector_rotation":
            rule0 = rules[0] if rules else None
            formation = (rule0.formation_period_days if rule0 else None) or 126
            return int(formation * 1.4) + 10
        if stype == "dual_momentum":
            rule0 = rules[0] if rules else None
            formation = (rule0.formation_period_days if rule0 else None) or 252
            return int(formation * 1.4) + 10
        if stype == "low_volatility":
            rule0 = rules[0] if rules else None
            vol_lookback = (rule0.lookback_days if rule0 else None) or 63
            return int(vol_lookback * 1.4) + 10
        if stype == "bollinger_mean_reversion":
            rule0 = rules[0] if rules else None
            lookback = (rule0.lookback_days if rule0 else None) or 20
            return int(lookback * 1.4) + 10
        if stype == "pairs_trading":
            rule0 = rules[0] if rules else None
            lookback = (rule0.lookback_days if rule0 else None) or 60
            return int(lookback * 1.4) + 10
        return 252

    async def _load_prices(self, db: Session, strategy: StrategyJSON) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
        lookback = self._compute_lookback(strategy)
        universe_frames: dict[str, pd.DataFrame] = {}
        for symbol in strategy.universe:
            universe_frames[symbol] = await self.market_data.get_price_frame(
                db, symbol, strategy.start_date, strategy.end_date, lookback_days=lookback
            )
        benchmark_frame = await self.market_data.get_price_frame(
            db, strategy.benchmark, strategy.start_date, strategy.end_date, lookback_days=lookback
        )
        return universe_frames, benchmark_frame

    def _rebalance_mask(self, index: pd.DatetimeIndex, frequency: str) -> pd.Series:
        if frequency == "daily":
            return pd.Series(True, index=index)
        if frequency == "weekly":
            return pd.Series(index.weekday == 0, index=index)
        if frequency == "quarterly":
            return pd.Series(index.is_quarter_start, index=index)
        return pd.Series(index.is_month_start, index=index)

    def _build_price_matrix(self, universe_frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
        closes = []
        aligned = {}
        for symbol, frame in universe_frames.items():
            if frame.empty:
                continue
            aligned[symbol] = frame.copy()
            closes.append(frame["adjusted_close"].rename(symbol))
        if not closes:
            return pd.DataFrame(), aligned
        close_matrix = pd.concat(closes, axis=1).sort_index().ffill().dropna(how="all")
        return close_matrix, aligned

    def _generate_cross_sectional_weights(
        self,
        close_matrix: pd.DataFrame,
        score_matrix: pd.DataFrame,
        rebalance_mask: pd.Series,
        top_n: Optional[int],
        top_pct: Optional[float],
        rank_direction: str = "top",
    ) -> pd.DataFrame:
        """
        Equal-weight the top_n or top_pct assets by score on each rebalance date.

        rank_direction="top"    → select highest scores (e.g. highest return, lowest vol via negation)
        rank_direction="bottom" → select lowest scores  (e.g. lowest return for short-term reversal)

        Non-rebalance rows are left as 0.0; the caller's common code handles ffill and
        exposure normalisation.
        """
        index = close_matrix.index
        weights = pd.DataFrame(0.0, index=index, columns=close_matrix.columns)
        ascending = rank_direction == "bottom"

        for dt in index[rebalance_mask]:
            scores = score_matrix.loc[dt].dropna()
            if scores.empty:
                continue
            # Determine selection size
            n = top_n
            if n is None and top_pct is not None:
                n = max(1, int(len(scores) * top_pct))
            if n is None:
                n = min(3, len(scores))
            sorted_scores = scores.sort_values(ascending=ascending)
            selected = sorted_scores.head(n).index.tolist()
            if selected:
                weights.loc[dt, selected] = 1.0 / len(selected)

        return weights

    def _generate_weights(
        self, strategy: StrategyJSON, close_matrix: pd.DataFrame, aligned_frames: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        index = close_matrix.index
        weights = pd.DataFrame(0.0, index=index, columns=close_matrix.columns)
        rebalance_mask = self._rebalance_mask(index, strategy.rebalance_frequency)

        # ── Original 6 strategy types (behavior unchanged) ────────────────────
        if strategy.strategy_type == "moving_average_filter":
            rule = strategy.rules[0]
            symbol = strategy.universe[0]
            ma = close_matrix[symbol].rolling(window=rule.lookback_days or 200).mean()
            weights[symbol] = (close_matrix[symbol] > ma).astype(float)

        elif strategy.strategy_type == "moving_average_crossover":
            rule = strategy.rules[0]
            symbol = strategy.universe[0]
            fast = close_matrix[symbol].rolling(window=rule.fast_window or 50).mean()
            slow = close_matrix[symbol].rolling(window=rule.slow_window or 200).mean()
            weights[symbol] = (fast > slow).astype(float)

        elif strategy.strategy_type == "rsi_mean_reversion":
            buy_rule, sell_rule = strategy.rules
            symbol = strategy.universe[0]
            rsi = compute_rsi(close_matrix[symbol], buy_rule.lookback_days or 14)
            in_position = False
            positions: list[float] = []
            for current_rsi in rsi.fillna(50):
                if not in_position and current_rsi < (buy_rule.threshold or 30):
                    in_position = True
                elif in_position and current_rsi > (sell_rule.threshold or 60):
                    in_position = False
                positions.append(1.0 if in_position else 0.0)
            weights[symbol] = positions

        elif strategy.strategy_type == "breakout":
            rule = strategy.rules[0]
            symbol = strategy.universe[0]
            highs = aligned_frames[symbol]["high"].reindex(index).ffill()
            closes = close_matrix[symbol]
            rolling_high = highs.rolling(window=rule.entry_window or 60).max().shift(1)
            rolling_low = closes.rolling(window=rule.exit_window or 20).min().shift(1)
            in_position = False
            positions: list[float] = []
            for dt in index:
                price = closes.loc[dt]
                if not in_position and price > rolling_high.loc[dt]:
                    in_position = True
                elif in_position and price < rolling_low.loc[dt]:
                    in_position = False
                positions.append(1.0 if in_position else 0.0)
            weights[symbol] = positions

        elif strategy.strategy_type == "static_allocation":
            for symbol, weight in (strategy.position_sizing.weights or {}).items():
                if symbol in weights.columns:
                    weights[symbol] = weight

        elif strategy.strategy_type == "momentum_rotation":
            # Refactored to use _generate_cross_sectional_weights — identical behaviour.
            rule = strategy.rules[0]
            lookback = rule.ranking_lookback_days or 126
            top_n = rule.top_n or min(3, len(strategy.universe))
            score_matrix = close_matrix / close_matrix.shift(lookback) - 1.0
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=None, rank_direction="top",
            )

        # ── New template types ────────────────────────────────────────────────

        elif strategy.strategy_type == "cross_sectional_momentum":
            rule = strategy.rules[0] if strategy.rules else None
            formation = (rule.formation_period_days if rule else None) or 252
            skip = (rule.skip_period_days if rule else None) or 21
            score_matrix = close_matrix.pct_change(formation).shift(skip)
            top_n = (rule.top_n if rule else None)
            top_pct = (rule.top_pct if rule else None)
            rank_direction = (rule.rank_direction if rule else None) or "top"
            if top_n is None and top_pct is None:
                top_n = min(3, len(strategy.universe))
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction=rank_direction,
            )

        elif strategy.strategy_type == "time_series_momentum":
            # Per-symbol: long if 12-month return > 0 on rebalance date; equal-weight actives.
            rule = strategy.rules[0] if strategy.rules else None
            lookback = (rule.lookback_days if rule else None) or 252
            returns_12m = close_matrix.pct_change(lookback)
            for dt in index[rebalance_mask]:
                row = returns_12m.loc[dt].dropna()
                active = row[row > 0].index.tolist()
                if active:
                    weights.loc[dt, active] = 1.0 / len(active)

        elif strategy.strategy_type == "short_term_reversal":
            # Rank by short-term return; select bottom performers (mean-reversion bet).
            rule = strategy.rules[0] if strategy.rules else None
            formation = (rule.formation_period_days if rule else None) or 5
            score_matrix = close_matrix.pct_change(formation)
            top_n = (rule.top_n if rule else None)
            top_pct = (rule.top_pct if rule else None)
            rank_direction = (rule.rank_direction if rule else None) or "bottom"
            if top_n is None and top_pct is None:
                top_n = min(3, len(strategy.universe))
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction=rank_direction,
            )

        elif strategy.strategy_type == "sector_rotation":
            # Same engine as cross_sectional_momentum; universe is typically SPDR sector ETFs.
            rule = strategy.rules[0] if strategy.rules else None
            formation = (rule.formation_period_days if rule else None) or 126
            score_matrix = close_matrix.pct_change(formation)
            top_n = (rule.top_n if rule else None) or 3
            rank_direction = (rule.rank_direction if rule else None) or "top"
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=None, rank_direction=rank_direction,
            )

        elif strategy.strategy_type == "dual_momentum":
            # Rank universe by formation-period return; pick the single best.
            # If best has negative return, allocate to safe_asset (if in universe) else cash.
            rule = strategy.rules[0] if strategy.rules else None
            formation = (rule.formation_period_days if rule else None) or 252
            returns = close_matrix.pct_change(formation)
            # Find safe-asset override: a rule with signal_source="safe_asset"
            safe_asset: Optional[str] = None
            for r in strategy.rules:
                if r.signal_source == "safe_asset" and r.value:
                    safe_asset = str(r.value)
                    break
            for dt in index[rebalance_mask]:
                scores = returns.loc[dt].dropna()
                if scores.empty:
                    continue
                top_sym = scores.idxmax()
                if scores[top_sym] > 0:
                    weights.loc[dt, top_sym] = 1.0
                elif safe_asset and safe_asset in weights.columns:
                    weights.loc[dt, safe_asset] = 1.0
                # else: hold cash (0 allocation)

        elif strategy.strategy_type == "low_volatility":
            # Select lowest-volatility assets; score = -rolling_vol so "top" = lowest vol.
            rule = strategy.rules[0] if strategy.rules else None
            vol_lookback = (rule.lookback_days if rule else None) or 63
            vol = close_matrix.pct_change().rolling(vol_lookback).std()
            score_matrix = -vol   # higher score → lower vol → preferred
            top_n = (rule.top_n if rule else None)
            top_pct = (rule.top_pct if rule else None)
            # rank_direction="top" selects highest score = lowest vol
            rank_direction = (rule.rank_direction if rule else None) or "top"
            if top_n is None and top_pct is None:
                top_n = min(3, len(strategy.universe))
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction=rank_direction,
            )

        elif strategy.strategy_type == "bollinger_mean_reversion":
            # Single-asset signal strategy: long when close < lower band; exit when close > MA.
            rule = strategy.rules[0] if strategy.rules else None
            lookback = (rule.lookback_days if rule else None) or 20
            num_std = (rule.num_std if rule else None) or 2.0
            symbol = strategy.universe[0]
            ma = close_matrix[symbol].rolling(lookback).mean()
            sigma = close_matrix[symbol].rolling(lookback).std()
            lower_band = ma - num_std * sigma
            in_position = False
            positions: list[float] = []
            for dt in index:
                price = close_matrix.loc[dt, symbol]
                lower = lower_band.loc[dt]
                mid = ma.loc[dt]
                if pd.isna(lower) or pd.isna(mid):
                    positions.append(0.0)
                    continue
                if not in_position and price < lower:
                    in_position = True
                elif in_position and price > mid:
                    in_position = False
                positions.append(1.0 if in_position else 0.0)
            weights[symbol] = positions

        elif strategy.strategy_type == "pairs_trading":
            # Long-only pairs: long sym_a when spread z-score is sufficiently negative.
            # Universe must contain at least 2 symbols; sym_b may be overridden via rule.pair_symbol.
            if len(strategy.universe) < 2:
                raise ValueError("pairs_trading requires at least 2 symbols in universe.")
            rule = strategy.rules[0] if strategy.rules else None
            sym_a = strategy.universe[0]
            sym_b_default = strategy.universe[1]
            pair_override = (rule.pair_symbol if rule else None)
            sym_b = pair_override if (pair_override and pair_override in close_matrix.columns) else sym_b_default
            hedge_ratio = (rule.hedge_ratio if rule else None) or 1.0
            lookback = (rule.lookback_days if rule else None) or 60
            zscore_entry = (rule.zscore_entry if rule else None) or 2.0
            zscore_exit = (rule.zscore_exit if rule else None) or 0.5
            zscore_stop = (rule.zscore_stop if rule else None) or 3.0

            log_spread = np.log(close_matrix[sym_a]) - hedge_ratio * np.log(close_matrix[sym_b])
            roll_mean = log_spread.rolling(lookback).mean()
            roll_std = log_spread.rolling(lookback).std().replace(0, np.nan)
            zscore = (log_spread - roll_mean) / roll_std

            in_position = False
            positions: list[float] = []
            for z in zscore.fillna(0.0):
                if not in_position and z <= -zscore_entry:
                    in_position = True
                elif in_position and (z >= zscore_exit or z <= -zscore_stop):
                    in_position = False
                positions.append(1.0 if in_position else 0.0)
            weights[sym_a] = positions

        # ── Post-processing (shared for all strategies) ───────────────────────

        # Signal strategies produce a new 0/1 weight each day — clip to binary.
        # Rotation/allocation strategies: NaN out non-rebalance rows then ffill so
        # holdings are held between rebalances.
        is_signal_strategy = strategy.strategy_type in {
            "moving_average_filter",
            "moving_average_crossover",
            "rsi_mean_reversion",
            "breakout",
            "bollinger_mean_reversion",
            "pairs_trading",
        }
        if is_signal_strategy:
            weights = weights.where(weights.eq(0.0), other=1.0)
        else:
            # Row-level assignment avoids the (n,1) vs (n,k) broadcast mismatch that
            # pd.DataFrame.where() raises on multi-asset DataFrames.
            non_rebalance = rebalance_mask[~rebalance_mask].index
            weights.loc[non_rebalance] = np.nan

        weights = weights.ffill().fillna(0.0)

        exposure = weights.sum(axis=1)
        over_allocated = exposure > 1.0
        if over_allocated.any():
            weights.loc[over_allocated] = weights.loc[over_allocated].div(exposure[over_allocated], axis=0)
        return weights

    def _extract_trade_log(self, close_matrix: pd.DataFrame, weights: pd.DataFrame) -> list[TradeLogItem]:
        trades: list[TradeLogItem] = []
        for symbol in close_matrix.columns:
            in_trade = False
            entry_date: Optional[date] = None
            entry_price = 0.0
            for dt, weight in weights[symbol].items():
                if not in_trade and weight > 0:
                    in_trade = True
                    entry_date = dt.date()
                    entry_price = float(close_matrix.loc[dt, symbol])
                elif in_trade and weight == 0 and entry_date is not None:
                    exit_date = dt.date()
                    exit_price = float(close_matrix.loc[dt, symbol])
                    trades.append(
                        TradeLogItem(
                            symbol=symbol,
                            entry_date=entry_date,
                            exit_date=exit_date,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            return_pct=(exit_price / entry_price) - 1.0,
                            holding_period_days=(exit_date - entry_date).days,
                        )
                    )
                    in_trade = False
            if in_trade and entry_date is not None:
                last_dt = close_matrix.index[-1].date()
                exit_price = float(close_matrix.iloc[-1][symbol])
                trades.append(
                    TradeLogItem(
                        symbol=symbol,
                        entry_date=entry_date,
                        exit_date=last_dt,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        return_pct=(exit_price / entry_price) - 1.0,
                        holding_period_days=(last_dt - entry_date).days,
                    )
                )
        return trades

    async def run(self, db: Session, strategy: StrategyJSON) -> BacktestResult:
        warnings = validate_strategy(strategy)
        universe_frames, benchmark_frame = await self._load_prices(db, strategy)
        close_matrix, aligned_frames = self._build_price_matrix(universe_frames)
        if close_matrix.empty:
            raise ValueError("No historical data was available for the requested symbols.")

        # Trim warmup rows before computing P&L (they exist only for indicator seeding)
        strategy_start = pd.Timestamp(strategy.start_date)
        close_matrix = close_matrix[close_matrix.index >= strategy_start]
        aligned_frames = {
            sym: frame[frame.index >= strategy_start]
            for sym, frame in aligned_frames.items()
        }

        benchmark_close = benchmark_frame["adjusted_close"].reindex(close_matrix.index).ffill().dropna()
        close_matrix = close_matrix.reindex(benchmark_close.index).ffill().dropna(how="all")
        benchmark_close = benchmark_close.reindex(close_matrix.index).ffill()

        weights = self._generate_weights(strategy, close_matrix, aligned_frames)
        asset_returns = close_matrix.pct_change().fillna(0.0)
        turnover = weights.diff().abs().sum(axis=1).fillna(0.0)
        costs = turnover * ((strategy.transaction_cost_bps + strategy.slippage_bps) / 10000)
        portfolio_returns = (weights.shift(1).fillna(0.0) * asset_returns).sum(axis=1) - costs
        benchmark_returns = benchmark_close.pct_change().fillna(0.0)

        equity_curve = strategy.initial_capital * (1.0 + portfolio_returns).cumprod()
        benchmark_curve = strategy.initial_capital * (1.0 + benchmark_returns).cumprod()
        drawdown_curve = compute_drawdown(equity_curve)
        trade_log = self._extract_trade_log(close_matrix, weights)
        trade_returns = [trade.return_pct for trade in trade_log]
        holding_periods = [trade.holding_period_days for trade in trade_log]

        # Buy-and-hold for the primary universe ticker (single-asset strategies)
        bah_curve: pd.Series | None = None
        bah_metrics: dict = {}
        if len(strategy.universe) == 1:
            primary = strategy.universe[0]
            if primary in close_matrix.columns:
                primary_prices = close_matrix[primary]
                bah_returns = primary_prices.pct_change().fillna(0.0)
                bah_curve = strategy.initial_capital * (1.0 + bah_returns).cumprod()
                bah_metrics = compute_buy_and_hold(primary_prices, strategy.initial_capital, len(primary_prices))

        metrics = BacktestMetrics(
            **compute_metrics(
                portfolio_returns=portfolio_returns,
                benchmark_returns=benchmark_returns,
                trade_returns=trade_returns,
                holding_periods=holding_periods,
                turnover_series=turnover,
                time_in_market_series=(weights.sum(axis=1) > 0).astype(float),
            ),
            **bah_metrics,
        )

        annual_returns = (
            (1.0 + portfolio_returns).resample("Y").prod() - 1.0
        ).to_dict()
        monthly_returns = (
            (1.0 + portfolio_returns).resample("M").prod() - 1.0
        )

        result = BacktestResult(
            backtest_id=str(uuid4()),
            strategy_json=strategy,
            metrics=metrics,
            equity_curve=[CurvePoint(date=dt.date(), value=float(value)) for dt, value in equity_curve.items()],
            benchmark_curve=[CurvePoint(date=dt.date(), value=float(value)) for dt, value in benchmark_curve.items()],
            buy_and_hold_curve=(
                [CurvePoint(date=dt.date(), value=float(v)) for dt, v in bah_curve.items()]
                if bah_curve is not None else []
            ),
            drawdown_curve=[CurvePoint(date=dt.date(), value=float(value)) for dt, value in drawdown_curve.items()],
            trade_log=trade_log,
            annual_returns=[
                AnnualReturnItem(year=ts.year, return_pct=float(value)) for ts, value in annual_returns.items()
            ],
            monthly_returns=[
                MonthlyReturnItem(year=dt.year, month=dt.month, return_pct=float(value))
                for dt, value in monthly_returns.items()
            ],
            warnings=warnings,
        )

        db.add(
            BacktestRecord(
                id=result.backtest_id,
                strategy_type=strategy.strategy_type,
                strategy_name=strategy.strategy_name,
                result_payload=result.model_dump(mode="json"),
            )
        )
        db.commit()
        return result
