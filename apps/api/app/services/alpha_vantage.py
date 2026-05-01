from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from app.core.config import get_settings


class AlphaVantageError(RuntimeError):
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

                info_message = payload.get("Information", "")
                if "Note" in payload:
                    raise AlphaVantageError(payload["Note"])
                if "Error Message" in payload:
                    raise AlphaVantageError(payload["Error Message"])
                if (
                    info_message
                    and "1 request per second" in info_message.lower()
                    and attempt < 2
                ):
                    await asyncio.sleep(1.2)
                    continue
                return payload

        raise AlphaVantageError("Alpha Vantage request failed after retries.")

    async def fetch_daily_adjusted(self, symbol: str) -> list[dict]:
        payload = await self._request(
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": "compact",
            }
        )
        raw_series = payload.get("Time Series (Daily)", {})
        bars = []
        for trading_date, values in raw_series.items():
            adjusted_close = float(values.get("5. adjusted close", values["4. close"]))
            volume_key = "6. volume" if "6. volume" in values else "5. volume"
            bars.append(
                {
                    "symbol": symbol,
                    "trading_date": datetime.strptime(trading_date, "%Y-%m-%d").date(),
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["4. close"]),
                    "adjusted_close": adjusted_close,
                    "volume": int(float(values[volume_key])),
                    "dividend_amount": float(values.get("7. dividend amount", 0.0)),
                    "split_coefficient": float(values.get("8. split coefficient", 1.0)),
                }
            )
        return sorted(bars, key=lambda item: item["trading_date"])

    async def search_symbols(self, query: str) -> list[dict]:
        payload = await self._request({"function": "SYMBOL_SEARCH", "keywords": query})
        matches = payload.get("bestMatches", [])
        results = []
        for match in matches[:10]:
            results.append(
                {
                    "symbol": match.get("1. symbol", "").upper(),
                    "name": match.get("2. name", ""),
                    "instrument_type": match.get("3. type"),
                    "region": match.get("4. region"),
                    "currency": match.get("8. currency"),
                }
            )
        return results
