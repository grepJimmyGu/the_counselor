"""PortfolioDiagnosisService — Portfolio Mode (PRD-13b).

Composes existing services to produce a `PortfolioDiagnosis` for an
arbitrary list of holdings:

  * `FundamentalService.get_profile/get_key_metrics` → sector + beta +
    market cap + P/E + ROE
  * `PriceDataService.get_price_frame` → daily-close history for vol,
    drawdown, 12-1m momentum
  * `compute_asset_behavior_fingerprint` → per-holding behavior bucket
    that we roll up into a portfolio aggregate

The service degrades gracefully on missing data (None values, caveats
list) rather than raising — diagnosis is a non-blocking dashboard, not
an alpha signal.

Reusability: future modes that ingest a list of tickers (Mode 1's
single-holding case is just N=1; a future watchlist diagnosis is N>1)
can call `diagnose()` with the same Holding shape.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.schemas.fundamental import CompanyProfile, KeyMetrics
from app.schemas.portfolio import (
    BehaviorAggregate,
    FactorExposure,
    Holding,
    OverlayKind,
    OverlayRecommendation,
    PortfolioDiagnosis,
    SectorBreakdown,
    StyleMix,
)
from app.services.asset_behavior_service import (
    BROAD_ETFS,
    COMMODITY_ETFS,
    SECTOR_ETFS,
    classify_asset_type,
    compute_asset_behavior_fingerprint,
)
from app.services.fundamental_service import FundamentalService
from app.services.price_data_service import PriceDataService


# ── Style classification ─────────────────────────────────────────────────────

# Lifted from typical GICS-style buckets. Defensive sectors are the
# textbook "low cyclicality" trio; macro-sensitive are the cyclicals +
# rate-sensitive. Anything not listed falls into `growth` (the catch-all
# for non-defensive equities, since most US large-caps trade as growth).

_DEFENSIVE_SECTORS = frozenset({
    "Consumer Defensive", "Consumer Staples",
    "Healthcare", "Health Care",
    "Utilities",
})

_MACRO_SECTORS = frozenset({
    "Financial Services", "Financials",
    "Energy",
    "Basic Materials", "Materials",
    "Industrials", "Real Estate",
})


def _bucket_for_holding(
    ticker: str,
    profile: Optional[CompanyProfile],
    metrics: Optional[KeyMetrics],
) -> str:
    """Return one of the StyleBucket literal values or 'unclassified'."""
    if not ticker:
        return "unclassified"
    asset_type = classify_asset_type(ticker)
    if asset_type == "commodity_etf":
        return "commodity"
    if asset_type in ("broad_etf", "sector_etf"):
        # Treat ETFs as defensive only if they're the explicit defensive
        # sector slice; otherwise they ride macro cycles.
        if ticker in {"XLP", "XLU", "XLV"}:
            return "defensive"
        return "macro_sensitive"
    if profile is None:
        return "unclassified"
    sector = profile.sector or ""
    if sector in _DEFENSIVE_SECTORS:
        return "defensive"
    if sector in _MACRO_SECTORS:
        return "macro_sensitive"
    # Single-stock value tilt: low P/E + high FCF yield. Otherwise growth.
    pe = (metrics.pe_ratio if metrics else None) or (profile.pe_ratio)
    fcf_y = metrics.free_cash_flow_yield if metrics else None
    if pe is not None and 0 < pe < 12 and (fcf_y is None or fcf_y > 0.06):
        return "value"
    return "growth"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_holding_weights(holdings: list[Holding]) -> dict[str, float]:
    """Resolve `weight` vs `shares` per the Holding contract and normalize
    to a {ticker -> weight} dict summing to 1.0.

    Precedence: explicit `weight` wins. If only `shares` is provided,
    the share counts become relative weights (we don't know prices yet
    at this stage; the diagnosis treats share counts as proportional
    exposures, which is a reasonable approximation when most holdings
    trade in similar price ranges and the user is using the field as a
    relative-sizing hint rather than a P&L source of truth).
    """
    weights: dict[str, float] = {}
    for h in holdings:
        w = h.weight if h.weight is not None else (h.shares or 0.0)
        weights[h.ticker] = weights.get(h.ticker, 0.0) + float(w)
    total = sum(weights.values())
    if total <= 0:
        # Falls back to equal weights so the diagnosis still produces a
        # sensible answer rather than zero-division-ing through every calc.
        n = len(weights) or 1
        return {t: 1.0 / n for t in weights}
    return {t: w / total for t, w in weights.items()}


def _weighted_mean(values: dict[str, float], weights: dict[str, float]) -> Optional[float]:
    """Weight-average of `values`, treating missing keys as exclusions."""
    num = 0.0
    den = 0.0
    for t, v in values.items():
        w = weights.get(t)
        if w is None or v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        num += float(v) * float(w)
        den += float(w)
    if den <= 0:
        return None
    return num / den


def _zscore(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional z-score of the supplied values (skip NaNs)."""
    arr = np.array([v for v in values.values() if v is not None and not math.isnan(v)])
    if arr.size < 2:
        return {t: 0.0 for t in values}
    mu = float(arr.mean())
    sigma = float(arr.std(ddof=0)) or 1.0
    return {t: (float(v) - mu) / sigma if v is not None else 0.0 for t, v in values.items()}


