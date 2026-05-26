"""Asset Behavior Fingerprint service — Module 2 (2026-05-26).

A lightweight diagnosis layer for the strategy picker. Given a symbol and a
daily-close price series, returns a plain-English "fingerprint" describing how
the asset has tended to behave (trending vs. mean-reverting), its recent and
long-run realised volatility, max drawdown over the last five years, the
current regime, and a short implication for strategy selection.

This is NOT a forward-looking model and NOT an alpha signal. It exists purely
to help retail users pick a strategy family (trend / mean-reversion / risk
overlays) that matches the asset's historical character. The implication
strings are written to avoid any "buy/sell" verbs or forward-looking claims.

Calculation is intentionally simple and transparent:

  * trending_pct        — % of valid 200-day rolling windows where price is
                          above its 200-day MA AND the MA slope is positive.
  * mean_reverting_pct  — % of |z| > 1.5 extremes (60-day rolling z-score)
                          that revert toward the mean within 10 trading days.
  * realized_vol_1y/5y  — annualised stdev of daily returns (last 252 / 1260).
  * max_drawdown_5y     — min of (price / running_max) - 1 over last 5 years.
  * current_regime      — rule-based classification from the above.
  * data_quality        — bucketed by row count (good / limited / insufficient).

The service operates on a plain pandas Series so it has no DB dependency and
is trivial to unit-test. The route layer (apps/api/app/api/routes/asset_behavior.py)
fetches prices via PriceDataService and feeds them in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

# ── Asset-type heuristics ───────────────────────────────────────────────────
# Keep these sets explicit and tight per the Module 2 spec. Adding new ETFs is
# encouraged; the catch-all is single_stock so a missing entry never errors.

BROAD_ETFS = frozenset({"SPY", "QQQ", "VTI", "IWM", "DIA"})
SECTOR_ETFS = frozenset({
    "XLE", "XLF", "XLK", "XLV", "XLY",
    "XLP", "XLU", "XLI", "XLB", "XLRE", "XLC",
})
COMMODITY_ETFS = frozenset({
    "GLD", "SLV", "USO", "UNG", "DBC", "DBA", "DBB", "CPER",
})

# Valid asset_type / regime / data_quality values, kept here so the route + the
# frontend TS contract can mirror the same source of truth.

ASSET_TYPES = (
    "single_stock", "commodity_etf", "broad_etf", "sector_etf",
    "pair", "basket", "unknown",
)
CURRENT_REGIMES = ("trending", "range_bound", "volatile", "mixed")
DATA_QUALITIES = ("good", "limited", "insufficient")


def classify_asset_type(symbol: str) -> str:
    """Return one of ASSET_TYPES from a single-ticker string.

    Pair / basket / unknown are reserved for higher-level entry paths that
    aren't single tickers — those route layers pass them in explicitly.
    """
    if not symbol or not isinstance(symbol, str):
        return "unknown"
    s = symbol.upper().strip()
    if not s:
        return "unknown"
    if s in BROAD_ETFS:
        return "broad_etf"
    if s in SECTOR_ETFS:
        return "sector_etf"
    if s in COMMODITY_ETFS:
        return "commodity_etf"
    return "single_stock"


# ── Calculation helpers ─────────────────────────────────────────────────────

_TRADING_DAYS_PER_YEAR = 252
_MIN_RETURNS_FOR_VOL = 20         # need at least 20 daily returns for a vol number
_TRENDING_MA_WINDOW = 200         # 200-day MA — the canonical retail trend filter
_TRENDING_SLOPE_WINDOW = 20       # compare MA vs MA[-20] to bucket "rising / falling"
_MR_ZSCORE_WINDOW = 60            # 60-day rolling for the z-score
_MR_ZSCORE_THRESHOLD = 1.5        # |z| > 1.5 is "extreme"
_MR_REVERT_WINDOW = 10            # gives 10 trading days for the spread to mean-revert
_MR_REVERT_TARGET_Z = 0.5         # "back toward the mean" = |z| < 0.5 inside the window
_MR_MIN_EVENTS = 5                # any fewer extremes and the % is too noisy to publish

_VOL_HIGH_THRESHOLD = 0.40        # 40% annualised stdev → "volatile" regime
_VOL_SPIKE_RATIO = 1.5            # 1y vol > 1.5× 5y vol → "volatile" regime
_TRENDING_HIGH_PCT = 60.0         # trending_pct > 60% AND not volatile → trending
_MR_HIGH_PCT = 60.0               # MR pct > 60% AND trending_pct < 40% → range_bound
_TRENDING_LOW_PCT = 40.0          # lower cap for range_bound classification


def compute_realized_vol(returns: pd.Series, periods: int) -> Optional[float]:
    """Annualised stdev of daily returns over the last `periods` rows.

    Returns None when fewer than _MIN_RETURNS_FOR_VOL rows exist in the window
    so we never surface a misleadingly precise number from a tiny sample.
    """
    if returns is None or len(returns) == 0:
        return None
    window = returns.tail(periods).dropna()
    if len(window) < _MIN_RETURNS_FOR_VOL:
        return None
    return float(window.std(ddof=1) * math.sqrt(_TRADING_DAYS_PER_YEAR))


def compute_max_drawdown(prices: pd.Series) -> Optional[float]:
    """Max drawdown over the given price slice, as a negative decimal (−0.32 == −32%)."""
    if prices is None or len(prices) < _MIN_RETURNS_FOR_VOL:
        return None
    running_max = prices.cummax()
    drawdown = (prices - running_max) / running_max
    dd_min = drawdown.min()
    return float(dd_min) if pd.notna(dd_min) else None


def classify_data_quality(prices: pd.Series) -> str:
    """Bucket by row count — see module docstring for thresholds."""
    n = 0 if prices is None else int(len(prices))
    if n < _TRADING_DAYS_PER_YEAR:
        return "insufficient"
    if n < _TRADING_DAYS_PER_YEAR * 3:
        return "limited"
    return "good"


def compute_trending_pct(prices: pd.Series, window: int = _TRENDING_MA_WINDOW) -> Optional[float]:
    """% of valid 200-day windows where price > MA(200) AND MA slope > 0.

    A "valid" window is one where both the MA and its 20-day-lagged version
    exist (so the slope is well-defined). Returns None when fewer than ~20
    valid windows are available — same noise-floor logic as realized vol.
    """
    if prices is None or len(prices) < window + _TRENDING_SLOPE_WINDOW + _MIN_RETURNS_FOR_VOL:
        return None
    ma = prices.rolling(window).mean()
    slope = ma - ma.shift(_TRENDING_SLOPE_WINDOW)
    is_trending = (prices > ma) & (slope > 0)
    valid_mask = ma.notna() & slope.notna()
    valid_count = int(valid_mask.sum())
    if valid_count < _MIN_RETURNS_FOR_VOL:
        return None
    trending_count = int((is_trending & valid_mask).sum())
    return round(100.0 * trending_count / valid_count, 1)


def compute_mean_reverting_pct(
    prices: pd.Series,
    window: int = _MR_ZSCORE_WINDOW,
    z_threshold: float = _MR_ZSCORE_THRESHOLD,
    revert_window: int = _MR_REVERT_WINDOW,
) -> Optional[float]:
    """% of |z| > 1.5 extreme events (60-day window) that revert within 10 days.

    Reversion = the future z-score crosses (or passes through) ±0.5 of the
    mean within the next `revert_window` trading days. Returns None when
    there are fewer than _MR_MIN_EVENTS extremes in the window — too few
    to publish a meaningful percentage.
    """
    if prices is None or len(prices) < window + revert_window + _MIN_RETURNS_FOR_VOL:
        return None
    rolling_mean = prices.rolling(window).mean()
    rolling_std = prices.rolling(window).std(ddof=1)
    zscore = (prices - rolling_mean) / rolling_std
    zscore = zscore.replace([float("inf"), float("-inf")], pd.NA).dropna()
    if len(zscore) == 0:
        return None
    extremes = zscore[zscore.abs() > z_threshold]
    if len(extremes) < _MR_MIN_EVENTS:
        return None

    n_reverted = 0
    n_eligible = 0
    z_index = zscore.index
    for ts, z_val in extremes.items():
        # Locate position in the (cleaned) z-score series so future-slice
        # arithmetic is exact, not date-offset (which is brittle around
        # weekends + holidays).
        try:
            pos = z_index.get_loc(ts)
        except KeyError:
            continue
        # `pos` may be an int or slice; the inputs guarantee uniqueness so
        # we always get a scalar here, but defend anyway.
        if not isinstance(pos, (int,)):
            continue
        future_slice = zscore.iloc[pos + 1 : pos + 1 + revert_window]
        if len(future_slice) == 0:
            continue
        n_eligible += 1
        if z_val > 0:
            if (future_slice < _MR_REVERT_TARGET_Z).any():
                n_reverted += 1
        else:
            if (future_slice > -_MR_REVERT_TARGET_Z).any():
                n_reverted += 1

    if n_eligible < _MR_MIN_EVENTS:
        return None
    return round(100.0 * n_reverted / n_eligible, 1)


def classify_current_regime(
    trending_pct: Optional[float],
    mean_reverting_pct: Optional[float],
    realized_vol_1y: Optional[float],
    realized_vol_5y: Optional[float],
) -> str:
    """Bucket current regime per the simple, transparent rules in the module docstring.

    Order of precedence:
      1. volatile — when 1y vol is high in absolute terms OR much higher than
         the asset's own 5y baseline. We classify volatile FIRST so the
         strategy_implication can warn about turnover even on a trending
         tape.
      2. trending — when trending_pct is comfortably above 60% and we did not
         already classify volatile.
      3. range_bound — when mean-reversion is high AND trending is low.
      4. mixed — fallback (also covers the "all metrics null" case).
    """
    if realized_vol_1y is not None and realized_vol_1y > _VOL_HIGH_THRESHOLD:
        return "volatile"
    if (
        realized_vol_1y is not None
        and realized_vol_5y is not None
        and realized_vol_5y > 0
        and realized_vol_1y > _VOL_SPIKE_RATIO * realized_vol_5y
    ):
        return "volatile"
    if trending_pct is not None and trending_pct > _TRENDING_HIGH_PCT:
        return "trending"
    if (
        mean_reverting_pct is not None
        and mean_reverting_pct > _MR_HIGH_PCT
        and (trending_pct is None or trending_pct < _TRENDING_LOW_PCT)
    ):
        return "range_bound"
    return "mixed"


def build_strategy_implication(
    asset_type: str,
    current_regime: str,
    data_quality: str,
    trending_pct: Optional[float],
    mean_reverting_pct: Optional[float],
    realized_vol_1y: Optional[float],
) -> str:
    """Return a single short plain-English implication string.

    Deliberately avoids buy/sell verbs and forward-looking claims (per the
    Module 2 spec — this is a strategy-family suggestion, not a trade idea).
    The data_quality=insufficient case short-circuits and never speculates.
    """
    if data_quality == "insufficient":
        return "There is not enough history to diagnose this asset reliably."

    bits = []
    if current_regime == "trending":
        bits.append("This asset has behaved like a trending asset.")
        bits.append("Trend-following, momentum, or breakout strategies may fit better than short-term mean reversion.")
    elif current_regime == "range_bound":
        bits.append("This asset has often reverted after short-term extremes.")
        bits.append("Mean-reversion strategies may be worth testing.")
    elif current_regime == "volatile":
        bits.append("This asset is currently in a high-volatility regime.")
        bits.append("Use risk controls and avoid strategies with excessive turnover.")
    else:  # mixed
        bits.append("This asset shows a mixed behavior pattern with no clear regime.")
        bits.append("Diversified or rules-based templates may fit better than a single-style strategy.")

    # Tack on a volatility caveat for trending/range_bound assets that are
    # also high-vol — the regime label says "trending" but the user still
    # needs to know the swings are large.
    if (
        current_regime in ("trending", "range_bound")
        and realized_vol_1y is not None
        and realized_vol_1y > _VOL_HIGH_THRESHOLD
    ):
        bits.append("Note: realised volatility is high — size positions and stops accordingly.")

    return " ".join(bits)


# ── Public dataclass — what the route returns ───────────────────────────────

@dataclass
class AssetBehaviorFingerprint:
    """The full diagnosis payload. Mirrored 1-to-1 by the FE TS contract."""

    symbol: str
    asset_type: str
    trending_pct: Optional[float]
    mean_reverting_pct: Optional[float]
    realized_vol_1y: Optional[float]
    realized_vol_5y: Optional[float]
    max_drawdown_5y: Optional[float]
    current_regime: str
    data_quality: str
    strategy_implication: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "trending_pct": self.trending_pct,
            "mean_reverting_pct": self.mean_reverting_pct,
            "realized_vol_1y": self.realized_vol_1y,
            "realized_vol_5y": self.realized_vol_5y,
            "max_drawdown_5y": self.max_drawdown_5y,
            "current_regime": self.current_regime,
            "data_quality": self.data_quality,
            "strategy_implication": self.strategy_implication,
        }


def compute_asset_behavior_fingerprint(
    symbol: str,
    prices: pd.Series,
    asset_type_override: Optional[str] = None,
) -> AssetBehaviorFingerprint:
    """Main entry point.

    Args:
        symbol: Ticker (single asset). Pair / basket entry paths should
            pass `asset_type_override` since they bypass the heuristic.
        prices: Daily close prices, indexed by date (DatetimeIndex or any
            sortable index that can be coerced to DatetimeIndex). NaNs and
            zero-price rows are dropped.
        asset_type_override: When the caller knows the asset type (e.g. a
            pair from the wizard), pass it through verbatim. Otherwise the
            symbol-based heuristic runs.

    Returns:
        AssetBehaviorFingerprint dataclass — never raises on small / empty
        inputs; instead it returns data_quality="insufficient" and a
        graceful implication string.
    """
    symbol_clean = (symbol or "").upper().strip() or "?"
    asset_type = asset_type_override or classify_asset_type(symbol_clean)

    # Defensive prep — make the rest of the pipeline assume a clean,
    # monotonically-increasing Series of positive floats.
    if prices is None or len(prices) == 0:
        prices_clean = pd.Series(dtype=float)
    else:
        prices_clean = prices.copy()
        if not isinstance(prices_clean.index, pd.DatetimeIndex):
            try:
                prices_clean.index = pd.to_datetime(prices_clean.index)
            except Exception:
                # Index isn't coercible — treat as insufficient rather than crash.
                prices_clean = pd.Series(dtype=float)
        else:
            prices_clean = prices_clean.copy()
        prices_clean = prices_clean.sort_index().dropna()
        # Drop non-positive prices — pct_change would explode otherwise.
        prices_clean = prices_clean[prices_clean > 0]

    data_quality = classify_data_quality(prices_clean)

    if len(prices_clean) < _MIN_RETURNS_FOR_VOL:
        return AssetBehaviorFingerprint(
            symbol=symbol_clean,
            asset_type=asset_type,
            trending_pct=None,
            mean_reverting_pct=None,
            realized_vol_1y=None,
            realized_vol_5y=None,
            max_drawdown_5y=None,
            current_regime="mixed",
            data_quality="insufficient",
            strategy_implication=build_strategy_implication(
                asset_type, "mixed", "insufficient", None, None, None
            ),
        )

    returns = prices_clean.pct_change().dropna()
    realized_vol_1y = compute_realized_vol(returns, _TRADING_DAYS_PER_YEAR)
    realized_vol_5y = compute_realized_vol(returns, _TRADING_DAYS_PER_YEAR * 5)
    max_drawdown_5y = compute_max_drawdown(prices_clean.tail(_TRADING_DAYS_PER_YEAR * 5))
    trending_pct = compute_trending_pct(prices_clean)
    mean_reverting_pct = compute_mean_reverting_pct(prices_clean)

    current_regime = classify_current_regime(
        trending_pct, mean_reverting_pct, realized_vol_1y, realized_vol_5y,
    )
    strategy_implication = build_strategy_implication(
        asset_type, current_regime, data_quality,
        trending_pct, mean_reverting_pct, realized_vol_1y,
    )

    return AssetBehaviorFingerprint(
        symbol=symbol_clean,
        asset_type=asset_type,
        trending_pct=trending_pct,
        mean_reverting_pct=mean_reverting_pct,
        realized_vol_1y=realized_vol_1y,
        realized_vol_5y=realized_vol_5y,
        max_drawdown_5y=max_drawdown_5y,
        current_regime=current_regime,
        data_quality=data_quality,
        strategy_implication=strategy_implication,
    )
