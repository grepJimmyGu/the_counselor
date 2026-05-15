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
