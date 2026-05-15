"""
PRD-08c: Pre-warm health scores for top 500 S&P constituents.

Run once on deploy, then weekly via Railway cron or manual trigger:
    railway run python -m app.scripts.prewarm_health_scores

Cost: ~500 FMP calls (income + cashflow + balance sheet per ticker = 3 calls each
for the 500-symbol batch, chunked to avoid rate limits).
No LLM usage — purely deterministic computation.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Top 500 S&P symbols (static fallback list — we also try FMP's constituents endpoint)
# Trimmed to the most liquid names; FMP's /stable/sp500-constituent fetched at runtime.
_SP500_FALLBACK_TOP_100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "LLY", "TSLA", "JPM",
    "V", "UNH", "XOM", "MA", "AVGO", "PG", "JNJ", "COST", "HD", "MRK",
    "ABBV", "CVX", "BAC", "NFLX", "KO", "ORCL", "AMD", "WMT", "PEP", "ACN",
    "TMO", "MCD", "ABT", "CSCO", "NKE", "WFC", "DHR", "LIN", "TXN", "CRM",
    "PM", "INTC", "RTX", "GE", "BMY", "UNP", "QCOM", "AMAT", "INTU", "IBM",
    "CAT", "GS", "BLK", "SPGI", "SYK", "AXP", "ELV", "DUK", "CI", "MDT",
    "MS", "AMGN", "MMM", "PLD", "GILD", "TJX", "DE", "SCHW", "ADI", "BKNG",
    "ISRG", "C", "SO", "CB", "VRTX", "PGR", "MO", "REGN", "ZTS", "AON",
    "ETN", "SLB", "CME", "EOG", "SHW", "CL", "WM", "ITW", "NOC", "BSX",
    "KLAC", "LRCX", "HUM", "ICE", "NSC", "GD", "MCO", "AIG", "APD", "FCX",
]


async def _fetch_sp500_symbols() -> list[str]:
    """Try fetching live S&P 500 list from FMP; fall back to hardcoded top 100."""
    try:
        import httpx
        from app.core.config import get_settings
        settings = get_settings()
        key = settings.financial_modeling_prep_api_key
        if not key:
            return _SP500_FALLBACK_TOP_100

        url = "https://financialmodelingprep.com/stable/sp500-constituent"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params={"apikey": key})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                symbols = [d.get("symbol") for d in data if d.get("symbol")]
                logger.info("Fetched %d S&P 500 constituents from FMP", len(symbols))
                return symbols[:500]
    except Exception as exc:
        logger.warning("Could not fetch S&P 500 list from FMP: %s — using fallback", exc)
    return _SP500_FALLBACK_TOP_100


async def _compute_one(symbol: str, db) -> bool:
    """Compute and persist health scores for one symbol. Returns True on success."""
    from app.services.health_score_service import HealthScoreService
    from app.services.fmp_client import FMPClient, FMPNotConfiguredError, FMPRateLimitError

    fmp = FMPClient()
    svc = HealthScoreService()
    try:
        profile = await fmp.get_profile(symbol)
        name = profile.get("companyName") or profile.get("name") or symbol
        sector = profile.get("sector")
        market_cap = profile.get("mktCap") or profile.get("marketCap")

        await svc.compute(
            symbol=symbol,
            company_name=name,
            sector=sector,
            market_cap=float(market_cap) if market_cap else None,
            db=db,
        )
        return True
    except (FMPNotConfiguredError, FMPRateLimitError) as exc:
        logger.warning("Rate limit / config error for %s: %s", symbol, exc)
        return False
    except Exception as exc:
        logger.warning("Failed to compute health score for %s: %s", symbol, exc)
        return False


async def run_prewarm(
    batch_size: int = 5,           # smaller batches to avoid FMP rate limits
    delay_between_batches: float = 4.0,  # longer delay between batches
    max_symbols: int = 500,
) -> None:
    """
    Main entry point. Fetches S&P 500 list, computes health scores in batches.
    Rate-limited to avoid overwhelming FMP.
    """
    from sqlalchemy import text
    from app.db.session import SessionLocal

    symbols = await _fetch_sp500_symbols()
    symbols = symbols[:max_symbols]

    db = SessionLocal()
    success = 0
    failed = 0
    skipped = 0

    try:
        # Load already-scored symbols to skip them
        existing_rows = db.execute(
            text("SELECT symbol FROM symbol_health_scores WHERE piotroski_score IS NOT NULL")
        ).fetchall()
        already_done = {r[0] for r in existing_rows}

        todo = [s for s in symbols if s not in already_done]
        logger.info(
            "Pre-warming health scores: %d todo, %d already done, %d total symbols",
            len(todo), len(already_done), len(symbols),
        )

        if not todo:
            logger.info("Pre-warm complete — all symbols already scored")
            return

        for i in range(0, len(todo), batch_size):
            batch = todo[i:i + batch_size]
            results = await asyncio.gather(
                *[_compute_one(sym, db) for sym in batch],
                return_exceptions=True,
            )
            for r in results:
                if r is True:
                    success += 1
                else:
                    failed += 1
            logger.info(
                "Progress: %d/%d (success=%d, failed=%d)",
                min(i + batch_size, len(todo)), len(todo), success, failed,
            )
            if i + batch_size < len(todo):
                await asyncio.sleep(delay_between_batches)
    finally:
        db.close()

    logger.info("Pre-warm complete: %d succeeded, %d failed, %d skipped", success, failed, skipped)


if __name__ == "__main__":
    asyncio.run(run_prewarm())
