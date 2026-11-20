"""The company page is built once and shared.

Measured in production on 2026-11-20, before this change:

  one view of /api/company/AMD/overview        2.9 s, every time
  12 views of 12 different companies at once   20 s for the last one
  12 views of the SAME company at once         27 s for the last one

Cause: every view made six FMP calls one after another, each on a new
connection, and nothing was kept or shared, so twelve views of one company
made seventy-two calls and ran into FMP's rate limiter.

Fix: a finished page is kept for ten minutes and served stale for two hours
while it is rebuilt; callers arriving during a build wait for that build; the
calls that do not depend on each other are made together.
"""
from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.schemas.fundamental import CompanyProfile
from app.services import company_overview_service as cos
from app.services.company_overview_service import CompanyOverviewService
from app.services.financial_validation_service import FinancialCheckMetrics, FinancialValidationService
from app.services.fmp_client import FMPRateLimitError
from app.services.live_quote_service import LiveQuote


def _live(symbol: str, price: float) -> LiveQuote:
    return LiveQuote(symbol=symbol, price=price, change=0.0, change_percent=0.0, day_high=None, day_low=None,
                     volume=None, market_cap=None, name=None, exchange=None, fetched_at=time.monotonic())


class _Quotes:
    """Stands in for the live quote service."""

    def __init__(self) -> None:
        self.prices = {"AMD": 150.0}
        self.fetches = 0
        self.fail = False

    async def get_quote(self, symbol: str):
        self.fetches += 1
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("quotes down")
        price = self.prices.get(symbol)
        return _live(symbol, price) if price is not None else None

    def cached(self, symbol: str, max_age: float = 30.0):
        price = self.prices.get(symbol)
        return _live(symbol, price) if price is not None and not self.fail else None


def _metrics() -> FinancialCheckMetrics:
    m = FinancialCheckMetrics()
    m.revenue_yoy = 0.12
    m.eps_yoy = 0.2
    m.gross_margin = 0.5
    return m


@pytest.fixture
def quotes(monkeypatch) -> _Quotes:
    fake = _Quotes()
    monkeypatch.setattr(cos, "live_quote_service", fake)
    return fake


@pytest.fixture(autouse=True)
def _empty_caches():
    for cache in (cos._OVERVIEWS, cos._STATEMENT_METRICS, cos._PEERS):
        cache.clear()
    yield
    for cache in (cos._OVERVIEWS, cos._STATEMENT_METRICS, cos._PEERS):
        cache.clear()


@pytest.fixture
def service(quotes: _Quotes) -> CompanyOverviewService:
    svc = CompanyOverviewService()
    svc._fundamental = MagicMock()
    svc._fundamental.get_profile = AsyncMock(side_effect=lambda db, sym: CompanyProfile(
        symbol=sym, name=sym + " Inc.", sector="Technology", industry="Semiconductors",
        price=1.0, peers=["OLD"], as_of_date=date(2026, 11, 20),
    ))
    svc._fmp = MagicMock()
    svc._fmp.get_key_metrics = AsyncMock(return_value={"peRatioTTM": 30.0})
    svc._fmp.get_peers = AsyncMock(return_value=["NVDA", "INTC"])
    svc._financial_svc = MagicMock()
    svc._financial_svc.statement_metrics = AsyncMock(side_effect=lambda sym: _metrics())
    svc._financial_svc.with_valuation = FinancialValidationService.with_valuation
    svc._segments = MagicMock()
    svc._segments.get = AsyncMock(return_value=None)
    svc._competitors = MagicMock()
    svc._bi = MagicMock()
    svc._bi.get = AsyncMock(return_value=None)
    return svc


async def test_twelve_views_of_one_company_at_once_build_it_once(service, quotes, db: Session) -> None:
    async def slow(*_args):
        await asyncio.sleep(0.01)
        return {"peRatioTTM": 30.0}

    service._fmp.get_key_metrics = AsyncMock(side_effect=slow)
    pages = await asyncio.gather(*(service.get_overview(db, "amd") for _ in range(12)))

    assert {page.symbol for page in pages} == {"AMD"}
    assert service._fmp.get_key_metrics.await_count == 1
    assert service._financial_svc.statement_metrics.await_count == 1
    assert service._fmp.get_peers.await_count == 1
    assert service._fundamental.get_profile.await_count == 1


