from __future__ import annotations

from typing import Protocol

from app.schemas.fundamental import CompanyProfile, KeyMetrics


class FundamentalAdapter(Protocol):
    """
    Abstract interface for fundamental data providers.
    Implementations: FMPAdapter (production), YFinanceAdapter (dev/fallback).
    Any new provider (Polygon, Finnhub fundamentals, etc.) implements this protocol.
    """

    async def get_profile(self, symbol: str) -> CompanyProfile: ...
    async def get_key_metrics(self, symbol: str) -> KeyMetrics: ...
    async def get_peers(self, symbol: str) -> list[str]: ...
