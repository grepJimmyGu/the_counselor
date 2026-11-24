"""Alpha Vantage real-time bulk quotes.

One endpoint: `REALTIME_BULK_QUOTES`, up to 100 symbols per call, on plans
that include "Realtime US Market Data". Used by `live_quote_service` as an
optional first source, with FMP behind it.

THE TRAP THIS MODULE EXISTS TO CONTAIN. A key that is not entitled does not
get an error from this endpoint. It gets HTTP 200 and a well-formed payload
of *artificial sample data* — MSFT at a 2024 price, with a `message` saying
so. Parsed naively that is a plausible-looking quote, and it would be shown
to a user as the current price of a stock. So a payload is refused when
either guard trips:

  1. its `message` says it is a premium endpoint / sample / artificial data;
  2. a row's own timestamp is more than `MAX_QUOTE_AGE_DAYS` old.

The second guard does not depend on the wording of the first. A refused
payload yields no quotes, and the caller falls back to FMP.

Verified against the live endpoint with the public `demo` key on
2026-11-16 (apps/api/CLAUDE.md trap #14: check the real surface) — that
response is the fixture in tests/test_alpha_vantage_quotes.py. A response
from an ENTITLED key has not been observed; `parse_bulk_quotes` logs sizes
at INFO so the first production cycle shows whether it parses.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import get_settings

try:  # Python 3.9+; tzdata ships with the OS on Railway and macOS.
    from zoneinfo import ZoneInfo

    _EASTERN: Optional[ZoneInfo] = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 — no tz database: fall back to a fixed offset
    _EASTERN = None

_log = logging.getLogger(__name__)

BULK_LIMIT = 100
MAX_QUOTE_AGE_DAYS = 7
_BASE_URL = "https://www.alphavantage.co/query"
_REFUSAL_MARKERS = ("premium endpoint", "artificial", "sample data")


def _to_float(value) -> Optional[float]:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _quote_epoch(raw: Optional[str]) -> Optional[float]:
    """AV stamps quotes in US/Eastern wall-clock time, without an offset."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            naive = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if _EASTERN is not None:
            return naive.replace(tzinfo=_EASTERN).timestamp()
        # Without a tz database, EST is at most an hour out — fine for the
        # week-scale staleness guard, and only that guard reads it then.
        return naive.replace(tzinfo=timezone(timedelta(hours=-5))).timestamp()
    return None


def parse_bulk_quotes(payload, now: Optional[datetime] = None) -> list[dict]:
    """Normalise a REALTIME_BULK_QUOTES response.

    Returns one dict per usable quote with the keys `live_quote_service`
    needs: symbol, price, change, change_percent, day_high, day_low, volume,
    as_of (epoch seconds of the quote itself). Returns [] for anything that
    is not real, current data — see the module docstring.
    """
    if not isinstance(payload, dict):
        return []
    message = str(payload.get("message") or "").lower()
    if any(marker in message for marker in _REFUSAL_MARKERS):
        _log.warning(
            "alpha_vantage_quotes: key is not entitled to real-time quotes; "
            "AV returned sample data, which was discarded"
        )
        return []
    rows = payload.get("data")
    if not isinstance(rows, list):
        # Rate-limit and error responses carry "Information" / "Note" /
        # "Error Message" instead of "data".
        _log.warning("alpha_vantage_quotes: no data in response (keys=%s)", sorted(payload))
        return []

    current = now or datetime.now(timezone.utc)
    oldest_allowed = (current - timedelta(days=MAX_QUOTE_AGE_DAYS)).timestamp()
    quotes: list[dict] = []
    stale = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        price = _to_float(row.get("close"))
        as_of = _quote_epoch(row.get("timestamp"))
        if not symbol or price is None or price <= 0:
            continue
        if as_of is None or as_of < oldest_allowed:
            stale += 1
            continue
        quotes.append(
            {
                "symbol": str(symbol).upper(),
                "price": price,
                "change": _to_float(row.get("change")) or 0.0,
                "change_percent": _to_float(row.get("change_percent")) or 0.0,
                "day_high": _to_float(row.get("high")),
                "day_low": _to_float(row.get("low")),
                "volume": _to_float(row.get("volume")),
                "as_of": as_of,
            }
        )
    if stale:
        _log.warning(
            "alpha_vantage_quotes: discarded %d quote(s) older than %d days",
            stale, MAX_QUOTE_AGE_DAYS,
        )
    return quotes


class AlphaVantageQuoteClient:
    async def get_bulk_quotes(self, symbols: list[str]) -> list[dict]:
        """Real-time quotes for up to `BULK_LIMIT` symbols per request.

        Raises on transport errors; the caller treats any failure as "ask
        the fallback", so nothing here retries.
        """
        settings = get_settings()
        if not settings.alpha_vantage_api_key or not symbols:
            return []
        wanted = list(dict.fromkeys(s.upper() for s in symbols if s))
        quotes: list[dict] = []
        async with httpx.AsyncClient(timeout=settings.api_timeout_seconds) as client:
            for start in range(0, len(wanted), BULK_LIMIT):
                chunk = wanted[start:start + BULK_LIMIT]
                params = {
                    "function": "REALTIME_BULK_QUOTES",
                    "symbol": ",".join(chunk),
                    "apikey": settings.alpha_vantage_api_key,
                }
                if settings.alpha_vantage_quote_entitlement:
                    params["entitlement"] = settings.alpha_vantage_quote_entitlement
                response = await client.get(_BASE_URL, params=params)
                response.raise_for_status()
                parsed = parse_bulk_quotes(response.json())
                # Sizes at INFO until an entitled key has been seen to work.
                _log.info(
                    "alpha_vantage_quotes: asked for %d symbol(s), got %d quote(s)",
                    len(chunk), len(parsed),
                )
                quotes.extend(parsed)
        return quotes
