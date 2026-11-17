"""Fetches a company's XBRL facts from SEC EDGAR and caches the analysis.

Two public, key-less endpoints:

  https://www.sec.gov/files/company_tickers.json          ticker → CIK
  https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json

Both verified against the live service on 2026-11-17 (apps/api/CLAUDE.md
trap #14); the second is the fixture in tests/test_filing_financials.py.

The raw facts for a large company are ~4 MB of JSON, so they are parsed,
reduced to a `FilingAnalysis`, and dropped — only the small result is kept.
Nothing here touches the database, and nothing holds an asyncio primitive
(trap #22): the caches are plain dicts, and a duplicated fetch under a race
costs one extra request, not correctness.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

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
_MAX_CACHED = 256

_tickers: dict[str, str] = {}
_tickers_loaded_at = 0.0
_analyses: dict[str, tuple[float, FilingAnalysis]] = {}


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

    cik = await cik_for(symbol)
    facts = await _get_json(_FACTS_URL.format(cik=cik))
    if facts is None:
        raise NoQuarterlyData(f"The SEC has no XBRL financial data for {symbol.upper()}.")
    analysis = analyse(facts, symbol, cik)

    if len(_analyses) >= _MAX_CACHED:
        oldest = min(_analyses, key=lambda item: _analyses[item][0])
        _analyses.pop(oldest, None)
    _analyses[key] = (time.monotonic(), analysis)
    return analysis
