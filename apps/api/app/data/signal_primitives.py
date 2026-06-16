"""Signal primitive catalog — the editorial product of PRD-16a Slice 1.

69 hand-authored entries spanning 8 categories (55 from PRD-16a + the
PRD-22b 52-week-extrema (7), RVOL (2), and Chandelier+TTM-Squeeze (5)
families). Every description is
plain English ("Measures overbought/oversold extremes…") not prescriptive
("Buy when RSI < 30") — that's the load-bearing UX choice the spec
calls out as pitfall A.

Voice rules (set by the existing template-description style in
`apps/web/src/lib/contracts.ts:researchTemplates`):
  - `description`: 1 line, ~50-80 chars, what-it-measures voice
  - `long_description`: optional paragraph, deeper but still descriptive
  - No Greek-letter jargon in the brief field (RSI/MACD spelled out)
  - No "use this to buy/sell" verbs — that's a strategy decision, not
    a primitive

Provider impl pointers reference registry keys that PRD-16a-2 will land
under `app/services/backtester/signal_provider.py:_REGISTRY`. The 9
existing keys (`fcf_yield`, `book_to_market`, `ebitda_ev`, `f_score`,
`buyback_yield_ttm`, `estimate_revision_3m`, `sentiment_score`,
`earnings_surprise`, `insider_net_buy`) reuse the existing impls; the
rest are stubs filled by 16a-2.

Adding a new entry:
  1. Pick the right category + family.
  2. Author the description in the same voice as the existing entries.
  3. Set `evidence_tier` honestly (A for SMA/RSI; C for novel composites).
  4. Add a test in `tests/test_signal_catalog.py` if the entry exercises
     a new code path (e.g. first `cross_sectional` ranking primitive).
"""
from __future__ import annotations

from app.schemas.signal_primitive import (
    OutputKind,
    Parameter,
    SignalCategory,
    SignalPrimitive,
)


# ── Trend (12 primitives) ────────────────────────────────────────────────────
# Moving averages + trend-strength oscillators. Every one of these answers
# "is the market in an up-trend?" — the variations differ in lag, sensitivity
# to recent prices, and how they handle noise.

