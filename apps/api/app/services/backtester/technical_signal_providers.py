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


class AdxSignalProvider(TechnicalSignalProvider):
    """Average Directional Index — Wilder's smoothed directional movement.
    Returns ADX values (0-100); >25 typically means trending."""
    name = "adx"

    def _default_params(self) -> dict:
        return {"period": 14}

    def _lookback_days(self) -> int:
        return int(self.params["period"]) * 5

    def _compute(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
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
        return dx.ewm(alpha=1 / period, adjust=False).mean()


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
        period = int(self.params["period"])
        std_dev = float(self.params["std_dev"])
        sma = frame["close"].rolling(period).mean()
        std = frame["close"].rolling(period).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
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
    ]
    return {cls.name: cls() for cls in classes}
