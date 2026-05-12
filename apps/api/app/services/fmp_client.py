from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings


class FMPError(RuntimeError):
    pass


class FMPRateLimitError(FMPError):
    pass


class FMPNotConfiguredError(FMPError):
    pass


class FMPClient:
    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _api_key(self) -> str:
        key = self.settings.financial_modeling_prep_api_key
        if not key:
            raise FMPNotConfiguredError("FINANCIAL_MODELING_PREP_API_KEY is not configured.")
        return key

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        all_params = {"apikey": self._api_key(), **(params or {})}
        url = f"{self.BASE_URL}{path}"
        async with httpx.AsyncClient(timeout=self.settings.api_timeout_seconds) as client:
            for attempt in range(3):
                response = await client.get(url, params=all_params)
                if response.status_code == 429:
                    if attempt < 2:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise FMPRateLimitError("FMP rate limit exceeded.")
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and data.get("Error Message"):
                    raise FMPError(data["Error Message"])
                return data
        raise FMPError("FMP request failed after retries.")

    async def get_profile(self, symbol: str) -> dict:
        """Company profile: name, sector, industry, description, market cap, P/E, etc."""
        data = await self._get(f"/profile/{symbol.upper()}")
        if not data or not isinstance(data, list):
            raise FMPError(f"No profile data for {symbol}")
        return data[0]

    async def get_key_metrics(self, symbol: str, limit: int = 1) -> dict:
        """Key financial metrics (TTM): P/E, P/B, ROE, FCF yield, debt/equity, etc."""
        data = await self._get(f"/key-metrics-ttm/{symbol.upper()}", {"limit": limit})
        if not data or not isinstance(data, list):
            raise FMPError(f"No key metrics for {symbol}")
        return data[0]

    async def get_income_statement(self, symbol: str, limit: int = 5) -> list[dict]:
        """Annual income statements for growth trend."""
        data = await self._get(f"/income-statement/{symbol.upper()}", {"limit": limit})
        return data if isinstance(data, list) else []

    async def get_cash_flow(self, symbol: str, limit: int = 5) -> list[dict]:
        """Annual cash flow statements."""
        data = await self._get(f"/cash-flow-statement/{symbol.upper()}", {"limit": limit})
        return data if isinstance(data, list) else []

    async def get_balance_sheet(self, symbol: str, limit: int = 3) -> list[dict]:
        """Annual balance sheets."""
        data = await self._get(f"/balance-sheet-statement/{symbol.upper()}", {"limit": limit})
        return data if isinstance(data, list) else []

    async def get_peers(self, symbol: str) -> list[str]:
        """Stock peers/competitors from FMP."""
        data = await self._get(f"/stock_peers", {"symbol": symbol.upper()})
        if isinstance(data, list) and data:
            return data[0].get("peersList", [])
        return []

    async def search(self, query: str, limit: int = 20) -> list[dict]:
        """Symbol search."""
        data = await self._get("/search", {"query": query, "limit": limit})
        return data if isinstance(data, list) else []

    async def get_sec_filings(
        self, symbol: str, filing_type: str = "10-K", limit: int = 1
    ) -> list[dict]:
        """SEC filing metadata including direct EDGAR document URL (finalLink)."""
        data = await self._get(
            f"/sec-filings/{symbol.upper()}",
            {"type": filing_type, "limit": limit},
        )
        return data if isinstance(data, list) else []
