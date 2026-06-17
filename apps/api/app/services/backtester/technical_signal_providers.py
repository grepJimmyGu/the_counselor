"""Technical-indicator SignalProvider impls — PRD-16a Slice 2.

Wires the ~46 new technical-indicator primitives from PRD-16a-1's catalog
(`app/data/signal_primitives.py`) into the SignalProvider protocol that
the backtester engine consumes.

**Design split** (per the catalog's `compute_strategy` field):

  - **Local** (~38 indicators): computed in pandas from the OHLCV frame
    returned by `PriceDataService.get_price_frame`. No external API call.
    Examples: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ROC, OBV.
  - **AV endpoint** (~8 indicators): fetched pre-computed from Alpha
    Vantage's TA endpoints via `AlphaVantageClient.fetch_technical_indicator`.
    Used for indicators that are expensive to compute (Hilbert Transform,
    KAMA) or have non-trivial algorithms where AV's implementation is
    canonical (SAR, AROON variants, ULTOSC).

The split is documented per-primitive in the catalog itself; if you want
to flip an indicator's compute strategy, edit the catalog's
`compute_strategy` field and add/remove the corresponding class here.

**Base class** `TechnicalSignalProvider` handles the common plumbing:
fetching the price frame, parameter storage, async wiring. Subclasses
override `_compute(frame: pd.DataFrame) -> pd.Series` (local) or
`_av_fetch_and_pick(symbol, start, end) -> pd.Series` (AV endpoint).

**Parameter overrides** at runtime: the registry stores instances with
default params. For PRD-16a-2's preview endpoint, the route instantiates
a fresh provider with overrides via the classmethod `with_params()`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.services.alpha_vantage import AlphaVantageClient, AlphaVantageError
from app.services.backtester.signal_provider import SignalProvider
from app.services.price_data_service import PriceDataService


# ── Base classes ─────────────────────────────────────────────────────────────


class TechnicalSignalProvider(SignalProvider):
    """Base for all technical-indicator providers.

    Subclasses set:
      - `name`: registry key (matches catalog `provider_impl`)
      - `default_lookback_days`: extra warmup beyond the requested window
        so the indicator can compute its first valid value at `start`
    """

    name: str = ""
    default_lookback_days: int = 30

    def __init__(self, **params):
        self.params = {**self._default_params(), **params}
        self._price_svc = PriceDataService()

    def _default_params(self) -> dict:
        """Subclass override to provide default parameter values."""
        return {}

    @classmethod
    def with_params(cls, **overrides) -> "TechnicalSignalProvider":
        """Factory for runtime parameter overrides (the preview endpoint
        path). Returns a fresh instance with `overrides` applied on top
        of `_default_params()`."""
        return cls(**overrides)

    def _lookback_days(self) -> int:
        return self.default_lookback_days

    async def get_signal_frame(
        self,
        db: Session,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.Series:
        frame = await self._price_svc.get_price_frame(
            db, symbol, start, end, lookback_days=self._lookback_days(),
        )
        if frame.empty:
            return pd.Series(dtype=float, name=self.name)
        series = self._compute(frame)
        # Slice back to the requested window so callers don't see warmup
        # bars they didn't ask for.
        series = series.loc[series.index >= pd.Timestamp(start)]
        series.name = self.name
        return series

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        raise NotImplementedError(
            f"Subclass {type(self).__name__} must override _compute()."
        )


class AVTechnicalSignalProvider(TechnicalSignalProvider):
    """Base for indicators that fetch from Alpha Vantage's TA endpoints
    rather than computing locally. Override `_av_function` (AV function
    name), `_av_params(self.params)` (AV-specific request params), and
    `_av_value_column` (which column from AV's response to keep)."""

    _av_function: str = ""
    _av_value_column: str = ""

    def _av_params(self) -> dict:
        """Map self.params to the AV request parameter names. Subclass
        override — AV's param names differ from our canonical ones
        (e.g. 'period' vs 'time_period')."""
        return {}

    async def get_signal_frame(
        self,
        db: Session,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.Series:
        av = AlphaVantageClient()
        try:
            rows = await av.fetch_technical_indicator(
                function=self._av_function,
                symbol=symbol.upper(),
                params=self._av_params(),
            )
        except AlphaVantageError:
            # Same protocol as the local providers — return empty series
            # on failure so the caller can fall back gracefully. The
            # endpoint surfaces the error explicitly via try/except.
            return pd.Series(dtype=float, name=self.name)
        if not rows:
            return pd.Series(dtype=float, name=self.name)
        df = pd.DataFrame(rows).set_index("date").sort_index()
        df.index = pd.to_datetime(df.index)
        if self._av_value_column not in df.columns:
            # AV uses different column names per indicator; surface the
            # mismatch as an empty series rather than a KeyError.
            return pd.Series(dtype=float, name=self.name)
        series = df[self._av_value_column]
        series = series.loc[series.index >= pd.Timestamp(start)]
        series = series.loc[series.index <= pd.Timestamp(end)]
        series.name = self.name
        return series


# ── Trend providers ──────────────────────────────────────────────────────────


class SmaSignalProvider(TechnicalSignalProvider):
    name = "sma"

    def _default_params(self) -> dict:
        return {"period": 200}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        return frame["close"].rolling(int(self.params["period"])).mean()


class EmaSignalProvider(TechnicalSignalProvider):
    name = "ema"

    def _default_params(self) -> dict:
        return {"period": 50}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        return frame["close"].ewm(span=int(self.params["period"]), adjust=False).mean()


class WmaSignalProvider(TechnicalSignalProvider):
    name = "wma"

    def _default_params(self) -> dict:
        return {"period": 30}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        weights = np.arange(1, period + 1, dtype=float)
        denominator = weights.sum()
        return frame["close"].rolling(period).apply(
            lambda window: np.dot(window, weights) / denominator,
            raw=True,
        )


class DemaSignalProvider(TechnicalSignalProvider):
    name = "dema"

    def _default_params(self) -> dict:
        return {"period": 21}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        ema1 = frame["close"].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        return 2 * ema1 - ema2


class TemaSignalProvider(TechnicalSignalProvider):
    name = "tema"

    def _default_params(self) -> dict:
        return {"period": 21}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        ema1 = frame["close"].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        return 3 * (ema1 - ema2) + ema3


class KamaSignalProvider(AVTechnicalSignalProvider):
    name = "kama"
    _av_function = "KAMA"
    _av_value_column = "KAMA"

    def _default_params(self) -> dict:
        return {"period": 30}

    def _av_params(self) -> dict:
        return {"time_period": int(self.params["period"]), "series_type": "close"}


class MaCrossoverSignalProvider(TechnicalSignalProvider):
    """Returns the difference (fast_ma - slow_ma). Positive → fast above
    slow (up-trend); negative → down-trend. Callers cross at zero for
    the binary signal."""
    name = "ma_crossover"

    def _default_params(self) -> dict:
        return {"fast_period": 50, "slow_period": 200}

    def _lookback_days(self) -> int:
        return int(self.params["slow_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        fast = frame["close"].rolling(int(self.params["fast_period"])).mean()
        slow = frame["close"].rolling(int(self.params["slow_period"])).mean()
        return fast - slow


class MacdSignalProvider(TechnicalSignalProvider):
    """Returns the MACD histogram (MACD - signal). Crossing zero is the
    canonical signal; full MACD/signal/histogram are accessible by
    subclassing if a future caller needs all three."""
    name = "macd"

    def _default_params(self) -> dict:
        return {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def _lookback_days(self) -> int:
        return (int(self.params["slow_period"]) + int(self.params["signal_period"])) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        fast = frame["close"].ewm(span=int(self.params["fast_period"]), adjust=False).mean()
        slow = frame["close"].ewm(span=int(self.params["slow_period"]), adjust=False).mean()
        macd_line = fast - slow
        signal_line = macd_line.ewm(span=int(self.params["signal_period"]), adjust=False).mean()
        return macd_line - signal_line


def _adx_components(
    frame: pd.DataFrame, period: int
) -> "tuple[pd.Series, pd.Series, pd.Series]":
    """Shared Wilder directional-movement decomposition: returns
    (adx, plus_di, minus_di). Single source of truth for `adx` and the
    PRD-22b ADX-family children (adx_regime / adx_rising / di crosses) so
    `composes=["adx"]` stays byte-consistent with the parent."""
    high, low, close = frame["high"], frame["low"], frame["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


class AdxSignalProvider(TechnicalSignalProvider):
    """Average Directional Index — Wilder's smoothed directional movement.
    Returns ADX values (0-100); >25 typically means trending."""
    name = "adx"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        adx, _, _ = _adx_components(frame, int(self.params["period"]))
        return adx


class AroonSignalProvider(TechnicalSignalProvider):
    """Returns Aroon Up. Aroon Down is computed but not returned; pair
    with AroonOscillator (`aroonosc`) for the up-down spread."""
    name = "aroon"

    def _default_params(self) -> dict:
        return {"period": 25}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        # Days since the highest high in the look-back window.
        return frame["high"].rolling(period + 1).apply(
            lambda w: 100 * (period - (period - int(np.argmax(w)))) / period,
            raw=True,
        )


class SarSignalProvider(AVTechnicalSignalProvider):
    """Parabolic SAR. Returns the SAR level; cross relative to price is
    the trend-flip signal."""
    name = "sar"
    _av_function = "SAR"
    _av_value_column = "SAR"

    def _default_params(self) -> dict:
        return {"acceleration": 0.02, "maximum": 0.2}

    def _av_params(self) -> dict:
        return {
            "acceleration": float(self.params["acceleration"]),
            "maximum": float(self.params["maximum"]),
        }


class HtTrendlineSignalProvider(AVTechnicalSignalProvider):
    """Hilbert Transform instantaneous trendline."""
    name = "ht_trendline"
    _av_function = "HT_TRENDLINE"
    _av_value_column = "TRENDLINE"

    def _default_params(self) -> dict:
        return {"period": 21}  # AV ignores it; we keep it for catalog consistency

    def _av_params(self) -> dict:
        return {"series_type": "close"}


# ── Mean-Reversion providers ─────────────────────────────────────────────────


class RsiSignalProvider(TechnicalSignalProvider):
    name = "rsi"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        delta = frame["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))


class StochSignalProvider(TechnicalSignalProvider):
    """Returns %K (the fast line). %D is the %K-smoothed version; callers
    can request it via a separate primitive in v2."""
    name = "stoch"

    def _default_params(self) -> dict:
        return {"k_period": 14, "d_period": 3}

    def _lookback_days(self) -> int:
        return int(self.params["k_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        k_period = int(self.params["k_period"])
        lowest = frame["low"].rolling(k_period).min()
        highest = frame["high"].rolling(k_period).max()
        return 100 * (frame["close"] - lowest) / (highest - lowest).replace(0, np.nan)


class StochRsiSignalProvider(TechnicalSignalProvider):
    name = "stochrsi"

    def _default_params(self) -> dict:
        return {"period": 14, "stoch_period": 14}

    def _lookback_days(self) -> int:
        return (int(self.params["period"]) + int(self.params["stoch_period"])) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        rsi = RsiSignalProvider(period=int(self.params["period"]))._compute(frame)
        stoch_period = int(self.params["stoch_period"])
        rsi_low = rsi.rolling(stoch_period).min()
        rsi_high = rsi.rolling(stoch_period).max()
        return (rsi - rsi_low) / (rsi_high - rsi_low).replace(0, np.nan)


class WillrSignalProvider(TechnicalSignalProvider):
    name = "willr"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        highest = frame["high"].rolling(period).max()
        lowest = frame["low"].rolling(period).min()
        return -100 * (highest - frame["close"]) / (highest - lowest).replace(0, np.nan)


class CciSignalProvider(TechnicalSignalProvider):
    name = "cci"

    def _default_params(self) -> dict:
        return {"period": 20}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        tp = (frame["high"] + frame["low"] + frame["close"]) / 3
        sma = tp.rolling(period).mean()
        mad = tp.rolling(period).apply(lambda w: np.mean(np.abs(w - np.mean(w))), raw=True)
        return (tp - sma) / (0.015 * mad.replace(0, np.nan))


class CmoSignalProvider(TechnicalSignalProvider):
    name = "cmo"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        delta = frame["close"].diff()
        up = delta.where(delta > 0, 0.0).rolling(period).sum()
        down = (-delta.where(delta < 0, 0.0)).rolling(period).sum()
        return 100 * (up - down) / (up + down).replace(0, np.nan)


def _bollinger_bands(
    frame: pd.DataFrame, period: int, std_dev: float
) -> "tuple[pd.Series, pd.Series, pd.Series]":
    """Shared Bollinger decomposition: returns (upper, middle, lower).
    Single source of truth for `bbands` and the PRD-22b Bollinger children
    (%B / bandwidth / squeeze / tags) so `composes=["bbands"]` stays
    byte-consistent with the parent."""
    middle = frame["close"].rolling(period).mean()
    std = frame["close"].rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


class BbandsSignalProvider(TechnicalSignalProvider):
    """Returns %B — where price sits within the bands ((close - lower) /
    (upper - lower)). 0 = on the lower band; 1 = on the upper band. The
    raw upper/lower bands are accessible via subclasses if needed."""
    name = "bbands"

    def _default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        upper, _, lower = _bollinger_bands(
            frame, int(self.params["period"]), float(self.params["std_dev"])
        )
        return (frame["close"] - lower) / (upper - lower).replace(0, np.nan)


class MfiSignalProvider(TechnicalSignalProvider):
    name = "mfi"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        tp = (frame["high"] + frame["low"] + frame["close"]) / 3
        mf = tp * frame["volume"]
        delta = tp.diff()
        positive = mf.where(delta > 0, 0.0).rolling(period).sum()
        negative = mf.where(delta < 0, 0.0).rolling(period).sum()
        mr = positive / negative.replace(0, np.nan)
        return 100 - (100 / (1 + mr))


class UltoscSignalProvider(AVTechnicalSignalProvider):
    name = "ultosc"
    _av_function = "ULTOSC"
    _av_value_column = "ULTOSC"

    def _default_params(self) -> dict:
        return {"period_short": 7, "period_medium": 14, "period_long": 28}

    def _av_params(self) -> dict:
        return {
            "timeperiod1": int(self.params["period_short"]),
            "timeperiod2": int(self.params["period_medium"]),
            "timeperiod3": int(self.params["period_long"]),
        }


# ── Momentum providers ──────────────────────────────────────────────────────


class RocSignalProvider(TechnicalSignalProvider):
    name = "roc"

    def _default_params(self) -> dict:
        return {"period": 20}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        return 100 * frame["close"].pct_change(period)


class MomSignalProvider(TechnicalSignalProvider):
    name = "mom"

    def _default_params(self) -> dict:
        return {"period": 10}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        return frame["close"] - frame["close"].shift(period)


class TrixSignalProvider(AVTechnicalSignalProvider):
    name = "trix"
    _av_function = "TRIX"
    _av_value_column = "TRIX"

    def _default_params(self) -> dict:
        return {"period": 18}

    def _av_params(self) -> dict:
        return {"time_period": int(self.params["period"]), "series_type": "close"}


class ApoSignalProvider(TechnicalSignalProvider):
    name = "apo"

    def _default_params(self) -> dict:
        return {"fast_period": 12, "slow_period": 26}

    def _lookback_days(self) -> int:
        return int(self.params["slow_period"]) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        fast = frame["close"].ewm(span=int(self.params["fast_period"]), adjust=False).mean()
        slow = frame["close"].ewm(span=int(self.params["slow_period"]), adjust=False).mean()
        return fast - slow


class PpoSignalProvider(TechnicalSignalProvider):
    name = "ppo"

    def _default_params(self) -> dict:
        return {"fast_period": 12, "slow_period": 26}

    def _lookback_days(self) -> int:
        return int(self.params["slow_period"]) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        fast = frame["close"].ewm(span=int(self.params["fast_period"]), adjust=False).mean()
        slow = frame["close"].ewm(span=int(self.params["slow_period"]), adjust=False).mean()
        return 100 * (fast - slow) / slow.replace(0, np.nan)


class DonchianBreakoutSignalProvider(TechnicalSignalProvider):
    """Returns 1 when today's close is above the prior N-day rolling
    high; 0 otherwise."""
    name = "donchian_breakout"

    def _default_params(self) -> dict:
        return {"period": 20}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        # Prior N-day high (exclusive of today) → close > that = breakout.
        rolling_high = frame["close"].rolling(period).max().shift(1)
        return (frame["close"] > rolling_high).astype(float)


class TimeSeriesMomentumSignalProvider(TechnicalSignalProvider):
    """12-1 momentum: 12-month return excluding the most recent month.
    Returns the percent return — positive means long, negative means
    flat/short per the academic factor."""
    name = "time_series_momentum"

    def _default_params(self) -> dict:
        return {"lookback_months": 12, "skip_months": 1}

    def _lookback_days(self) -> int:
        return int(self.params["lookback_months"]) * 30 + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback_months"]) * 21  # trading days
        skip = int(self.params["skip_months"]) * 21
        # 12-month return excluding the most recent skip months.
        return frame["close"].pct_change(lookback - skip).shift(skip)


class BopSignalProvider(TechnicalSignalProvider):
    name = "bop"

    def _default_params(self) -> dict:
        return {"smoothing": 14}

    def _lookback_days(self) -> int:
        return int(self.params["smoothing"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        smoothing = int(self.params["smoothing"])
        raw = (frame["close"] - frame["open"]) / (
            (frame["high"] - frame["low"]).replace(0, np.nan)
        )
        return raw.rolling(smoothing).mean()


class AdxrSignalProvider(AVTechnicalSignalProvider):
    name = "adxr"
    _av_function = "ADXR"
    _av_value_column = "ADXR"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _av_params(self) -> dict:
        return {"time_period": int(self.params["period"])}


class AroonOscSignalProvider(TechnicalSignalProvider):
    """Aroon Up - Aroon Down. Positive = up-trend, negative = down-trend."""
    name = "aroonosc"

    def _default_params(self) -> dict:
        return {"period": 25}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        aroon_up = frame["high"].rolling(period + 1).apply(
            lambda w: 100 * int(np.argmax(w)) / period, raw=True,
        )
        aroon_down = frame["low"].rolling(period + 1).apply(
            lambda w: 100 * int(np.argmin(w)) / period, raw=True,
        )
        return aroon_up - aroon_down


# ── Volume providers ────────────────────────────────────────────────────────


class ObvSignalProvider(TechnicalSignalProvider):
    name = "obv"

    def _default_params(self) -> dict:
        return {"smoothing_period": 20}

    def _lookback_days(self) -> int:
        return int(self.params["smoothing_period"]) + 60

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        direction = np.sign(frame["close"].diff()).fillna(0)
        obv = (direction * frame["volume"]).cumsum()
        smoothing = int(self.params["smoothing_period"])
        if smoothing > 1:
            obv = obv.rolling(smoothing).mean()
        return obv


class AdSignalProvider(TechnicalSignalProvider):
    name = "ad"

    def _default_params(self) -> dict:
        return {"smoothing_period": 20}

    def _lookback_days(self) -> int:
        return int(self.params["smoothing_period"]) + 60

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        clv = ((frame["close"] - frame["low"]) - (frame["high"] - frame["close"])) / (
            (frame["high"] - frame["low"]).replace(0, np.nan)
        )
        ad = (clv * frame["volume"]).cumsum()
        smoothing = int(self.params["smoothing_period"])
        if smoothing > 1:
            ad = ad.rolling(smoothing).mean()
        return ad


class AdoscSignalProvider(AVTechnicalSignalProvider):
    name = "adosc"
    _av_function = "ADOSC"
    _av_value_column = "Chaikin A/D"

    def _default_params(self) -> dict:
        return {"fast_period": 3, "slow_period": 10}

    def _av_params(self) -> dict:
        return {
            "fastperiod": int(self.params["fast_period"]),
            "slowperiod": int(self.params["slow_period"]),
        }


class VwapSignalProvider(TechnicalSignalProvider):
    name = "vwap"

    def _default_params(self) -> dict:
        return {"period": 20}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        tp = (frame["high"] + frame["low"] + frame["close"]) / 3
        tpv = tp * frame["volume"]
        return tpv.rolling(period).sum() / frame["volume"].rolling(period).sum()


class AvgDollarVolumeSignalProvider(TechnicalSignalProvider):
    name = "avg_dollar_volume"

    def _default_params(self) -> dict:
        return {"period": 60}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        return (frame["close"] * frame["volume"]).rolling(period).mean()


# ── Volatility providers ────────────────────────────────────────────────────


class AtrSignalProvider(TechnicalSignalProvider):
    name = "atr"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        tr = pd.concat([
            (frame["high"] - frame["low"]).abs(),
            (frame["high"] - frame["close"].shift()).abs(),
            (frame["low"] - frame["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / period, adjust=False).mean()


class NatrSignalProvider(TechnicalSignalProvider):
    name = "natr"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        atr = AtrSignalProvider(period=int(self.params["period"]))._compute(frame)
        return 100 * atr / frame["close"]


class TrangeSignalProvider(AVTechnicalSignalProvider):
    name = "trange"
    _av_function = "TRANGE"
    _av_value_column = "TRANGE"

    def _default_params(self) -> dict:
        return {"lookback_smoothing": 1}

    def _av_params(self) -> dict:
        return {}


class RealizedVolSignalProvider(TechnicalSignalProvider):
    name = "realized_vol"

    def _default_params(self) -> dict:
        return {"period": 21, "trading_days": 252}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        trading_days = int(self.params["trading_days"])
        returns = frame["close"].pct_change()
        return returns.rolling(period).std() * np.sqrt(trading_days)


class VolRegimeSignalProvider(TechnicalSignalProvider):
    """Short-window realized vol divided by long-window median.
    Values > high_multiplier → high-vol regime; < low_multiplier → low-vol."""
    name = "vol_regime"

    def _default_params(self) -> dict:
        return {"short_period": 10, "long_period": 126}

    def _lookback_days(self) -> int:
        return int(self.params["long_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        returns = frame["close"].pct_change()
        short_vol = returns.rolling(int(self.params["short_period"])).std()
        long_median = returns.rolling(int(self.params["long_period"])).std().rolling(
            int(self.params["long_period"])
        ).median()
        return short_vol / long_median.replace(0, np.nan)


# ── Cross-sectional providers (single-symbol versions) ──────────────────────
# These primitives are *defined* as universe-ranking operations. For the
# single-symbol preview path (PRD-16a-2), each returns the raw underlying
# value (e.g. 6-month return for rank_return_6m); the ranking step happens
# in the composer (PRD-16b) when the universe is known.


class RankReturn6mSignalProvider(TechnicalSignalProvider):
    """Single-symbol value side of the rank: trailing N-day return."""
    name = "rank_return_6m"

    def _default_params(self) -> dict:
        return {"lookback_days": 126, "top_n": 3}

    def _lookback_days(self) -> int:
        return int(self.params["lookback_days"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        return frame["close"].pct_change(int(self.params["lookback_days"]))


class RankCompositeScoreSignalProvider(TechnicalSignalProvider):
    """For single-symbol preview, returns a placeholder constant (the
    composite needs cross-sectional context that's not available here).
    PRD-16b's composer wires the real ranking logic."""
    name = "rank_composite_score"

    def _default_params(self) -> dict:
        return {
            "value_weight": 0.4,
            "quality_weight": 0.3,
            "momentum_weight": 0.3,
            "top_n": 10,
        }

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        # Single-symbol preview: a placeholder series of zeros indexed
        # by the frame's dates. The composer reconciles in PRD-16b.
        return pd.Series(0.0, index=frame.index, name=self.name)


class SectorRotationRankSignalProvider(TechnicalSignalProvider):
    """Single-symbol preview: trailing 3-month return. Universe-aware
    ranking happens in PRD-16b."""
    name = "sector_rotation_rank"

    def _default_params(self) -> dict:
        return {"lookback_days": 63, "top_n": 2}

    def _lookback_days(self) -> int:
        return int(self.params["lookback_days"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        return frame["close"].pct_change(int(self.params["lookback_days"]))


class PairSpreadZscoreSignalProvider(TechnicalSignalProvider):
    """Single-symbol preview: returns the z-score of the close against
    its own rolling mean/std. True pair-spread z-score requires a
    second symbol — PRD-16b's composer wires it."""
    name = "pair_spread_zscore"

    def _default_params(self) -> dict:
        return {"lookback_days": 60, "entry_z": 2.0}

    def _lookback_days(self) -> int:
        return int(self.params["lookback_days"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback_days"])
        mean = frame["close"].rolling(lookback).mean()
        std = frame["close"].rolling(lookback).std()
        return (frame["close"] - mean) / std.replace(0, np.nan)


# ── Sentiment placeholder ───────────────────────────────────────────────────


class AnalystRatingChangeSignalProvider(TechnicalSignalProvider):
    """Placeholder — no analyst-rating data source on `main` yet. Returns
    an empty series; the provider exists so the catalog's `provider_impl`
    reference resolves. A future PRD wires a real ratings provider."""
    name = "analyst_rating_change"

    def _default_params(self) -> dict:
        return {"window_days": 90}

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        return pd.Series(np.nan, index=frame.index, name=self.name)


# ── 52-week extrema providers (PRD-22b) ─────────────────────────────────────
# Proximity + breakout primitives over a rolling 52-week (252-day) window.
# Pure rolling max/min over daily closes — no new data source. The DISTANCE
# kind (signed % gap) powers the "within 2-25% of the 52-week high" setup
# filter; the EVENT kinds fire only on the bar a new extreme is first printed
# (strictly above the PRIOR window high / below the prior low), not while the
# extreme persists.


class DistanceTo52wHighProvider(TechnicalSignalProvider):
    """Signed percent gap from the rolling 52-week high. Negative = below
    the high; zero = at a fresh high. DISTANCE kind."""
    name = "distance_to_52w_high"

    def _default_params(self) -> dict:
        return {"lookback": 252}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        high = frame["close"].rolling(lookback, min_periods=20).max()
        return (frame["close"] / high.replace(0, np.nan) - 1.0) * 100


class DistanceTo52wLowProvider(TechnicalSignalProvider):
    """Signed percent gap from the rolling 52-week low. Positive = above
    the low; zero = at a fresh low. DISTANCE kind."""
    name = "distance_to_52w_low"

    def _default_params(self) -> dict:
        return {"lookback": 252}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        low = frame["close"].rolling(lookback, min_periods=20).min()
        return (frame["close"] / low.replace(0, np.nan) - 1.0) * 100


class Price52wHighRatioProvider(TechnicalSignalProvider):
    """Close as a fraction of the rolling 52-week high (0-1). 1.0 = at the
    annual peak. Comparable across names of any price level."""
    name = "price_52w_high_ratio"

    def _default_params(self) -> dict:
        return {"lookback": 252}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        high = frame["close"].rolling(lookback, min_periods=20).max()
        return frame["close"] / high.replace(0, np.nan)


class Price52wHighBreakoutProvider(TechnicalSignalProvider):
    """EVENT: 1.0 only on the bar price first closes strictly above the
    PRIOR 52-week high; 0.0 elsewhere (including while the breakout run
    persists)."""
    name = "price_52w_high_breakout"

    def _default_params(self) -> dict:
        return {"lookback": 252}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        prior_high = frame["close"].rolling(lookback, min_periods=20).max().shift(1)
        breakout = frame["close"] > prior_high
        event = breakout & ~breakout.shift(1, fill_value=False)
        return event.astype(float)


class Price52wLowBreakdownProvider(TechnicalSignalProvider):
    """EVENT: 1.0 only on the bar price first closes strictly below the
    PRIOR 52-week low; 0.0 elsewhere."""
    name = "price_52w_low_breakdown"

    def _default_params(self) -> dict:
        return {"lookback": 252}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        prior_low = frame["close"].rolling(lookback, min_periods=20).min().shift(1)
        breakdown = frame["close"] < prior_low
        event = breakdown & ~breakdown.shift(1, fill_value=False)
        return event.astype(float)


class PriceIn52wHighZoneProvider(TechnicalSignalProvider):
    """LEVEL: true (1.0) while price sits in a band below the 52-week high
    (default 2-25% below) — the breakout-setup zone."""
    name = "price_in_52w_high_zone"

    def _default_params(self) -> dict:
        return {"min_pct": 2.0, "max_pct": 25.0, "lookback": 252}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        high = frame["close"].rolling(lookback, min_periods=20).max()
        distance = (frame["close"] / high.replace(0, np.nan) - 1.0) * 100
        min_pct = float(self.params["min_pct"])
        max_pct = float(self.params["max_pct"])
        return ((distance <= -min_pct) & (distance >= -max_pct)).astype(float)


class DaysSince52wHighProvider(TechnicalSignalProvider):
    """Trading days since the rolling 52-week high was last printed.
    0 = today is a fresh high; rises as price drifts from the peak."""
    name = "days_since_52w_high"

    def _default_params(self) -> dict:
        return {"lookback": 252}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        # Bars since the rolling-window argmax (0 = the high is the last bar).
        return frame["close"].rolling(lookback, min_periods=20).apply(
            lambda w: float(len(w) - 1 - int(np.argmax(w))), raw=True,
        )


# ── RVOL + Chandelier + TTM Squeeze providers (PRD-22b) ─────────────────────
# Fully vectorized; formulas per v2 spec §4.3 / §4.1 / §4.5. ATR is reused
# from AtrSignalProvider (Wilder smoothing) rather than recomputed. EVENT
# kinds fire only on the transition bar.


class RvolSignalProvider(TechnicalSignalProvider):
    """Relative volume: today's volume over its trailing average. 1.0 =
    average turnover; 2.0 = a volume surge."""
    name = "rvol"

    def _default_params(self) -> dict:
        return {"lookback": 20}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        avg = frame["volume"].shift(1).rolling(lookback).mean()
        return frame["volume"] / avg.replace(0, np.nan)


class RvolSurgeSignalProvider(TechnicalSignalProvider):
    """EVENT: fires on the bar relative volume first crosses above the
    surge multiple (default 2.0)."""
    name = "rvol_surge"

    def _default_params(self) -> dict:
        return {"lookback": 20, "surge_mult": 2.0}

    def _lookback_days(self) -> int:
        return int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        lookback = int(self.params["lookback"])
        mult = float(self.params["surge_mult"])
        avg = frame["volume"].shift(1).rolling(lookback).mean()
        rvol = frame["volume"] / avg.replace(0, np.nan)
        above = rvol > mult
        event = above & ~above.shift(1, fill_value=False)
        return event.astype(float)


class ChandelierExitLongSignalProvider(TechnicalSignalProvider):
    """Long-side volatility trailing stop: the N-bar highest high minus a
    multiple of ATR. Ratchets up with new highs; price closing below it is
    the long-exit flag."""
    name = "chandelier_exit_long"

    def _default_params(self) -> dict:
        return {"period": 22, "atr_mult": 3.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        mult = float(self.params["atr_mult"])
        atr = AtrSignalProvider(period=period)._compute(frame)
        return frame["high"].rolling(period).max() - mult * atr


class ChandelierExitShortSignalProvider(TechnicalSignalProvider):
    """Short-side volatility trailing stop: the N-bar lowest low plus a
    multiple of ATR. Price closing above it is the short-exit flag."""
    name = "chandelier_exit_short"

    def _default_params(self) -> dict:
        return {"period": 22, "atr_mult": 3.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        mult = float(self.params["atr_mult"])
        atr = AtrSignalProvider(period=period)._compute(frame)
        return frame["low"].rolling(period).min() + mult * atr


class ChandelierExitBreachSignalProvider(TechnicalSignalProvider):
    """EVENT: fires on the bar price first closes below the long-side
    Chandelier trailing stop."""
    name = "chandelier_exit_breach"

    def _default_params(self) -> dict:
        return {"period": 22, "atr_mult": 3.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        mult = float(self.params["atr_mult"])
        atr = AtrSignalProvider(period=period)._compute(frame)
        ce_long = frame["high"].rolling(period).max() - mult * atr
        breach = frame["close"] < ce_long
        event = breach & ~breach.shift(1, fill_value=False)
        return event.astype(float)


class TtmSqueezeSignalProvider(TechnicalSignalProvider):
    """REGIME: 1.0 while the Bollinger Bands sit inside the Keltner
    Channels (a low-volatility squeeze); 0.0 otherwise."""
    name = "ttm_squeeze"

    def _default_params(self) -> dict:
        return {"period": 20, "bb_std": 2.0, "kc_mult": 1.5}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _squeeze_on(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        bb_std = float(self.params["bb_std"])
        kc_mult = float(self.params["kc_mult"])
        ma = frame["close"].rolling(period).mean()
        std = frame["close"].rolling(period).std()
        atr = AtrSignalProvider(period=period)._compute(frame)
        bb_u, bb_l = ma + bb_std * std, ma - bb_std * std
        kc_u, kc_l = ma + kc_mult * atr, ma - kc_mult * atr
        return (bb_u < kc_u) & (bb_l > kc_l)

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        return self._squeeze_on(frame).astype(float)


class TtmSqueezeFireSignalProvider(TtmSqueezeSignalProvider):
    """EVENT: fires on the bar the squeeze releases — Bollinger Bands
    expand back outside the Keltner Channels (the breakout trigger)."""
    name = "ttm_squeeze_fire"

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        squeeze_on = self._squeeze_on(frame)
        fire = (~squeeze_on) & squeeze_on.shift(1, fill_value=False)
        return fire.astype(float)


# ── MA + MACD events (PRD-22b) ──────────────────────────────────────────────
# The MA/MACD families historically emitted only VALUE scalars
# (`ma_crossover` → fast−slow, `macd` → histogram). v2 decomposes the
# canonical *consumption patterns* into standalone event/cross/level
# primitives so the composer can offer "golden cross fired" / "close
# above the 200-day" directly instead of asking the user to threshold a
# raw scalar. Encoding matches `_apply_rule_threshold`:
#   CROSS  → +1 on the up-cross bar, −1 on the down-cross bar, 0 elsewhere
#   EVENT  → non-zero on the transition bar (fires), 0 elsewhere
#   LEVEL  → 1.0 while the condition holds, 0.0 otherwise


class PriceAboveMaSignalProvider(TechnicalSignalProvider):
    """LEVEL: 1.0 while close trades above its N-day simple moving average
    (e.g. above the 200-day = bull-market filter)."""
    name = "price_above_ma"

    def _default_params(self) -> dict:
        return {"period": 200}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        ma = frame["close"].rolling(int(self.params["period"])).mean()
        return (frame["close"] > ma).astype(float)


class PriceMaCrossUpSignalProvider(TechnicalSignalProvider):
    """CROSS: +1 on the bar close crosses ABOVE its moving average."""
    name = "price_ma_cross_up"

    def _default_params(self) -> dict:
        return {"period": 50}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        ma = frame["close"].rolling(int(self.params["period"])).mean()
        above = frame["close"] > ma
        cross_up = above & ~above.shift(1, fill_value=False)
        return cross_up.astype(float)


class PriceMaCrossDownSignalProvider(TechnicalSignalProvider):
    """CROSS: −1 on the bar close crosses BELOW its moving average."""
    name = "price_ma_cross_down"

    def _default_params(self) -> dict:
        return {"period": 50}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        ma = frame["close"].rolling(int(self.params["period"])).mean()
        below = frame["close"] < ma
        cross_down = below & ~below.shift(1, fill_value=False)
        return cross_down.astype(float) * -1.0


class GoldenCrossSignalProvider(TechnicalSignalProvider):
    """CROSS: +1 on the bar the fast MA crosses ABOVE the slow MA — the
    textbook 50-over-200 golden cross (periods configurable)."""
    name = "golden_cross"

    def _default_params(self) -> dict:
        return {"fast_period": 50, "slow_period": 200}

    def _lookback_days(self) -> int:
        return int(self.params["slow_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        fast = frame["close"].rolling(int(self.params["fast_period"])).mean()
        slow = frame["close"].rolling(int(self.params["slow_period"])).mean()
        above = fast > slow
        cross_up = above & ~above.shift(1, fill_value=False)
        return cross_up.astype(float)


class DeathCrossSignalProvider(TechnicalSignalProvider):
    """CROSS: −1 on the bar the fast MA crosses BELOW the slow MA — the
    death cross, inverse of the golden cross."""
    name = "death_cross"

    def _default_params(self) -> dict:
        return {"fast_period": 50, "slow_period": 200}

    def _lookback_days(self) -> int:
        return int(self.params["slow_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        fast = frame["close"].rolling(int(self.params["fast_period"])).mean()
        slow = frame["close"].rolling(int(self.params["slow_period"])).mean()
        below = fast < slow
        cross_down = below & ~below.shift(1, fill_value=False)
        return cross_down.astype(float) * -1.0


class MaSlopePositiveSignalProvider(TechnicalSignalProvider):
    """LEVEL: 1.0 while the moving average is rising — MA(t) > MA(t−N) —
    a trend-strength filter on top of a directional signal."""
    name = "ma_slope_positive"

    def _default_params(self) -> dict:
        return {"period": 50, "lookback": 10}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + int(self.params["lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        ma = frame["close"].rolling(int(self.params["period"])).mean()
        return (ma > ma.shift(int(self.params["lookback"]))).astype(float)


def _macd_lines(
    frame: pd.DataFrame, fast: int, slow: int, signal: int
) -> "tuple[pd.Series, pd.Series]":
    """Shared MACD decomposition: returns (macd_line, signal_line). The
    histogram is `macd_line - signal_line`; identical maths to
    `MacdSignalProvider` so the cross/flip children stay byte-consistent
    with the parent `macd` primitive."""
    fast_ema = frame["close"].ewm(span=fast, adjust=False).mean()
    slow_ema = frame["close"].ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


class MacdSignalCrossSignalProvider(TechnicalSignalProvider):
    """CROSS: +1 when the MACD line crosses ABOVE its signal line
    (bullish), −1 when it crosses below (bearish), 0 otherwise.
    Composes on the `macd` primitive's params."""
    name = "macd_signal_cross"

    def _default_params(self) -> dict:
        return {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def _lookback_days(self) -> int:
        return (int(self.params["slow_period"]) + int(self.params["signal_period"])) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        macd_line, signal_line = _macd_lines(
            frame,
            int(self.params["fast_period"]),
            int(self.params["slow_period"]),
            int(self.params["signal_period"]),
        )
        above = macd_line > signal_line
        bull = above & ~above.shift(1, fill_value=False)
        bear = (~above) & above.shift(1, fill_value=False)
        out = pd.Series(0.0, index=frame.index)
        out[bull] = 1.0
        out[bear] = -1.0
        return out


class MacdHistogramFlipSignalProvider(TechnicalSignalProvider):
    """EVENT: fires on the bar the MACD histogram changes sign — the
    earliest momentum-shift signal. +1 on a flip to positive, −1 on a
    flip to negative; both are non-zero so the EVENT `fires` operator
    catches either direction. Composes on `macd`.

    NOTE (editorial): a histogram sign-change is mathematically the same
    bar as `macd_signal_cross` (histogram = macd_line − signal_line, so
    its zero-cross IS the signal-line cross). The two are kept distinct
    by output_kind — this is the direction-agnostic "momentum flipped"
    EVENT; `macd_signal_cross` is the direction-aware CROSS."""
    name = "macd_histogram_flip"

    def _default_params(self) -> dict:
        return {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def _lookback_days(self) -> int:
        return (int(self.params["slow_period"]) + int(self.params["signal_period"])) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        macd_line, signal_line = _macd_lines(
            frame,
            int(self.params["fast_period"]),
            int(self.params["slow_period"]),
            int(self.params["signal_period"]),
        )
        hist = macd_line - signal_line
        positive = hist > 0
        flip_up = positive & ~positive.shift(1, fill_value=False)
        flip_down = (~positive) & positive.shift(1, fill_value=False)
        out = pd.Series(0.0, index=frame.index)
        out[flip_up] = 1.0
        out[flip_down] = -1.0
        return out


class MacdZeroLineCrossSignalProvider(TechnicalSignalProvider):
    """CROSS: +1 when the MACD line crosses ABOVE zero, −1 when it crosses
    below — a trend-regime change. Composes on `macd`."""
    name = "macd_zero_line_cross"

    def _default_params(self) -> dict:
        return {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def _lookback_days(self) -> int:
        return (int(self.params["slow_period"]) + int(self.params["signal_period"])) * 3

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        macd_line, _ = _macd_lines(
            frame,
            int(self.params["fast_period"]),
            int(self.params["slow_period"]),
            int(self.params["signal_period"]),
        )
        positive = macd_line > 0
        up = positive & ~positive.shift(1, fill_value=False)
        down = (~positive) & positive.shift(1, fill_value=False)
        out = pd.Series(0.0, index=frame.index)
        out[up] = 1.0
        out[down] = -1.0
        return out


# ── RSI / Stochastic / ADX-DMI events (PRD-22b) ─────────────────────────────
# v2 decomposes the mean-reversion + directional-movement families' canonical
# consumption patterns into level/event/cross/regime primitives. RSI +
# Stochastic children compose on the existing `rsi`/`stoch` scalars; the ADX
# children compose on `adx` via the shared `_adx_components` helper.


class RsiOversoldSignalProvider(TechnicalSignalProvider):
    """LEVEL: 1.0 while RSI sits below its oversold threshold (default 30)."""
    name = "rsi_oversold"

    def _default_params(self) -> dict:
        return {"period": 14, "threshold": 30}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        rsi = RsiSignalProvider(period=int(self.params["period"]))._compute(frame)
        return (rsi < float(self.params["threshold"])).astype(float)


class RsiOverboughtSignalProvider(TechnicalSignalProvider):
    """LEVEL: 1.0 while RSI sits above its overbought threshold (default 70)."""
    name = "rsi_overbought"

    def _default_params(self) -> dict:
        return {"period": 14, "threshold": 70}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 4

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        rsi = RsiSignalProvider(period=int(self.params["period"]))._compute(frame)
        return (rsi > float(self.params["threshold"])).astype(float)


def _stoch_k_d(
    frame: pd.DataFrame, k_period: int, d_period: int
) -> "tuple[pd.Series, pd.Series]":
    """Shared stochastic decomposition: %K (matches the `stoch` primitive)
    and %D = SMA(%K, d_period). Keeps the cross children byte-consistent
    with the parent `stoch` scalar."""
    lowest = frame["low"].rolling(k_period).min()
    highest = frame["high"].rolling(k_period).max()
    k = 100 * (frame["close"] - lowest) / (highest - lowest).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


class StochKDCrossSignalProvider(TechnicalSignalProvider):
    """CROSS: +1 when %K crosses above %D, −1 when it crosses below."""
    name = "stoch_k_d_cross"

    def _default_params(self) -> dict:
        return {"k_period": 14, "d_period": 3}

    def _lookback_days(self) -> int:
        return int(self.params["k_period"]) + int(self.params["d_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        k, d = _stoch_k_d(frame, int(self.params["k_period"]), int(self.params["d_period"]))
        above = k > d
        up = above & ~above.shift(1, fill_value=False)
        down = (~above) & above.shift(1, fill_value=False)
        out = pd.Series(0.0, index=frame.index)
        out[up] = 1.0
        out[down] = -1.0
        return out


class StochOversoldCrossUpSignalProvider(TechnicalSignalProvider):
    """EVENT: fires when %K crosses above %D while the %D signal line is
    still in the oversold zone (below the oversold level, default 20) — the
    Wilder-style entry. Gating on %D (the slower line) rather than %K keeps
    the trigger from being skipped when %K rockets off a sharp bottom."""
    name = "stoch_oversold_cross_up"

    def _default_params(self) -> dict:
        return {"k_period": 14, "d_period": 3, "oversold": 20}

    def _lookback_days(self) -> int:
        return int(self.params["k_period"]) + int(self.params["d_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        k, d = _stoch_k_d(frame, int(self.params["k_period"]), int(self.params["d_period"]))
        above = k > d
        cross_up = above & ~above.shift(1, fill_value=False)
        fire = cross_up & (d < float(self.params["oversold"]))
        return fire.astype(float)


class StochOverboughtCrossDownSignalProvider(TechnicalSignalProvider):
    """EVENT: fires when %K crosses below %D while the %D signal line is
    still in the overbought zone (above the overbought level, default 80) —
    the symmetric short entry. Gating on %D rather than %K keeps the trigger
    from being skipped when %K plunges off a sharp top."""
    name = "stoch_overbought_cross_down"

    def _default_params(self) -> dict:
        return {"k_period": 14, "d_period": 3, "overbought": 80}

    def _lookback_days(self) -> int:
        return int(self.params["k_period"]) + int(self.params["d_period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        k, d = _stoch_k_d(frame, int(self.params["k_period"]), int(self.params["d_period"]))
        above = k > d
        cross_down = (~above) & above.shift(1, fill_value=False)
        fire = cross_down & (d > float(self.params["overbought"]))
        return fire.astype(float)


class AdxRegimeSignalProvider(TechnicalSignalProvider):
    """REGIME: trend-strength regime from ADX. Codes: 0 = ranging
    (ADX < 20), 1 = weak (20 ≤ ADX ≤ 25), 2 = trending (ADX > 25)."""
    name = "adx_regime"

    def _default_params(self) -> dict:
        return {"period": 14, "ranging_below": 20, "trending_above": 25}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        adx, _, _ = _adx_components(frame, int(self.params["period"]))
        ranging = float(self.params["ranging_below"])
        trending = float(self.params["trending_above"])
        out = pd.Series(1.0, index=frame.index)  # weak by default
        out[adx < ranging] = 0.0
        out[adx > trending] = 2.0
        out[adx.isna()] = float("nan")  # warmup bars carry no regime
        return out


class AdxRisingSignalProvider(TechnicalSignalProvider):
    """LEVEL: 1.0 while ADX is higher than it was `lookback` bars ago —
    trend strength building."""
    name = "adx_rising"

    def _default_params(self) -> dict:
        return {"period": 14, "lookback": 5}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5 + int(self.params["lookback"])

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        adx, _, _ = _adx_components(frame, int(self.params["period"]))
        return (adx > adx.shift(int(self.params["lookback"]))).astype(float)


class DiCrossBullishSignalProvider(TechnicalSignalProvider):
    """CROSS: +1 on the bar DI+ crosses above DI− — directional momentum
    shifting up."""
    name = "di_cross_bullish"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        _, plus_di, minus_di = _adx_components(frame, int(self.params["period"]))
        above = plus_di > minus_di
        cross_up = above & ~above.shift(1, fill_value=False)
        return cross_up.astype(float)


class DiCrossBearishSignalProvider(TechnicalSignalProvider):
    """CROSS: −1 on the bar DI− crosses above DI+ — directional momentum
    shifting down."""
    name = "di_cross_bearish"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        _, plus_di, minus_di = _adx_components(frame, int(self.params["period"]))
        below = minus_di > plus_di
        cross_down = below & ~below.shift(1, fill_value=False)
        return cross_down.astype(float) * -1.0


# ── Bollinger Band events (PRD-22b) ─────────────────────────────────────────
# v2 decomposes the Bollinger family into its consumption patterns: the
# bandwidth compression metric, the squeeze regime + its release event, and
# the band-walk + band-tag events. All compose on `bbands` via the shared
# `_bollinger_bands` helper. (%B is already shipped as the `bbands` primitive.)


class BbBandwidthSignalProvider(TechnicalSignalProvider):
    """VALUE: Bollinger Bandwidth = (upper − lower) / middle — the
    band-compression metric the squeeze is built on."""
    name = "bb_bandwidth"

    def _default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        upper, middle, lower = _bollinger_bands(
            frame, int(self.params["period"]), float(self.params["std_dev"])
        )
        return (upper - lower) / middle.replace(0, np.nan)


class BbSqueezeSignalProvider(TechnicalSignalProvider):
    """REGIME: 1.0 while Bollinger Bandwidth sits below the squeeze
    threshold (default 4%) — a low-volatility coiling regime; 0.0 otherwise."""
    name = "bb_squeeze"

    def _default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0, "bandwidth_threshold": 0.04}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        upper, middle, lower = _bollinger_bands(
            frame, int(self.params["period"]), float(self.params["std_dev"])
        )
        bbw = (upper - lower) / middle.replace(0, np.nan)
        out = (bbw < float(self.params["bandwidth_threshold"])).astype(float)
        out[bbw.isna()] = float("nan")  # warmup carries no regime
        return out


class BbSqueezeFireSignalProvider(TechnicalSignalProvider):
    """EVENT: fires the bar a squeeze releases — the squeeze was active
    last bar and close exits a band this bar. +1 breakout above the upper
    band, −1 breakdown below the lower band."""
    name = "bb_squeeze_fire"

    def _default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0, "bandwidth_threshold": 0.04}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        upper, middle, lower = _bollinger_bands(
            frame, int(self.params["period"]), float(self.params["std_dev"])
        )
        bbw = (upper - lower) / middle.replace(0, np.nan)
        squeeze_on = bbw < float(self.params["bandwidth_threshold"])
        exits_up = frame["close"] > upper
        exits_down = frame["close"] < lower
        fired = squeeze_on.shift(1, fill_value=False) & (exits_up | exits_down)
        out = pd.Series(0.0, index=frame.index)
        out[fired & exits_up] = 1.0
        out[fired & exits_down] = -1.0
        return out


class BbWalkUpperSignalProvider(TechnicalSignalProvider):
    """EVENT: fires when price completes N consecutive closes above the
    upper band — a band-walk, the trend-continuation signal."""
    name = "bb_walk_upper"

    def _default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0, "consecutive": 3}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        upper, _, _ = _bollinger_bands(
            frame, int(self.params["period"]), float(self.params["std_dev"])
        )
        above = (frame["close"] > upper).astype(int)
        # consecutive run-length of closes above the upper band (the leading
        # below-band bar in each group contributes 0, so the count is clean)
        run = above.groupby((above == 0).cumsum()).cumsum()
        return (run == int(self.params["consecutive"])).astype(float)


class BbTagUpperSignalProvider(TechnicalSignalProvider):
    """EVENT: 1.0 on any bar that closes above the upper band — a band
    tag, the reversal-trader entry."""
    name = "bb_tag_upper"

    def _default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        upper, _, _ = _bollinger_bands(
            frame, int(self.params["period"]), float(self.params["std_dev"])
        )
        return (frame["close"] > upper).astype(float)


class BbTagLowerSignalProvider(TechnicalSignalProvider):
    """EVENT: 1.0 on any bar that closes below the lower band."""
    name = "bb_tag_lower"

    def _default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        _, _, lower = _bollinger_bands(
            frame, int(self.params["period"]), float(self.params["std_dev"])
        )
        return (frame["close"] < lower).astype(float)


# ── Supertrend (PRD-22b) ────────────────────────────────────────────────────
# An ATR-banded trailing line that flips between an upper (down-trend) and
# lower (up-trend) band. The carry-forward band + direction logic is stateful
# (each bar depends on the prior bar), so it's an explicit O(n) pass.


def _supertrend(
    frame: pd.DataFrame, period: int, mult: float
) -> "tuple[pd.Series, pd.Series]":
    """Shared Supertrend decomposition: returns (line, direction). Direction
    is +1 in an up-trend (line = lower band, below price) and −1 in a
    down-trend (line = upper band, above price). Single source of truth for
    the supertrend / flip / above-price children."""
    high, low, close = frame["high"], frame["low"], frame["close"]
    hl2 = (high + low) / 2.0
    atr = AtrSignalProvider(period=period)._compute(frame)
    upper = (hl2 + mult * atr).values
    lower = (hl2 - mult * atr).values
    close_v = close.values
    n = len(frame)
    fu = upper.copy()
    fl = lower.copy()
    line = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    for i in range(1, n):
        # carry-forward final upper band
        if np.isnan(fu[i - 1]) or upper[i] < fu[i - 1] or close_v[i - 1] > fu[i - 1]:
            fu[i] = upper[i]
        else:
            fu[i] = fu[i - 1]
        # carry-forward final lower band
        if np.isnan(fl[i - 1]) or lower[i] > fl[i - 1] or close_v[i - 1] < fl[i - 1]:
            fl[i] = lower[i]
        else:
            fl[i] = fl[i - 1]
        # direction: stay until price breaks the opposite band
        if np.isnan(direction[i - 1]):
            direction[i] = 1.0 if close_v[i] > fu[i] else -1.0
        elif direction[i - 1] == 1.0:
            direction[i] = -1.0 if close_v[i] < fl[i] else 1.0
        else:
            direction[i] = 1.0 if close_v[i] > fu[i] else -1.0
        line[i] = fl[i] if direction[i] == 1.0 else fu[i]
    return (
        pd.Series(line, index=frame.index),
        pd.Series(direction, index=frame.index),
    )


class SupertrendSignalProvider(TechnicalSignalProvider):
    """VALUE: the Supertrend trailing line (hl2 ± mult × ATR with the
    direction carry-forward). Sits below price in an up-trend, above in a
    down-trend — a trailing stop level."""
    name = "supertrend"

    def _default_params(self) -> dict:
        return {"period": 10, "mult": 3.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        line, _ = _supertrend(frame, int(self.params["period"]), float(self.params["mult"]))
        return line


class SupertrendFlipSignalProvider(TechnicalSignalProvider):
    """EVENT: fires the bar the Supertrend flips direction — +1 on a flip
    to up-trend (green), −1 on a flip to down-trend (red). A trend-regime
    change."""
    name = "supertrend_flip"

    def _default_params(self) -> dict:
        return {"period": 10, "mult": 3.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        _, direction = _supertrend(frame, int(self.params["period"]), float(self.params["mult"]))
        flipped = (direction != direction.shift(1)) & direction.shift(1).notna()
        out = pd.Series(0.0, index=frame.index)
        out[flipped & (direction == 1.0)] = 1.0
        out[flipped & (direction == -1.0)] = -1.0
        return out


class SupertrendAbovePriceSignalProvider(TechnicalSignalProvider):
    """LEVEL: 1.0 while the Supertrend line sits above price (a down-trend /
    persistent short flag); 0.0 in an up-trend."""
    name = "supertrend_above_price"

    def _default_params(self) -> dict:
        return {"period": 10, "mult": 3.0}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        _, direction = _supertrend(frame, int(self.params["period"]), float(self.params["mult"]))
        out = (direction == -1.0).astype(float)
        out[direction.isna()] = float("nan")  # warmup carries no direction
        return out


# ── Anchored VWAP (PRD-22b) ─────────────────────────────────────────────────
# v1 anchors to a trailing `anchor_lookback`-bar window (the last-bar value
# equals a true VWAP anchored that many bars back). A fixed date / most-recent-
# earnings anchor is a future enhancement (it needs the earnings-calendar
# source that the fundamental/event family is deferred behind).


def _anchored_vwap(frame: pd.DataFrame, lookback: int) -> pd.Series:
    """Volume-weighted average typical price over a trailing `lookback`
    window. Single source of truth for the AVWAP children."""
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    tpv = (typical * frame["volume"]).rolling(lookback).sum()
    vol = frame["volume"].rolling(lookback).sum()
    return tpv / vol.replace(0, np.nan)


class AnchoredVwapSignalProvider(TechnicalSignalProvider):
    """VALUE: anchored VWAP — the volume-weighted average price since the
    anchor — an institutional reference level."""
    name = "anchored_vwap"

    def _default_params(self) -> dict:
        return {"anchor_lookback": 63}

    def _lookback_days(self) -> int:
        return int(self.params["anchor_lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        return _anchored_vwap(frame, int(self.params["anchor_lookback"]))


class DistanceToAnchoredVwapSignalProvider(TechnicalSignalProvider):
    """DISTANCE: signed percent gap between close and the anchored VWAP.
    Positive = price above the reference, negative = below."""
    name = "distance_to_anchored_vwap"

    def _default_params(self) -> dict:
        return {"anchor_lookback": 63}

    def _lookback_days(self) -> int:
        return int(self.params["anchor_lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        avwap = _anchored_vwap(frame, int(self.params["anchor_lookback"]))
        return 100.0 * (frame["close"] - avwap) / avwap.replace(0, np.nan)


class PriceAboveAnchoredVwapSignalProvider(TechnicalSignalProvider):
    """LEVEL: 1.0 while close trades above the anchored VWAP — a persistent
    buyer-control flag from the anchor date."""
    name = "price_above_anchored_vwap"

    def _default_params(self) -> dict:
        return {"anchor_lookback": 63}

    def _lookback_days(self) -> int:
        return int(self.params["anchor_lookback"]) + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        avwap = _anchored_vwap(frame, int(self.params["anchor_lookback"]))
        return (frame["close"] > avwap).astype(float)


# ── Momentum acceleration + Heikin-Ashi (PRD-22b) ───────────────────────────
# `momentum_12_1` is already shipped as `time_series_momentum` (12-month
# return ex the recent month), so only the acceleration delta is new here.
# The 12-1 / composite z-scores are cross-sectional (standardized across the
# universe) and belong to the rank/cross-sectional path, not the per-symbol
# snapshot — deferred.


class MomentumAccelerationSignalProvider(TechnicalSignalProvider):
    """VALUE: difference between the recent-3-month and trailing-9-month
    return *rates* (each normalized to a per-month rate). Positive =
    momentum is accelerating; ~0 for a steady trend; negative when fading.

    Note: the rates are compared per-month rather than as raw cumulative
    returns — a 9-month cumulative return is mechanically larger than a
    3-month one (compounding), so a raw `ret_3mo - ret_9mo` would just track
    trend magnitude, not acceleration."""
    name = "momentum_acceleration"

    def _default_params(self) -> dict:
        return {"short_months": 3, "long_months": 9}

    def _lookback_days(self) -> int:
        return int(self.params["long_months"]) * 21 + 30

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        short_m = int(self.params["short_months"])
        long_m = int(self.params["long_months"])
        short_rate = frame["close"].pct_change(short_m * 21) / short_m
        long_rate = frame["close"].pct_change(long_m * 21) / long_m
        return short_rate - long_rate


def _heikin_ashi(frame: pd.DataFrame, smoothing: int = 1) -> "tuple[pd.Series, pd.Series]":
    """Shared Heikin-Ashi decomposition: returns (ha_open, ha_close). HA_open
    is recursive (½ of the prior HA open + close), so it's an explicit O(n)
    pass. HA_close is the bar's OHLC average. `smoothing` > 1 applies an EMA
    to both lines (the "smoothed HA" variant); smoothing=1 is raw HA."""
    ha_close = (frame["open"] + frame["high"] + frame["low"] + frame["close"]) / 4.0
    open_v = frame["open"].values
    close_v = frame["close"].values
    hac = ha_close.values
    n = len(frame)
    ha_open_arr = np.full(n, np.nan)
    if n:
        ha_open_arr[0] = (open_v[0] + close_v[0]) / 2.0
    for i in range(1, n):
        ha_open_arr[i] = (ha_open_arr[i - 1] + hac[i - 1]) / 2.0
    ha_open = pd.Series(ha_open_arr, index=frame.index)
    if smoothing > 1:
        ha_open = ha_open.ewm(span=smoothing, adjust=False).mean()
        ha_close = ha_close.ewm(span=smoothing, adjust=False).mean()
    return ha_open, ha_close


class HeikinAshiTrendSignalProvider(TechnicalSignalProvider):
    """REGIME: 1.0 while the Heikin-Ashi candle is up (HA close above HA
    open), 0.0 while down — the smoothed trend direction."""
    name = "heikin_ashi_trend"

    def _default_params(self) -> dict:
        return {"smoothing": 1}

    def _lookback_days(self) -> int:
        return 60

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        ha_open, ha_close = _heikin_ashi(frame, int(self.params["smoothing"]))
        return (ha_close > ha_open).astype(float)


class HeikinAshiConsecutiveSignalProvider(TechnicalSignalProvider):
    """VALUE: signed count of consecutive same-direction Heikin-Ashi candles
    — +N for N green in a row, −N for N red. A trend-persistence metric."""
    name = "heikin_ashi_consecutive"

    def _default_params(self) -> dict:
        return {"smoothing": 1}

    def _lookback_days(self) -> int:
        return 60

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        ha_open, ha_close = _heikin_ashi(frame, int(self.params["smoothing"]))
        color = np.sign((ha_close - ha_open).values)
        n = len(color)
        run = np.zeros(n)
        for i in range(n):
            if i > 0 and color[i] != 0 and color[i] == color[i - 1]:
                run[i] = run[i - 1] + color[i]
            else:
                run[i] = color[i]
        return pd.Series(run, index=frame.index)


class HeikinAshiColorFlipSignalProvider(TechnicalSignalProvider):
    """EVENT: fires the bar a Heikin-Ashi candle changes color — +1 on a
    flip to green (up), −1 on a flip to red (down). A trend-reversal trigger
    with a 1-2 bar delay vs raw price."""
    name = "heikin_ashi_color_flip"

    def _default_params(self) -> dict:
        return {"smoothing": 1}

    def _lookback_days(self) -> int:
        return 60

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        ha_open, ha_close = _heikin_ashi(frame, int(self.params["smoothing"]))
        color = pd.Series(np.sign((ha_close - ha_open).values), index=frame.index)
        prev = color.shift(1)
        flipped = (color != prev) & (color != 0) & prev.notna()
        out = pd.Series(0.0, index=frame.index)
        out[flipped & (color == 1.0)] = 1.0
        out[flipped & (color == -1.0)] = -1.0
        return out


# ── Registry assembly ──────────────────────────────────────────────────────


def get_technical_providers() -> dict:
    """Build the technical-provider registry. Called by `signal_provider.py`
    at module load to extend `_REGISTRY` with these primitives.

    Each entry is `(name, instance_with_default_params)`. Runtime
    parameter overrides happen via the `with_params()` classmethod
    in the preview endpoint, not via the registry.
    """
    classes = [
        # Trend
        SmaSignalProvider, EmaSignalProvider, WmaSignalProvider,
        DemaSignalProvider, TemaSignalProvider, KamaSignalProvider,
        MaCrossoverSignalProvider, MacdSignalProvider, AdxSignalProvider,
        AroonSignalProvider, SarSignalProvider, HtTrendlineSignalProvider,
        # Mean reversion
        RsiSignalProvider, StochSignalProvider, StochRsiSignalProvider,
        WillrSignalProvider, CciSignalProvider, CmoSignalProvider,
        BbandsSignalProvider, MfiSignalProvider, UltoscSignalProvider,
        # Momentum
        RocSignalProvider, MomSignalProvider, TrixSignalProvider,
        ApoSignalProvider, PpoSignalProvider, DonchianBreakoutSignalProvider,
        TimeSeriesMomentumSignalProvider, BopSignalProvider,
        AdxrSignalProvider, AroonOscSignalProvider,
        # Volume
        ObvSignalProvider, AdSignalProvider, AdoscSignalProvider,
        VwapSignalProvider, AvgDollarVolumeSignalProvider,
        # Volatility
        AtrSignalProvider, NatrSignalProvider, TrangeSignalProvider,
        RealizedVolSignalProvider, VolRegimeSignalProvider,
        # Cross-sectional
        RankReturn6mSignalProvider, RankCompositeScoreSignalProvider,
        SectorRotationRankSignalProvider, PairSpreadZscoreSignalProvider,
        # Sentiment placeholder
        AnalystRatingChangeSignalProvider,
        # 52-week extrema (PRD-22b)
        DistanceTo52wHighProvider, DistanceTo52wLowProvider,
        Price52wHighRatioProvider, Price52wHighBreakoutProvider,
        Price52wLowBreakdownProvider, PriceIn52wHighZoneProvider,
        DaysSince52wHighProvider,
        # RVOL + Chandelier + TTM Squeeze (PRD-22b)
        RvolSignalProvider, RvolSurgeSignalProvider,
        ChandelierExitLongSignalProvider, ChandelierExitShortSignalProvider,
        ChandelierExitBreachSignalProvider,
        TtmSqueezeSignalProvider, TtmSqueezeFireSignalProvider,
        # MA + MACD events (PRD-22b)
        PriceAboveMaSignalProvider, PriceMaCrossUpSignalProvider,
        PriceMaCrossDownSignalProvider, GoldenCrossSignalProvider,
        DeathCrossSignalProvider, MaSlopePositiveSignalProvider,
        MacdSignalCrossSignalProvider, MacdHistogramFlipSignalProvider,
        MacdZeroLineCrossSignalProvider,
        # RSI / Stochastic / ADX-DMI events (PRD-22b)
        RsiOversoldSignalProvider, RsiOverboughtSignalProvider,
        StochKDCrossSignalProvider, StochOversoldCrossUpSignalProvider,
        StochOverboughtCrossDownSignalProvider, AdxRegimeSignalProvider,
        AdxRisingSignalProvider, DiCrossBullishSignalProvider,
        DiCrossBearishSignalProvider,
        # Bollinger Band events (PRD-22b)
        BbBandwidthSignalProvider, BbSqueezeSignalProvider,
        BbSqueezeFireSignalProvider, BbWalkUpperSignalProvider,
        BbTagUpperSignalProvider, BbTagLowerSignalProvider,
        # Supertrend + Anchored VWAP (PRD-22b)
        SupertrendSignalProvider, SupertrendFlipSignalProvider,
        SupertrendAbovePriceSignalProvider, AnchoredVwapSignalProvider,
        DistanceToAnchoredVwapSignalProvider, PriceAboveAnchoredVwapSignalProvider,
        # Momentum acceleration + Heikin-Ashi (PRD-22b)
        MomentumAccelerationSignalProvider, HeikinAshiTrendSignalProvider,
        HeikinAshiConsecutiveSignalProvider, HeikinAshiColorFlipSignalProvider,
    ]
    return {cls.name: cls() for cls in classes}
