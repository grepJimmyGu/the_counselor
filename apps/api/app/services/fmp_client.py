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
    # FMP deprecated /api/v3 for new subscribers after Aug 2025; all calls now use /stable
    BASE_URL = "https://financialmodelingprep.com/stable"

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
        """Company profile: name, sector, industry, description, market cap, price, etc."""
        data = await self._get("/profile", {"symbol": symbol.upper()})
        if not data or not isinstance(data, list):
            raise FMPError(f"No profile data for {symbol}")
        return data[0]

    async def get_key_metrics(self, symbol: str, limit: int = 1) -> dict:
        """
        Key financial metrics (TTM). Returns a normalised dict that maps
        stable-API field names to the legacy TTM names our downstream code expects.
        """
        data = await self._get("/key-metrics-ttm", {"symbol": symbol.upper()})
        if not data or not isinstance(data, list):
            raise FMPError(f"No key metrics for {symbol}")
        raw = data[0]
        return _normalise_key_metrics(raw)

    async def get_income_statement(self, symbol: str, limit: int = 5) -> list[dict]:
        """Annual income statements."""
        data = await self._get("/income-statement", {"symbol": symbol.upper(), "limit": limit})
        return data if isinstance(data, list) else []

    async def get_cash_flow(self, symbol: str, limit: int = 5) -> list[dict]:
        """Annual cash flow statements."""
        data = await self._get("/cash-flow-statement", {"symbol": symbol.upper(), "limit": limit})
        return data if isinstance(data, list) else []

    async def get_balance_sheet(self, symbol: str, limit: int = 3) -> list[dict]:
        """Annual balance sheets."""
        data = await self._get("/balance-sheet-statement", {"symbol": symbol.upper(), "limit": limit})
        return data if isinstance(data, list) else []

    async def get_peers(self, symbol: str) -> list[str]:
        """
        Stock peers. Stable API returns full objects; we extract symbols only.
        """
        data = await self._get("/stock-peers", {"symbol": symbol.upper()})
        if not isinstance(data, list):
            return []
        # New format: [{symbol, companyName, price, mktCap}, ...]
        # Old format: [{peersList: [...]}] — handle both for safety
        if data and isinstance(data[0], dict):
            if "peersList" in data[0]:
                return data[0].get("peersList", [])
            return [p["symbol"] for p in data if p.get("symbol")]
        return []

    async def get_sec_filings(
        self, symbol: str, filing_type: str = "10-K", limit: int = 1
    ) -> list[dict]:
        """
        Get SEC filing metadata. FMP's stable API doesn't expose sec-filings,
        so we resolve the latest 10-K URL via SEC EDGAR's free submissions API
        using the CIK from the company profile.
        """
        try:
            profile = await self.get_profile(symbol)
            cik = profile.get("cik", "")
            if not cik:
                return []
            return await _edgar_latest_filing(cik, filing_type, limit)
        except Exception:
            return []

    async def get_quote(self, symbol: str) -> dict | None:
        """Live quote — price, change, volume. Never cached. Extremely fast."""
        try:
            data = await self._get("/quote", {"symbol": symbol.upper()})
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict) and data.get("price"):
                return data
        except Exception:
            pass
        return None

    async def get_historical_eod(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> list[dict]:
        """End-of-day historical OHLCV bars for `symbol` between
        `from_date` and `to_date` (both ISO YYYY-MM-DD strings, inclusive).

        Supports `^`-prefixed index symbols like `^GSPC` / `^DJI` /
        `^IXIC` — the same symbols `get_quote` accepts. Used by the
        ^GSPC backfill script (`apps/api/scripts/backfill_gspc.py`).

        Returns a list of dicts with keys: `symbol`, `date`, `open`,
        `high`, `low`, `close`, `volume`, `change`, `changePercent`,
        `vwap`. Empty list if FMP returns nothing (bad symbol, gap in
        the date range, etc.).
        """
        data = await self._get(
            "/historical-price-eod/full",
            {"symbol": symbol.upper(), "from": from_date, "to": to_date},
        )
        if isinstance(data, list):
            return data
        return []

    async def get_quotes_batch(self, symbols: list[str]) -> list[dict]:
        """Live quotes for N symbols. Fans out to N parallel `get_quote(symbol)`
        calls via asyncio.gather. Drops the comma-separated batch optimization
        because FMP's /stable/quote treats `?symbol=A,B,C` as a single literal
        ticker rather than a list (verified 2026-05-21 — endpoint returned `{}`).

        Cost note: at the design point (~11 ticker-bar symbols polled every
        30s when all stale), this is ~22 calls/min steady-state — well
        under FMP starter's ~300/min limit.
        """
        if not symbols:
            return []
        upper = [s.upper() for s in symbols]
        results = await asyncio.gather(
            *(self.get_quote(sym) for sym in upper),
            return_exceptions=False,
        )
        return [r for r in results if r is not None]

    async def get_revenue_segments(self, symbol: str, limit: int = 5) -> list[dict]:
        """Annual product/business revenue segmentation (last N years)."""
        try:
            data = await self._get(
                "/revenue-product-segmentation",
                {"symbol": symbol.upper(), "limit": limit},
            )
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def get_geo_segments(self, symbol: str, limit: int = 5) -> list[dict]:
        """Annual geographic revenue segmentation (last N years)."""
        try:
            data = await self._get(
                "/revenue-geographic-segmentation",
                {"symbol": symbol.upper(), "limit": limit},
            )
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def search(self, query: str, limit: int = 20) -> list[dict]:
        """Symbol search — uses stable search endpoint, falls back to empty list."""
        try:
            data = await self._get("/search", {"query": query, "limit": limit})
            return data if isinstance(data, list) else []
        except Exception:
            return []


# ── Field normalisation ───────────────────────────────────────────────────────

def _normalise_key_metrics(raw: dict) -> dict:
    """
    Map stable-API key-metric field names to the legacy names used by
    financial_validation_service.py and fmp_adapter.py, so those services
    need no changes.
    """
    out = dict(raw)

    # ROE: stable uses returnOnEquityTTM
    out.setdefault("roeTTM", raw.get("returnOnEquityTTM"))

    # P/E: stable dropped peRatioTTM; derive from earningsYieldTTM (= E/P)
    if "peRatioTTM" not in raw:
        ey = raw.get("earningsYieldTTM")
        try:
            out["peRatioTTM"] = round(1.0 / float(ey), 2) if ey and float(ey) > 0 else None
        except (ValueError, TypeError):
            out["peRatioTTM"] = None

    # P/S: use EV/Sales as the closest available proxy
    out.setdefault("priceToSalesRatioTTM", raw.get("evToSalesTTM"))

    # P/B: not in new key-metrics; leave as None (will show "—" in UI)
    out.setdefault("pbRatioTTM", None)

    # Dividend yield: not in key-metrics-ttm; caller can enrich from profile
    out.setdefault("dividendYieldPercentageTTM", None)

    # EV/EBITDA alias
    out.setdefault("enterpriseValueOverEBITDATTM", raw.get("evToEBITDATTM"))

    return out


# ── SEC EDGAR helper ──────────────────────────────────────────────────────────

async def _edgar_latest_filing(cik: str, filing_type: str, limit: int) -> list[dict]:
    """
    Use SEC EDGAR's free submissions API to find the latest 10-K/10-Q filing URL.
    CIK must be zero-padded to 10 digits.
    """
    cik_clean = cik.lstrip("0")
    cik_padded = cik_clean.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    headers = {
        "User-Agent": "livermore-research/1.0 contact@livermore.app",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])

    results = []
    for form, date, acc, doc in zip(forms, dates, accessions, primary_docs):
        if form == filing_type:
            acc_clean = acc.replace("-", "")
            final_link = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{acc_clean}/{doc}"
            )
            results.append({
                "symbol": "",
                "type": form,
                "dateFiled": date,
                "finalLink": final_link,
                "link": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_padded}&type={filing_type}",
            })
            if len(results) >= limit:
                break

    return results
