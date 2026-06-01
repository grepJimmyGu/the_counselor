from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal, Optional
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Strategy types whose weights are driven by fundamental SignalProviders
_FUNDAMENTAL_STRATEGY_TYPES = frozenset({
    "value_composite", "quality_piotroski", "buyback_yield",
    "pead_drift", "earnings_revision",
    "news_sentiment_momentum", "insider_buying",
    "multi_factor_composite",
})

from app.models.backtest import BacktestRecord
from app.schemas.backtest import (
    AnnualReturnItem,
    BacktestMetrics,
    BacktestResult,
    CurvePoint,
    MonthlyReturnItem,
    TradeLogItem,
)
from app.schemas.strategy import PORTFOLIO_OVERLAY_TYPES, StrategyJSON
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
        # Multi-factor composite: momentum_12_1 sub-factor needs 252+21 days
        if stype == "multi_factor_composite":
            return int(273 * 1.4) + 10   # 392 — covers 12-1 momentum warmup
        # ── PRD-13b portfolio overlays ────────────────────────────────────────
        if stype == "portfolio_defensive_overlay":
            # MA-length per-holding signal; default 200-day MA
            rule0 = rules[0] if rules else None
            window = (rule0.lookback_days if rule0 else None) or 200
            return int(window * 1.5) + 5
        if stype == "portfolio_rotation_overlay":
            # Rank holdings by N-month return; default 6-month (~126 trading days)
            rule0 = rules[0] if rules else None
            lookback = (rule0.ranking_lookback_days if rule0 else None) or 126
            return int(lookback * 1.5) + 5
        if stype == "portfolio_rebalance_overlay":
            # Pure target-weight re-balance; no indicator warmup.
            return 5
        # ── PRD-13c portfolio overlay expansion ────────────────────────────────
        if stype == "portfolio_dual_momentum_overlay":
            # Relative ranking + absolute momentum filter; use max of the two.
            rule0 = rules[0] if rules else None
            ranking_lb = (rule0.ranking_lookback_days if rule0 else None) or 126
            absolute_lb = (rule0.lookback_days if rule0 else None) or 252
            return int(max(ranking_lb, absolute_lb) * 1.5) + 5
        if stype == "portfolio_defense_first_overlay":
            # Breadth-of-holdings MA signal; default 200-day MA
            rule0 = rules[0] if rules else None
            window = (rule0.lookback_days if rule0 else None) or 200
            return int(window * 1.5) + 5
        if stype == "portfolio_stability_tilt_overlay":
            # Trailing volatility window; default 63 days (1 quarter)
            rule0 = rules[0] if rules else None
            lookback = (rule0.lookback_days if rule0 else None) or 63
            return int(lookback * 1.4) + 10
        # Signal-provider-backed strategies: no price-based lookback needed
        if stype in _FUNDAMENTAL_STRATEGY_TYPES:
            return 5
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

    async def _fetch_signal_matrix(
        self,
        providers: list,
        universe: list[str],
        db: Session,
        close_index: pd.DatetimeIndex,
        signal_start: date,
        signal_end: date,
        ffill_limit: Optional[int] = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch signal frames for each provider × each universe symbol and align
        to close_index via forward-fill only (no look-ahead bias).

        ffill_limit: maximum number of trading-day rows to forward-fill from each
          disclosure date.  None = unlimited (hold until next disclosure).
          Set to holding_window_days for PEAD to expire positions automatically.

        Returns {signal_name: DataFrame(columns=universe, index=close_index)}.
        Observations dated before the first disclosure are NaN.
        """
        result: dict[str, pd.DataFrame] = {}
        for provider in providers:
            cols: dict[str, pd.Series] = {}
            for sym in universe:
                try:
                    sparse = await provider.get_signal_frame(db, sym, signal_start, signal_end)
                except Exception as exc:
                    logger.warning(
                        "_fetch_signal_matrix: provider=%s sym=%s error=%s",
                        provider.name, sym, exc,
                    )
                    sparse = pd.Series(dtype=float)

                if sparse.empty:
                    cols[sym] = pd.Series(float("nan"), index=close_index, dtype=float)
                else:
                    combined_idx = sparse.index.union(close_index)
                    cols[sym] = (
                        sparse
                        .reindex(combined_idx)
                        .ffill(limit=ffill_limit)
                        .reindex(close_index)
                    )
            result[provider.name] = pd.DataFrame(cols, index=close_index)
        return result

    @staticmethod
    def _zscore_row(row: pd.Series) -> pd.Series:
        """Cross-sectional z-score: standardize a row of values across symbols."""
        valid = row.dropna()
        if len(valid) < 2:
            return pd.Series(float("nan"), index=row.index)
        std = valid.std()
        if std == 0:
            return pd.Series(0.0, index=row.index)
        return (row - valid.mean()) / std

    def _build_factor_score_matrix(
        self,
        factor_name: str,
        close_matrix: pd.DataFrame,
        precomputed_signals: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Return a raw (un-z-scored) score matrix for a single named factor.
        Supported factor names:
          "value_composite"  — average z-score of fcf_yield, book_to_market, ebitda_ev
          "momentum_12_1"    — 12-month return shifted 1 month (standard cross-sectional momentum)
          "quality_f_score"  — Piotroski F-Score from FundamentalSignalProvider("f_score")
          "low_volatility"   — negated 63-day rolling volatility (higher = lower vol)
        Unknown factor names produce a NaN matrix and log a warning.
        """
        index = close_matrix.index
        empty = pd.DataFrame(float("nan"), index=index, columns=close_matrix.columns)

        if factor_name == "value_composite":
            ps = precomputed_signals
            fcf = ps.get("fcf_yield", empty)
            btm = ps.get("book_to_market", empty)
            ev  = ps.get("ebitda_ev", empty)
            z_fcf = fcf.apply(self._zscore_row, axis=1)
            z_btm = btm.apply(self._zscore_row, axis=1)
            z_ev  = ev.apply(self._zscore_row, axis=1)
            arr = np.stack([z_fcf.values, z_btm.values, z_ev.values], axis=2)
            return pd.DataFrame(
                np.nanmean(arr, axis=2), index=index, columns=close_matrix.columns
            )

        if factor_name == "momentum_12_1":
            # 12-month total return, skip most recent month (standard 12-1 momentum)
            return close_matrix.pct_change(252).shift(21)

        if factor_name == "quality_f_score":
            return precomputed_signals.get("f_score", empty)

        if factor_name == "low_volatility":
            vol = close_matrix.pct_change().rolling(63).std()
            return -vol   # higher score → lower vol → preferred

        logger.warning(
            "_build_factor_score_matrix: unknown factor '%s' — treating as zero.", factor_name
        )
        return empty

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
        self,
        strategy: StrategyJSON,
        close_matrix: pd.DataFrame,
        aligned_frames: dict[str, pd.DataFrame],
        precomputed_signals: dict[str, pd.DataFrame] | None = None,
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

        # ── Fundamental signal strategies (require precomputed_signals) ────────

        elif strategy.strategy_type == "value_composite":
            # z-score fcf_yield, book_to_market, ebitda_ev cross-sectionally;
            # average the z-scores; rank top_pct by composite.
            ps = precomputed_signals or {}
            _empty = pd.DataFrame(float("nan"), index=index, columns=close_matrix.columns)
            fcf_mat = ps.get("fcf_yield", _empty)
            btm_mat = ps.get("book_to_market", _empty)
            ev_mat  = ps.get("ebitda_ev", _empty)
            # Cross-sectional z-score each signal matrix row-by-row
            z_fcf = fcf_mat.apply(self._zscore_row, axis=1)
            z_btm = btm_mat.apply(self._zscore_row, axis=1)
            z_ev  = ev_mat.apply(self._zscore_row, axis=1)
            # Average z-scores treating NaN as missing (nanmean across 3 layers)
            arr = np.stack([z_fcf.values, z_btm.values, z_ev.values], axis=2)
            composite = pd.DataFrame(
                np.nanmean(arr, axis=2), index=index, columns=close_matrix.columns
            )
            rule = strategy.rules[0] if strategy.rules else None
            top_pct = (rule.top_pct if rule else None) or 0.1
            top_n   = (rule.top_n   if rule else None)
            weights = self._generate_cross_sectional_weights(
                close_matrix, composite, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction="top",
            )

        elif strategy.strategy_type == "quality_piotroski":
            # Long if f_score >= 8; equal-weight across qualifying names.
            ps = precomputed_signals or {}
            f_mat = ps.get("f_score", pd.DataFrame(float("nan"), index=index,
                                                     columns=close_matrix.columns))
            threshold = 8.0
            for dt in index[rebalance_mask]:
                row = f_mat.loc[dt]
                qualifying = [
                    sym for sym in close_matrix.columns
                    if pd.notna(row.get(sym)) and float(row.get(sym, -1)) >= threshold
                ]
                if qualifying:
                    weights.loc[dt, qualifying] = 1.0 / len(qualifying)

        elif strategy.strategy_type == "buyback_yield":
            ps = precomputed_signals or {}
            score_matrix = ps.get(
                "buyback_yield_ttm",
                pd.DataFrame(float("nan"), index=index, columns=close_matrix.columns),
            )
            rule = strategy.rules[0] if strategy.rules else None
            top_pct = (rule.top_pct if rule else None) or 0.1
            top_n   = (rule.top_n   if rule else None)
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction="top",
            )

        elif strategy.strategy_type == "pead_drift":
            # Post-earnings announcement drift.
            # SUE signals were fetched with ffill_limit=holding_window_days, so
            # each symbol's signal is active only for the holding window after
            # its earnings announcement.  Cross-sectional ranking selects the
            # top decile of symbols with ACTIVE (non-expired) top-decile SUE.
            ps = precomputed_signals or {}
            sue_mat = ps.get(
                "earnings_surprise",
                pd.DataFrame(float("nan"), index=index, columns=close_matrix.columns),
            )
            rule = strategy.rules[0] if strategy.rules else None
            top_pct = (rule.top_pct if rule else None) or 0.1
            top_n   = (rule.top_n   if rule else None)
            weights = self._generate_cross_sectional_weights(
                close_matrix, sue_mat, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction="top",
            )

        elif strategy.strategy_type == "earnings_revision":
            # Rank by 3-quarter EPS momentum (proxy for analyst estimate revision).
            ps = precomputed_signals or {}
            score_matrix = ps.get(
                "estimate_revision_3m",
                pd.DataFrame(float("nan"), index=index, columns=close_matrix.columns),
            )
            rule = strategy.rules[0] if strategy.rules else None
            top_pct = (rule.top_pct if rule else None) or 0.1
            top_n   = (rule.top_n   if rule else None)
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction="top",
            )

        elif strategy.strategy_type == "news_sentiment_momentum":
            # 30-day rolling mean sentiment score (SentimentSignalProvider).
            # Note: validate_strategy() emits a mixed-evidence warning for this type.
            ps = precomputed_signals or {}
            score_matrix = ps.get(
                "sentiment_score",
                pd.DataFrame(float("nan"), index=index, columns=close_matrix.columns),
            )
            rule = strategy.rules[0] if strategy.rules else None
            top_pct = (rule.top_pct if rule else None) or 0.1
            top_n   = (rule.top_n   if rule else None)
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction="top",
            )

        elif strategy.strategy_type == "insider_buying":
            # Rolling 30-day cluster-insider net-$ buying (InsiderSignalProvider).
            ps = precomputed_signals or {}
            score_matrix = ps.get(
                "insider_net_buy",
                pd.DataFrame(float("nan"), index=index, columns=close_matrix.columns),
            )
            rule = strategy.rules[0] if strategy.rules else None
            top_n   = (rule.top_n   if rule else None) or 20
            top_pct = (rule.top_pct if rule else None)
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=top_pct, rank_direction="top",
            )

        elif strategy.strategy_type == "multi_factor_composite":
            # Weighted composite of named factors.  Each factor is z-scored
            # cross-sectionally; contributions are combined by supplied weights.
            rule = strategy.rules[0] if strategy.rules else None
            fw: dict[str, float] = (rule.factor_weights if rule else None) or {}
            top_pct = (rule.top_pct if rule else None) or 0.1
            top_n   = (rule.top_n   if rule else None)
            ps = precomputed_signals or {}

            if fw:
                total_w = sum(abs(w) for w in fw.values()) or 1.0
                # Accumulate weighted z-scores; track total valid weight per cell
                numerator   = np.zeros((len(index), len(close_matrix.columns)))
                denominator = np.zeros_like(numerator)
                for factor_name, factor_w in fw.items():
                    raw = self._build_factor_score_matrix(factor_name, close_matrix, ps)
                    z   = raw.apply(self._zscore_row, axis=1).values
                    valid = ~np.isnan(z)
                    norm_w = factor_w / total_w
                    numerator   += np.where(valid, z * norm_w, 0.0)
                    denominator += np.where(valid, norm_w, 0.0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    composite_vals = np.where(
                        denominator > 0,
                        numerator / denominator,
                        float("nan"),
                    )
                composite = pd.DataFrame(composite_vals,
                                          index=index, columns=close_matrix.columns)
                weights = self._generate_cross_sectional_weights(
                    close_matrix, composite, rebalance_mask,
                    top_n=top_n, top_pct=top_pct, rank_direction="top",
                )
            # else: no factors → hold cash (weights remain all-zero)

        # ── PRD-13b portfolio overlays ────────────────────────────────────────

        elif strategy.strategy_type == "portfolio_defensive_overlay":
            # Per-holding MA filter. For each rebalance date and each holding:
            #   weight = target_weight if close > MA else 0 (goes to cash).
            # Target weights default to equal-weight if not provided.
            rule0 = strategy.rules[0] if strategy.rules else None
            window = (rule0.lookback_days if rule0 else None) or 200
            target_weights = strategy.position_sizing.weights or {}
            if not target_weights:
                # Default to equal-weight across the holdings the engine can see.
                visible = [s for s in strategy.universe if s in close_matrix.columns]
                if visible:
                    equal = 1.0 / len(visible)
                    target_weights = {s: equal for s in visible}
            for symbol in close_matrix.columns:
                target = float(target_weights.get(symbol, 0.0))
                if target <= 0.0:
                    continue
                ma = close_matrix[symbol].rolling(window=window).mean()
                in_position = close_matrix[symbol] > ma
                weights[symbol] = in_position.astype(float) * target

        elif strategy.strategy_type == "portfolio_rotation_overlay":
            # Rank holdings by N-month return; hold top-K equal-weight.
            # Same mechanic as momentum_rotation but the universe is the
            # user's book, not a template default.
            rule = strategy.rules[0] if strategy.rules else None
            lookback = (rule.ranking_lookback_days if rule else None) or 126
            top_n = (rule.top_n if rule else None)
            if top_n is None:
                top_n = min(3, len(strategy.universe))
            score_matrix = close_matrix / close_matrix.shift(lookback) - 1.0
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=None, rank_direction="top",
            )

        elif strategy.strategy_type == "portfolio_rebalance_overlay":
            # Apply target weights on every rebalance date. Mechanically
            # identical to static_allocation, but reads the user's holdings
            # via inherited_universe rather than a template's default list.
            for symbol, weight in (strategy.position_sizing.weights or {}).items():
                if symbol in weights.columns:
                    weights[symbol] = weight

        # ── PRD-13c portfolio overlay expansion ────────────────────────────────

        elif strategy.strategy_type == "portfolio_dual_momentum_overlay":
            # Rank holdings by relative momentum; only invest in those that also
            # pass an absolute momentum filter. Holdings that fail → cash.
            # If none pass both filters → portfolio is 100% cash.
            rule = strategy.rules[0] if strategy.rules else None
            ranking_lookback = (rule.ranking_lookback_days if rule else None) or 126
            absolute_lookback = (rule.lookback_days if rule else None) or 252
            top_n = (rule.top_n if rule else None)
            if top_n is None:
                top_n = min(3, len(strategy.universe))

            # Step 1: relative momentum ranking (same mechanic as rotation)
            score_matrix = close_matrix / close_matrix.shift(ranking_lookback) - 1.0
            weights = self._generate_cross_sectional_weights(
                close_matrix, score_matrix, rebalance_mask,
                top_n=top_n, top_pct=None, rank_direction="top",
            )

            # Step 2: absolute momentum filter — zero out any selected holding
            # whose trailing return over the absolute lookback is <= 0.
            absolute_returns = close_matrix.pct_change(absolute_lookback)
            for dt in weights.index[weights.sum(axis=1) > 0]:
                active = weights.columns[weights.loc[dt] > 0]
                for sym in active:
                    abs_ret = absolute_returns.loc[dt, sym]
                    if pd.isna(abs_ret) or abs_ret <= 0.0:
                        weights.loc[dt, sym] = 0.0

        elif strategy.strategy_type == "portfolio_defense_first_overlay":
            # Breadth-of-holdings regime check. Compute what fraction of holdings
            # are above their MA. If breadth >= threshold → full exposure.
            # If breadth < threshold → scale all positions by scale_down factor.
            rule = strategy.rules[0] if strategy.rules else None
            ma_window = (rule.lookback_days if rule else None) or 200
            breadth_threshold = (rule.threshold if rule else None) or 0.5
            scale_down = (rule.value if rule else None) or 0.5
            if not (0.0 < scale_down <= 1.0):
                scale_down = 0.5

            # Target weights (same pattern as rebalance: user's allocation)
            target_weights = strategy.position_sizing.weights or {}
            if not target_weights:
                visible = [s for s in strategy.universe if s in close_matrix.columns]
                if visible:
                    equal = 1.0 / len(visible)
                    target_weights = {s: equal for s in visible}

            # Apply target weights on every rebalance date
            for dt in index[rebalance_mask]:
                tw = {s: float(target_weights.get(s, 0.0))
                      for s in close_matrix.columns}
                total = sum(tw.values()) or 1.0
                for s, w in tw.items():
                    if s in weights.columns and w > 0:
                        weights.loc[dt, s] = w / total

            # Compute breadth: what fraction of target holdings are above their MA
            above_ma = pd.DataFrame(0.0, index=close_matrix.index,
                                    columns=close_matrix.columns)
            active_cols = [s for s in close_matrix.columns
                          if target_weights.get(s, 0) > 0]
            for sym in active_cols:
                ma = close_matrix[sym].rolling(window=ma_window).mean()
                above_ma[sym] = (close_matrix[sym] > ma).astype(float)
            breadth = above_ma[active_cols].sum(axis=1) / max(len(active_cols), 1)

            # Scale exposure when breadth is weak
            for dt in index[rebalance_mask]:
                if dt not in breadth.index:
                    continue
                b = breadth.loc[dt]
                if pd.notna(b) and b < breadth_threshold:
                    weights.loc[dt] = weights.loc[dt] * scale_down

        elif strategy.strategy_type == "portfolio_stability_tilt_overlay":
            # Weight each holding inversely to its trailing realized volatility.
            # Normalize so weights sum to 1.0 on each rebalance date.
            # Cap per-holding weight to avoid concentration in one calm name.
            rule = strategy.rules[0] if strategy.rules else None
            vol_window = (rule.lookback_days if rule else None) or 63
            max_weight = (rule.value if rule else None) or 0.25
            if not (0.0 < max_weight <= 1.0):
                max_weight = 0.25

            rets = close_matrix.pct_change().fillna(0.0)
            vol = rets.rolling(vol_window).std()

            for dt in index[rebalance_mask]:
                vols = vol.loc[dt].dropna()
                if vols.empty:
                    continue
                # Replace zero / near-zero vol with median to avoid div-by-zero
                vol_median = vols.median()
                if vol_median <= 0:
                    vol_median = vols[vols > 0].median()
                if pd.isna(vol_median) or vol_median <= 0:
                    continue
                vols = vols.replace(0.0, vol_median).clip(lower=vol_median * 0.1)
                inv_vol = 1.0 / vols
                raw_weights = inv_vol / inv_vol.sum()

                # Apply per-holding cap, redistributing excess proportionally
                for _ in range(10):  # converges in 2–3 iterations
                    excess_mask = raw_weights > max_weight
                    if not excess_mask.any():
                        break
                    excess = (raw_weights[excess_mask] - max_weight).sum()
                    raw_weights[excess_mask] = max_weight
                    denom = raw_weights[~excess_mask].sum()
                    if denom > 0:
                        raw_weights[~excess_mask] += excess * (
                            raw_weights[~excess_mask] / denom
                        )

                for sym, w in raw_weights.items():
                    if sym in weights.columns:
                        weights.loc[dt, sym] = w

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

        # ── Position-sizing overlay (applied after strategy logic is complete) ──

        ps_method = strategy.position_sizing.method
        if ps_method == "vol_target":
            target_vol = strategy.position_sizing.target_vol_annual or 0.10
            vol_window = 21  # trading-day window for realized-vol estimate
            # Daily portfolio return from raw (pre-scaled) weights, using a 1-day
            # lag so vol is estimated from past data only (no look-ahead bias).
            asset_rets = close_matrix.pct_change().fillna(0.0)
            raw_port_ret = (weights.shift(1).fillna(0.0) * asset_rets).sum(axis=1)
            # Annualized realized vol over trailing vol_window days
            realized_vol = raw_port_ret.rolling(vol_window).std() * np.sqrt(252)
            # Scale: target / realized, capped at 1.0 (long-only; no leverage)
            scale = (target_vol / realized_vol.replace(0.0, np.nan)).clip(upper=1.0)
            # During warmup window: ffill then fall back to 1.0 (full allocation)
            scale = scale.ffill().fillna(1.0)
            weights = weights.mul(scale, axis=0)
            # Defensively re-normalize (scale <= 1 guarantees sum still <= 1,
            # but floating-point drift could push a row marginally over)
            exposure = weights.sum(axis=1)
            over_vol = exposure > 1.0
            if over_vol.any():
                weights.loc[over_vol] = weights.loc[over_vol].div(exposure[over_vol], axis=0)

        elif ps_method == "signal_weighted":
            # TODO: implement signal-weighted position sizing
            raise NotImplementedError(
                "signal_weighted position sizing is not yet implemented."
            )
        # "equal_weight" and "fixed_weight": no overlay — strategy logic already
        # handles allocation; PositionSizing fields are used by the parser/validator.

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

    async def _check_microcap(self, strategy: StrategyJSON, db: Session) -> list[str]:
        """
        For pead_drift strategies: warn if the universe consists of microcaps
        (average market cap from the symbols table < $300M).
        """
        from sqlalchemy import text
        try:
            placeholders = ", ".join(f":s{i}" for i in range(len(strategy.universe)))
            params = {f"s{i}": sym for i, sym in enumerate(strategy.universe)}
            rows = db.execute(
                text(f"SELECT market_cap FROM symbols WHERE symbol IN ({placeholders})"),
                params,
            ).fetchall()
            caps = [float(r[0]) for r in rows if r[0] is not None]
            if caps:
                avg_cap = sum(caps) / len(caps)
                if avg_cap < 300_000_000:
                    return [
                        f"PEAD drift with microcap universe "
                        f"(avg market cap ${avg_cap / 1e6:.0f}M < $300M threshold): "
                        "SUE signals can be noisy for small companies and "
                        "execution may be challenging due to liquidity constraints."
                    ]
        except Exception as exc:
            logger.debug("Microcap check failed: %s", exc)
        return []

    async def run(self, db: Session, strategy: StrategyJSON) -> BacktestResult:
        # PRD-13b: For portfolio overlays, the user's holdings (inherited_universe)
        # ARE the universe. Swap once at the top so every downstream helper
        # (_load_prices, _generate_weights, _check_microcap, trade log, etc.)
        # reads the right set of tickers without each branch needing to know.
        if (
            strategy.strategy_type in PORTFOLIO_OVERLAY_TYPES
            and strategy.inherited_universe
        ):
            strategy = strategy.model_copy(
                update={"universe": list(strategy.inherited_universe)}
            )

        warnings = list(validate_strategy(strategy))

        # Microcap warning for PEAD strategies (requires DB access)
        if strategy.strategy_type == "pead_drift":
            warnings.extend(await self._check_microcap(strategy, db))

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

        # Pre-fetch fundamental/event signals before generating weights (async step)
        precomputed_signals: dict[str, pd.DataFrame] = {}
        if strategy.strategy_type in _FUNDAMENTAL_STRATEGY_TYPES:
            from app.services.backtester.signal_provider import (
                EarningsEventSignalProvider,
                FundamentalSignalProvider,
            )

            def _build_providers(stype: str) -> list:
                if stype == "value_composite":
                    return [FundamentalSignalProvider(s)
                            for s in ("fcf_yield", "book_to_market", "ebitda_ev")]
                if stype == "quality_piotroski":
                    return [FundamentalSignalProvider("f_score")]
                if stype == "buyback_yield":
                    return [FundamentalSignalProvider("buyback_yield_ttm")]
                if stype == "pead_drift":
                    return [EarningsEventSignalProvider()]
                if stype == "earnings_revision":
                    return [FundamentalSignalProvider("estimate_revision_3m")]
                if stype == "news_sentiment_momentum":
                    from app.services.backtester.signal_provider import SentimentSignalProvider
                    return [SentimentSignalProvider()]
                if stype == "insider_buying":
                    from app.services.backtester.signal_provider import InsiderSignalProvider
                    return [InsiderSignalProvider()]
                if stype == "multi_factor_composite":
                    rule0 = strategy.rules[0] if strategy.rules else None
                    fw = (rule0.factor_weights if rule0 else None) or {}
                    providers_for_composite = []
                    if "value_composite" in fw:
                        providers_for_composite += [
                            FundamentalSignalProvider(s)
                            for s in ("fcf_yield", "book_to_market", "ebitda_ev")
                        ]
                    if "quality_f_score" in fw:
                        providers_for_composite.append(FundamentalSignalProvider("f_score"))
                    # momentum_12_1 and low_volatility are price-derived — no providers needed
                    # Dedup by name (avoids fetching the same signal twice)
                    seen: set[str] = set()
                    deduped = []
                    for p in providers_for_composite:
                        if p.name not in seen:
                            seen.add(p.name)
                            deduped.append(p)
                    return deduped
                return []

            providers = _build_providers(strategy.strategy_type)

            # PEAD: limited ffill so positions expire after holding_window_days
            ffill_limit: Optional[int] = None
            if strategy.strategy_type == "pead_drift":
                rule0 = strategy.rules[0] if strategy.rules else None
                ffill_limit = (rule0.holding_window_days if rule0 else None) or 60

            # 2-year pre-strategy window captures prior disclosures / earnings
            signal_start = strategy.start_date - timedelta(days=2 * 365)
            precomputed_signals = await self._fetch_signal_matrix(
                providers,
                strategy.universe,
                db,
                close_matrix.index,
                signal_start,
                strategy.end_date,
                ffill_limit=ffill_limit,
            )

        weights = self._generate_weights(strategy, close_matrix, aligned_frames, precomputed_signals)
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
