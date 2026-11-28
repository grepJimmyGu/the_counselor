"""A symbol's stored adjusted closes must all be on one basis: today's.

Symptom (production, 2026-11-25): a backtest or a chart showed each
ex-dividend drop as a loss (about 0.08% per AAPL dividend, 0.25% per SPY
one), and the adjustment factor jumped between two fetches with no dividend
between them. A split after a symbol's first load would have been a cliff of
the whole split ratio.

Root cause: the provider's `adjusted_close` is relative to the day it was
fetched, and `PriceCacheService._upsert_bars` only ever inserts
(ON CONFLICT DO NOTHING). Rows stored before a dividend or split kept the
old basis; rows stored after it got the new one.

Fix: `price_basis_service` fetches the provider's whole series for a symbol
a person opens or backtests, and rewrites only the rows that differ.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest
from sqlalchemy import select

import app.services.price_basis_service as pb
from app.models.data_fetch_log import DataFetchLog
from app.models.price_bar import PriceBar
from app.services.alpha_vantage import AlphaVantageError
from app.services.price_basis_service import PriceBasisService
from app.services.price_cache_service import PriceCacheService

SYM = "TEST"


def _weekdays(start: date, count: int) -> List[date]:
    days: List[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


DAYS = _weekdays(date(2026, 1, 5), 70)
EX_DIVIDEND = DAYS[50]
SPLIT = DAYS[60]


class FakeProvider:
    """A daily-adjusted provider that behaves like the real one: every
    answer is adjusted for the dividends and splits it knows of on the day
    it is asked.

    `closes` are prices as traded. `through` is the last day it has.
    """

    def __init__(self, closes: Dict[date, float]) -> None:
        self.closes = closes
        self.dividends: Dict[date, float] = {}
        self.splits: Dict[date, float] = {}
        self.through = max(closes)
        self.calls = 0
        self.fail: Optional[Exception] = None
        self.gate: Optional[asyncio.Event] = None

    async def fetch_daily_adjusted(self, symbol: str, outputsize: str = "full") -> List[dict]:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.fail is not None:
            raise self.fail
        days = sorted(d for d in self.closes if d <= self.through)
        factor = 1.0
        bars = []
        for i in range(len(days) - 1, -1, -1):
            day = days[i]
            close = self.closes[day]
            bars.append(
                {
                    "symbol": symbol.upper(),
                    "trading_date": day,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adjusted_close": close * factor,
                    "volume": 1_000_000,
                    "dividend_amount": self.dividends.get(day, 0.0),
                    "split_coefficient": self.splits.get(day, 1.0),
                }
            )
            # What happens on `day` restates every day before it.
            if day in self.dividends and i > 0:
                factor *= 1 - self.dividends[day] / self.closes[days[i - 1]]
            if day in self.splits:
                factor /= self.splits[day]
        return sorted(bars, key=lambda b: b["trading_date"])


def _provider(split: bool = True) -> FakeProvider:
    """A stock near $100 that goes 4-for-1 on SPLIT (when `split`)."""
    closes = {}
    for i, day in enumerate(DAYS):
        price = 100.0 + 0.05 * i
        closes[day] = price / 4 if split and day >= SPLIT else price
    return FakeProvider(closes)


async def _load_then_dividend_and_split(db, provider: FakeProvider) -> None:
    """Store 40 days; then a dividend and a split happen and 30 more days
    are stored, the way production reached its state."""
    cache = PriceCacheService(provider)
    provider.through = DAYS[39]
    await cache.ensure_history(db, SYM, DAYS[0], force=True)
    provider.dividends[EX_DIVIDEND] = 0.5
    provider.splits[SPLIT] = 4.0
    provider.through = DAYS[-1]
    await cache.ensure_history(db, SYM, DAYS[0], force=True)


def _stored(db, symbol: str = SYM) -> List[PriceBar]:
    db.expire_all()
    return list(
        db.execute(
            select(PriceBar).where(PriceBar.symbol == symbol).order_by(PriceBar.trading_date)
        ).scalars()
    )


def _worst_adjusted_move(rows: List[PriceBar]) -> float:
    return max(
        abs(b.adjusted_close / a.adjusted_close - 1) for a, b in zip(rows, rows[1:])
    )


def _logs(db, status: Optional[str] = None) -> List[DataFetchLog]:
    db.expire_all()
    query = select(DataFetchLog).where(DataFetchLog.fetch_type == pb.FETCH_TYPE)
    if status is not None:
        query = query.where(DataFetchLog.status == status)
    return list(db.execute(query.order_by(DataFetchLog.id)).scalars())


async def _drain(symbol: str = SYM) -> None:
    while pb._flights.is_running(("basis", symbol)):
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def _fresh_state():
    pb._budget_warned_on = None  # conftest clears the back-offs


# ── The regression ───────────────────────────────────────────────────────────


async def test_stored_series_is_on_one_basis_after_a_later_dividend_and_split(db):
    provider = _provider()
    await _load_then_dividend_and_split(db, provider)

    # The defect, as stored before the fix: the first 40 rows are on the
    # basis of the day they were loaded, the rest on today's, and the seam
    # between them reads as a 75% fall in one day.
    before = _stored(db)
    assert len(before) == len(DAYS)
    assert before[39].adjusted_close == before[39].close
    assert _worst_adjusted_move(before) > 0.7

    await PriceBasisService(provider).settle(db.get_bind(), [SYM])

    rows = _stored(db)
    by_day = {r.trading_date: r for r in rows}
    factor = {r.trading_date: r.adjusted_close / r.close for r in rows}

    # Across the ex-dividend date the factor steps by 1 - dividend / previous
    # close, and by nothing else on any other day but the split.
    for prev, day in zip(DAYS, DAYS[1:]):
        step = factor[prev] / factor[day]
        if day == EX_DIVIDEND:
            assert step == pytest.approx(1 - 0.5 / by_day[prev].close, rel=1e-12)
        elif day == SPLIT:
            assert step == pytest.approx(1 / 4.0, rel=1e-12)
        else:
            assert step == pytest.approx(1.0, rel=1e-12)

    # No cliff: the largest one-day move in the adjusted series is the
    # dividend's half a percent, not the split's 75%.
    assert _worst_adjusted_move(rows) < 0.01
    # The newest day is always its own basis.
    assert factor[DAYS[-1]] == 1.0
    # The stored series is the provider's, exactly.
    assert [r.adjusted_close for r in rows] == [
        b["adjusted_close"] for b in await provider.fetch_daily_adjusted(SYM)
    ]


async def test_a_dividend_amount_the_provider_fills_in_late_is_picked_up(db):
    """SPY's December 2025 and March 2026 ex-date rows were stored with a
    dividend of zero: the amount was not known on the day. The row itself
    has to be corrected, as well as every day before it."""
    provider = _provider(split=False)
    cache = PriceCacheService(provider)
    await cache.ensure_history(db, SYM, DAYS[0], force=True)
    service = PriceBasisService(provider)
    await service.settle(db.get_bind(), [SYM])
    assert _logs(db)[-1].bars_upserted == 0

    provider.dividends[EX_DIVIDEND] = 0.5  # the amount arrives
    provider.closes[DAYS[-1] + timedelta(days=3)] = 104.0  # and so does a new day
    provider.through = max(provider.closes)
    await cache.ensure_history(db, SYM, DAYS[0], force=True)
    await service.settle(db.get_bind(), [SYM])

    by_day = {r.trading_date: r for r in _stored(db)}
    assert by_day[EX_DIVIDEND].dividend_amount == 0.5
    assert by_day[DAYS[49]].adjusted_close == pytest.approx(
        by_day[DAYS[49]].close * (1 - 0.5 / by_day[DAYS[49]].close)
    )
    # The ex-date row and the 50 days before it; nothing after.
    assert _logs(db)[-1].bars_upserted == 51


# ── When it runs ─────────────────────────────────────────────────────────────


async def test_a_symbol_is_due_only_when_a_bar_has_arrived_since(db):
    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    service = PriceBasisService(provider)

    await service.settle(db.get_bind(), [SYM])
    calls = provider.calls
    assert not pb.reconcile_due(db, SYM)

    # Asked again, the same day or the next: nothing can have changed.
    await service.settle(db.get_bind(), [SYM])
    await service.settle(db.get_bind(), [SYM, SYM.lower()])
    assert provider.calls == calls

    # A new bar is stored: it may carry a dividend or a split.
    provider.closes[DAYS[-1] + timedelta(days=3)] = 26.0
    provider.through = max(provider.closes)
    await PriceCacheService(provider).ensure_history(db, SYM, DAYS[0], force=True)
    assert pb.reconcile_due(db, SYM)
    calls = provider.calls
    await service.settle(db.get_bind(), [SYM])
    assert provider.calls == calls + 1
    assert not pb.reconcile_due(db, SYM)


async def test_rows_that_already_agree_are_not_rewritten(db):
    provider = _provider()
    provider.dividends[EX_DIVIDEND] = 0.5
    provider.splits[SPLIT] = 4.0
    await PriceCacheService(provider).ensure_history(db, SYM, DAYS[0], force=True)
    stamps = {r.trading_date: r.fetched_at for r in _stored(db)}

    await PriceBasisService(provider).settle(db.get_bind(), [SYM])

    assert {r.trading_date: r.fetched_at for r in _stored(db)} == stamps
    (log,) = _logs(db)
    assert (log.status, log.bars_upserted) == ("success", 0)


async def test_only_the_rows_before_the_dividend_are_rewritten(db):
    provider = _provider(split=False)
    cache = PriceCacheService(provider)
    provider.through = DAYS[39]
    await cache.ensure_history(db, SYM, DAYS[0], force=True)
    provider.dividends[EX_DIVIDEND] = 0.5
    provider.through = DAYS[-1]
    await cache.ensure_history(db, SYM, DAYS[0], force=True)
    stamps = {r.trading_date: r.fetched_at for r in _stored(db)}

    await PriceBasisService(provider).settle(db.get_bind(), [SYM])

    after = {r.trading_date: r.fetched_at for r in _stored(db)}
    rewritten = sorted(day for day in DAYS if after[day] != stamps[day])
    # The first load's 40 days. Days 41 to 70 were stored after the dividend
    # and were right already.
    assert rewritten == DAYS[:40]
    assert _logs(db)[-1].bars_upserted == 40


async def test_a_bar_newer_than_the_newest_stored_is_not_added(db):
    """That day may be a session still in progress, and a row is only
    rewritten when a later bar arrives."""
    provider = _provider(split=False)
    provider.through = DAYS[39]
    await PriceCacheService(provider).ensure_history(db, SYM, DAYS[0], force=True)
    provider.through = DAYS[-1]

    await PriceBasisService(provider).settle(db.get_bind(), [SYM])

    assert [r.trading_date for r in _stored(db)] == DAYS[:40]


async def test_a_hole_inside_the_stored_history_is_filled(db):
    provider = _provider(split=False)
    await PriceCacheService(provider).ensure_history(db, SYM, DAYS[0], force=True)
    db.execute(PriceBar.__table__.delete().where(PriceBar.trading_date == DAYS[10]))
    db.commit()

    await PriceBasisService(provider).settle(db.get_bind(), [SYM])

    assert [r.trading_date for r in _stored(db)] == DAYS


async def test_series_from_other_sources_are_left_alone(db):
    """The index comes from another provider and carries no adjustment; a
    spot series is synthetic. Neither is asked about, and a stray row of
    theirs under an Alpha Vantage symbol is never overwritten."""
    stamp = datetime(2026, 1, 1)
    for symbol, source in (("^GSPC", "fmp_index"), (SYM, "alpha_vantage"), (SYM, "commodity_spot")):
        day = DAYS[0] if source != "alpha_vantage" else DAYS[1]
        db.add(PriceBar(
            symbol=symbol, trading_date=day, open=1.0, high=1.0, low=1.0, close=1.0,
            adjusted_close=1.0, volume=1, dividend_amount=0.0, split_coefficient=1.0,
            source=source, fetched_at=stamp,
        ))
    db.commit()
    assert not pb.reconcile_due(db, "^GSPC")

    provider = _provider(split=False)
    provider.through = DAYS[1]
    written = pb.apply_provider_bars(db, SYM, await provider.fetch_daily_adjusted(SYM), datetime.utcnow())
    db.commit()

    first, second = _stored(db)
    assert written == 1
    assert (first.source, first.close) == ("commodity_spot", 1.0)
    assert (second.source, second.close) == ("alpha_vantage", provider.closes[DAYS[1]])

    # Even sent straight to the statement, the other source's row holds.
    row = {c: 9.0 for c in pb.VALUE_COLUMNS}
    row.update(symbol=SYM, trading_date=DAYS[0], volume=9, source="alpha_vantage", fetched_at=stamp)
    assert pb.upsert_changed(db, [row]) == 0


# ── What bounds it ───────────────────────────────────────────────────────────


async def test_the_daily_allowance_stops_reconciling_until_tomorrow(db, monkeypatch):
    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    monkeypatch.setattr(pb, "get_settings", lambda: SimpleNamespace(price_basis_daily_row_budget=30))
    service = PriceBasisService(provider)

    # Under the allowance: runs, and rewrites the 40 stale rows.
    await service.settle(db.get_bind(), [SYM])
    assert pb.rows_rewritten_today(db) == 40

    # A second symbol the same day is over it: not even downloaded.
    other = _provider()
    await PriceCacheService(other).ensure_history(db, "OTHER", DAYS[0], force=True)
    assert pb.reconcile_due(db, "OTHER")
    calls = other.calls
    await PriceBasisService(other).settle(db.get_bind(), ["OTHER"])
    assert other.calls == calls
    assert pb.reconcile_due(db, "OTHER")  # still owed, for tomorrow


async def test_an_allowance_of_zero_turns_it_off(db, monkeypatch):
    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    monkeypatch.setattr(pb, "get_settings", lambda: SimpleNamespace(price_basis_daily_row_budget=0))
    calls = provider.calls

    await PriceBasisService(provider).settle(db.get_bind(), [SYM])

    assert provider.calls == calls
    assert _logs(db) == []


async def test_a_failed_download_is_swallowed_logged_and_not_retried_at_once(db, monkeypatch):
    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    before = [(r.trading_date, r.adjusted_close) for r in _stored(db)]
    service = PriceBasisService(provider)
    calls = provider.calls

    # An httpx error's text holds the request URL and the API key.
    provider.fail = RuntimeError("GET https://provider.example/query?apikey=SECRET failed")
    await service.settle(db.get_bind(), [SYM])  # does not raise
    await service.settle(db.get_bind(), [SYM])  # backing off: no second call

    assert provider.calls == calls + 1
    assert [(r.trading_date, r.adjusted_close) for r in _stored(db)] == before
    (log,) = _logs(db)
    assert (log.status, log.error_message) == ("error", "RuntimeError")

    # A provider message is safe to keep. After the back-off it is tried
    # again, and a success clears the way.
    clock = pb._now()
    monkeypatch.setattr(pb, "_now", lambda: clock + pb._RETRY_SECONDS + 1)
    provider.fail = AlphaVantageError("No price data returned for TEST.")
    await service.settle(db.get_bind(), [SYM])
    assert _logs(db)[-1].error_message == "No price data returned for TEST."

    monkeypatch.setattr(pb, "_now", lambda: clock + 2 * pb._RETRY_SECONDS + 2)
    provider.fail = None
    await service.settle(db.get_bind(), [SYM])
    assert _worst_adjusted_move(_stored(db)) < 0.01
    assert not pb.reconcile_due(db, SYM)


async def test_requests_for_one_symbol_share_one_download(db):
    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    service = PriceBasisService(provider)
    calls = provider.calls

    await asyncio.gather(*[service.settle(db.get_bind(), [SYM]) for _ in range(5)])

    assert provider.calls == calls + 1


async def test_a_slow_download_does_not_hold_the_caller_past_the_wait(db):
    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    provider.gate = asyncio.Event()

    await PriceBasisService(provider).settle(db.get_bind(), [SYM], wait_seconds=0.01)
    assert _worst_adjusted_move(_stored(db)) > 0.7  # not done yet

    provider.gate.set()
    await _drain()
    assert _worst_adjusted_move(_stored(db)) < 0.01  # finished behind the caller


# ── Where it is called from ──────────────────────────────────────────────────


async def test_opening_a_chart_reconciles_behind_the_request(db, monkeypatch):
    from app.services.market_data import MarketDataService

    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    service = MarketDataService()
    monkeypatch.setattr(service._price_data.cache_svc, "client", provider)
    monkeypatch.setattr(pb.price_basis_service, "client", provider)
    provider.gate = asyncio.Event()
    # The stored bars end in April, so the request itself refetches first.
    asyncio.get_running_loop().call_later(0.01, provider.gate.set)

    bars = await service.get_cached_bars(db, SYM.lower(), date.today())
    assert len(bars) == len(DAYS)

    await _drain()
    assert _worst_adjusted_move(_stored(db)) < 0.01


async def test_a_backtest_of_a_few_symbols_waits_for_them(db, monkeypatch):
    from app.services.backtest_preflight import ensure_data_available

    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    monkeypatch.setattr(pb.price_basis_service, "client", provider)

    errors = await ensure_data_available(db, [SYM], DAYS[0])

    assert errors == {}
    assert _worst_adjusted_move(_stored(db)) < 0.01


async def test_a_backtest_of_a_large_universe_does_not_wait(db, monkeypatch):
    from app.services.backtest_preflight import ensure_data_available

    provider = _provider()
    await _load_then_dividend_and_split(db, provider)
    monkeypatch.setattr(pb.price_basis_service, "client", provider)
    provider.gate = asyncio.Event()
    # 26 more names with one stored bar each, so nothing is fetched for them
    # by the preflight itself.
    extra = [f"X{i:02d}" for i in range(pb.AWAIT_MAX_SYMBOLS)]
    for symbol in extra:
        db.add(PriceBar(
            symbol=symbol, trading_date=DAYS[0], open=1.0, high=1.0, low=1.0, close=1.0,
            adjusted_close=1.0, volume=1, dividend_amount=0.0, split_coefficient=1.0,
            source="fmp_index", fetched_at=datetime(2026, 1, 1),
        ))
    db.commit()

    errors = await asyncio.wait_for(ensure_data_available(db, [SYM] + extra, DAYS[0]), timeout=2)
    assert errors == {}
    assert _worst_adjusted_move(_stored(db)) > 0.7  # the test would run on this

    provider.gate.set()
    await _drain()
    assert _worst_adjusted_move(_stored(db)) < 0.01
