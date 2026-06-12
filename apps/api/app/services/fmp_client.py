from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Optional

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
    # FMP /stable/quote/{symbols} (path-based) accepts comma-separated symbols and
    # returns a list, same as the v3 /quote/{symbols} convention preserved in stable.
    # 100 is the proven FMP chunk size — splits 500 S&P 500 names into 5 concurrent calls.
    BATCH_SYMBOL_LIMIT = 100
    # Max concurrent path-batch chunks. Even 2 concurrent triggered FMP's burst
    # limiter for late-alphabet chunks (M-Z), dropping coverage to ~88% on cold
    # cache. Strict serial (1) trades ~1s latency for 100% first-call coverage.
    # 5 chunks × ~500ms = ~2.5s — still well inside the user-facing budget.
    BATCH_CONCURRENT_CHUNKS = 1
    # Conservative bound for the individual-call fallback path: 10 concurrent requests
    # keeps the worst case (path-batch entirely broken) safely under FMP rate limits.
    CONCURRENT_QUOTE_LIMIT = 10

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

    # ── Intraday bars (PRD-16c live tracking) ────────────────────────────────
    # FMP's /stable/historical-chart serves fresh intraday DURING market hours
    # (~15-min delayed on our plan) — unlike AV's plain TIME_SERIES_INTRADAY,
    # which lags a full session intraday without the (separately-priced)
    # realtime/delayed entitlement our key lacks. Returns the SAME shape as
    # `AlphaVantageClient.fetch_intraday_bars` so `IntradayBarService` can use
    # either interchangeably.
    _INTRADAY_INTERVALS = {
        "5min": "5min", "15min": "15min", "30min": "30min", "60min": "1hour",
    }

    async def fetch_intraday_bars(
        self,
        symbol: str,
        interval: str = "15min",
        outputsize: str = "compact",
    ) -> list[dict]:
        """Fetch intraday OHLCV bars from `/stable/historical-chart/{interval}`.

        interval: '5min' | '15min' | '30min' | '60min' (60min → FMP '1hour').
        outputsize: 'compact' caps to the most recent ~120 bars (live cron);
                    'full' keeps ~800 (intraday backtests).

        Returns a list of {"bar_time": datetime, "open", "high", "low",
        "close", "volume"} dicts sorted oldest→newest. FMP's `date` is naive
        wall-clock US/Eastern — parsed naive, matching the `intraday_bars`
        cache convention (identical to the AV path)."""
        fmp_iv = self._INTRADAY_INTERVALS.get(interval)
        if fmp_iv is None:
            raise FMPError(
                f"Invalid intraday interval '{interval}'. "
                "Must be 5min, 15min, 30min, or 60min."
            )
        data = await self._get(
            f"/historical-chart/{fmp_iv}", {"symbol": symbol.upper()}
        )
        if not isinstance(data, list) or not data:
            raise FMPError(f"No intraday data returned for {symbol} @ {interval}.")
        cap = 120 if outputsize == "compact" else 800
        bars: list[dict] = []
        for row in data[:cap]:  # FMP returns newest-first
            ds = row.get("date")
            if not ds:
                continue
            try:
                bar_time = datetime.strptime(ds, "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                continue
            try:
                bars.append({
                    "bar_time": bar_time,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        if not bars:
            raise FMPError(f"No parseable intraday bars for {symbol} @ {interval}.")
        return sorted(bars, key=lambda b: b["bar_time"])

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
        """Live quote — price, change, volume. Never cached. Extremely fast.

        Normalises class-share dot notation to FMP's hyphen convention on the
        way out (BRK.B → BRK-B), then maps the response symbol back to the
        caller's convention so downstream lookups by `BRK.B` continue to work.
        """
        original = symbol.upper()
        fmp_sym = original.replace(".", "-")
        try:
            data = await self._get("/quote", {"symbol": fmp_sym})
            row = None
            if isinstance(data, list) and data:
                row = data[0]
            elif isinstance(data, dict) and data.get("price"):
                row = data
            if row is not None:
                row["symbol"] = original
                return row
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
        """Live quotes for N symbols via FMP /stable/quote.

        Strategy:
          Phase 1 — path-based batch: hit /stable/quote/SYM1,SYM2,...,SYM100 per
            chunk. FMP returns a JSON list covering all asset types (stocks,
            ETFs, indices). 500 S&P 500 symbols resolve in 5 concurrent calls.
            This is the same convention fmpsdk / fmp_py use against v3.
          Phase 2 — individual fallback: any symbol the batch didn't return is
            fetched via /stable/quote?symbol=SYM, bounded by
            CONCURRENT_QUOTE_LIMIT to stay under FMP's rate limit. Handles the
            edge case where path-based batch silently drops a symbol (bad
            ticker, FMP-internal filter, etc.).
        """
        if not symbols:
            return []
        pending = list(dict.fromkeys(s.upper() for s in symbols if s))
        collected: dict[str, dict] = {}

        # Phase 1: path-based batch — throttled to avoid FMP burst rate limit
        chunks = [
            pending[i:i + self.BATCH_SYMBOL_LIMIT]
            for i in range(0, len(pending), self.BATCH_SYMBOL_LIMIT)
        ]
        batch_sem = asyncio.Semaphore(self.BATCH_CONCURRENT_CHUNKS)

        async def _throttled_batch(chunk: list[str]) -> list[dict]:
            async with batch_sem:
                return await self._get_quote_batch_path(chunk)

        batch_results = await asyncio.gather(
            *(_throttled_batch(chunk) for chunk in chunks),
            return_exceptions=True,
        )
        for result in batch_results:
            if isinstance(result, Exception):
                continue
            for item in result:
                if not isinstance(item, dict):
                    continue
                sym = item.get("symbol")
                if not sym:
                    continue
                collected[str(sym).upper()] = item

        # Phase 2: individual fallback for any symbols the batch missed
        missing = [s for s in pending if s not in collected]
        if missing:
            sem = asyncio.Semaphore(self.CONCURRENT_QUOTE_LIMIT)

            async def _fetch_one(sym: str) -> Optional[dict]:
                async with sem:
                    return await self.get_quote(sym)

            fallback = await asyncio.gather(
                *(_fetch_one(s) for s in missing),
                return_exceptions=True,
            )
            for r in fallback:
                if isinstance(r, dict) and r.get("symbol"):
                    collected[str(r["symbol"]).upper()] = r

        return [collected[s] for s in pending if s in collected]

    async def _get_quote_batch_path(self, symbols: list[str]) -> list[dict]:
        """Fetch one chunk via /stable/quote/SYM1,SYM2,...,SYMN (path-based).

        FMP normalises class-share tickers to the hyphen convention
        (BRK-B, not BRK.B). We translate on the way out and reverse-map the
        response symbols back to the caller's convention so the rest of the
        codebase can look up `BRK.B` directly.
        """
        if not symbols:
            return []
        # Caller convention (dot) ↔ FMP convention (hyphen)
        to_caller = {s.replace(".", "-"): s for s in symbols}
        fmp_syms = list(to_caller.keys())
        data = await self._get(f"/quote/{','.join(fmp_syms)}", {})
        if not isinstance(data, list):
            return []
        out: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            fmp_sym = str(item.get("symbol", "")).upper()
            caller_sym = to_caller.get(fmp_sym, fmp_sym)
            item["symbol"] = caller_sym
            out.append(item)
        return out

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
