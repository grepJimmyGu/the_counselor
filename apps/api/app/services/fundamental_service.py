from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.sectors import normalize_sector
from app.models.symbol import SymbolCache
from app.schemas.fundamental import CompanyProfile, FundamentalSummary, KeyMetrics
from app.services.adapters.fmp_adapter import FMPAdapter
from app.services.adapters.yfinance_adapter import YFinanceAdapter
from app.services.fmp_client import FMPNotConfiguredError, FMPRateLimitError

_CACHE_TTL_HOURS = 24  # fundamentals refresh daily


def _market_cap_category(market_cap: Optional[float]) -> Optional[str]:
    if market_cap is None:
        return None
    if market_cap >= 200e9:
        return "mega"
    if market_cap >= 10e9:
        return "large"
    if market_cap >= 2e9:
        return "mid"
    if market_cap >= 300e6:
        return "small"
    return "micro"


# A dividend yield is a fraction: 0.0116 is SPY's ~1.16%. Nothing at or above
# 1.0 is a yield — it is dollars per share, or a percent that escaped its
# conversion. Both shapes are in production: SPY holds 7.525, which is its
# ~$7.50 annual payout, and the screener compared that against a 0.04 threshold
# and returned it as a 752% yielder.
MAX_PLAUSIBLE_YIELD = 1.0


def sane_dividend_yield(value: Optional[float]) -> Optional[float]:
    """The yield as a fraction, or None when the number cannot be one.

    **Refuses rather than converts.** Dividing SPY's 7.525 by 100 would produce
    a confident "0.075 — a 7.5% yielder" when the real figure is ~1.16%: a
    wrong number that looks right, which is precisely the failure this column
    already shipped once. None is honest, and a missing yield simply drops the
    name out of a min-yield screen instead of topping it.

    Applied at the DB write rather than inside one adapter, because that is the
    only chokepoint every source passes through. `fmp_adapter` computes a
    fraction correctly; `yfinance_adapter` forwarded whatever `dividendYield`
    happened to mean in the installed version; a third source tomorrow arrives
    with its own convention.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < 0 or v >= MAX_PLAUSIBLE_YIELD:
        return None
    return v


class FundamentalService:
    def __init__(self) -> None:
        self._fmp = FMPAdapter()
        self._yf = YFinanceAdapter()

    def _is_stale(self, updated_at: Optional[datetime]) -> bool:
        if updated_at is None:
            return True
        return datetime.utcnow() - updated_at > timedelta(hours=_CACHE_TTL_HOURS)

    def _upsert_symbol(self, db: Session, profile: CompanyProfile) -> None:
        existing = db.get(SymbolCache, profile.symbol)
        now = datetime.utcnow()
        if existing is None:
            existing = SymbolCache(symbol=profile.symbol, name=profile.name, last_seen_at=now)
            db.add(existing)
        existing.name = profile.name or existing.name
        # Canonicalise on write: this upsert fires on every company-page view and
        # was rewriting GICS-seeded rows into FMP's vocabulary, silently dropping
        # them out of the exact-match sector screen. See app/data/sectors.py.
        existing.sector = normalize_sector(profile.sector)
        existing.industry = profile.industry
        existing.country = profile.country
        existing.description = profile.description
        existing.market_cap = profile.market_cap
        # Never null out a P/E we already have. FMP's *profile* has no P/E at
        # all (`fmp_adapter` hardcodes None — it comes from key-metrics), so an
        # unguarded write here wiped the value `get_summary` had just merged
        # in, on every cache refresh. That write-then-clobber loop is why
        # `max_pe=60` matched 0 of 16,832 symbols.
        if profile.pe_ratio is not None:
            existing.pe_ratio = profile.pe_ratio
        existing.dividend_yield = sane_dividend_yield(profile.dividend_yield)
        existing.beta = profile.beta
        existing.week_52_high = profile.week_52_high
        existing.week_52_low = profile.week_52_low
        existing.employees = profile.employees
        existing.market_cap_category = _market_cap_category(profile.market_cap)
        existing.price = profile.price
        existing.exchange = profile.exchange or existing.exchange
        existing.currency = profile.currency or existing.currency
        existing.fundamentals_updated_at = now
        db.commit()

    async def _fetch_profile(self, symbol: str) -> CompanyProfile:
        try:
            profile = await self._fmp.get_profile(symbol)
        except (FMPNotConfiguredError, FMPRateLimitError):
            profile = await self._yf.get_profile(symbol)
        # Canonicalise here too, not just at the DB write: this profile is what
        # the caller renders and what the value-chain lookup keys on, so a fresh
        # fetch must agree with what a later cache hit will return.
        return profile.model_copy(update={"sector": normalize_sector(profile.sector)})

    async def _fetch_metrics(self, symbol: str) -> KeyMetrics:
        try:
            return await self._fmp.get_key_metrics(symbol)
        except (FMPNotConfiguredError, FMPRateLimitError):
            return await self._yf.get_key_metrics(symbol)

    async def get_profile(self, db: Session, symbol: str) -> CompanyProfile:
        sym = symbol.upper()
        # Check cache freshness
        row = db.scalar(select(SymbolCache).where(SymbolCache.symbol == sym))
        if row and not self._is_stale(row.fundamentals_updated_at) and row.sector is not None:
            return CompanyProfile(
                symbol=sym,
                name=row.name,
                sector=row.sector,
                industry=row.industry,
                exchange=row.exchange,
                country=row.country,
                currency=row.currency,
                description=row.description,
                price=row.price,
                market_cap=row.market_cap,
                pe_ratio=row.pe_ratio,
                dividend_yield=row.dividend_yield,
                beta=row.beta,
                week_52_high=row.week_52_high,
                week_52_low=row.week_52_low,
                employees=row.employees,
                data_source="cache",
                as_of_date=row.fundamentals_updated_at.date() if row.fundamentals_updated_at else None,
            )
        # Fetch fresh data
        profile = await self._fetch_profile(sym)
        self._upsert_symbol(db, profile)
        return profile

    async def get_key_metrics(self, db: Session, symbol: str) -> KeyMetrics:
        sym = symbol.upper()
        # Key metrics are always fetched fresh (or from a separate cache — simplified here)
        try:
            return await self._fetch_metrics(sym)
        except Exception:
            return KeyMetrics(symbol=sym, data_source="unavailable")

    async def get_summary(self, db: Session, symbol: str) -> FundamentalSummary:
        profile, metrics = await self.get_profile(db, symbol), await self.get_key_metrics(db, symbol)
        # Merge P/E from metrics into profile if profile doesn't have it
        if profile.pe_ratio is None and metrics.pe_ratio is not None:
            profile = profile.model_copy(update={"pe_ratio": metrics.pe_ratio})
            # Write merged PE back to SymbolCache so the screener shows it
            try:
                existing = db.get(SymbolCache, symbol.upper())
                if existing and existing.pe_ratio is None:
                    existing.pe_ratio = metrics.pe_ratio
                    db.commit()
            except Exception:
                pass
        return FundamentalSummary(profile=profile, metrics=metrics)
