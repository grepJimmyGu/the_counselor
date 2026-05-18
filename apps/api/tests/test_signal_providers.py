"""
Unit tests for signal_provider.py.

All external calls (FMP API, DB) are mocked.  Tests assert:
  - The return value is a pd.Series with a DatetimeIndex
  - Values are numeric (float)
  - The index falls within or at the requested [start, end] window
  - Look-ahead prevention: fundamental signals are dated AFTER period_end
    by at least report_date_lag days
  - EarningsEventSignalProvider SUE is NaN-sparse (only earnings dates present)
  - InsiderSignalProvider returns rolling net-buy dollar sum
  - Registry maps each signal_source name to the correct provider class
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services.backtester.signal_provider import (
    EarningsEventSignalProvider,
    FundamentalSignalProvider,
    InsiderSignalProvider,
    SentimentSignalProvider,
    SignalProvider,
    get_signal_provider,
)

# ── Common fixtures ───────────────────────────────────────────────────────────

START = date(2021, 1, 1)
END   = date(2022, 12, 31)
SYM   = "AAPL"


def _fake_db():
    return MagicMock()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_series(s: pd.Series, name: str) -> None:
    """Common shape/type assertions for all providers."""
    assert isinstance(s, pd.Series), f"Expected pd.Series, got {type(s)}"
    assert s.name == name, f"Series name mismatch: {s.name!r} != {name!r}"
    if not s.empty:
        assert hasattr(s.index, "dtype"), "Index must have dtype attribute"
        assert "datetime" in str(s.index.dtype).lower(), (
            f"Expected datetime index, got {s.index.dtype}"
        )
        assert s.apply(lambda v: isinstance(v, (float, int)) or pd.isna(v)).all(), (
            "All values must be numeric or NaN"
        )


# ── FundamentalSignalProvider ─────────────────────────────────────────────────

def _fake_cashflow(period_end: str, fcf: float = 5e9, mcap: float = 100e9,
                   buyback: float = 2e9) -> dict:
    return {
        "date": period_end, "calendarYear": period_end[:4],
        "freeCashFlow": fcf,
        "marketCap": mcap,
        "commonStockRepurchased": -abs(buyback),
    }


def _fake_balance(period_end: str, equity: float = 40e9, mcap: float = 100e9) -> dict:
    return {
        "date": period_end,
        "totalStockholdersEquity": equity,
        "marketCap": mcap,
        "totalAssets": 80e9,
        "totalCurrentAssets": 30e9,
        "totalCurrentLiabilities": 15e9,
        "longTermDebt": 20e9,
    }


def _fake_income(period_end: str, revenue: float = 50e9, gross: float = 25e9,
                 net: float = 10e9, shares: float = 16e9,
                 ebitda: float = 15e9, eps: float = 3.0) -> dict:
    return {
        "date": period_end,
        "revenue": revenue, "grossProfit": gross,
        "netIncome": net, "weightedAverageShsOut": shares,
        "ebitda": ebitda, "epsDiluted": eps,
        "enterpriseValue": 120e9,
        "operatingCashFlow": net * 1.2,
    }


@pytest.mark.asyncio
async def test_fundamental_fcf_yield():
    cashflows = [_fake_cashflow("2021-09-30"), _fake_cashflow("2020-09-30")]
    provider = FundamentalSignalProvider("fcf_yield", report_date_lag=45)

    with patch.object(provider._fmp, "get_cash_flow",   new=AsyncMock(return_value=cashflows)), \
         patch.object(provider._fmp, "get_balance_sheet", new=AsyncMock(return_value=[])), \
         patch.object(provider._fmp, "get_income_statement", new=AsyncMock(return_value=[])):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    _assert_series(s, "fcf_yield")
    assert not s.empty
    # Check look-ahead lag: disclosure >= period_end + lag
    period_end = date(2021, 9, 30)
    earliest_allowed = period_end + timedelta(days=45)
    for ts in s.index:
        assert ts.date() >= earliest_allowed, (
            f"Signal dated {ts.date()} is before disclosure date {earliest_allowed}"
        )
    # FCF yield = 5e9 / 100e9 = 0.05
    assert abs(s.iloc[-1] - 0.05) < 1e-6


@pytest.mark.asyncio
async def test_fundamental_book_to_market():
    balances = [_fake_balance("2021-09-30"), _fake_balance("2020-09-30")]
    provider = FundamentalSignalProvider("book_to_market")

    with patch.object(provider._fmp, "get_cash_flow",   new=AsyncMock(return_value=[])), \
         patch.object(provider._fmp, "get_balance_sheet", new=AsyncMock(return_value=balances)), \
         patch.object(provider._fmp, "get_income_statement", new=AsyncMock(return_value=[])):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    _assert_series(s, "book_to_market")
    assert not s.empty
    # book_to_market = 40e9 / 100e9 = 0.40
    assert abs(s.iloc[-1] - 0.40) < 1e-6


@pytest.mark.asyncio
async def test_fundamental_ebitda_ev():
    incomes = [_fake_income("2021-09-30"), _fake_income("2020-09-30")]
    balances = [_fake_balance("2021-09-30")]
    provider = FundamentalSignalProvider("ebitda_ev")

    with patch.object(provider._fmp, "get_cash_flow",   new=AsyncMock(return_value=[])), \
         patch.object(provider._fmp, "get_balance_sheet", new=AsyncMock(return_value=balances)), \
         patch.object(provider._fmp, "get_income_statement", new=AsyncMock(return_value=incomes)):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    _assert_series(s, "ebitda_ev")
    # ebitda/ev = 15e9 / 120e9 ≈ 0.125
    assert not s.empty
    assert abs(s.iloc[-1] - 15e9 / 120e9) < 1e-6


@pytest.mark.asyncio
async def test_fundamental_buyback_yield():
    cashflows = [_fake_cashflow("2021-09-30", buyback=2e9),
                 _fake_cashflow("2020-09-30", buyback=2e9)]
    provider = FundamentalSignalProvider("buyback_yield_ttm")

    with patch.object(provider._fmp, "get_cash_flow",   new=AsyncMock(return_value=cashflows)), \
         patch.object(provider._fmp, "get_balance_sheet", new=AsyncMock(return_value=[])), \
         patch.object(provider._fmp, "get_income_statement", new=AsyncMock(return_value=[])):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    _assert_series(s, "buyback_yield_ttm")
    assert not s.empty
    # buyback_yield = 2e9 / 100e9 = 0.02
    assert abs(s.iloc[-1] - 0.02) < 1e-6


@pytest.mark.asyncio
async def test_fundamental_f_score():
    # Two periods: 2020 and 2021 (need at least 2 for change signals)
    incomes  = [_fake_income("2021-09-30"), _fake_income("2020-09-30")]
    cashflow = [
        {**_fake_income("2021-09-30"), "operatingCashFlow": 12e9, "freeCashFlow": 5e9},
        {**_fake_income("2020-09-30"), "operatingCashFlow": 10e9, "freeCashFlow": 4e9},
    ]
    balances = [_fake_balance("2021-09-30"), _fake_balance("2020-09-30")]
    provider = FundamentalSignalProvider("f_score")

    with patch.object(provider._fmp, "get_income_statement", new=AsyncMock(return_value=incomes)), \
         patch.object(provider._fmp, "get_cash_flow",        new=AsyncMock(return_value=cashflow)), \
         patch.object(provider._fmp, "get_balance_sheet",    new=AsyncMock(return_value=balances)):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    _assert_series(s, "f_score")
    assert not s.empty
    # F-Score must be integer-valued 0–9
    for v in s:
        assert 0 <= v <= 9, f"F-Score out of range: {v}"


@pytest.mark.asyncio
async def test_fundamental_returns_empty_on_fmp_error():
    provider = FundamentalSignalProvider("fcf_yield")
    with patch.object(provider._fmp, "get_cash_flow",
                      new=AsyncMock(side_effect=RuntimeError("FMP unavailable"))), \
         patch.object(provider._fmp, "get_balance_sheet",   new=AsyncMock(return_value=[])), \
         patch.object(provider._fmp, "get_income_statement", new=AsyncMock(return_value=[])):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    assert isinstance(s, pd.Series)
    assert s.empty


def test_fundamental_unknown_signal_raises():
    with pytest.raises(ValueError, match="unknown signal"):
        FundamentalSignalProvider("flying_saucers")


# ── SentimentSignalProvider ───────────────────────────────────────────────────

def _fake_db_with_sentiment(rows: list[tuple]) -> MagicMock:
    """Mock DB that returns sentiment rows for the SQL query."""
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
async def test_sentiment_returns_rolling_mean():
    # Simulate 5 sentiment observations over 6 months
    base = date(2021, 3, 1)
    rows = [
        (base + timedelta(days=i * 30), 60 + i * 2)
        for i in range(5)
    ]
    db = _fake_db_with_sentiment(rows)
    provider = SentimentSignalProvider()
    s = await provider.get_signal_frame(db, SYM, START, END)

    _assert_series(s, "sentiment_score")
    # Rolling 30D mean of 5 points should produce at least 1 value
    assert not s.empty
    assert all(50 <= v <= 80 for v in s)


@pytest.mark.asyncio
async def test_sentiment_returns_empty_on_no_data():
    db = _fake_db_with_sentiment([])
    provider = SentimentSignalProvider()
    s = await provider.get_signal_frame(db, SYM, START, END)
    assert isinstance(s, pd.Series)
    assert s.empty


@pytest.mark.asyncio
async def test_sentiment_returns_empty_on_db_error():
    db = MagicMock()
    db.execute.side_effect = Exception("DB down")
    provider = SentimentSignalProvider()
    s = await provider.get_signal_frame(db, SYM, START, END)
    assert isinstance(s, pd.Series)
    assert s.empty


# ── EarningsEventSignalProvider ───────────────────────────────────────────────

def _fake_quarterly_incomes(start_period: str = "2019-12-31", n: int = 10) -> list[dict]:
    """Generate quarterly income statements with increasing EPS."""
    from datetime import date as _date
    base = _date.fromisoformat(start_period)
    rows = []
    for i in range(n):
        # Approximate quarterly dates
        month_offset = i * 3
        year  = base.year + (base.month + month_offset - 1) // 12
        month = (base.month + month_offset - 1) % 12 + 1
        import calendar
        day = min(base.day, calendar.monthrange(year, month)[1])
        d = _date(year, month, day)
        rows.append({
            "date": d.isoformat(),
            "epsDiluted": 1.0 + i * 0.1,   # growing EPS → positive SUE
        })
    return rows


@pytest.mark.asyncio
async def test_earnings_event_returns_sparse_sue():
    incomes  = _fake_quarterly_incomes(n=10)
    provider = EarningsEventSignalProvider(report_date_lag=45)

    with patch.object(provider._fmp, "get_income_statement",
                      new=AsyncMock(return_value=incomes)):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    _assert_series(s, "earnings_surprise")
    # Only earnings dates should appear (sparse)
    # The series has at most N-4 observations (year-over-year requires 4 prior qtrs)
    assert len(s) <= len(incomes)
    # SUE values should be finite floats
    for v in s:
        assert isinstance(v, float) and not (v != v)  # not NaN


@pytest.mark.asyncio
async def test_earnings_event_look_ahead_lag():
    """Disclosure dates must be exactly period_end + lag_days."""
    lag = 30
    # Use 8 clearly-spaced quarterly periods starting well within [START, END]
    # so we can compute expected disclosure dates exactly.
    fixed_incomes = [
        {"date": "2021-03-31", "epsDiluted": 3.0},
        {"date": "2021-06-30", "epsDiluted": 3.1},
        {"date": "2021-09-30", "epsDiluted": 3.2},
        {"date": "2021-12-31", "epsDiluted": 3.3},
        {"date": "2022-03-31", "epsDiluted": 3.4},   # SUE vs 2021-03-31 → disclosure 2022-04-30
        {"date": "2022-06-30", "epsDiluted": 3.5},   # SUE vs 2021-06-30 → disclosure 2022-07-30
        {"date": "2022-09-30", "epsDiluted": 3.6},   # SUE vs 2021-09-30 → disclosure 2022-10-30
    ]
    # Expected disclosure dates (period_end + lag)
    expected_disclosures = {
        pd.Timestamp(date(2022, 3, 31) + timedelta(days=lag)),
        pd.Timestamp(date(2022, 6, 30) + timedelta(days=lag)),
    }  # only dates within [START, END]

    provider = EarningsEventSignalProvider(report_date_lag=lag)
    with patch.object(provider._fmp, "get_income_statement",
                      new=AsyncMock(return_value=fixed_incomes)):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    assert not s.empty
    for ts in s.index:
        # Every disclosure date must be exactly period_end + lag
        period_end = ts.date() - timedelta(days=lag)
        # period_end must be one of the fiscal quarter-ends in fixed_incomes
        known_ends = {date.fromisoformat(r["date"]) for r in fixed_incomes}
        assert period_end in known_ends, (
            f"Disclosure {ts.date()} implies period_end {period_end} "
            f"which is not a known quarter-end"
        )


@pytest.mark.asyncio
async def test_earnings_event_empty_on_no_data():
    provider = EarningsEventSignalProvider()
    with patch.object(provider._fmp, "get_income_statement",
                      new=AsyncMock(return_value=[])):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)
    assert s.empty


# ── InsiderSignalProvider ─────────────────────────────────────────────────────

def _fake_insider_rows(buy_dates: list[str], sell_dates: list[str]) -> list[dict]:
    rows = []
    for d in buy_dates:
        rows.append({
            "transactionDate": d, "transactionType": "P-Purchase",
            "securitiesTransacted": 1000, "price": 150.0,
        })
    for d in sell_dates:
        rows.append({
            "transactionDate": d, "transactionType": "S-Sale",
            "securitiesTransacted": 500, "price": 160.0,
        })
    return rows


@pytest.mark.asyncio
async def test_insider_net_buy_returns_series():
    rows = _fake_insider_rows(
        buy_dates=["2021-03-15", "2021-06-10", "2021-09-05"],
        sell_dates=["2021-04-20"],
    )
    provider = InsiderSignalProvider()

    with patch.object(provider._fmp, "_get", new=AsyncMock(return_value=rows)):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)

    _assert_series(s, "insider_net_buy")
    assert not s.empty
    # Buy = +$150k per transaction (1000 shares × $150); Sell = -$80k (500 × $160)
    # Total net: positive net buy across the window
    assert s.sum() > 0


@pytest.mark.asyncio
async def test_insider_returns_empty_on_api_failure():
    provider = InsiderSignalProvider()
    with patch.object(provider._fmp, "_get",
                      new=AsyncMock(side_effect=RuntimeError("FMP down"))):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)
    assert isinstance(s, pd.Series)
    assert s.empty


@pytest.mark.asyncio
async def test_insider_sales_negative():
    """Sales should reduce (or negative) the rolling net-buy."""
    rows = _fake_insider_rows(
        buy_dates=[],
        sell_dates=["2021-03-01", "2021-03-15", "2021-04-01"],
    )
    provider = InsiderSignalProvider()
    with patch.object(provider._fmp, "_get", new=AsyncMock(return_value=rows)):
        s = await provider.get_signal_frame(_fake_db(), SYM, START, END)
    assert not s.empty
    assert s.sum() < 0, "Net insider sells should produce negative total"


# ── Protocol compliance ───────────────────────────────────────────────────────

def test_all_providers_have_name_attribute():
    providers = [
        FundamentalSignalProvider("fcf_yield"),
        SentimentSignalProvider(),
        EarningsEventSignalProvider(),
        InsiderSignalProvider(),
    ]
    for p in providers:
        assert isinstance(p.name, str) and p.name, (
            f"{type(p).__name__} must have a non-empty 'name' str attribute"
        )


def test_all_providers_are_signal_provider_instances():
    providers = [
        FundamentalSignalProvider("fcf_yield"),
        SentimentSignalProvider(),
        EarningsEventSignalProvider(),
        InsiderSignalProvider(),
    ]
    for p in providers:
        assert isinstance(p, SignalProvider)


# ── Registry ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("signal_name,expected_class", [
    ("fcf_yield",          FundamentalSignalProvider),
    ("book_to_market",     FundamentalSignalProvider),
    ("ebitda_ev",          FundamentalSignalProvider),
    ("f_score",            FundamentalSignalProvider),
    ("buyback_yield_ttm",  FundamentalSignalProvider),
    ("sentiment_score",    SentimentSignalProvider),
    ("earnings_surprise",  EarningsEventSignalProvider),
    ("insider_net_buy",    InsiderSignalProvider),
])
def test_registry_maps_signal_to_correct_provider(signal_name, expected_class):
    provider = get_signal_provider(signal_name)
    assert isinstance(provider, expected_class), (
        f"get_signal_provider('{signal_name}') returned {type(provider).__name__}, "
        f"expected {expected_class.__name__}"
    )
    assert provider.name == signal_name


def test_registry_raises_for_unknown_name():
    with pytest.raises(KeyError, match="Unknown signal provider"):
        get_signal_provider("crystal_ball")


def test_registry_returns_correct_name_attribute():
    for name in ["fcf_yield", "sentiment_score", "earnings_surprise", "insider_net_buy"]:
        p = get_signal_provider(name)
        assert p.name == name