_TREND: list[SignalPrimitive] = [
    SignalPrimitive(
        id="sma",
        category=SignalCategory.TREND,
        family="MA",
        name="Simple Moving Average (SMA)",
        description="Average closing price over N days — the classic trend line.",
        long_description=(
            "Equal-weighted average of the last N closes. Longer windows produce "
            "smoother but laggier signals; the 200-day SMA is the textbook "
            "long-term trend reference, the 50-day is the medium-term."
        ),
        parameters=[
            Parameter(name="period", default=200, min_value=2, max_value=500,
                      description="Look-back window in days"),
        ],
        default_thresholds={"price_above_ma": 1.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="sma",
        data_source="price",
    ),
    SignalPrimitive(
        id="ema",
        category=SignalCategory.TREND,
        family="MA",
        name="Exponential Moving Average (EMA)",
        description="Weighted moving average that reacts faster to recent prices than SMA.",
        long_description=(
            "Each new close gets a higher weight than the older ones, controlled "
            "by a smoothing factor derived from the period. EMAs respond to "
            "regime shifts faster than SMAs but are noisier."
        ),
        parameters=[
            Parameter(name="period", default=50, min_value=2, max_value=500,
                      description="Smoothing period in days"),
        ],
        default_thresholds={"price_above_ma": 1.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="ema",
        data_source="price",
    ),
    SignalPrimitive(
        id="wma",
        category=SignalCategory.TREND,
        family="MA",
        name="Weighted Moving Average (WMA)",
        description="Linearly weighted average — recent prices count more, oldest count least.",
        parameters=[
            Parameter(name="period", default=30, min_value=2, max_value=200,
                      description="Look-back window in days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="wma",
        data_source="price",
    ),
    SignalPrimitive(
        id="dema",
        category=SignalCategory.TREND,
        family="MA",
        name="Double Exponential Moving Average (DEMA)",
        description="EMA with the EMA-lag cancelled out — faster reaction, smoother than EMA.",
        parameters=[
            Parameter(name="period", default=21, min_value=2, max_value=200,
                      description="Underlying EMA period"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="dema",
        data_source="price",
    ),
    SignalPrimitive(
        id="tema",
        category=SignalCategory.TREND,
        family="MA",
        name="Triple Exponential Moving Average (TEMA)",
        description="Three-stage EMA smoothing — even less lag, more noise than DEMA.",
        parameters=[
            Parameter(name="period", default=21, min_value=2, max_value=200,
                      description="Underlying EMA period"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="C",
        provider_impl="tema",
        data_source="price",
    ),
    SignalPrimitive(
        id="kama",
        category=SignalCategory.TREND,
        family="MA",
        name="Kaufman Adaptive Moving Average (KAMA)",
        description="Self-adapting MA — smooths more when noisy, less when trending cleanly.",
        parameters=[
            Parameter(name="period", default=30, min_value=5, max_value=200,
                      description="Look-back window for efficiency ratio"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="kama",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
    SignalPrimitive(
        id="ma_crossover",
        category=SignalCategory.TREND,
        family="MA",
        name="Moving Average Crossover",
        description="Compares two MAs — fast over slow signals up-trend; fast under signals down.",
        long_description=(
            "Classic 'golden cross' / 'death cross' construction. With fast=50 + "
            "slow=200 it's the textbook long-term trend filter; with fast=10 + "
            "slow=30 it's a fast-cycle swing signal."
        ),
        parameters=[
            Parameter(name="fast_period", default=50, min_value=2, max_value=200,
                      description="Fast MA window"),
            Parameter(name="slow_period", default=200, min_value=5, max_value=500,
                      description="Slow MA window"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="ma_crossover",
        data_source="price",
        output_kind=OutputKind.CROSS,
    ),
    SignalPrimitive(
        id="macd",
        category=SignalCategory.TREND,
        family="MACD",
        name="MACD (Moving Average Convergence Divergence)",
        description="Difference between fast and slow EMAs; crossovers signal trend changes.",
        long_description=(
            "The MACD line is fast EMA − slow EMA. The signal line is a "
            "smoothed version of the MACD line. The histogram is their "
            "difference. Used to confirm trend changes already underway."
        ),
        parameters=[
            Parameter(name="fast_period", default=12, min_value=2, max_value=100,
                      description="Fast EMA period"),
            Parameter(name="slow_period", default=26, min_value=2, max_value=200,
                      description="Slow EMA period"),
            Parameter(name="signal_period", default=9, min_value=2, max_value=50,
                      description="Signal-line smoothing period"),
        ],
        default_thresholds={"histogram_zero_cross": 0.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="macd",
        data_source="price",
        output_channels=["macd_line", "signal_line", "histogram"],
    ),
    SignalPrimitive(
        id="adx",
        category=SignalCategory.TREND,
        family="ADX",
        name="ADX (Average Directional Index)",
        description="Measures trend STRENGTH (not direction) — above 25 typically means trending.",
        long_description=(
            "ADX rises when a directional move is sustained, regardless of "
            "whether it's up or down. Pair with a directional indicator (DI+ / "
            "DI-) to know which way; or use as a filter on top of an MA "
            "crossover ('only trade crossovers when ADX > 25')."
        ),
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="ADX smoothing period"),
        ],
        default_thresholds={"trending": 25.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="adx",
        data_source="price",
        output_channels=["adx", "plus_di", "minus_di"],
    ),
    SignalPrimitive(
        id="aroon",
        category=SignalCategory.TREND,
        family="AROON",
        name="Aroon Up / Aroon Down",
        description="Tracks how recently the period high or low occurred — measures trend freshness.",
        parameters=[
            Parameter(name="period", default=25, min_value=5, max_value=100,
                      description="Look-back window for the high/low"),
        ],
        default_thresholds={"strong": 70.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="aroon",
        data_source="price",
    ),
    SignalPrimitive(
        id="sar",
        category=SignalCategory.TREND,
        family="SAR",
        name="Parabolic SAR",
        description="Trailing stop level that flips above/below price when the trend reverses.",
        long_description=(
            "Wilder's parabolic stop-and-reverse. Dots below price signal an "
            "up-trend; above price, a down-trend. The flip itself is the "
            "reversal signal. Sensitive parameters; the defaults (0.02 / 0.2) "
            "are textbook but conservative."
        ),
        parameters=[
            Parameter(name="acceleration", default=0.02, min_value=0.01, max_value=0.1,
                      description="Acceleration factor"),
            Parameter(name="maximum", default=0.2, min_value=0.1, max_value=0.5,
                      description="Maximum acceleration"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="sar",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
    SignalPrimitive(
        id="ht_trendline",
        category=SignalCategory.TREND,
        family="HT",
        name="Hilbert Transform Instantaneous Trendline",
        description="Trend line derived from price's dominant cycle — adapts to changing rhythm.",
        parameters=[
            Parameter(name="period", default=21, min_value=10, max_value=100,
                      description="Underlying cycle period"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="C",
        provider_impl="ht_trendline",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
]


# ── Mean Reversion (9 primitives) ─────────────────────────────────────────────
# Oscillators measuring how stretched price is relative to its recent range.

_MEAN_REVERSION: list[SignalPrimitive] = [
    SignalPrimitive(
        id="rsi",
        category=SignalCategory.MEAN_REVERSION,
        family="RSI",
        name="RSI (Relative Strength Index)",
        description="Measures overbought (>70) and oversold (<30) extremes from recent gains vs losses.",
        long_description=(
            "Wilder's classic momentum oscillator. The 14-day period is "
            "default; shorter periods (5-9) produce more signals but more "
            "noise. Most useful on mean-reverting universes (ETFs, large-cap "
            "stocks); less useful on strongly trending names."
        ),
        parameters=[
            Parameter(name="period", default=14, min_value=2, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={"upper": 70.0, "lower": 30.0},
        asset_compat=["equity", "etf", "commodity", "fx"],
        evidence_tier="A",
        provider_impl="rsi",
        data_source="price",
    ),
    SignalPrimitive(
        id="stoch",
        category=SignalCategory.MEAN_REVERSION,
        family="STOCH",
        name="Stochastic Oscillator (%K / %D)",
        description="Where the close sits within the N-day high-low range — extremes mean exhaustion.",
        parameters=[
            Parameter(name="k_period", default=14, min_value=5, max_value=100,
                      description="%K look-back window"),
            Parameter(name="d_period", default=3, min_value=1, max_value=20,
                      description="%D smoothing period"),
        ],
        default_thresholds={"upper": 80.0, "lower": 20.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="stoch",
        data_source="price",
        output_channels=["k", "d"],
    ),
    SignalPrimitive(
        id="stochrsi",
        category=SignalCategory.MEAN_REVERSION,
        family="RSI",
        name="Stochastic RSI",
        description="Stochastic oscillator applied to RSI — more sensitive than either alone.",
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="Underlying RSI period"),
            Parameter(name="stoch_period", default=14, min_value=5, max_value=100,
                      description="Stochastic look-back over RSI series"),
        ],
        default_thresholds={"upper": 0.8, "lower": 0.2},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="stochrsi",
        data_source="price",
    ),
    SignalPrimitive(
        id="willr",
        category=SignalCategory.MEAN_REVERSION,
        family="WILLR",
        name="Williams %R",
        description="Inverted stochastic — readings near 0 mean overbought, near -100 mean oversold.",
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={"upper": -20.0, "lower": -80.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="willr",
        data_source="price",
    ),
    SignalPrimitive(
        id="cci",
        category=SignalCategory.MEAN_REVERSION,
        family="CCI",
        name="CCI (Commodity Channel Index)",
        description="How far typical price has moved from its average, scaled by typical deviation.",
        parameters=[
            Parameter(name="period", default=20, min_value=5, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={"upper": 100.0, "lower": -100.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="cci",
        data_source="price",
    ),
    SignalPrimitive(
        id="cmo",
        category=SignalCategory.MEAN_REVERSION,
        family="CMO",
        name="CMO (Chande Momentum Oscillator)",
        description="Like RSI but normalized to -100/+100 — sharper at extremes.",
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={"upper": 50.0, "lower": -50.0},
        asset_compat=["equity", "etf"],
        evidence_tier="C",
        provider_impl="cmo",
        data_source="price",
    ),
    SignalPrimitive(
        id="bbands",
        category=SignalCategory.MEAN_REVERSION,
        family="BBANDS",
        name="Bollinger Bands",
        description="Bands at ±N standard deviations around a moving average — tags the band signal a stretch.",
        long_description=(
            "Volatility-adjusted envelope around a moving average (typically "
            "20-day SMA, 2 std-dev). Band widening signals expanding "
            "volatility; band tags signal price exhaustion at the current "
            "vol regime."
        ),
        parameters=[
            Parameter(name="period", default=20, min_value=5, max_value=100,
                      description="MA + std-dev look-back window"),
            Parameter(name="std_dev", default=2.0, min_value=0.5, max_value=4.0,
                      description="Band width in std-devs from the mean"),
        ],
        default_thresholds={"price_outside_upper": 1.0, "price_outside_lower": -1.0},
        asset_compat=["equity", "etf", "commodity", "fx"],
        evidence_tier="A",
        provider_impl="bbands",
        data_source="price",
        output_channels=["upper", "lower", "middle"],
    ),
    SignalPrimitive(
        id="mfi",
        category=SignalCategory.MEAN_REVERSION,
        family="MFI",
        name="MFI (Money Flow Index)",
        description="RSI weighted by volume — overbought/oversold confirmed by trading intensity.",
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={"upper": 80.0, "lower": 20.0},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="mfi",
        data_source="price",
    ),
    SignalPrimitive(
        id="ultosc",
        category=SignalCategory.MEAN_REVERSION,
        family="ULTOSC",
        name="Ultimate Oscillator",
        description="Combines three time-frames of buying pressure into one oscillator — fewer false signals.",
        parameters=[
            Parameter(name="period_short", default=7, min_value=3, max_value=30,
                      description="Short period"),
            Parameter(name="period_medium", default=14, min_value=7, max_value=50,
                      description="Medium period"),
            Parameter(name="period_long", default=28, min_value=14, max_value=100,
                      description="Long period"),
        ],
        default_thresholds={"upper": 70.0, "lower": 30.0},
        asset_compat=["equity", "etf"],
        evidence_tier="C",
        provider_impl="ultosc",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
]


# ── Momentum (17 primitives) ─────────────────────────────────────────────────
# Rate-of-change + breakout primitives. Distinguished from "mean reversion"
# by extracting the existence of a sustained move, not the extremity of it.
# Includes the PRD-22b 52-week-extrema family (proximity + breakout).

_MOMENTUM: list[SignalPrimitive] = [
    SignalPrimitive(
        id="roc",
        category=SignalCategory.MOMENTUM,
        family="ROC",
        name="Rate of Change (ROC)",
        description="Percent change over N days — the simplest momentum measurement.",
        parameters=[
            Parameter(name="period", default=20, min_value=2, max_value=252,
                      description="Look-back window in days"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="roc",
        data_source="price",
    ),
    SignalPrimitive(
        id="mom",
        category=SignalCategory.MOMENTUM,
        family="MOM",
        name="Momentum (price - price[N])",
        description="Price minus the price N days ago — direction + magnitude in raw units.",
        parameters=[
            Parameter(name="period", default=10, min_value=2, max_value=200,
                      description="Look-back window in days"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="mom",
        data_source="price",
    ),
    SignalPrimitive(
        id="trix",
        category=SignalCategory.MOMENTUM,
        family="TRIX",
        name="TRIX (Triple-Smoothed EMA Rate of Change)",
        description="Percent change of a triple-smoothed EMA — filters short-term noise from momentum.",
        parameters=[
            Parameter(name="period", default=18, min_value=5, max_value=100,
                      description="Underlying EMA period"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="trix",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
    SignalPrimitive(
        id="apo",
        category=SignalCategory.MOMENTUM,
        family="APO",
        name="APO (Absolute Price Oscillator)",
        description="MACD's pre-signal-line cousin — fast EMA minus slow EMA in price units.",
        parameters=[
            Parameter(name="fast_period", default=12, min_value=2, max_value=100,
                      description="Fast EMA period"),
            Parameter(name="slow_period", default=26, min_value=5, max_value=200,
                      description="Slow EMA period"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="apo",
        data_source="price",
    ),
    SignalPrimitive(
        id="ppo",
        category=SignalCategory.MOMENTUM,
        family="PPO",
        name="PPO (Percentage Price Oscillator)",
        description="APO scaled by the slow EMA — comparable across assets at different price levels.",
        parameters=[
            Parameter(name="fast_period", default=12, min_value=2, max_value=100,
                      description="Fast EMA period"),
            Parameter(name="slow_period", default=26, min_value=5, max_value=200,
                      description="Slow EMA period"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="ppo",
        data_source="price",
    ),
    SignalPrimitive(
        id="donchian_breakout",
        category=SignalCategory.MOMENTUM,
        family="BREAKOUT",
        name="Donchian Breakout",
        description="True when today's close prints above the highest close of the prior N days.",
        long_description=(
            "Turtle Traders' classic. Long breakout = close above N-day rolling "
            "high (typically 20 days for fast, 55 days for slow). Pairs with a "
            "lower-channel exit. Works best on assets that exhibit sustained "
            "trends; chops the trader in mean-reverting names."
        ),
        parameters=[
            Parameter(name="period", default=20, min_value=5, max_value=252,
                      description="Look-back window for the rolling high"),
        ],
        default_thresholds={"breakout": 1.0},
        asset_compat=["equity", "etf", "commodity", "fx"],
        evidence_tier="A",
        provider_impl="donchian_breakout",
        data_source="price",
        output_kind=OutputKind.EVENT,
    ),
    SignalPrimitive(
        id="time_series_momentum",
        category=SignalCategory.MOMENTUM,
        family="TSMOM",
        name="Time-Series Momentum (12-1)",
        description="12-month return excluding the most recent month — the canonical academic momentum factor.",
        long_description=(
            "Moskowitz, Ooi & Pedersen (2012). Long when 12-1 return is "
            "positive, flat/short otherwise. The 'skip the last month' is to "
            "avoid the short-term reversal effect. Widely-replicated, "
            "tier-A momentum primitive."
        ),
        parameters=[
            Parameter(name="lookback_months", default=12, min_value=3, max_value=36,
                      description="Look-back window in months"),
            Parameter(name="skip_months", default=1, min_value=0, max_value=3,
                      description="Most-recent months to exclude"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="time_series_momentum",
        data_source="price",
    ),
    SignalPrimitive(
        id="bop",
        category=SignalCategory.MOMENTUM,
        family="BOP",
        name="BOP (Balance of Power)",
        description="Where the close sits within the day's range — close-to-high signals strength.",
        parameters=[
            Parameter(name="smoothing", default=14, min_value=1, max_value=50,
                      description="Smoothing window over raw BOP"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf"],
        evidence_tier="C",
        provider_impl="bop",
        data_source="price",
    ),
    SignalPrimitive(
        id="adxr",
        category=SignalCategory.MOMENTUM,
        family="ADX",
        name="ADXR (Average Directional Movement Rating)",
        description="Smoothed ADX — slower but less prone to whipsaws than raw ADX.",
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="ADX smoothing period"),
        ],
        default_thresholds={"trending": 25.0},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="adxr",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
    SignalPrimitive(
        id="aroonosc",
        category=SignalCategory.MOMENTUM,
        family="AROON",
        name="Aroon Oscillator",
        description="Aroon Up minus Aroon Down — positive in up-trends, negative in down-trends.",
        parameters=[
            Parameter(name="period", default=25, min_value=5, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="aroonosc",
        data_source="price",
    ),
    # ── 52-week extrema (PRD-22b) ─────────────────────────────────────────────
    # Proximity + breakout primitives over a rolling 52-week window. Pure
    # rolling max/min over daily closes — no new data source. The DISTANCE
    # kind powers the "within 2-25% of the 52-week high" setup filter.
    SignalPrimitive(
        id="distance_to_52w_high",
        category=SignalCategory.MOMENTUM,
        family="52W_EXTREMA",
        name="Distance to 52-week high",
        description="Signed percent gap between today's close and the highest close of the past 52 weeks.",
        long_description=(
            "Negative values sit below the 52-week high; zero marks a fresh "
            "high. The size of the gap is the raw input for proximity-to-high "
            "setup filters."
        ),
        parameters=[
            Parameter(name="lookback", default=252, min_value=20, max_value=504,
                      description="52-week window in trading days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="distance_to_52w_high",
        data_source="price",
        output_kind=OutputKind.DISTANCE,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="distance_to_52w_low",
        category=SignalCategory.MOMENTUM,
        family="52W_EXTREMA",
        name="Distance to 52-week low",
        description="Signed percent gap between today's close and the lowest close of the past 52 weeks.",
        long_description=(
            "Positive values sit above the 52-week low; zero marks a fresh "
            "low. Larger values mean more cushion above the annual floor."
        ),
        parameters=[
            Parameter(name="lookback", default=252, min_value=20, max_value=504,
                      description="52-week window in trading days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="distance_to_52w_low",
        data_source="price",
        output_kind=OutputKind.DISTANCE,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="price_52w_high_ratio",
        category=SignalCategory.MOMENTUM,
        family="52W_EXTREMA",
        name="Price-to-52-week-high ratio",
        description="Today's close as a fraction of the 52-week high — 1.0 means price sits at its annual peak.",
        long_description=(
            "A normalized 0-to-1 proximity gauge: 0.90 means price is 10% off "
            "its 52-week high. Comparable across names of any price level."
        ),
        parameters=[
            Parameter(name="lookback", default=252, min_value=20, max_value=504,
                      description="52-week window in trading days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="price_52w_high_ratio",
        data_source="price",
        output_kind=OutputKind.VALUE,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="price_52w_high_breakout",
        category=SignalCategory.MOMENTUM,
        family="52W_EXTREMA",
        name="52-week high breakout",
        description="Marks the bar on which price first prints a new 52-week high after trading below it.",
        long_description=(
            "Fires only on the transition into new-high territory — not while "
            "price keeps making highs — isolating the 'broke out to a new "
            "annual high today' event."
        ),
        parameters=[
            Parameter(name="lookback", default=252, min_value=20, max_value=504,
                      description="52-week window in trading days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="price_52w_high_breakout",
        data_source="price",
        output_kind=OutputKind.EVENT,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="price_52w_low_breakdown",
        category=SignalCategory.MOMENTUM,
        family="52W_EXTREMA",
        name="52-week low breakdown",
        description="Marks the bar on which price first prints a new 52-week low after trading above it.",
        long_description=(
            "Fires only on the transition into new-low territory — not while "
            "price keeps making lows — isolating the 'broke down to a new "
            "annual low today' event."
        ),
        parameters=[
            Parameter(name="lookback", default=252, min_value=20, max_value=504,
                      description="52-week window in trading days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="price_52w_low_breakdown",
        data_source="price",
        output_kind=OutputKind.EVENT,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="price_in_52w_high_zone",
        category=SignalCategory.MOMENTUM,
        family="52W_EXTREMA",
        name="Price in 52-week high zone",
        description=(
            "True while price sits in a parameterized band below the 52-week "
            "high — the breakout setup zone from 2-25% below by default."
        ),
        long_description=(
            "Captures the early-breakout setup pattern: stocks that have "
            "pulled back from a recent high but not retraced more than 25%. "
            "Used in event-driven momentum strategies to filter for names "
            "that are close to, but not at, new highs."
        ),
        parameters=[
            Parameter(name="min_pct", default=2.0, min_value=0.0, max_value=50.0,
                      description="Inner boundary (percent below high)"),
            Parameter(name="max_pct", default=25.0, min_value=1.0, max_value=80.0,
                      description="Outer boundary (percent below high)"),
            Parameter(name="lookback", default=252, min_value=20, max_value=504,
                      description="52-week window in trading days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="price_in_52w_high_zone",
        data_source="price",
        output_kind=OutputKind.LEVEL,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="days_since_52w_high",
        category=SignalCategory.MOMENTUM,
        family="52W_EXTREMA",
        name="Days since 52-week high",
        description="Trading days since price last touched its 52-week high — zero means today is a fresh high.",
        long_description=(
            "A staleness gauge for the annual peak. Low values mean price is "
            "near recent highs in time; high values mean the peak is distant."
        ),
        parameters=[
            Parameter(name="lookback", default=252, min_value=20, max_value=504,
                      description="52-week window in trading days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="C",
        provider_impl="days_since_52w_high",
        data_source="price",
        output_kind=OutputKind.VALUE,
        resolution=["daily"],
    ),
]


# ── Volume (7 primitives) ─────────────────────────────────────────────────────
# Volume-aware primitives — they confirm or contradict price-only signals.
# Includes the PRD-22b relative-volume (RVOL) family.

_VOLUME: list[SignalPrimitive] = [
    SignalPrimitive(
        id="obv",
        category=SignalCategory.VOLUME,
        family="OBV",
        name="OBV (On-Balance Volume)",
        description="Cumulative sum of volume — adds on up-days, subtracts on down-days.",
        long_description=(
            "Granville's classic. Rising OBV during a price up-trend confirms "
            "buyer conviction; OBV divergence (price up, OBV flat) warns of "
            "weakening trend. Best used as a confirmation overlay, not a "
            "standalone entry signal."
        ),
        parameters=[
            Parameter(name="smoothing_period", default=20, min_value=1, max_value=200,
                      description="Smoothing window over the OBV line"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="A",
        provider_impl="obv",
        data_source="price",
    ),
    SignalPrimitive(
        id="ad",
        category=SignalCategory.VOLUME,
        family="AD",
        name="Accumulation/Distribution Line",
        description="Volume weighted by where the close sits in the daily range — measures buying pressure.",
        parameters=[
            Parameter(name="smoothing_period", default=20, min_value=1, max_value=200,
                      description="Smoothing window"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="ad",
        data_source="price",
    ),
    SignalPrimitive(
        id="adosc",
        category=SignalCategory.VOLUME,
        family="AD",
        name="Chaikin A/D Oscillator",
        description="MACD applied to the A/D line — momentum of accumulation/distribution.",
        parameters=[
            Parameter(name="fast_period", default=3, min_value=2, max_value=20,
                      description="Fast EMA period"),
            Parameter(name="slow_period", default=10, min_value=5, max_value=50,
                      description="Slow EMA period"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="adosc",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
    SignalPrimitive(
        id="vwap",
        category=SignalCategory.VOLUME,
        family="VWAP",
        name="VWAP (Volume-Weighted Average Price)",
        description="Volume-weighted mean price over the look-back — institutional reference level.",
        long_description=(
            "VWAP is where the average share traded today. Price above VWAP "
            "means buyers are paying up; price below means sellers are "
            "dominating. Heavily used by execution desks to grade fill quality."
        ),
        parameters=[
            Parameter(name="period", default=20, min_value=5, max_value=200,
                      description="Look-back window in days"),
        ],
        default_thresholds={"price_above_vwap": 1.0},
        asset_compat=["equity", "etf"],
        evidence_tier="A",
        provider_impl="vwap",
        data_source="price",
    ),
    SignalPrimitive(
        id="avg_dollar_volume",
        category=SignalCategory.VOLUME,
        family="LIQUIDITY",
        name="Average Dollar Volume",
        description="N-day mean of (close × volume) — a liquidity filter, not a directional signal.",
        long_description=(
            "Used to screen out micro-caps that don't trade enough for the "
            "strategy's intended position size. The default $10M floor "
            "eliminates names where 1k-share entries would move the tape."
        ),
        parameters=[
            Parameter(name="period", default=60, min_value=20, max_value=252,
                      description="Look-back window in days"),
        ],
        default_thresholds={"min_usd": 10_000_000.0},
        asset_compat=["equity", "etf"],
        evidence_tier="A",
        provider_impl="avg_dollar_volume",
        data_source="price",
    ),
    # ── Relative volume (PRD-22b) ─────────────────────────────────────────────
    SignalPrimitive(
        id="rvol",
        category=SignalCategory.VOLUME,
        family="RVOL",
        name="Relative Volume (RVOL)",
        description="Today's volume divided by its trailing-20-day average — 2.0 means twice normal turnover.",
        long_description=(
            "The catalyst-confirmation gauge. Readings above 1.5 are elevated, "
            "above 2.0 a surge, above 3.0 a major-catalyst day. Independent of "
            "price direction."
        ),
        parameters=[
            Parameter(name="lookback", default=20, min_value=5, max_value=120,
                      description="Average-volume look-back window in days"),
        ],
        default_thresholds={"elevated": 1.5, "surge": 2.0},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="rvol",
        data_source="price",
        output_kind=OutputKind.VALUE,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="rvol_surge",
        category=SignalCategory.VOLUME,
        family="RVOL",
        name="Relative Volume surge",
        description="Marks the bar on which relative volume first crosses above the surge multiple (2.0 default).",
        long_description=(
            "Isolates the day a volume spike begins rather than every day "
            "volume stays elevated — pairs with a price trigger to confirm a "
            "move has conviction behind it."
        ),
        parameters=[
            Parameter(name="lookback", default=20, min_value=5, max_value=120,
                      description="Average-volume look-back window in days"),
            Parameter(name="surge_mult", default=2.0, min_value=1.0, max_value=10.0,
                      description="Relative-volume multiple that counts as a surge"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="rvol_surge",
        data_source="price",
        output_kind=OutputKind.EVENT,
        composes=["rvol"],
        resolution=["daily"],
    ),
]


# ── Volatility (10 primitives) ────────────────────────────────────────────────
# Volatility primitives — used as risk overlays + position sizing inputs more
# than as directional signals. Includes the PRD-22b Chandelier Exit + TTM
# Squeeze families.

_VOLATILITY: list[SignalPrimitive] = [
    SignalPrimitive(
        id="atr",
        category=SignalCategory.VOLATILITY,
        family="ATR",
        name="ATR (Average True Range)",
        description="Average daily price range — the canonical volatility-based stop-distance unit.",
        long_description=(
            "Wilder's true range averages over N days. Used to size stops as a "
            "multiple of ATR (e.g. 2× ATR stop = exit when price moves 2 days' "
            "average range against position). Vol-scaled stops adapt to "
            "the asset's natural noise."
        ),
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity", "fx"],
        evidence_tier="A",
        provider_impl="atr",
        data_source="price",
    ),
    SignalPrimitive(
        id="natr",
        category=SignalCategory.VOLATILITY,
        family="ATR",
        name="NATR (Normalized ATR)",
        description="ATR divided by price — comparable across assets at different price levels.",
        parameters=[
            Parameter(name="period", default=14, min_value=5, max_value=100,
                      description="Look-back window in days"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="natr",
        data_source="price",
    ),
    SignalPrimitive(
        id="trange",
        category=SignalCategory.VOLATILITY,
        family="ATR",
        name="True Range (raw, unsmoothed)",
        description="Single-day max of (high-low, |high-prev_close|, |low-prev_close|) — raw daily range.",
        parameters=[
            Parameter(name="lookback_smoothing", default=1, min_value=1, max_value=20,
                      description="Set >1 to smooth the raw True Range output"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="A",
        provider_impl="trange",
        data_source="price",
        compute_strategy="av_endpoint",
    ),
    SignalPrimitive(
        id="realized_vol",
        category=SignalCategory.VOLATILITY,
        family="VOL",
        name="Realized Volatility (annualized)",
        description="Annualized standard deviation of daily returns — the textbook vol estimator.",
        parameters=[
            Parameter(name="period", default=21, min_value=5, max_value=252,
                      description="Look-back window in days"),
            Parameter(name="trading_days", default=252, min_value=200, max_value=260,
                      description="Trading days per year for annualization"),
        ],
        default_thresholds={"high_vol": 0.30, "low_vol": 0.10},
        asset_compat=["equity", "etf", "commodity", "fx"],
        evidence_tier="A",
        provider_impl="realized_vol",
        data_source="price",
    ),
    SignalPrimitive(
        id="vol_regime",
        category=SignalCategory.VOLATILITY,
        family="VOL",
        name="Volatility Regime Classifier",
        description="Today's realized vol relative to its rolling N-day median — high/normal/low buckets.",
        long_description=(
            "Compares short-window realized vol to a longer-window median to "
            "classify the current regime. Useful as a risk overlay — turn "
            "down position size when vol is in the 'high' bucket."
        ),
        parameters=[
            Parameter(name="short_period", default=10, min_value=5, max_value=60,
                      description="Short-window realized vol period"),
            Parameter(name="long_period", default=126, min_value=21, max_value=504,
                      description="Long-window median reference"),
        ],
        default_thresholds={"high_multiplier": 1.5, "low_multiplier": 0.7},
        asset_compat=["equity", "etf", "commodity"],
        evidence_tier="B",
        provider_impl="vol_regime",
        data_source="price",
        output_kind=OutputKind.REGIME,
    ),
    # ── Chandelier Exit + TTM Squeeze (PRD-22b) ───────────────────────────────
    SignalPrimitive(
        id="chandelier_exit_long",
        category=SignalCategory.VOLATILITY,
        family="CHANDELIER",
        name="Chandelier Exit (long)",
        description="Long-side volatility trailing stop — the 22-day highest high minus three times ATR.",
        long_description=(
            "A stop level that ratchets up as price makes new highs but never "
            "loosens. Charles Le Beau's construction; price closing below it is "
            "the classic long-exit flag."
        ),
        parameters=[
            Parameter(name="period", default=22, min_value=5, max_value=100,
                      description="High + ATR look-back window in days"),
            Parameter(name="atr_mult", default=3.0, min_value=0.5, max_value=10.0,
                      description="ATR multiple subtracted from the rolling high"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="chandelier_exit_long",
        data_source="price",
        output_kind=OutputKind.VALUE,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="chandelier_exit_short",
        category=SignalCategory.VOLATILITY,
        family="CHANDELIER",
        name="Chandelier Exit (short)",
        description="Short-side volatility trailing stop — the 22-day lowest low plus three times ATR.",
        long_description=(
            "The short-side mirror of the long Chandelier stop. Price closing "
            "above it is the short-exit flag."
        ),
        parameters=[
            Parameter(name="period", default=22, min_value=5, max_value=100,
                      description="Low + ATR look-back window in days"),
            Parameter(name="atr_mult", default=3.0, min_value=0.5, max_value=10.0,
                      description="ATR multiple added to the rolling low"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="chandelier_exit_short",
        data_source="price",
        output_kind=OutputKind.VALUE,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="chandelier_exit_breach",
        category=SignalCategory.VOLATILITY,
        family="CHANDELIER",
        name="Chandelier Exit breach (long)",
        description="Marks the bar on which price first closes below the long-side Chandelier trailing stop.",
        long_description=(
            "The discrete exit event for a long Chandelier stop — fires once on "
            "the breach, not on every bar price stays below the line."
        ),
        parameters=[
            Parameter(name="period", default=22, min_value=5, max_value=100,
                      description="High + ATR look-back window in days"),
            Parameter(name="atr_mult", default=3.0, min_value=0.5, max_value=10.0,
                      description="ATR multiple subtracted from the rolling high"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="chandelier_exit_breach",
        data_source="price",
        output_kind=OutputKind.EVENT,
        composes=["chandelier_exit_long"],
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="ttm_squeeze",
        category=SignalCategory.VOLATILITY,
        family="TTM_SQUEEZE",
        name="TTM Squeeze",
        description="True while the Bollinger Bands sit inside the Keltner Channels — a low-volatility coiling regime.",
        long_description=(
            "John Carter's squeeze: volatility compresses until the Bollinger "
            "Bands contract inside the Keltner Channels, often preceding a "
            "directional expansion. Default 20-period, 2-sigma Bollinger vs "
            "1.5x-ATR Keltner."
        ),
        parameters=[
            Parameter(name="period", default=20, min_value=5, max_value=100,
                      description="Bollinger + Keltner look-back window in days"),
            Parameter(name="bb_std", default=2.0, min_value=0.5, max_value=4.0,
                      description="Bollinger band width in standard deviations"),
            Parameter(name="kc_mult", default=1.5, min_value=0.5, max_value=4.0,
                      description="Keltner channel width in ATR multiples"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="ttm_squeeze",
        data_source="price",
        output_kind=OutputKind.REGIME,
        resolution=["daily"],
    ),
    SignalPrimitive(
        id="ttm_squeeze_fire",
        category=SignalCategory.VOLATILITY,
        family="TTM_SQUEEZE",
        name="TTM Squeeze fire",
        description="Marks the bar the squeeze releases — Bollinger Bands expand back outside the Keltner Channels.",
        long_description=(
            "The breakout trigger that follows a TTM squeeze: fires once when "
            "the compression ends, signaling volatility is expanding again."
        ),
        parameters=[
            Parameter(name="period", default=20, min_value=5, max_value=100,
                      description="Bollinger + Keltner look-back window in days"),
            Parameter(name="bb_std", default=2.0, min_value=0.5, max_value=4.0,
                      description="Bollinger band width in standard deviations"),
            Parameter(name="kc_mult", default=1.5, min_value=0.5, max_value=4.0,
                      description="Keltner channel width in ATR multiples"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="B",
        provider_impl="ttm_squeeze_fire",
        data_source="price",
        output_kind=OutputKind.EVENT,
        composes=["ttm_squeeze"],
        resolution=["daily"],
    ),
]


# ── Fundamental (7 primitives) ────────────────────────────────────────────────
# Quality + value primitives from financial statements. These 6 wire to the
# existing `FundamentalSignalProvider` impls (already in the registry); the
# `estimate_revision_3m` reuses the same impl with a different `name`.

_FUNDAMENTAL: list[SignalPrimitive] = [
    SignalPrimitive(
        id="fcf_yield",
        category=SignalCategory.FUNDAMENTAL,
        family="VALUE",
        name="Free Cash Flow Yield",
        description="Trailing 12-month free cash flow divided by market cap — pure cash-return value metric.",
        long_description=(
            "FCF yield is harder to manipulate than P/E (earnings can be "
            "managed; cash is cash). Top decile of FCF yield is a "
            "well-replicated value-factor screen across U.S. equities."
        ),
        parameters=[
            Parameter(name="lag_days", default=90, min_value=30, max_value=180,
                      description="Disclosure lag (days from period-end to availability)"),
        ],
        default_thresholds={"min_yield": 0.05},
        asset_compat=["equity"],
        evidence_tier="A",
        provider_impl="fcf_yield",
        data_source="fundamental",
    ),
    SignalPrimitive(
        id="book_to_market",
        category=SignalCategory.FUNDAMENTAL,
        family="VALUE",
        name="Book-to-Market Ratio",
        description="Book value divided by market cap — the classic Fama-French value factor.",
        parameters=[
            Parameter(name="lag_days", default=90, min_value=30, max_value=180,
                      description="Disclosure lag (days from period-end to availability)"),
        ],
        default_thresholds={"min_bm": 0.5},
        asset_compat=["equity"],
        evidence_tier="A",
        provider_impl="book_to_market",
        data_source="fundamental",
    ),
    SignalPrimitive(
        id="ebitda_ev",
        category=SignalCategory.FUNDAMENTAL,
        family="VALUE",
        name="EBITDA / Enterprise Value",
        description="Operating earnings yield on the whole capital structure — debt-adjusted value metric.",
        parameters=[
            Parameter(name="lag_days", default=90, min_value=30, max_value=180,
                      description="Disclosure lag (days from period-end to availability)"),
        ],
        default_thresholds={"min_yield": 0.10},
        asset_compat=["equity"],
        evidence_tier="A",
        provider_impl="ebitda_ev",
        data_source="fundamental",
    ),
    SignalPrimitive(
        id="f_score",
        category=SignalCategory.FUNDAMENTAL,
        family="QUALITY",
        name="Piotroski F-Score (0-9)",
        description="Nine-point quality scorecard from financial-statement signals — higher means cleaner business.",
        long_description=(
            "Piotroski (2000). Scores 9 binary signals across profitability, "
            "leverage/liquidity, and operating efficiency. F-Score ≥ 7 has "
            "been a durable filter for separating real-value stocks from "
            "deteriorating ones in the cheap bucket."
        ),
        parameters=[
            Parameter(name="lag_days", default=90, min_value=30, max_value=180,
                      description="Disclosure lag in days"),
        ],
        default_thresholds={"min_score": 7.0},
        asset_compat=["equity"],
        evidence_tier="A",
        provider_impl="f_score",
        data_source="fundamental",
    ),
    SignalPrimitive(
        id="buyback_yield_ttm",
        category=SignalCategory.FUNDAMENTAL,
        family="VALUE",
        name="Buyback Yield (TTM)",
        description="Trailing 12-month share repurchase value divided by market cap.",
        parameters=[
            Parameter(name="lag_days", default=90, min_value=30, max_value=180,
                      description="Disclosure lag in days"),
        ],
        default_thresholds={"min_yield": 0.02},
        asset_compat=["equity"],
        evidence_tier="B",
        provider_impl="buyback_yield_ttm",
        data_source="fundamental",
    ),
    SignalPrimitive(
        id="estimate_revision_3m",
        category=SignalCategory.FUNDAMENTAL,
        family="GROWTH",
        name="3-Month Estimate Revision (proxy)",
        description="Quarter-over-quarter EPS direction over the last 3 quarters — analyst-revision proxy.",
        long_description=(
            "True analyst-estimate-revision data is paywalled; this proxy uses "
            "reported quarterly EPS direction. Less sensitive than real "
            "revisions but cheap and well-correlated on the medium-term."
        ),
        parameters=[
            Parameter(name="lag_days", default=90, min_value=30, max_value=180,
                      description="Disclosure lag in days"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity"],
        evidence_tier="B",
        provider_impl="estimate_revision_3m",
        data_source="fundamental",
    ),
    SignalPrimitive(
        id="earnings_surprise",
        category=SignalCategory.FUNDAMENTAL,
        family="GROWTH",
        name="Earnings Surprise",
        description="Reported EPS minus consensus EPS, scaled — the post-earnings drift trigger.",
        long_description=(
            "Magnitude of the beat or miss vs analyst consensus on the most "
            "recent quarterly report. Documented post-earnings drift in "
            "academic literature persists for several weeks after the print."
        ),
        parameters=[
            Parameter(name="window_days", default=60, min_value=5, max_value=180,
                      description="Days the surprise remains 'fresh' as a signal"),
        ],
        default_thresholds={"positive": 0.0},
        asset_compat=["equity"],
        evidence_tier="A",
        provider_impl="earnings_surprise",
        data_source="event",
    ),
]


# ── Sentiment (3 primitives) ──────────────────────────────────────────────────
# Information-flow primitives. Smaller category — fewer primitives but each
# one is qualitatively different from the others.

_SENTIMENT: list[SignalPrimitive] = [
    SignalPrimitive(
        id="sentiment_score",
        category=SignalCategory.SENTIMENT,
        family="NEWS",
        name="News Sentiment Score (FinBERT)",
        description="Rolling mean of FinBERT-scored daily news headlines — -1 (negative) to +1 (positive).",
        long_description=(
            "FinBERT applied to the day's news for each ticker, averaged over "
            "the rolling window. Sentiment-only alpha has mixed empirical "
            "support; useful primarily as a confirmation signal alongside a "
            "fundamental or technical primitive."
        ),
        parameters=[
            Parameter(name="window_days", default=30, min_value=5, max_value=90,
                      description="Rolling-mean window in days"),
        ],
        default_thresholds={"bullish": 0.2, "bearish": -0.2},
        asset_compat=["equity"],
        evidence_tier="B",
        provider_impl="sentiment_score",
        data_source="sentiment",
    ),
    SignalPrimitive(
        id="insider_net_buy",
        category=SignalCategory.SENTIMENT,
        family="INSIDER",
        name="Insider Net Buying (90 days)",
        description="Insider purchases minus sales over the last 90 days, scaled by market cap.",
        long_description=(
            "Cluster insider buying (multiple insiders, large dollar amounts) "
            "is one of the better-replicated standalone alpha signals in "
            "academic literature. Single-insider buys are noisier."
        ),
        parameters=[
            Parameter(name="window_days", default=90, min_value=30, max_value=180,
                      description="Look-back window in days"),
        ],
        default_thresholds={"strong_buy": 0.001},
        asset_compat=["equity"],
        evidence_tier="A",
        provider_impl="insider_net_buy",
        data_source="event",
    ),
    SignalPrimitive(
        id="analyst_rating_change",
        category=SignalCategory.SENTIMENT,
        family="ANALYST",
        name="Analyst Rating Change (90 days)",
        description="Net upgrades minus downgrades from sell-side analysts over the last 90 days.",
        parameters=[
            Parameter(name="window_days", default=90, min_value=30, max_value=180,
                      description="Look-back window in days"),
        ],
        default_thresholds={"net_upgrade": 1.0},
        asset_compat=["equity"],
        evidence_tier="C",
        provider_impl="analyst_rating_change",
        data_source="event",
    ),
]


# ── Cross-Sectional (4 primitives) ────────────────────────────────────────────
# Ranking primitives — produce a score relative to the rest of the universe,
# not an absolute level. Marked with `is_ranking=True`.

_CROSS_SECTIONAL: list[SignalPrimitive] = [
    SignalPrimitive(
        id="rank_return_6m",
        category=SignalCategory.CROSS_SECTIONAL,
        family="RANK",
        name="Rank by Trailing 6-Month Return",
        description="Position in the universe by 6-month price return — the canonical relative-strength rank.",
        long_description=(
            "Used by rotation strategies (sector rotation, top-N momentum) to "
            "pick winners from a universe. Pairs naturally with `time_series_"
            "momentum` as a 2-stage filter: only rotate into TSMOM-positive "
            "names, ranked by 6-month return."
        ),
        parameters=[
            Parameter(name="lookback_days", default=126, min_value=21, max_value=504,
                      description="Look-back window in trading days"),
            Parameter(name="top_n", default=3, min_value=1, max_value=20,
                      description="Hold the top N performers"),
        ],
        default_thresholds={},
        asset_compat=["equity", "etf"],
        evidence_tier="A",
        provider_impl="rank_return_6m",
        data_source="price",
        is_ranking=True,
    ),
    SignalPrimitive(
        id="rank_composite_score",
        category=SignalCategory.CROSS_SECTIONAL,
        family="RANK",
        name="Rank by Multi-Factor Composite",
        description="Average of standardized factor scores (value + quality + momentum) — multi-factor rank.",
        parameters=[
            Parameter(name="value_weight", default=0.4, min_value=0.0, max_value=1.0,
                      description="Weight on the value factor"),
            Parameter(name="quality_weight", default=0.3, min_value=0.0, max_value=1.0,
                      description="Weight on the quality factor"),
            Parameter(name="momentum_weight", default=0.3, min_value=0.0, max_value=1.0,
                      description="Weight on the momentum factor"),
            Parameter(name="top_n", default=10, min_value=1, max_value=50,
                      description="Hold the top N composite-scoring names"),
        ],
        default_thresholds={},
        asset_compat=["equity"],
        evidence_tier="B",
        provider_impl="rank_composite_score",
        data_source="price",
        is_ranking=True,
    ),
    SignalPrimitive(
        id="sector_rotation_rank",
        category=SignalCategory.CROSS_SECTIONAL,
        family="ROTATION",
        name="Sector Rotation Rank",
        description="Rank of GICS sectors by trailing 3-month return — picks the leading sectors.",
        parameters=[
            Parameter(name="lookback_days", default=63, min_value=21, max_value=252,
                      description="Look-back window in trading days"),
            Parameter(name="top_n", default=2, min_value=1, max_value=11,
                      description="Hold the top N sectors"),
        ],
        default_thresholds={},
        asset_compat=["etf"],
        evidence_tier="B",
        provider_impl="sector_rotation_rank",
        data_source="price",
        is_ranking=True,
    ),
    SignalPrimitive(
        id="pair_spread_zscore",
        category=SignalCategory.CROSS_SECTIONAL,
        family="STAT_ARB",
        name="Pair Spread Z-Score",
        description="Z-score of the price ratio between two cointegrated names — pair-trading entry signal.",
        long_description=(
            "Used by stat-arb pair traders. |z| > 2 indicates the pair has "
            "moved beyond its historical co-movement range. Mean-reversion "
            "back to z=0 is the canonical exit. Universe construction (which "
            "pairs are actually cointegrated) is the harder problem."
        ),
        parameters=[
            Parameter(name="lookback_days", default=60, min_value=20, max_value=252,
                      description="Look-back for spread mean + std"),
            Parameter(name="entry_z", default=2.0, min_value=1.0, max_value=4.0,
                      description="Entry threshold in std-devs"),
        ],
        default_thresholds={"entry": 2.0, "exit": 0.5},
        asset_compat=["equity"],
        evidence_tier="C",
        provider_impl="pair_spread_zscore",
        data_source="price",
        is_ranking=True,
    ),
]


# ── PRD-16c-4 editorial: intraday-eligible primitives ──────────────────────
#
# Technical indicators that work on any bar series (price-derived, no
# calendar-tied data) get `resolution=["daily", "intraday"]`. Everything
# else stays `["daily"]` because:
#   - Fundamentals don't change tick-to-tick (FCF yield, F-score, etc.)
#   - Sentiment + earnings events are daily-cadence at finest
#   - Cross-sectional rankings need a fixed snapshot window
#
# Add an id here when (a) the provider can run on intraday bars without
# semantic change, AND (b) the resulting signal is actually useful at
# that timescale. SAR + ParabolicSAR are eligible mechanically but
# tuned for daily — leave them daily-only unless someone validates the
# intraday parameter defaults. Same logic for KAMA.
_INTRADAY_ELIGIBLE_IDS: frozenset[str] = frozenset({
    # Trend (10): pure MA-based indicators work the same on any bar.
    "sma", "ema", "wma", "dema", "tema",
    "ma_crossover", "macd", "adx", "aroon", "ht_trendline",
    # Mean-reversion / momentum oscillators (16): price-derived, work
    # on any frame. Bollinger, RSI, Stochastics are the SpaceX-style
    # ladder's natural intraday building blocks.
    "rsi", "stoch", "stochrsi", "willr", "cci", "cmo", "bbands",
    "mfi", "ultosc", "roc", "mom", "trix", "apo", "ppo",
    "donchian_breakout", "bop",
    # Volume (5): all OHLCV-derived; VWAP is intraday-canonical.
    "obv", "ad", "adosc", "vwap", "avg_dollar_volume",
    # Volatility (4): bar-window-based; valid at any resolution.
    "atr", "natr", "trange", "realized_vol",
})


def _apply_intraday_resolution(primitives: list[SignalPrimitive]) -> list[SignalPrimitive]:
    """Bump `resolution` to `['daily', 'intraday']` for the editorially-
    chosen subset. Returns the same list — mutation is in-place since
    the items are mutable Pydantic models."""
    for p in primitives:
        if p.id in _INTRADAY_ELIGIBLE_IDS:
            # Preserve `daily` first for backwards-compat with the
            # ETag-cached frontend payload from PRD-16a (which ships
            # with `["daily"]` order).
            p.resolution = ["daily", "intraday"]
    return primitives


# ── Full catalog ──────────────────────────────────────────────────────────────

SIGNAL_PRIMITIVES: list[SignalPrimitive] = _apply_intraday_resolution([
    *_TREND,
    *_MEAN_REVERSION,
    *_MOMENTUM,
    *_VOLUME,
    *_VOLATILITY,
    *_FUNDAMENTAL,
    *_SENTIMENT,
    *_CROSS_SECTIONAL,
])


def get_catalog_version_hash() -> str:
    """Content hash over the catalog. Used as ETag for the endpoint +
    cache key for the frontend's localStorage. Stable across server
    restarts (pure function of the catalog data); changes only when the
    catalog data changes."""
    import hashlib
    payload = "|".join(
        f"{p.id}:{p.name}:{p.description}:{len(p.parameters)}"
        for p in SIGNAL_PRIMITIVES
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
