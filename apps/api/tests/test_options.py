"""Option chains: what is kept from the provider, what a screen is sent, and saved plans."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes import options as options_routes
from app.schemas.options import OptionLeg, OptionPlanCreate
from app.services.alpha_vantage import AlphaVantageClient, AlphaVantageError, option_root
from app.services.options import chain_service
from app.services.options.estimate import black_scholes, estimate_chain, years_to_expiry
from app.services.options.chain_service import (
    NO_OPTIONS,
    NOT_AVAILABLE,
    OptionChainService,
    OptionsUnavailable,
    default_expiration,
    implied_move_pct,
    is_monthly,
    parse_chain,
    slice_chain,
)

# A real NVDA chain from 2026-11-20, cut to six expiries and strikes 100-150.
# NVDA closed at 125.53 that day.
ROWS: List[dict] = json.loads((Path(__file__).parent / "fixtures" / "option_chain_nvda.json").read_text())["data"]
CLOSE = 125.53
TODAY = date(2026, 11, 20)


def row(contract_id: str, **changes: object) -> dict:
    base = {
        "contractID": contract_id, "symbol": "NVDA", "expiration": "2026-12-18", "strike": "125.00",
        "type": "call", "last": "9.00", "bid": "8.90", "ask": "9.10", "volume": "10",
        "open_interest": "200", "date": "2026-11-20",
    }
    base.update(changes)
    return base


# ── Parsing ───────────────────────────────────────────────────────────────────

def test_a_chain_keeps_bid_ask_and_the_price_halfway_between() -> None:
    chain = parse_chain("NVDA", ROWS, CLOSE)
    assert chain is not None and chain.as_of == TODAY and chain.underlying_price == CLOSE
    january = {(c.kind, c.strike): c for c in chain.by_expiration[date(2027, 1, 15)]}
    call = january[("call", 120.0)]
    assert (call.contract_id, call.bid, call.ask, call.mid) == ("NVDA270115C00120000", 16.60, 17.40, 17.00)
    assert (call.volume, call.open_interest) == (3031, 8392)
    # 10.25 and 10.50 are 10.375 apart; the plan is built on a price in cents.
    assert january[("put", 120.0)].mid == 10.38


def test_contracts_that_expired_on_the_day_of_the_prices_are_left_out() -> None:
    assert any(r["expiration"] == "2026-11-20" for r in ROWS)
    chain = parse_chain("NVDA", ROWS, CLOSE)
    assert min(chain.by_expiration) == date(2026, 11, 27)


def test_only_standard_hundred_share_contracts_are_kept() -> None:
    rows = [
        row("NVDA261218C00125000"),
        # After a split or special dividend the exchange renames the old
        # contracts; they no longer deliver 100 shares at the strike.
        row("NVDA1261218C00125000", strike="125.00"),
        row("XXYYZZ999999C00020000", symbol="XXYYZZ"),
    ]
    chain = parse_chain("NVDA", rows, CLOSE)
    assert [c.contract_id for c in chain.by_expiration[date(2026, 12, 18)]] == ["NVDA261218C00125000"]


def test_rows_nobody_could_trade_on_are_dropped() -> None:
    rows = [
        row("NVDA261218C00120000", strike="120.00", ask="0.00", bid="0.00"),   # nobody offering
        row("NVDA261218C00121000", strike="121.00", bid="9.50", ask="9.10"),   # bid above ask
        row("NVDA261218C00122000", strike="122.00", bid="-", ask="9.10"),      # not a number
        row("NVDA261218C00010000", strike="10.00"),                             # far from the price
        row("NVDA261218C00126000", strike="126.00", bid="0.00", ask="0.05"),   # cheap but real
    ]
    chain = parse_chain("NVDA", rows, CLOSE)
    (kept,) = chain.by_expiration[date(2026, 12, 18)]
    assert (kept.strike, kept.bid, kept.mid) == (126.0, 0.0, 0.03)


def test_a_chain_with_nothing_usable_is_no_chain() -> None:
    assert parse_chain("NVDA", [], CLOSE) is None
    assert parse_chain("NVDA", [row("XXYYZZ999999C00020000")], CLOSE) is None
    # Everything listed has already expired.
    assert parse_chain("NVDA", [row("NVDA261120C00125000", expiration="2026-11-20")], CLOSE) is None


def test_class_shares_are_spelled_the_way_option_contracts_spell_them() -> None:
    assert option_root("BRK-B") == option_root("brk.b") == "BRKB"
    chain = parse_chain("BRK-B", [row("BRKB261218C00500000", symbol="BRKB", strike="500.00")], 500.0)
    assert chain.symbol == "BRK-B" and len(chain.by_expiration[date(2026, 12, 18)]) == 1


# ── Expiries ──────────────────────────────────────────────────────────────────

def test_the_monthly_expiry_is_the_third_friday_or_the_thursday_before_a_holiday() -> None:
    listed = [date(2026, 11, 27), date(2026, 12, 18), date(2027, 6, 17)]
    assert is_monthly(date(2026, 12, 18), listed)
    assert not is_monthly(date(2026, 11, 27), listed)
    # 18 June 2027 is the Juneteenth holiday, so that month expires on the 17th.
    assert is_monthly(date(2027, 6, 17), listed)
    # A Thursday weekly in a month whose Friday is listed is not the monthly.
    assert not is_monthly(date(2026, 12, 17), listed + [date(2026, 12, 17)])


def test_a_plan_starts_at_the_first_monthly_expiry_a_month_or_more_out() -> None:
    part = slice_chain(parse_chain("NVDA", ROWS, CLOSE), None, TODAY)
    assert [(e.date.isoformat(), e.days, e.monthly) for e in part.expirations] == [
        ("2026-11-27", 7, False), ("2026-12-18", 28, True), ("2027-01-15", 56, True),
        ("2027-03-19", 119, True), ("2027-06-17", 209, True),
    ]
    # 18 December is monthly but 28 days out; January is the first past 30.
    assert part.default_expiration == part.expiration == date(2027, 1, 15)
    # With nothing a month out, it is the furthest there is.
    near = [e for e in part.expirations if e.days < 30]
    assert default_expiration(near) == date(2026, 12, 18)


def test_the_implied_move_is_the_call_and_put_at_the_money_over_the_price() -> None:
    chain = parse_chain("NVDA", ROWS, CLOSE)
    january = chain.by_expiration[date(2027, 1, 15)]
    # The 125 call is 14.23 and the 125 put 12.40: 26.63 on a 125.53 stock.
    assert implied_move_pct(january, CLOSE) == pytest.approx(21.2)
    # Further out costs more, so implies more.
    moves = [e.implied_move_pct for e in slice_chain(chain, None, TODAY).expirations]
    assert moves == sorted(moves) and all(m is not None for m in moves)


def test_no_implied_move_without_a_call_and_put_near_the_price() -> None:
    chain = parse_chain("NVDA", ROWS, CLOSE)
    calls_only = [c for c in chain.by_expiration[date(2027, 1, 15)] if c.kind == "call"]
    assert implied_move_pct(calls_only, CLOSE) is None
    far = [c for c in chain.by_expiration[date(2027, 1, 15)] if c.strike >= 140]
    assert implied_move_pct(far, CLOSE) is None


def test_a_screen_is_sent_one_expiry_near_the_price() -> None:
    chain = parse_chain("NVDA", ROWS, CLOSE)
    part = slice_chain(chain, date(2026, 12, 18), TODAY)
    assert part.expiration == date(2026, 12, 18) and part.default_expiration == date(2027, 1, 15)
    assert {c.expiration for c in part.contracts} == {date(2026, 12, 18)}
    strikes = [c.strike for c in part.contracts]
    assert strikes == sorted(strikes) and CLOSE * 0.65 <= strikes[0] and strikes[-1] <= CLOSE * 1.35


def test_asking_for_an_expiry_that_is_not_listed_or_has_passed() -> None:
    chain = parse_chain("NVDA", ROWS, CLOSE)
    with pytest.raises(OptionsUnavailable) as missing:
        slice_chain(chain, date(2026, 12, 19), TODAY)
    assert missing.value.reason == NO_OPTIONS
    # The cached chain outlived its nearest expiry: that one is no longer offered.
    later = slice_chain(chain, None, date(2026, 11, 27))
    assert later.expirations[0].date == date(2026, 12, 18)
    with pytest.raises(OptionsUnavailable):
        slice_chain(chain, date(2026, 11, 27), date(2026, 11, 27))
    # And once every expiry has passed there is nothing to show.
    with pytest.raises(OptionsUnavailable) as stale:
        slice_chain(chain, None, date(2028, 1, 1))
    assert stale.value.reason == NOT_AVAILABLE


# ── The provider call ─────────────────────────────────────────────────────────

class FakeProvider:
    """Stands in for AlphaVantageClient, counting what it is asked."""

    def __init__(self, rows: Optional[List[dict]] = None, fail: Optional[Exception] = None,
                 closes: Optional[List[dict]] = None, delay: float = 0.0) -> None:
        self.rows = ROWS if rows is None else rows
        self.fail = fail
        self.closes = closes if closes is not None else [
            {"trading_date": date(2026, 11, 19), "close": 145.98},
            {"trading_date": date(2026, 11, 20), "close": CLOSE},
        ]
        self.delay = delay
        self.chain_calls = 0
        # What asking for one expiry returns: the whole thing, both sides.
        self.expiry_rows = ROWS
        self.expiry_fail: Optional[Exception] = None
        self.expiry_calls = 0

    async def fetch_option_chain(self, symbol: str, expiration: Optional[date] = None) -> List[dict]:
        if expiration is not None:
            self.expiry_calls += 1
            await asyncio.sleep(self.delay)
            if self.expiry_fail is not None:
                raise self.expiry_fail
            return [r for r in self.expiry_rows if r["expiration"] == expiration.isoformat()]
        self.chain_calls += 1
        await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        return self.rows

    async def fetch_daily_adjusted(self, symbol: str, outputsize: str = "full") -> List[dict]:
        if not self.closes:
            raise AlphaVantageError("no prices")
        return self.closes


async def test_a_plan_the_key_does_not_cover_is_an_error_not_a_chain(monkeypatch) -> None:
    client = AlphaVantageClient()

    async def premium_notice(params: dict) -> dict:
        assert params == {"function": "HISTORICAL_OPTIONS", "symbol": "BRKB", "expiration": "2027-01-15"}
        return {
            "endpoint": "Historical Options",
            "message": "This is a premium endpoint. ***THE SAMPLE DATA SCHEMA BELOW IS ARTIFICIAL***",
            "data": [{"contractID": "XXYYZZ999999C00020000", "symbol": "XXYYZZ"}],
        }

    monkeypatch.setattr(client, "_request", premium_notice)
    with pytest.raises(AlphaVantageError):
        await client.fetch_option_chain("BRK-B", date(2027, 1, 15))


async def test_an_unknown_symbol_is_an_empty_chain(monkeypatch) -> None:
    client = AlphaVantageClient()

    async def unknown(params: dict) -> dict:
        return {"endpoint": "Historical Options", "message": "Invalid/empty symbol", "data": []}

    monkeypatch.setattr(client, "_request", unknown)
    assert await client.fetch_option_chain("ZZZZQ") == []

    async def success(params: dict) -> dict:
        return {"endpoint": "Historical Options", "message": "success", "data": ROWS[:3]}

    monkeypatch.setattr(client, "_request", success)
    assert await client.fetch_option_chain("NVDA") == ROWS[:3]


# ── The service ───────────────────────────────────────────────────────────────

async def test_everyone_asking_at_once_shares_one_provider_call() -> None:
    provider = FakeProvider(delay=0.02)
    service = OptionChainService(client=provider)
    chains = await asyncio.gather(*(service.get("nvda") for _ in range(25)))
    assert provider.chain_calls == 1
    assert all(c is chains[0] for c in chains) and chains[0].symbol == "NVDA"
    # And again a moment later: still the one call.
    await service.get("NVDA")
    assert provider.chain_calls == 1


async def test_the_stock_price_is_the_close_on_the_day_the_option_prices_are_from() -> None:
    # The provider's daily series already has a later day; the chain is from the 20th.
    closes = [
        {"trading_date": date(2026, 11, 20), "close": CLOSE},
        {"trading_date": date(2026, 11, 23), "close": 131.00},
    ]
    chain = await OptionChainService(client=FakeProvider(closes=closes)).get("NVDA")
    assert chain.underlying_price == CLOSE


async def test_without_a_daily_close_the_live_quote_is_used(monkeypatch) -> None:
    async def quote(symbol: str):
        return SimpleNamespace(price=126.10)

    monkeypatch.setattr(chain_service.live_quote_service, "get_quote", quote)
    chain = await OptionChainService(client=FakeProvider(closes=[])).get("NVDA")
    assert chain.underlying_price == 126.10


async def test_no_price_for_the_stock_means_no_chain(monkeypatch) -> None:
    async def no_quote(symbol: str):
        return None

    monkeypatch.setattr(chain_service.live_quote_service, "get_quote", no_quote)
    with pytest.raises(OptionsUnavailable) as failed:
        await OptionChainService(client=FakeProvider(closes=[])).get("NVDA")
    assert failed.value.reason == NOT_AVAILABLE


async def test_a_stock_with_no_options_is_remembered_and_not_asked_about_again() -> None:
    provider = FakeProvider(rows=[])
    service = OptionChainService(client=provider)
    for _ in range(3):
        with pytest.raises(OptionsUnavailable) as none:
            await service.get("ZZZZQ")
        assert none.value.reason == NO_OPTIONS and "ZZZZQ" in none.value.message
    assert provider.chain_calls == 1


async def test_a_failing_provider_is_left_alone_for_a_minute_then_tried_again() -> None:
    provider = FakeProvider(fail=AlphaVantageError("rate limit"))
    service = OptionChainService(client=provider)
    for _ in range(3):
        with pytest.raises(OptionsUnavailable) as down:
            await service.get("NVDA")
        assert down.value.reason == NOT_AVAILABLE
    assert provider.chain_calls == 1
    # The provider recovers and the minute passes.
    provider.fail = None
    service._provider_down.clear()
    assert (await service.get("NVDA")).symbol == "NVDA"
    assert provider.chain_calls == 2


async def test_a_failure_never_puts_the_api_key_in_the_log(caplog) -> None:
    secret = RuntimeError("GET https://www.alphavantage.co/query?function=X&apikey=SECRETKEY failed")
    service = OptionChainService(client=FakeProvider(fail=secret))
    with caplog.at_level("INFO"), pytest.raises(OptionsUnavailable) as down:
        await service.get("NVDA")
    assert "SECRETKEY" not in caplog.text and "SECRETKEY" not in down.value.message
    assert down.value.__cause__ is None


async def test_a_chain_that_arrives_without_its_puts_is_repaired_one_expiry_at_a_time() -> None:
    # What the provider sent for AAPL and SPY on 2026-11-20: every call, no put.
    calls_only = [r for r in ROWS if r["type"] == "call"]
    provider = FakeProvider(rows=calls_only, delay=0.01)
    service = OptionChainService(client=provider)
    parts = await asyncio.gather(*(service.slice("NVDA", None, TODAY) for _ in range(10)))
    part = parts[0]
    assert {c.kind for c in part.contracts} == {"call", "put"}
    assert (provider.chain_calls, provider.expiry_calls) == (1, 1)
    # The expiry that was fetched has its implied move; the others cannot have one yet.
    moves = {e.date: e.implied_move_pct for e in part.expirations}
    assert moves[date(2027, 1, 15)] == pytest.approx(21.2) and moves[date(2026, 12, 18)] is None
    # Another expiry is one more call; the same one again is none.
    december = await service.slice("NVDA", date(2026, 12, 18), TODAY)
    assert {c.kind for c in december.contracts} == {"call", "put"}
    await service.slice("NVDA", None, TODAY)
    assert (provider.chain_calls, provider.expiry_calls) == (1, 2)


async def test_a_whole_chain_is_never_fetched_twice_over() -> None:
    provider = FakeProvider()
    part = await OptionChainService(client=provider).slice("NVDA", None, TODAY)
    assert {c.kind for c in part.contracts} == {"call", "put"}
    assert (provider.chain_calls, provider.expiry_calls) == (1, 0)


async def test_when_the_repair_fails_the_calls_are_still_sent() -> None:
    calls_only = [r for r in ROWS if r["type"] == "call"]
    provider = FakeProvider(rows=calls_only)
    provider.expiry_fail = AlphaVantageError("down")
    service = OptionChainService(client=provider)
    part = await service.slice("NVDA", None, TODAY)
    assert {c.kind for c in part.contracts} == {"call"}
    # A repair that came back one-sided too is not kept: it is tried again.
    provider.expiry_fail, provider.expiry_rows = None, calls_only
    assert {c.kind for c in (await service.slice("NVDA", None, TODAY)).contracts} == {"call"}
    provider.expiry_rows = ROWS
    assert {c.kind for c in (await service.slice("NVDA", None, TODAY)).contracts} == {"call", "put"}


# ── The endpoints ─────────────────────────────────────────────────────────────

@pytest.fixture
def chains(monkeypatch) -> FakeProvider:
    provider = FakeProvider()
    monkeypatch.setattr(options_routes, "option_chain_service", OptionChainService(client=provider))
    monkeypatch.setattr(options_routes, "today_et", lambda: TODAY)
    return provider


def test_the_chain_endpoint_sends_the_default_expiry_and_every_date(chains, make_user, db: Session) -> None:
    user = make_user(email="chain@example.com")
    view = asyncio.run(options_routes.get_chain("nvda", None, _user=user, db=db))
    assert (view.symbol, view.as_of, view.underlying_price) == ("NVDA", TODAY, CLOSE)
    assert view.expiration == view.default_expiration == date(2027, 1, 15)
    assert len(view.expirations) == 5 and view.expirations[2].implied_move_pct == pytest.approx(21.2)
    assert {c.kind for c in view.contracts} == {"call", "put"}
    december = asyncio.run(options_routes.get_chain("NVDA", date(2026, 12, 18), _user=user, db=db))
    assert december.expiration == date(2026, 12, 18) and december.default_expiration == date(2027, 1, 15)
    assert chains.chain_calls == 1


def test_the_chain_endpoint_says_why_there_is_nothing(monkeypatch, make_user, db: Session) -> None:
    user = make_user(email="none@example.com")
    monkeypatch.setattr(options_routes, "today_et", lambda: TODAY)
    monkeypatch.setattr(options_routes, "option_chain_service", OptionChainService(client=FakeProvider(rows=[])))
    with pytest.raises(HTTPException) as none:
        asyncio.run(options_routes.get_chain("ZZZZQ", None, _user=user, db=db))
    assert none.value.status_code == 404 and "no listed options" in none.value.detail

    monkeypatch.setattr(
        options_routes, "option_chain_service", OptionChainService(client=FakeProvider(fail=AlphaVantageError("down")))
    )
    with pytest.raises(HTTPException) as down:
        asyncio.run(options_routes.get_chain("NVDA", None, _user=user, db=db))
    assert down.value.status_code == 503 and "Try again" in down.value.detail

    with pytest.raises(HTTPException) as junk:
        asyncio.run(options_routes.get_chain("not a ticker!", None, _user=user, db=db))
    assert junk.value.status_code == 404


# ── Estimates for the stock's price now ──────────────────────────────────────
#
# Jimmy, 2026-11-25: the chain is the last close's (real-time option prices are
# not on the plan), and on a day the stock moves 12% it describes a different
# stock. Estimate each contract for the price now, and say it is an estimate.
#
# Measured against real chains (price day D from day D-1's chain and D's
# stock close, compare with D's chain; strikes within 20%, 20 to 200 days out):
#
#                      stock    estimate off by   last close off by
#   NVDA 11-23 > 24    -5.9%         3.4%              29.5%
#   NVDA 11-20 > 23   +31.5%         9.1%              93.0%
#   AAPL 11-23 > 24    +1.4%         1.1%              12.7%
#   REGN 11-23 > 24    +4.8%         1.0%              31.3%
#   SPY  11-23 > 24    -0.5%         2.0%               6.6%
#   MSFT 11-19 > 20    -2.8%         7.6%              20.4%

NEW_YORK = chain_service._ET
MONDAY_MIDDAY = datetime(2026, 11, 23, 12, 58, tzinfo=NEW_YORK)   # the session after the chain's
JANUARY = date(2027, 1, 15)


def test_the_pricing_model_gives_the_textbook_values() -> None:
    # Hull's standard example: stock 100, strike 100, a year, 20% volatility, 5%.
    assert black_scholes("call", 100, 100, 1.0, 0.20, 0.05) == pytest.approx(10.4506, abs=1e-4)
    assert black_scholes("put", 100, 100, 1.0, 0.20, 0.05) == pytest.approx(5.5735, abs=1e-4)
    # A call less a put is the stock less the discounted strike, at any strike.
    for strike in (60, 100, 140):
        gap = black_scholes("call", 100, strike, 0.5, 0.35) - black_scholes("put", 100, strike, 0.5, 0.35)
        assert gap == pytest.approx(100 - strike * 2.718281828459045 ** (-0.04 * 0.5), abs=1e-9)
    # At expiry, or with nothing left to vary, it is what exercising is worth.
    assert black_scholes("call", 110, 100, 0, 0.3) == 10 and black_scholes("put", 110, 100, 0, 0.3) == 0
    assert black_scholes("put", 90, 100, 0.5, 0) == 10


def test_time_to_expiry_runs_to_the_close_on_the_expiry_day() -> None:
    at = datetime(2027, 1, 14, 16, 0, tzinfo=NEW_YORK)
    assert years_to_expiry(JANUARY, at) == pytest.approx(1 / 365)
    assert years_to_expiry(JANUARY, datetime(2027, 1, 16, 9, 0, tzinfo=NEW_YORK)) == 0


def test_regression_a_chain_is_estimated_for_the_stock_price_now() -> None:
    """The reported shape: the stock has fallen since the close the chain is from."""
    quoted = parse_chain("NVDA", ROWS, CLOSE)
    fallen = round(CLOSE * 0.88, 2)  # 12% lower, as NVDA was on 2026-11-25
    chain = estimate_chain(quoted, fallen, MONDAY_MIDDAY)

    assert chain.underlying_price == fallen
    assert chain.quoted_underlying_price == CLOSE and chain.estimated_at == MONDAY_MIDDAY
    assert chain.as_of == TODAY  # still says which close the quotes are from

    before = {(c.kind, c.strike): c for c in quoted.by_expiration[JANUARY]}
    after = {(c.kind, c.strike): c for c in chain.by_expiration[JANUARY]}
    for key, contract in after.items():
        kind, strike = key
        # The quote it came from is kept, and bid and ask are still the close's.
        assert contract.quoted_mid == before[key].mid
        assert (contract.bid, contract.ask) == (before[key].bid, before[key].ask)
        # A fall takes calls down and puts up, and nothing below what exercising is worth.
        if kind == "call":
            assert contract.mid < before[key].mid
            assert contract.mid >= max(fallen - strike, 0)
        else:
            assert contract.mid > before[key].mid
            assert contract.mid >= round(max(strike - fallen, 0), 2)
        assert contract.mid >= 0.01

    # Worked by hand for the $120 call: quoted 17.00 at 71.73% volatility,
    # 56 days from the Friday close and 53.127 from Monday 12:58.
    then = black_scholes("call", CLOSE, 120, 56 / 365, 0.7173)
    now = black_scholes("call", fallen, 120, years_to_expiry(JANUARY, MONDAY_MIDDAY), 0.7173)
    assert after[("call", 120.0)].mid == pytest.approx(round(17.00 + now - then, 2), abs=0.005)
    assert 7.0 < after[("call", 120.0)].mid < 10.0


def test_a_stock_that_has_not_moved_keeps_its_quotes_less_the_time_gone() -> None:
    quoted = parse_chain("NVDA", ROWS, CLOSE)
    chain = estimate_chain(quoted, CLOSE, MONDAY_MIDDAY)
    before = {(c.kind, c.strike): c.mid for c in quoted.by_expiration[JANUARY]}
    for contract in chain.by_expiration[JANUARY]:
        was = before[(contract.kind, contract.strike)]
        # Nearly three days of time value, and no more than that.
        assert was - 0.60 <= contract.mid <= was


def test_a_price_from_the_chains_own_day_changes_nothing() -> None:
    """The evening after the close, or before the next open, the live quote is
    the last trade of the day the chain is already priced on."""
    quoted = parse_chain("NVDA", ROWS, CLOSE)
    friday_close = datetime(2026, 11, 20, 16, 0, tzinfo=NEW_YORK)
    assert estimate_chain(quoted, 125.60, friday_close) is quoted
    assert estimate_chain(quoted, 125.60, None) is quoted
    assert estimate_chain(quoted, 0, MONDAY_MIDDAY) is quoted


def test_a_contract_with_no_usable_volatility_keeps_its_quote_or_its_exercise_value() -> None:
    rows = [
        row("NVDA261218C00100000", strike="100.00", bid="27.00", ask="27.40", implied_volatility="0.00000"),
        row("NVDA261218P00140000", strike="140.00", type="put", bid="15.00", ask="15.40", implied_volatility="-"),
    ]
    chain = estimate_chain(parse_chain("NVDA", rows, CLOSE), 110.00, MONDAY_MIDDAY)
    call, put = chain.by_expiration[date(2026, 12, 18)]
    assert call.mid == 27.20            # no model for it: the quote stands
    assert put.mid == 30.00             # the quote, 15.20, is below 140 - 110


async def test_a_screen_asking_for_the_price_now_is_sent_estimates_around_it() -> None:
    service = OptionChainService(client=FakeProvider())
    quoted = await service.slice("NVDA", None, TODAY)
    part = await service.slice("NVDA", None, TODAY, stock_now=110.00, traded_at=MONDAY_MIDDAY)

    assert (part.underlying_price, part.quoted_underlying_price, part.estimated_at) == (110.00, CLOSE, MONDAY_MIDDAY)
    assert all(c.quoted_mid is not None for c in part.contracts)
    # Cut around the price now, not the close.
    assert all(110 * 0.65 <= c.strike <= 110 * 1.35 for c in part.contracts)
    # The plain chain is untouched by having been estimated.
    assert quoted.estimated_at is None and all(c.quoted_mid is None for c in quoted.contracts)
    assert (await service.slice("NVDA", None, TODAY)).underlying_price == CLOSE


async def test_a_repaired_expiry_is_estimated_too() -> None:
    calls_only = [r for r in ROWS if r["type"] == "call"]
    service = OptionChainService(client=FakeProvider(rows=calls_only))
    part = await service.slice("NVDA", None, TODAY, stock_now=110.00, traded_at=MONDAY_MIDDAY)
    assert {c.kind for c in part.contracts} == {"call", "put"}
    assert all(c.quoted_mid is not None for c in part.contracts)


def _quote(price: float, at: Optional[datetime]) -> SimpleNamespace:
    return SimpleNamespace(price=price, as_of=at.timestamp() if at else None)


def test_the_endpoint_estimates_only_when_asked(chains, monkeypatch, make_user, db: Session) -> None:
    user = make_user(email="estimate@example.com")
    asked: List[str] = []

    async def live(symbol: str):
        asked.append(symbol)
        return _quote(110.00, MONDAY_MIDDAY)

    monkeypatch.setattr(options_routes.live_quote_service, "get_quote", live)

    # An app that does not ask gets the close's prices and no live lookup:
    # it has no way to say the prices are estimates.
    plain = asyncio.run(options_routes.get_chain("NVDA", None, _user=user, db=db))
    assert (plain.underlying_price, plain.estimated_at, plain.quoted_underlying_price) == (CLOSE, None, None)
    assert all(c.quoted_mid is None for c in plain.contracts) and asked == []

    view = asyncio.run(options_routes.get_chain("NVDA", None, estimate=True, _user=user, db=db))
    assert asked == ["NVDA"]
    assert (view.underlying_price, view.quoted_underlying_price, view.as_of) == (110.00, CLOSE, TODAY)
    assert view.estimated_at == MONDAY_MIDDAY
    call = next(c for c in view.contracts if c.kind == "call" and c.strike == 120.0)
    assert call.quoted_mid == 17.00 and call.mid < 17.00 and (call.bid, call.ask) == (16.60, 17.40)
    assert chains.chain_calls == 1


def test_without_a_live_price_the_endpoint_sends_the_close(chains, monkeypatch, make_user, db: Session) -> None:
    user = make_user(email="nolive@example.com")

    async def down(symbol: str):
        raise RuntimeError("quote provider is down")

    monkeypatch.setattr(options_routes.live_quote_service, "get_quote", down)
    view = asyncio.run(options_routes.get_chain("NVDA", None, estimate=True, _user=user, db=db))
    assert (view.underlying_price, view.estimated_at) == (CLOSE, None)

    async def stale(symbol: str):
        return _quote(125.60, datetime(2026, 11, 20, 16, 0, tzinfo=NEW_YORK))  # the chain's own day

    monkeypatch.setattr(options_routes.live_quote_service, "get_quote", stale)
    view = asyncio.run(options_routes.get_chain("NVDA", None, estimate=True, _user=user, db=db))
    assert (view.underlying_price, view.estimated_at) == (CLOSE, None)

    async def untimed(symbol: str):
        return _quote(110.00, None)  # a price with no trade time cannot be placed

    monkeypatch.setattr(options_routes.live_quote_service, "get_quote", untimed)
    view = asyncio.run(options_routes.get_chain("NVDA", None, estimate=True, _user=user, db=db))
    assert (view.underlying_price, view.estimated_at) == (CLOSE, None)


def test_the_option_endpoints_are_for_signed_in_users() -> None:
    routes = [r for r in options_routes.router.routes if r.path.startswith("/api/options")]
    assert len(routes) == 4
    for route in routes:
        needs = {d.call for d in route.dependant.dependencies}
        assert get_current_user in needs, f"{sorted(route.methods)} {route.path} is open to anyone"


# ── Saved plans ───────────────────────────────────────────────────────────────

def long_call() -> OptionPlanCreate:
    return OptionPlanCreate(
        symbol="nvda", strategy="long_call", underlying_price=CLOSE, as_of=TODAY,
        legs=[OptionLeg(kind="call", side="buy", quantity=1, price=14.23, strike=125.0,
                        expiration=date(2027, 1, 15), contract_id="NVDA270115C00125000")],
    )


def covered_call() -> OptionPlanCreate:
    return OptionPlanCreate(
        symbol="NVDA", strategy="covered_call", underlying_price=CLOSE, as_of=TODAY,
        legs=[
            OptionLeg(kind="stock", side="buy", quantity=100, price=CLOSE),
            OptionLeg(kind="call", side="sell", quantity=1, price=9.80, strike=135.0,
                      expiration=date(2027, 1, 15), contract_id="NVDA270115C00135000"),
        ],
    )


def test_a_saved_plan_comes_back_as_it_was_saved_newest_first(make_user, db: Session) -> None:
    user = make_user(email="plans@example.com")
    first = options_routes.save_plan(long_call(), user=user, db=db)
    second = options_routes.save_plan(covered_call(), user=user, db=db)
    assert first.symbol == "NVDA" and first.id != second.id
    listed = options_routes.list_plans(user=user, db=db)
    assert {p.id for p in listed} == {first.id, second.id}
    saved = next(p for p in listed if p.id == second.id)
    assert saved.strategy == "covered_call" and saved.as_of == TODAY and saved.underlying_price == CLOSE
    assert [(leg.kind, leg.side, leg.quantity, leg.price) for leg in saved.legs] == [
        ("stock", "buy", 100, CLOSE), ("call", "sell", 1, 9.80),
    ]
    assert saved.legs[1].expiration == date(2027, 1, 15) and saved.legs[1].contract_id == "NVDA270115C00135000"


def test_a_plan_belongs_to_the_person_who_saved_it(make_user, db: Session) -> None:
    owner = make_user(email="owner@example.com")
    other = make_user(email="other@example.com")
    plan = options_routes.save_plan(long_call(), user=owner, db=db)
    assert options_routes.list_plans(user=other, db=db) == []
    with pytest.raises(HTTPException) as denied:
        options_routes.delete_plan(plan.id, user=other, db=db)
    assert denied.value.status_code == 404
    assert len(options_routes.list_plans(user=owner, db=db)) == 1
    options_routes.delete_plan(plan.id, user=owner, db=db)
    assert options_routes.list_plans(user=owner, db=db) == []
    with pytest.raises(HTTPException):
        options_routes.delete_plan(plan.id, user=owner, db=db)


def test_there_is_a_ceiling_on_saved_plans(monkeypatch, make_user, db: Session) -> None:
    user = make_user(email="many@example.com")
    monkeypatch.setattr(options_routes, "MAX_PLANS_PER_USER", 2)
    options_routes.save_plan(long_call(), user=user, db=db)
    options_routes.save_plan(long_call(), user=user, db=db)
    with pytest.raises(HTTPException) as full:
        options_routes.save_plan(long_call(), user=user, db=db)
    assert full.value.status_code == 409 and "Delete one" in full.value.detail


def test_a_plan_that_does_not_make_sense_is_refused() -> None:
    option = dict(kind="call", side="buy", quantity=1, price=1.0, strike=125.0,
                  expiration=date(2027, 1, 15), contract_id="NVDA270115C00125000")
    for missing in ("strike", "expiration", "contract_id"):
        with pytest.raises(ValidationError):
            OptionLeg(**{k: v for k, v in option.items() if k != missing})
    with pytest.raises(ValidationError):
        OptionLeg(kind="stock", side="buy", quantity=100, price=125.0, strike=125.0)
    with pytest.raises(ValidationError):
        OptionLeg(**{**option, "quantity": 0})
    with pytest.raises(ValidationError):
        OptionLeg(**{**option, "price": -1})
    good = OptionLeg(**option)
    for bad in (
        dict(symbol="not a ticker!"), dict(strategy="iron_butterfly"), dict(legs=[]),
        dict(legs=[good] * 5), dict(underlying_price=0),
    ):
        with pytest.raises(ValidationError):
            OptionPlanCreate(**{**dict(symbol="NVDA", strategy="long_call", legs=[good],
                                       underlying_price=CLOSE, as_of=TODAY), **bad})
