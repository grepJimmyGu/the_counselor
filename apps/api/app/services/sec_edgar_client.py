from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# SEC EDGAR throttles to 10 req/sec — 30s timeout is generous for large filings
_TIMEOUT = 30.0
_HEADERS = {
    "User-Agent": "livermore-research/1.0 contact@livermore.app",
    "Accept-Encoding": "gzip, deflate",
}
# Cap download size: most 10-K HTMs are 2-8 MB; 15 MB covers edge cases
_MAX_BYTES = 15 * 1024 * 1024


async def fetch_filing_html(url: str) -> str:
    """
    Download a SEC EDGAR filing document and return its raw HTML.
    Returns empty string on any failure so callers can degrade gracefully.
    """
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers=_HEADERS,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_BYTES:
                        logger.warning("Filing truncated at %d bytes: %s", total, url)
                        break
                return b"".join(chunks).decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Failed to fetch filing from %s: %s", url, exc)
        return ""