async def test_a_second_view_within_ten_minutes_asks_no_provider(service, quotes, db: Session) -> None:
    first = await service.get_overview(db, "AMD")
    second = await service.get_overview(db, "AMD")
    assert second.financial_check.pe_ratio == first.financial_check.pe_ratio == 30.0
    assert service._fmp.get_key_metrics.await_count == 1
    assert service._fundamental.get_profile.await_count == 1
    # Another instance of the service (the chat tool makes its own) shares it too.
    other = CompanyOverviewService()
    other._fmp = MagicMock()
    other._fmp.get_key_metrics = AsyncMock(side_effect=AssertionError("should not be called"))
    assert (await other.get_overview(db, "AMD")).symbol == "AMD"


async def test_the_price_on_a_kept_page_follows_the_live_quote(service, quotes, db: Session) -> None:
    assert (await service.get_overview(db, "AMD")).price == 150.0
    quotes.prices["AMD"] = 155.5
    page = await service.get_overview(db, "AMD")
    assert page.price == 155.5
    assert service._fmp.get_key_metrics.await_count == 1  # still the kept page


async def test_the_independent_provider_calls_are_made_together(service, quotes, db: Session) -> None:
    """Six calls at ~0.45 s each, one after another, was the 2.9 s."""
    events: List[str] = []

    def recorded(name: str, result):
        async def call(*_args):
            events.append(name + " started")
            await asyncio.sleep(0.01)
            events.append(name + " finished")
            return result
        return call

    service._fmp.get_key_metrics = AsyncMock(side_effect=recorded("key metrics", {}))
    service._fmp.get_peers = AsyncMock(side_effect=recorded("peers", ["NVDA"]))
    service._financial_svc.statement_metrics = AsyncMock(side_effect=recorded("statements", _metrics()))
    await service.get_overview(db, "AMD")

    first_finish = min(i for i, event in enumerate(events) if event.endswith("finished"))
    assert sorted(events[:first_finish]) == ["key metrics started", "peers started", "statements started"]


async def test_a_page_built_while_a_provider_was_failing_is_not_kept(service, quotes, db: Session) -> None:
    service._fmp.get_key_metrics = AsyncMock(side_effect=FMPRateLimitError("slow down"))
    degraded = await service.get_overview(db, "AMD")
    assert degraded.financial_check.pe_ratio is None  # the fallback, as before

    service._fmp.get_key_metrics = AsyncMock(return_value={"peRatioTTM": 30.0})
    recovered = await service.get_overview(db, "AMD")
    assert recovered.financial_check.pe_ratio == 30.0  # rebuilt, not served the degraded page

    await service.get_overview(db, "AMD")
    assert service._fmp.get_key_metrics.await_count == 1  # and the good one is kept


@pytest.mark.parametrize("break_it", ["quote", "statements unavailable", "peers"])
async def test_each_provider_failure_marks_the_page_incomplete(service, quotes, db: Session, break_it: str) -> None:
    if break_it == "quote":
        quotes.fail = True
    elif break_it == "statements unavailable":
        service._financial_svc.statement_metrics = AsyncMock(return_value=None)
    else:
        service._fmp.get_peers = AsyncMock(side_effect=RuntimeError("peers down"))
    page, complete = await service._build(db, "AMD")
    assert complete is False
    if break_it == "quote":
        assert page.price == 1.0  # the profile's price, as before
    if break_it == "peers":
        assert page.market_position.key_competitors == ["OLD"]  # the profile's peers, as before


async def test_a_statement_that_cannot_be_read_still_fails_the_page(service, quotes, db: Session) -> None:
    """Unchanged: anything other than FMP being unavailable is an error, and
    the route turns it into a 404."""
    service._financial_svc.statement_metrics = AsyncMock(side_effect=KeyError("revenue"))
    with pytest.raises(KeyError):
        await service.get_overview(db, "AMD")


