"""FRED (Federal Reserve Economic Data) client — Macro Pulse signal source.

Thin HTTP wrapper around `https://api.stlouisfed.org/fred/series/observations`
mirroring the AlphaVantageClient pattern. Used by `macro_signals_service` to
fetch:

  - CFNAI         — Chicago Fed National Activity Index (Growth signal proxy;
                    chosen because ISM PMI is no longer redistributed by FRED
                    after the 2017 ISM licensing change. CFNAI tracks 85
                    monthly indicators including industrial production, hours
                    worked, and personal consumption — same narrative as PMI
                    for the "is the economy expanding above trend" question).
  - BAMLH0A0HYM2  — ICE BofA US High Yield Index Option-Adjusted Spread
                    (Stress signal — credit-market risk premium).

Failure modes:
  - Missing API key → raises `FREDError`; caller falls back to mock.
  - HTTP 5xx / network → raises `FREDError`; caller falls back to mock.
  - Empty data payload → raises `FREDError`.

The 2026-05-26 Postgres-process-wedge incident reinforced that external API
clients must NEVER hold a DB session across an `await` (see apps/api/CLAUDE.md
trap #13). This client takes no DB session; it's pure HTTP.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import httpx

from app.core.config import get_settings


class FREDError(RuntimeError):
    """Generic FRED API failure — surfaces to the macro signal builder which
    falls back to the mock series."""


class FREDClient:
    """Async client for the FRED `series/observations` endpoint."""

    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def _request(
        self,
        series_id: str,
        *,
        units: str = "lin",
        frequency: Optional[str] = None,
        observation_start: Optional[str] = None,
    ) -> list[dict]:
        """Fetch raw observations for a FRED series.

        Args:
            series_id: FRED series identifier (e.g. `CFNAI`, `BAMLH0A0HYM2`).
            units: FRED transformation — `lin` (default, no transform),
                `pc1` (percent change YoY), etc. We almost always want `lin`
                and let the service layer compute changes itself.
            frequency: Optional aggregation — `m` (monthly), `d` (daily),
                etc. None = native frequency of the series.
            observation_start: ISO date `YYYY-MM-DD` lower bound. Reduces
                payload size; FRED returns ~30 years by default otherwise.

        Returns:
            List of `{"date": "YYYY-MM-DD", "value": "1.23"}` dicts in
            chronological order (FRED's default sort).

        Raises:
            FREDError if no key, no data, or HTTP error.
        """
        if not self.settings.fred_api_key:
            raise FREDError("FRED_API_KEY is not configured.")

        params: dict[str, str] = {
            "series_id": series_id,
            "api_key": self.settings.fred_api_key,
            "file_type": "json",
            "units": units,
        }
        if frequency:
            params["frequency"] = frequency
        if observation_start:
            params["observation_start"] = observation_start

        async with httpx.AsyncClient(timeout=self.settings.api_timeout_seconds) as client:
            for attempt in range(3):
                try:
                    response = await client.get(self.BASE_URL, params=params)
                except httpx.HTTPError as exc:
                    if attempt < 2:
                        await asyncio.sleep(0.6 * (attempt + 1))
                        continue
                    raise FREDError(f"FRED network error: {exc}") from exc

                if response.status_code == 429:
                    # FRED rate-limit: 120 req/min — should never hit this on
                    # the daily macro pulse cadence, but back-off-and-retry
                    # anyway in case of bursty load.
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise FREDError("FRED rate limit (429) after retries.")

                if response.status_code >= 400:
                    # 400 here is usually a bad series_id or expired key.
                    # Surface the body so the caller log is actionable.
                    raise FREDError(
                        f"FRED HTTP {response.status_code}: {response.text[:200]}"
                    )

                payload = response.json()
                observations = payload.get("observations", [])
                if not observations:
                    raise FREDError(
                        f"FRED returned no observations for series_id={series_id}"
                    )
                return observations

        raise FREDError("FRED request failed after retries.")

    async def fetch_series(
        self,
        series_id: str,
        *,
        observation_start: Optional[str] = None,
        frequency: Optional[str] = None,
    ) -> list[dict]:
        """Public fetch — returns chronologically-ordered observations.

        Each observation: `{"date": date, "value": float}`. FRED's `.`
        sentinel for missing values is filtered out so callers get a
        clean numeric series.
        """
        raw = await self._request(
            series_id,
            observation_start=observation_start,
            frequency=frequency,
        )
        cleaned: list[dict] = []
        for obs in raw:
            value_str = obs.get("value")
            if value_str is None or value_str in (".", "", "NaN"):
                continue
            try:
                cleaned.append(
                    {
                        "date": datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                        "value": float(value_str),
                    }
                )
            except (KeyError, ValueError):
                continue
        return cleaned