# ── Service ──────────────────────────────────────────────────────────────────


class PortfolioDiagnosisService:
    """Composes existing services into a single PortfolioDiagnosis payload."""

    def __init__(
        self,
        fundamental_service: Optional[FundamentalService] = None,
        price_data_service: Optional[PriceDataService] = None,
    ) -> None:
        self._fundamental = fundamental_service or FundamentalService()
        self._prices = price_data_service or PriceDataService()

    async def diagnose(
        self,
        db: Session,
        holdings: list[Holding],
    ) -> PortfolioDiagnosis:
        if not holdings:
            raise ValueError("PortfolioDiagnosisService.diagnose requires at least 1 holding")

        norm_weights = _normalize_holding_weights(holdings)
        tickers = list(norm_weights.keys())
        caveats: list[str] = []

        # 1. Fundamentals + sector / beta (one fetch per unique ticker)
        profiles: dict[str, Optional[CompanyProfile]] = {}
        metrics_map: dict[str, Optional[KeyMetrics]] = {}
        for t in tickers:
            try:
                profiles[t] = await self._fundamental.get_profile(db, t)
            except Exception:
                profiles[t] = None
            try:
                metrics_map[t] = await self._fundamental.get_key_metrics(db, t)
            except Exception:
                metrics_map[t] = None

        # 2. Price history per holding (~6yr; behavior fingerprint reuses
        # this same window). Service caches via PriceCacheService.
        today = date.today()
        history_start = today - timedelta(days=int(365.25 * 5) + 30)
        # Fetch a slightly longer window for the 12-1m momentum sub-factor
        # so the first day of the 5y window has a 252-day return defined.
        fetch_start = history_start - timedelta(days=365)
        price_frames: dict[str, pd.DataFrame] = {}
        for t in tickers:
            try:
                price_frames[t] = await self._prices.get_price_frame(
                    db, t, start_date=fetch_start, end_date=today, lookback_days=0,
                )
            except Exception:
                price_frames[t] = pd.DataFrame()

        # 3. Style mix
        style = self._compute_style_mix(tickers, norm_weights, profiles, metrics_map)

        # 4. Sector breakdown
        sectors = self._compute_sector_breakdown(norm_weights, profiles)

        # 5. Behavior aggregate (per-ticker fingerprint, weight-averaged)
        behavior = self._compute_behavior(tickers, norm_weights, price_frames, caveats)

        # 6. Factor exposure (weighted, where data exists)
        factor_exp = self._compute_factor_exposure(
            tickers, norm_weights, profiles, metrics_map, price_frames,
        )

        # 7. Portfolio-level vol + drawdown over trailing 5y at current weights
        realized_vol, max_dd = self._compute_portfolio_risk(
            norm_weights, price_frames, today, caveats,
        )

        return PortfolioDiagnosis(
            n_holdings=len(tickers),
            style_mix=style,
            factor_exposure=factor_exp,
            behavior=behavior,
            sectors=sectors,
            realized_vol_1y=realized_vol,
            max_drawdown_5y=max_dd,
            caveats=caveats,
        )

    # ── Recommendation logic ─────────────────────────────────────────────

    def recommend_overlays(self, diag: PortfolioDiagnosis) -> list[OverlayRecommendation]:
        """Pick a rank-ordered set of 3 overlay recommendations.

        Simple heuristic — no ML. Each overlay has a fit score; we sort
        and produce a 1/2/3 ranking with a one-line reason.
        """
        scores: dict[OverlayKind, float] = {
            "defensive": 0.0,
            "rotation": 0.0,
            "rebalance": 0.0,
        }
        reasons: dict[OverlayKind, str] = {
            "defensive": "",
            "rotation": "",
            "rebalance": "",
        }

        # Defensive fit ↑ when book is concentrated, vol-heavy, or trending
        # weak. Trending names benefit from MA filters most.
        if diag.max_drawdown_5y is not None and diag.max_drawdown_5y < -0.25:
            scores["defensive"] += 1.2
        if diag.behavior.trending_pct >= 0.4:
            scores["defensive"] += 0.8
        if diag.realized_vol_1y is not None and diag.realized_vol_1y > 0.22:
            scores["defensive"] += 0.6
        reasons["defensive"] = (
            "Caps losses by selling holdings that break their trend; "
            "best when drawdown control matters more than upside capture."
        )

        # Rotation fit ↑ when there are enough names to rank (≥3) and
        # behavior aggregate skews trending.
        if diag.n_holdings >= 3:
            scores["rotation"] += 0.6
        scores["rotation"] += float(diag.behavior.trending_pct)
        if diag.n_holdings >= 5:
            scores["rotation"] += 0.3
        reasons["rotation"] = (
            "Rebalances monthly into the top-3 holdings by 6-month return; "
            "best for following strength within your existing book."
        )

        # Rebalance fit ↑ when the book has clear target weights to
        # restore — i.e. when no single holding dominates.
        if diag.n_holdings >= 2:
            scores["rebalance"] += 0.5
        # Penalize when book is single-name or concentration is extreme;
        # heuristic only — no Herfindahl computation needed here.
        if diag.n_holdings >= 4:
            scores["rebalance"] += 0.3
        reasons["rebalance"] = (
            "Periodically re-weights back to your target allocation; "
            "best for keeping discipline without timing the market."
        )

        ordered: list[OverlayKind] = sorted(scores, key=lambda k: -scores[k])
        return [
            OverlayRecommendation(overlay=ok, rank=i + 1, reason=reasons[ok])
            for i, ok in enumerate(ordered)
        ]

    # ── Internal computations ────────────────────────────────────────────

    def _compute_style_mix(
        self,
        tickers: list[str],
        weights: dict[str, float],
        profiles: dict[str, Optional[CompanyProfile]],
        metrics_map: dict[str, Optional[KeyMetrics]],
    ) -> StyleMix:
        buckets: dict[str, float] = {
            "growth": 0.0, "value": 0.0, "defensive": 0.0,
            "commodity": 0.0, "macro_sensitive": 0.0,
        }
        unclassified = 0.0
        for t in tickers:
            bucket = _bucket_for_holding(t, profiles.get(t), metrics_map.get(t))
            w = weights.get(t, 0.0)
            if bucket == "unclassified":
                unclassified += w
            else:
                buckets[bucket] = buckets.get(bucket, 0.0) + w
        return StyleMix(
            growth=buckets["growth"],
            value=buckets["value"],
            defensive=buckets["defensive"],
            commodity=buckets["commodity"],
            macro_sensitive=buckets["macro_sensitive"],
            unclassified_weight=unclassified,
        )

    def _compute_sector_breakdown(
        self,
        weights: dict[str, float],
        profiles: dict[str, Optional[CompanyProfile]],
    ) -> SectorBreakdown:
        sectors: dict[str, float] = {}
        unknown = 0.0
        for t, w in weights.items():
            prof = profiles.get(t)
            sector = (prof.sector if prof else None) or ""
            if not sector:
                unknown += w
            else:
                sectors[sector] = sectors.get(sector, 0.0) + w
        return SectorBreakdown(sectors=sectors, unknown_sector_weight=unknown)

    def _compute_behavior(
        self,
        tickers: list[str],
        weights: dict[str, float],
        price_frames: dict[str, pd.DataFrame],
        caveats: list[str],
    ) -> BehaviorAggregate:
        # Per-holding fingerprint → bucket → weighted aggregate.
        # asset_behavior_service handles small / empty inputs (returns
        # `mixed` + insufficient data quality) so we never raise here.
        bucket_weights = {"trending": 0.0, "mean_reverting": 0.0, "mixed": 0.0}
        insufficient = 0
        for t in tickers:
            frame = price_frames.get(t, pd.DataFrame())
            if frame.empty or "adjusted_close" not in frame.columns:
                fingerprint = compute_asset_behavior_fingerprint(t, prices=None)  # type: ignore[arg-type]
                insufficient += 1
            else:
                prices = frame["adjusted_close"].astype(float)
                fingerprint = compute_asset_behavior_fingerprint(t, prices=prices)
            w = weights.get(t, 0.0)
            # Map current_regime → bucket. Regimes other than trending or
            # range_bound collapse to mixed for the portfolio rollup.
            if fingerprint.current_regime == "trending":
                bucket_weights["trending"] += w
            elif fingerprint.current_regime == "range_bound":
                bucket_weights["mean_reverting"] += w
            else:
                bucket_weights["mixed"] += w
        if insufficient and insufficient >= max(1, len(tickers) // 3):
            caveats.append(
                f"{insufficient} of {len(tickers)} holdings have limited price history; "
                "behavior estimates may be noisy."
            )
        return BehaviorAggregate(
            trending_pct=bucket_weights["trending"],
            mean_reverting_pct=bucket_weights["mean_reverting"],
            mixed_pct=bucket_weights["mixed"],
        )

    def _compute_factor_exposure(
        self,
        tickers: list[str],
        weights: dict[str, float],
        profiles: dict[str, Optional[CompanyProfile]],
        metrics_map: dict[str, Optional[KeyMetrics]],
        price_frames: dict[str, pd.DataFrame],
    ) -> FactorExposure:
        # Per-ticker raw factor values (None when missing). Z-score
        # cross-sectionally so values are comparable across the book.
        raw_size: dict[str, float] = {}
        raw_value: dict[str, float] = {}
        raw_momentum: dict[str, float] = {}
        raw_quality: dict[str, float] = {}
        raw_lowvol: dict[str, float] = {}
        raw_beta: dict[str, float] = {}

        for t in tickers:
            prof = profiles.get(t)
            metr = metrics_map.get(t)
            frame = price_frames.get(t, pd.DataFrame())

            if prof and prof.market_cap and prof.market_cap > 0:
                raw_size[t] = math.log(prof.market_cap)
            pe = (metr.pe_ratio if metr else None) or (prof.pe_ratio if prof else None)
            if pe and pe > 0:
                raw_value[t] = -float(pe)  # cheap (low P/E) → high value
            if metr and metr.roe is not None:
                raw_quality[t] = float(metr.roe)
            if prof and prof.beta is not None:
                raw_beta[t] = float(prof.beta)

            if not frame.empty and "adjusted_close" in frame.columns:
                prices = frame["adjusted_close"].astype(float).dropna()
                if len(prices) >= 273:
                    # 12-1m return: cumulative return from t-252 to t-21
                    p_now = prices.iloc[-21]
                    p_then = prices.iloc[-273]
                    if p_then > 0:
                        raw_momentum[t] = float(p_now / p_then - 1.0)
                if len(prices) >= 252:
                    rets = prices.pct_change().tail(252).dropna()
                    if not rets.empty:
                        raw_lowvol[t] = -float(rets.std() * math.sqrt(252))

        # Z-score then weight-mean each factor (skip None / missing).
        size_z = _zscore(raw_size)
        value_z = _zscore(raw_value)
        momo_z = _zscore(raw_momentum)
        qual_z = _zscore(raw_quality)
        lowvol_z = _zscore(raw_lowvol)

        return FactorExposure(
            size=_weighted_mean(size_z, weights),
            value=_weighted_mean(value_z, weights),
            momentum=_weighted_mean(momo_z, weights),
            quality=_weighted_mean(qual_z, weights),
            low_vol=_weighted_mean(lowvol_z, weights),
            beta_to_spy=_weighted_mean(raw_beta, weights),
        )

    def _compute_portfolio_risk(
        self,
        weights: dict[str, float],
        price_frames: dict[str, pd.DataFrame],
        as_of: date,
        caveats: list[str],
    ) -> tuple[Optional[float], Optional[float]]:
        # Build a price matrix of holdings that have data, align on a
        # common index, and simulate the portfolio as fixed-weight
        # (daily rebalanced; close enough for a diagnosis summary).
        series_list: list[pd.Series] = []
        ticker_order: list[str] = []
        for t, w in weights.items():
            frame = price_frames.get(t, pd.DataFrame())
            if frame.empty or "adjusted_close" not in frame.columns:
                continue
            s = frame["adjusted_close"].astype(float).dropna()
            if s.empty:
                continue
            series_list.append(s.rename(t))
            ticker_order.append(t)

        if not series_list:
            caveats.append("No holdings have price history; vol and drawdown unavailable.")
            return None, None

        df = pd.concat(series_list, axis=1).dropna(how="all").ffill().dropna()
        if df.empty:
            return None, None

        five_y_ago = pd.Timestamp(as_of) - pd.Timedelta(days=int(365.25 * 5))
        df = df[df.index >= five_y_ago]
        if df.empty:
            return None, None

        # Normalize weights to the in-data subset.
        sub_w = {t: weights[t] for t in ticker_order}
        sub_total = sum(sub_w.values()) or 1.0
        norm_w = pd.Series({t: w / sub_total for t, w in sub_w.items()})

        returns = df.pct_change().fillna(0.0)
        port_returns = (returns * norm_w).sum(axis=1)
        equity = (1.0 + port_returns).cumprod()

        # 1y annualized vol from trailing 252 observations
        tail = port_returns.tail(252)
        realized_vol = (
            float(tail.std() * math.sqrt(252)) if len(tail) >= 50 else None
        )

        # Max drawdown over the trailing 5y window we built
        if equity.empty:
            return realized_vol, None
        running_max = equity.cummax()
        drawdown = equity / running_max - 1.0
        max_dd = float(drawdown.min()) if not drawdown.empty else None

        return realized_vol, max_dd