async def test_statements_and_peers_outlive_the_page(service, quotes, db: Session) -> None:
    """They change when a company reports. A rebuilt page asks only for key metrics."""
    await service.get_overview(db, "AMD")
    cos._OVERVIEWS.clear()  # the ten minutes are up
    await service.get_overview(db, "AMD")
    assert service._fmp.get_key_metrics.await_count == 2
    assert service._financial_svc.statement_metrics.await_count == 1
    assert service._fmp.get_peers.await_count == 1


async def test_an_old_page_is_returned_at_once_while_a_new_one_is_built(service, quotes, db: Session, monkeypatch) -> None:
    now = {"t": 5000.0}
    monkeypatch.setattr(cos._OVERVIEWS, "_clock", lambda: now["t"])
    await service.get_overview(db, "AMD")

    release = asyncio.Event()

    async def held(*_args):
        await release.wait()
        return {"peRatioTTM": 45.0}

    service._fmp.get_key_metrics = AsyncMock(side_effect=held)
    now["t"] += cos.OVERVIEW_TTL_SECONDS + 60
    page = await asyncio.wait_for(service.get_overview(db, "AMD"), timeout=0.5)
    assert page.financial_check.pe_ratio == 30.0  # the old page, without waiting

    release.set()
    for _ in range(20):
        await asyncio.sleep(0)
    assert (await service.get_overview(db, "AMD")).financial_check.pe_ratio == 45.0


async def test_forgetting_a_company_rebuilds_its_page(service, quotes, db: Session) -> None:
    await service.get_overview(db, "AMD")
    cos.forget_overview("amd")
    await service.get_overview(db, "AMD")
    assert service._fmp.get_key_metrics.await_count == 2


async def test_only_a_few_pages_are_built_at_once(service, quotes, db: Session) -> None:
    """Each build holds a database connection and makes several FMP calls."""
    building = 0
    most = 0

    async def slow(*_args):
        nonlocal building, most
        building += 1
        most = max(most, building)
        await asyncio.sleep(0.01)
        building -= 1
        return {}

    service._fmp.get_key_metrics = AsyncMock(side_effect=slow)
    symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "V", "UNH"]
    pages = await asyncio.gather(*(service.get_overview(db, s) for s in symbols))
    assert [page.symbol for page in pages] == symbols
    assert most == 3


# ── the statements themselves ────────────────────────────────────────────────

async def test_the_three_statements_are_fetched_together() -> None:
    events: List[str] = []

    def recorded(name: str):
        async def call(_sym, limit=5):
            events.append(name + " started")
            await asyncio.sleep(0.01)
            events.append(name + " finished")
            return []
        return call

    svc = FinancialValidationService()
    svc._client = MagicMock()
    svc._client.get_income_statement = recorded("income")
    svc._client.get_cash_flow = recorded("cash flow")
    svc._client.get_balance_sheet = recorded("balance sheet")
    assert isinstance(await svc.statement_metrics("AMD"), FinancialCheckMetrics)
    assert sorted(events[:3]) == ["balance sheet started", "cash flow started", "income started"]


async def test_compute_gives_the_same_answer_as_before_and_leaves_the_base_alone() -> None:
    svc = FinancialValidationService()
    svc._client = MagicMock()
    svc._client.get_income_statement = AsyncMock(side_effect=FMPRateLimitError("slow down"))
    svc._client.get_cash_flow = AsyncMock(return_value=[])
    svc._client.get_balance_sheet = AsyncMock(return_value=[])
    # FMP unavailable: empty metrics and no valuation, exactly as it was.
    assert (await svc.compute("AMD", {"peRatioTTM": 30.0})).pe_ratio is None

    base = _metrics()
    valued = FinancialValidationService.with_valuation(base, {"peRatioTTM": 30.0})
    assert valued.pe_ratio == 30.0 and valued.peg_ratio == pytest.approx(30.0 / 20.0)
    assert base.pe_ratio is None  # the kept copy is untouched
