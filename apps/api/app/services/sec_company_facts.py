"""Fetches a company's XBRL facts from SEC EDGAR and caches the analysis.

Two public, key-less endpoints:

  https://www.sec.gov/files/company_tickers.json          ticker → CIK
  https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json

Both verified against the live service on 2026-11-17 (apps/api/CLAUDE.md
trap #14); the second is the fixture in tests/test_filing_financials.py.

The raw facts for a large company are ~4 MB of JSON, so they are parsed,
reduced to a `FilingAnalysis`, and dropped — only the small result is kept.
Nothing here touches the database. The caches are plain dicts; the only
asyncio state is the sharing of an in-flight fetch, and that is kept per
event loop (trap #22).

A fetch is shared because the portfolio agent reads filings for many users in
the same minute, and most watchlists have the same few names on them: without
sharing, eight scans starting together each download Apple's 4 MB.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

from app.core.concurrency import PerLoop, SingleFlight
from app.services.filing_financials import FilingAnalysis, NoQuarterlyData, analyse
from app.services.sec_edgar_client import _HEADERS

_log = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_TIMEOUT = 30.0

# A filing changes the answer at most once a quarter; six hours means a new
# 10-Q shows up the same day without asking the SEC on every page view.
ANALYSIS_TTL_SECONDS = 6 * 3600
TICKERS_TTL_SECONDS = 24 * 3600
# An analysis is about 12 KB once the raw facts are dropped, so this is ~25 MB
# at most. It was 256, which the agent's scans would cycle through and refetch
# once a few hundred different symbols were being watched.
_MAX_CACHED = 2048
# The SEC asks for no more than ten requests a second from one client.
_MAX_FETCHES_AT_ONCE = 4
# A ticker the SEC lists but has no quarterly data for (a fund, a foreign
# filer) is remembered too, so it is not asked about again on every scan.
NO_DATA_TTL_SECONDS = 6 * 3600

_tickers: dict[str, str] = {}
_tickers_loaded_at = 0.0
_analyses: dict[str, tuple[float, FilingAnalysis]] = {}
_no_data: dict[str, float] = {}
_fetches = SingleFlight()
_fetch_slots: "PerLoop[asyncio.Semaphore]" = PerLoop(lambda: asyncio.Semaphore(_MAX_FETCHES_AT_ONCE))


class UnknownTicker(LookupError):
    pass


class SecUnavailable(RuntimeError):
    pass


def _sec_symbol(symbol: str) -> str:
    """The SEC lists class shares with a hyphen: BRK.B is BRK-B."""
    return symbol.strip().upper().replace(".", "-")


async def _get_json(url: str):
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise SecUnavailable(f"SEC EDGAR did not answer: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise SecUnavailable(f"SEC EDGAR returned {response.status_code}")
    return response.json()


async def cik_for(symbol: str) -> str:
    """Ten-digit, zero-padded CIK for a US-listed ticker."""
    global _tickers, _tickers_loaded_at
    if not _tickers or time.monotonic() - _tickers_loaded_at > TICKERS_TTL_SECONDS:
        payload = await _get_json(_TICKERS_URL)
        if not isinstance(payload, dict) or not payload:
            raise SecUnavailable("SEC EDGAR returned no ticker list")
        _tickers = {
            str(row["ticker"]).upper(): f"{int(row['cik_str']):010d}"
            for row in payload.values() if row.get("ticker") and row.get("cik_str") is not None
        }
        _tickers_loaded_at = time.monotonic()
        _log.info("sec_company_facts: loaded %d tickers", len(_tickers))
    cik = _tickers.get(_sec_symbol(symbol))
    if cik is None:
        raise UnknownTicker(f"{symbol.upper()} is not in the SEC's list of US-listed companies.")
    return cik


async def filing_analysis(symbol: str) -> FilingAnalysis:
    """The analysis for a ticker, from cache when it is fresh."""
    key = _sec_symbol(symbol)
    cached: Optional[tuple[float, FilingAnalysis]] = _analyses.get(key)
    if cached and time.monotonic() - cached[0] < ANALYSIS_TTL_SECONDS:
        return cached[1]
    known_empty = _no_data.get(key)
    if known_empty is not None and time.monotonic() - known_empty < NO_DATA_TTL_SECONDS:
        raise NoQuarterlyData(f"The SEC has no XBRL financial data for {symbol.upper()}.")
    return await _fetches.run(key, lambda: _fetch_analysis(symbol, key))


async def _fetch_analysis(symbol: str, key: str) -> FilingAnalysis:
    cik = await cik_for(symbol)
    async with _fetch_slots.get():
        facts = await _get_json(_FACTS_URL.format(cik=cik))
    if facts is None:
        if len(_no_data) >= _MAX_CACHED:
            _no_data.clear()
        _no_data[key] = time.monotonic()
        raise NoQuarterlyData(f"The SEC has no XBRL financial data for {symbol.upper()}.")
    analysis = analyse(facts, symbol, cik)

    if len(_analyses) >= _MAX_CACHED:
        oldest = min(_analyses, key=lambda item: _analyses[item][0])
        _analyses.pop(oldest, None)
    _analyses[key] = (time.monotonic(), analysis)
    return analysis
