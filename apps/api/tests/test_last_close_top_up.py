"""A stock someone is looking at ends on the last completed close.

Measured in production on 2026-11-25 at 12:58 New York time:

  /api/data/daily/{NVDA,AAPL,MSFT,SPY,REGN}
      newest bar Monday 2026-11-23; the provider already had Tuesday's close
  NVDA
      chart, trend, signals and tests ended at $165.05; the stock was $145.72

Cause: `ensure_history` refetches a symbol only once its newest bar is three
to four days old. That rule is shared by sweeps over thousands of symbols and
is left alone; a request for one stock now tops it up to the last close.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import List, Tuple
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_fetch_log import DataFetchLog
from app.models.price_bar import PriceBar
from app.schemas.strategy import StrategyJSON
from app.services import price_data_service
from app.services.alpha_vantage import AlphaVantageError
from app.services.backtester import engine as engine_module
from app.services.backtester.engine import BacktestEngine
from app.services.market_data import MarketDataService
from app.services.price_data_service import PriceDataService, last_completed_session

ET = ZoneInfo("America/New_York")
MONDAY = date(2026, 11, 23)
TUESDAY = date(2026, 11, 24)
WEDNESDAY = date(2026, 11, 25)


def _bar(symbol: str, day: date, close: float = 10.0) -> PriceBar:
    return PriceBar(symbol=symbol, trading_date=day, open=close, high=close, low=close, close=close,
                    adjusted_close=close, volume=1, dividend_amount=0.0, split_coefficient=1.0,
                    source="test", fetched_at=datetime.utcnow())


def _provider_bar(symbol: str, day: date, close: float) -> dict:
    return {"symbol": symbol, "trading_date": day, "open": close, "high": close, "low": close,
            "close": close, "adjusted_close": close, "volume": 1}


class FakeProvider:
    """Answers with Monday, Tuesday and a half-finished Wednesday."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str]] = []
        self.fails = False

    async def fetch_daily_adjusted(self, symbol: str, outputsize: str = "full") -> List[dict]:
        self.calls.append((symbol, outputsize))
        await asyncio.sleep(0.01)
        if self.fails:
            raise AlphaVantageError("provider is down")
        return [
            _provider_bar(symbol, MONDAY, 165.05),
            _provider_bar(symbol, TUESDAY, 155.38),
            _provider_bar(symbol, WEDNESDAY, 145.72),
        ]


@pytest.fixture(autouse=True)
def _wednesday_midday(monkeypatch):
    """Wednesday before the close: the last completed session is Tuesday."""
    price_data_service._top_up_attempts.clear()
    monkeypatch.setattr(price_data_service, "last_completed_session", lambda now=None: TUESDAY)
    yield
    price_data_service._top_up_attempts.clear()


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def service(provider: FakeProvider) -> PriceDataService:
    svc = PriceDataService()
    svc.cache_svc.client = provider  # type: ignore[assignment]
    return svc


def _days(db: Session, symbol: str) -> List[date]:
    db.expire_all()
    return list(db.execute(
        select(PriceBar.trading_date).where(PriceBar.symbol == symbol).order_by(PriceBar.trading_date)
    ).scalars())


# ── Which close is the last one ──────────────────────────────────────────────

@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 11, 25, 12, 58, tzinfo=ET), TUESDAY),      # Wednesday, session open
    (datetime(2026, 11, 25, 15, 59, tzinfo=ET), TUESDAY),
    (datetime(2026, 11, 25, 16, 0, tzinfo=ET), WEDNESDAY),     # the close has passed
    (datetime(2026, 11, 23, 9, 0, tzinfo=ET), date(2026, 11, 20)),   # Monday morning: Friday
    (datetime(2026, 11, 21, 17, 0, tzinfo=ET), date(2026, 11, 20)),  # Saturday
    (datetime(2026, 11, 22, 23, 0, tzinfo=ET), date(2026, 11, 20)),  # Sunday
    # The same instant read from a UTC clock, as on the server.
    (datetime(2026, 11, 25, 21, 30, tzinfo=ZoneInfo("UTC")), WEDNESDAY),
    (datetime(2026, 11, 26, 2, 0, tzinfo=ZoneInfo("UTC")), WEDNESDAY),
])
def test_the_last_completed_session(now: datetime, expected: date) -> None:
    assert last_completed_session(now) == expected


# ── The top-up ───────────────────────────────────────────────────────────────

async def test_regression_a_symbol_two_sessions_behind_is_brought_to_the_last_close(
    service: PriceDataService, provider: FakeProvider, db: Session
) -> None:
    """The reported case: newest bar Monday, asked on Wednesday before the close."""
    db.add(_bar("NVDA", MONDAY, 165.05))
    db.commit()

    await service.ensure_last_close(db, "nvda")

    # The short answer, not the whole history.
    assert provider.calls == [("NVDA", "compact")]
    # Tuesday is in. Wednesday's session has not closed: rows are never
    # updated once written, so a half-finished day must not be stored.
    assert _days(db, "NVDA") == [MONDAY, TUESDAY]
    log = db.execute(select(DataFetchLog).where(DataFetchLog.symbol == "NVDA")).scalar_one()
    assert (log.fetch_type, log.status, log.bars_upserted) == ("daily_compact", "success", 1)


