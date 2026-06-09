from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from app.core.config import get_settings


class AlphaVantageError(RuntimeError):
    pass


class AlphaVantageRateLimitError(AlphaVantageError):
    pass


class AlphaVantageClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = "https://www.alphavantage.co/query"

    async def _request(self, params: dict[str, str]) -> dict:
        if not self.settings.alpha_vantage_api_key:
            raise AlphaVantageError("ALPHA_VANTAGE_API_KEY is not configured.")

        params = {**params, "apikey": self.settings.alpha_vantage_api_key}
        async with httpx.AsyncClient(timeout=self.settings.api_timeout_seconds) as client:
            for attempt in range(3):
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()

                if "Error Message" in payload:
                    raise AlphaVantageError(payload["Error Message"])
                if "Note" in payload:
                    raise AlphaVantageError(payload["Note"])

                info = payload.get("Information", "")
                if info and "api call frequency" in info.lower():
                    if attempt < 2:
                        await asyncio.sleep(1.2 * (attempt + 1))
                        continue
                    raise AlphaVantageRateLimitError(info)

                return payload

        raise AlphaVantageError("Alpha Vantage request failed after retries.")

    async def fetch_daily_adjusted(self, symbol: str, outputsize: str = "full") -> list[dict]:
        payload = await self._request(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol,
                "outputsize": outputsize,
            }
        )
        raw_series = payload.get("Time Series (Daily)", {})
        if not raw_series:
            raise AlphaVantageError(
                f"No price data returned for {symbol}. "
                "The symbol may be invalid or delisted."
            )
        bars = []
        for trading_date, values in raw_series.items():
            bars.append(
                {
                    "symbol": symbol.upper(),
                    "trading_date": datetime.strptime(trading_date, "%Y-%m-%d").date(),
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["4. close"]),
                    "adjusted_close": float(values["5. adjusted close"]),
                    "volume": int(float(values["6. volume"])),
                    "dividend_amount": float(values.get("7. dividend amount", 0.0)),
                    "split_coefficient": float(values.get("8. split coefficient", 1.0)),
                }
            )
        return sorted(bars, key=lambda item: item["trading_date"])

    async def fetch_commodity_spot(
        self,
        function: str,
        interval: str = "monthly",
    ) -> list[dict]:
        """
        Fetch commodity spot price series from Alpha Vantage's commodity endpoints.

        function: "WTI" | "BRENT" | "NATURAL_GAS" | "COPPER" | "WHEAT" | "CORN" etc.
        interval: "daily" | "weekly" | "monthly" (free plan: monthly only)

        Returns list of {"date": date, "value": float} sorted oldest→newest.
        The "value" is in the unit Alpha Vantage reports:
          WTI/BRENT     → dollars per barrel
          COPPER        → dollars per metric ton (AV) — caller converts to $/lb
          WHEAT         → cents per bushel
          NATURAL_GAS   → dollars per million BTU
        """
        payload = await self._request({
            "function": function,
            "interval": interval,
            "datatype": "json",
        })
        raw_data = payload.get("data", [])
        if not raw_data:
            raise AlphaVantageError(
                f"No commodity data returned for function={function} interval={interval}"
            )

        result = []
        for item in raw_data:
            try:
                val_str = item.get("value", ".")
                if val_str and val_str not in (".", "None", ""):
                    result.append({
                        "date": datetime.strptime(item["date"], "%Y-%m-%d").date(),
                        "value": float(val_str),
                    })
            except (KeyError, ValueError):
                continue
        return sorted(result, key=lambda x: x["date"])

    async def fetch_treasury_yield(
        self, maturity: str = "10year", interval: str = "monthly"
    ) -> list[dict]:
        """AV Economic Indicators — `function=TREASURY_YIELD`. Returns the
        full historical series for the requested maturity. Free-tier per
        AV docs; no Premium gate.

        Phase 1c uses this for the Rates row in MacroPulseTable.
        """
        payload = await self._request(
            {
                "function": "TREASURY_YIELD",
                "interval": interval,
                "maturity": maturity,
                "datatype": "json",
            }
        )
        data = payload.get("data", [])
        if not data:
            raise AlphaVantageError(
                f"No Treasury yield data returned ({maturity}, {interval})."
            )
        # AV returns [{ "date": "2026-05-01", "value": "4.30" }, ...]
        # Newest first; we flip to chronological order for downstream consumers.
        return list(reversed(data))

    async def fetch_cpi(self, interval: str = "monthly") -> list[dict]:
        """AV Economic Indicators — `function=CPI`. Returns the full
        historical CPI series. Free-tier per AV docs.

        Note: this is HEADLINE CPI, not Core CPI. AV doesn't expose a
        dedicated Core CPI series; FRED (`CORESTICKM158SFRBATL` or
        `CPILFESL`) is the typical source. Phase 1c uses headline CPI as
        an approximation; Phase 1c-extra wires FRED for the dedicated
        Core CPI series.
        """
        payload = await self._request(
            {
                "function": "CPI",
                "interval": interval,
                "datatype": "json",
            }
        )
        data = payload.get("data", [])
        if not data:
            raise AlphaVantageError("No CPI data returned.")
        return list(reversed(data))

    async def fetch_intraday_bars(
        self,
        symbol: str,
        interval: str = "15min",
        outputsize: str = "compact",
    ) -> list[dict]:
        """Fetch intraday OHLCV bars from Alpha Vantage.

        interval: '5min' | '15min' | '30min' | '60min' (1min skipped in v1).
        outputsize:
          - 'compact' → ~100 most-recent bars (~25h of 15-min bars).
            Used by the live monitor (recent state only).
          - 'full' → up to 30 days of history. Used by intraday backtests.

        Returns a list of {"bar_time": datetime, "open", "high", "low",
        "close", "volume"} dicts sorted oldest→newest. Caller writes them
        to the `intraday_bars` cache.

        AV's intraday endpoint quirks:
          - Times are wall-clock in market timezone (US/Eastern); we parse
            naive and let the cache key on naive bar_time.
          - The "Time Series ({interval})" key is hyphenated, not
            underscore (different from daily / TA endpoints).
        """
        if interval not in {"5min", "15min", "30min", "60min"}:
            raise AlphaVantageError(
                f"Invalid intraday interval '{interval}'. "
                "Must be 5min, 15min, 30min, or 60min."
            )
        payload = await self._request(
            {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "datatype": "json",
            }
        )
        series_key = f"Time Series ({interval})"
        raw_series = payload.get(series_key, {})
        if not raw_series:
            raise AlphaVantageError(
                f"No intraday data returned for {symbol} @ {interval}."
            )
        bars = []
        for bar_time_str, values in raw_series.items():
            bars.append(
                {
                    "bar_time": datetime.strptime(bar_time_str, "%Y-%m-%d %H:%M:%S"),
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["4. close"]),
                    "volume": float(values["5. volume"]),
                }
            )
        return sorted(bars, key=lambda item: item["bar_time"])

    async def fetch_technical_indicator(
        self,
        function: str,
        symbol: str,
        params: dict,
        interval: str = "daily",
    ) -> list[dict]:
        """Generic wrapper for Alpha Vantage's TA indicator endpoints.

        function: e.g. 'KAMA', 'SAR', 'HT_TRENDLINE', 'AROON', 'ULTOSC',
                  'TRIX', 'ADXR', 'ADOSC', 'TRANGE' — anything from AV's
                  technical-indicators surface.
        symbol:   ticker to compute the indicator for.
        params:   indicator-specific parameters (e.g. {"time_period": 14}
                  for RSI). AV's required+optional params vary by function;
                  pass the raw param names AV expects.
        interval: 'daily' | 'weekly' | 'monthly' | '60min' | etc.
                  Daily is the default for PRD-16a; PRD-16c extends to
                  intraday intervals.

        Returns the parsed payload as a list of {"date": date, **values}
        dicts sorted oldest→newest. AV's response shape differs per
        indicator — most use a single value key (e.g. "RSI"), some use
        multiple (MACD has "MACD", "MACD_Signal", "MACD_Hist"). Callers
        get the raw values and pick the column they want.

        Raises `AlphaVantageError` on payload errors (rate limit,
        invalid symbol, missing data).
        """
        request_params = {
            "function": function,
            "symbol": symbol,
            "interval": interval,
            "datatype": "json",
            **{k: str(v) for k, v in params.items()},
        }
        payload = await self._request(request_params)

        # AV returns the time series under a key like "Technical Analysis: RSI".
        # Find it by prefix-matching rather than hard-coding per indicator.
        series_key = next(
            (k for k in payload.keys() if k.startswith("Technical Analysis:")),
            None,
        )
        if series_key is None:
            raise AlphaVantageError(
                f"No technical-indicator series returned for {function}({symbol})."
            )
        raw_series = payload[series_key]

        rows = []
        for trading_date, values in raw_series.items():
            parsed = {"date": datetime.strptime(trading_date, "%Y-%m-%d").date()}
            for col_name, val_str in values.items():
                try:
                    parsed[col_name] = float(val_str)
                except (TypeError, ValueError):
                    parsed[col_name] = None
            rows.append(parsed)
        return sorted(rows, key=lambda item: item["date"])

    async def search_symbols(self, query: str) -> list[dict]:
        payload = await self._request({"function": "SYMBOL_SEARCH", "keywords": query})
        matches = payload.get("bestMatches", [])
        results = []
        for match in matches[:10]:
            raw_score = match.get("9. matchScore")
            results.append(
                {
                    "symbol": match.get("1. symbol", "").upper(),
                    "name": match.get("2. name", ""),
                    "instrument_type": match.get("3. type"),
                    "region": match.get("4. region"),
                    "timezone": match.get("7. timezone"),
                    "currency": match.get("8. currency"),
                    "alpha_vantage_match_score": float(raw_score) if raw_score else None,
                    "exchange": None,  # AV SYMBOL_SEARCH v1 does not expose a clean exchange field
                }
            )
        return results