async def test_a_symbol_at_the_last_close_asks_for_nothing(service, provider, db: Session) -> None:
    db.add(_bar("AAPL", TUESDAY))
    db.commit()
    await service.ensure_last_close(db, "AAPL")
    assert provider.calls == []


async def test_a_symbol_with_no_history_is_left_to_the_full_download(service, provider, db: Session) -> None:
    await service.ensure_last_close(db, "NEWCO")
    assert provider.calls == []


async def test_six_requests_at_once_ask_the_provider_once(service, provider, db: Session) -> None:
    db.add(_bar("NVDA", MONDAY))
    db.commit()
    await asyncio.gather(*(service.ensure_last_close(db, "NVDA") for _ in range(6)))
    assert provider.calls == [("NVDA", "compact")]


async def test_a_symbol_that_stays_behind_is_not_asked_for_again_for_ten_minutes(
    service, provider, db: Session, monkeypatch
) -> None:
    """A market holiday, or the minutes after a close: nothing newer exists yet."""
    db.add(_bar("NVDA", MONDAY))
    db.commit()
    # The provider has nothing past Monday.
    async def nothing_new(symbol: str, outputsize: str = "full") -> List[dict]:
        provider.calls.append((symbol, outputsize))
        return [_provider_bar(symbol, MONDAY, 165.05)]
    monkeypatch.setattr(provider, "fetch_daily_adjusted", nothing_new)
    now = {"t": 100.0}
    # The module's own clock, not time.monotonic: the event loop runs on that.
    monkeypatch.setattr(price_data_service, "_now", lambda: now["t"])

    await service.ensure_last_close(db, "NVDA")
    await service.ensure_last_close(db, "NVDA")
    now["t"] += 599
    await service.ensure_last_close(db, "NVDA")
    assert len(provider.calls) == 1

    now["t"] += 2
    await service.ensure_last_close(db, "NVDA")
    assert len(provider.calls) == 2


async def test_a_failed_top_up_serves_what_is_cached(service, provider, db: Session) -> None:
    db.add(_bar("NVDA", MONDAY))
    db.commit()
    provider.fails = True
    await service.ensure_last_close(db, "NVDA")  # does not raise
    assert _days(db, "NVDA") == [MONDAY]
    log = db.execute(select(DataFetchLog).where(DataFetchLog.symbol == "NVDA")).scalar_one()
    assert log.status == "error"


async def test_a_symbol_months_behind_gets_the_whole_history(service, provider, db: Session) -> None:
    """The short answer reaches back 100 sessions; a wider gap would leave a hole."""
    db.add(_bar("OLD", TUESDAY - timedelta(days=121)))
    db.commit()
    await service.ensure_last_close(db, "OLD")
    assert provider.calls == [("OLD", "full")]


# ── Where it is used ─────────────────────────────────────────────────────────

async def test_the_daily_prices_a_chart_reads_end_on_the_last_close(provider, db: Session) -> None:
    market = MarketDataService()
    market._price_data.cache_svc.client = provider  # type: ignore[assignment]
    # Five years of history, so the older rule sees nothing to do.
    db.add(_bar("NVDA", date(2020, 1, 2)))
    db.add(_bar("NVDA", MONDAY, 165.05))
    db.commit()

    bars = await market.get_cached_bars(db, "NVDA", WEDNESDAY, start_date=date(2026, 11, 1))

    assert [(b.trading_date, b.close) for b in bars] == [(MONDAY, 165.05), (TUESDAY, 155.38)]


def _strategy(universe: List[str]) -> StrategyJSON:
    return StrategyJSON.model_validate({
        "strategy_name": "Top-up test", "strategy_type": "low_volatility", "universe": universe, "benchmark": "SPY",
        "start_date": "2026-08-25", "end_date": "2026-11-25", "initial_capital": 100_000,
        "rebalance_frequency": "monthly", "position_sizing": {"method": "equal_weight"},
    })


async def test_a_backtest_brings_its_symbols_to_the_last_close_first(db: Session, monkeypatch) -> None:
    engine = BacktestEngine()
    asked: List[str] = []

    async def top_up(_db, symbol: str) -> None:
        asked.append(symbol)

    async def frame(*_args, **_kwargs):
        return None

    monkeypatch.setattr(engine.market_data, "ensure_last_close", top_up)
    monkeypatch.setattr(engine.market_data, "get_price_frame", frame)

    await engine._load_prices(db, _strategy(["NVDA", "AAPL", "SPY"]))
    # The benchmark too, and a symbol that is both is asked for once.
    assert asked == ["NVDA", "AAPL", "SPY"]


async def test_a_backtest_over_hundreds_of_symbols_uses_what_is_cached(db: Session, monkeypatch) -> None:
    """One request per symbol at the provider's rate limit would take minutes."""
    engine = BacktestEngine()
    asked: List[str] = []

    async def top_up(_db, symbol: str) -> None:
        asked.append(symbol)

    async def frame(*_args, **_kwargs):
        return None

    monkeypatch.setattr(engine.market_data, "ensure_last_close", top_up)
    monkeypatch.setattr(engine.market_data, "get_price_frame", frame)

    many = [f"S{i}" for i in range(engine_module._TOP_UP_AT_MOST)]  # plus the benchmark
    await engine._load_prices(db, _strategy(many))
    assert asked == []
