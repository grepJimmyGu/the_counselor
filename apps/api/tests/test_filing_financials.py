"""Quarterly filing analysis: figures, trends and flags from SEC XBRL data.

Two kinds of test:

  - Against NVIDIA's real company facts (tests/fixtures/sec_companyfacts_nvda.json,
    the SEC's own data trimmed to the tags and periods this reader uses,
    fetched 2026-11-17). These pin the numbers to the filing: if a quarter
    comes out differently from what the 10-Q says, the reader is wrong.
  - Against small synthetic filings, for the rules that decide what is
    flagged and what is left alone.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest

from app.services import filing_financials as ff
from app.services import sec_company_facts as sec

TODAY = date(2026, 11, 17)
NVDA = json.loads((Path(__file__).parent / "fixtures" / "sec_companyfacts_nvda.json").read_text())


@pytest.fixture(scope="module")
def nvda() -> ff.FilingAnalysis:
    return ff.analyse(NVDA, "NVDA", "0001045810", today=TODAY)


# ── Real data: the numbers are the filing's ─────────────────────────────────


def test_latest_quarter_is_labelled_from_its_own_filing(nvda):
    latest = nvda.quarters[-1]
    assert latest.label == "Q2 FY2027"
    assert latest.period_end == date(2026, 7, 26)
    assert latest.form == "10-Q"
    assert latest.filed == date(2026, 8, 26)
    assert latest.filing_url == (
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075/0001045810-26-000075-index.htm"
    )
    assert [q.label for q in nvda.quarters] == [
        "Q2 FY2025", "Q3 FY2025", "Q4 FY2025", "Q1 FY2026", "Q2 FY2026",
        "Q3 FY2026", "Q4 FY2026", "Q1 FY2027", "Q2 FY2027",
    ]


def test_reported_quarter_figures_match_the_10q(nvda):
    q = nvda.quarters[-1]
    assert q.get("revenue") == 96_221_000_000
    assert q.get("gross_profit") == 72_142_000_000
    assert q.get("operating_income") == 63_734_000_000
    assert q.get("net_income") == 59_688_000_000
    assert q.get("eps_diluted") == 2.46
    assert q.get("receivables") == 63_059_000_000
    assert q.get("inventory") == 31_575_000_000
    assert q.get("gross_margin") == pytest.approx(0.7498, abs=1e-4)
    assert q.get("operating_margin") == pytest.approx(0.6624, abs=1e-4)


def test_cash_flow_quarter_is_year_to_date_less_the_quarter_before(nvda):
    """10-Qs give cash flow for the year so far. Q2 = six months − Q1."""
    q = nvda.quarters[-1]
    assert q.get("operating_cash_flow") == 74_421_000_000 - 50_344_000_000
    # And Q1, which the filing does state directly, is untouched.
    assert nvda.quarters[-2].get("operating_cash_flow") == 50_344_000_000


def test_fourth_quarter_is_the_year_less_nine_months(nvda):
    """The 10-K reports the year, never the fourth quarter."""
    q4 = next(q for q in nvda.quarters if q.label == "Q4 FY2026")
    assert q4.form == "10-K"
    assert q4.get("revenue") == 215_938_000_000 - 147_811_000_000
    assert q4.get("operating_cash_flow") == 102_718_000_000 - 66_530_000_000


def test_share_count_is_never_a_difference_of_averages(nvda):
    """Regression: 'year − nine months' of a weighted share count came out at
    about zero. The fourth quarter is four times the year's average less
    the other three, and the series stays smooth across it."""
    shares = [q.get("diluted_shares") for q in nvda.quarters]
    assert all(value is not None and value > 2e10 for value in shares)
    steps = [abs(b / a - 1) for a, b in zip(shares, shares[1:])]
    assert max(steps) < 0.02


def test_investments_follow_a_change_of_tag(nvda):
    """NVIDIA moved its marketable securities from one XBRL tag to another in
    FY2026. Reading only the old tag made cash and investments fall by
    $50B overnight and produced a false 'moved to net debt' flag."""
    values = [q.get("cash_and_investments") for q in nvda.quarters]
    assert all(value is not None for value in values)
    assert nvda.quarters[-1].get("cash_and_investments") > 50e9
    assert not any(f.title == "Moved to net debt" for f in nvda.findings)


def test_findings_on_the_real_quarter(nvda):
    by_title = {finding.title: finding for finding in nvda.findings}
    receivables = by_title["Receivables grew faster than sales"]
    assert receivables.severity == "watch"
    assert "$63.1B" in receivables.detail and "from 45 to 60 days" in receivables.detail

    cash = by_title["Profit ran ahead of cash"]
    assert "$24.1B" in cash.detail and "$59.7B" in cash.detail and "40 cents" in cash.detail

    growth = by_title["Revenue growth sped up"]
    assert growth.severity == "good"
    assert "+105.9% from a year ago" in growth.detail and "+17.9% from last quarter" in growth.detail

    # Watch items lead; plain information trails.
    severities = [finding.severity for finding in nvda.findings]
    assert severities == sorted(severities, key=["watch", "good", "info"].index)


def test_metrics_carry_their_change_and_a_fact_about_the_run(nvda):
    metrics = {metric.key: metric for metric in nvda.metrics}
    revenue = metrics["revenue"]
    assert len(revenue.values) == 9 and revenue.latest == 96_221_000_000
    assert revenue.change_kind == "relative"
    assert revenue.change_qoq == pytest.approx(0.179, abs=1e-3)
    assert revenue.change_yoy == pytest.approx(1.059, abs=1e-3)
    assert revenue.note == "Highest of the last 9 quarters."

    margin = metrics["gross_margin"]
    assert margin.change_kind == "points"
    assert margin.change_yoy == pytest.approx(0.026, abs=1e-3)

    dso = metrics["days_sales_outstanding"]
    assert dso.better == "down" and dso.change_kind == "absolute"
    assert dso.change_qoq == pytest.approx(14.2, abs=0.2)
    assert metrics["net_cash"].change_kind == "absolute"


def test_no_finding_or_note_makes_a_forecast(nvda):
    """Facts, not assumptions: nothing says what will happen or what to do."""
    import re

    banned = re.compile(r"\b(will|should|expect\w*|likely|forecast\w*|recommend\w*|buy|sell)\b")
    for text in [f.detail for f in nvda.findings] + [f.title for f in nvda.findings] + [m.note or "" for m in nvda.metrics]:
        assert not banned.search(text.lower()), text


# ── Synthetic filings: what is flagged, and what is left alone ──────────────


def _fact(start, end, val, form="10-Q", filed=None, fy=2026, fp="Q1", accn="0000000001-26-000001"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed or end, "fy": fy, "fp": fp, "accn": accn}


QUARTER_ENDS = [
    ("2024-07-01", "2024-09-30"), ("2024-10-01", "2024-12-31"), ("2025-01-01", "2025-03-31"),
    ("2025-04-01", "2025-06-30"), ("2025-07-01", "2025-09-30"), ("2025-10-01", "2025-12-31"),
    ("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30"),
]


def _company(**series) -> dict:
    """A filer whose every figure is reported per quarter. `series` maps an
    XBRL tag to nine values, oldest first; instants take the period end."""
    instants = {tag for tags in ff.INSTANT_TAGS.values() for tag in tags}
    us_gaap = {}
    for tag, values in series.items():
        rows = []
        for (start, end), value in zip(QUARTER_ENDS, values):
            if value is None:
                continue
            rows.append(_fact(None if tag in instants else start, end, value))
        us_gaap[tag] = {"units": {"USD": rows}}
    return {"entityName": "Test Co", "facts": {"us-gaap": us_gaap}}


def _analyse(**series) -> ff.FilingAnalysis:
    series.setdefault("Revenues", [100.0e6] * 9)
    return ff.analyse(_company(**series), "TEST", "0000000001", today=date(2026, 11, 1))


def _titles(analysis: ff.FilingAnalysis) -> set:
    return {finding.title for finding in analysis.findings}


def test_a_seasonal_receivables_build_is_not_flagged():
    """Regression: Apple's receivables jump every September quarter. Against
    the quarter before it looks like a build; against the same quarter a
    year earlier it is flat."""
    seasonal = [20e6, 20e6, 20e6, 20e6, 35e6, 20e6, 20e6, 20e6, 35e6]
    assert "Receivables grew faster than sales" not in _titles(_analyse(AccountsReceivableNetCurrent=seasonal))

    building = [20e6] * 8 + [35e6]
    assert "Receivables grew faster than sales" in _titles(_analyse(AccountsReceivableNetCurrent=building))


def test_a_line_that_stops_being_tagged_makes_the_total_unknown_not_smaller():
    cash = [10e6] * 9
    securities = [50e6] * 7 + [None, None]
    analysis = _analyse(CashAndCashEquivalentsAtCarryingValue=cash, MarketableSecuritiesCurrent=securities)
    assert analysis.quarters[-3].get("cash_and_investments") == 60e6
    assert analysis.quarters[-1].get("cash_and_investments") is None
    assert "Moved to net debt" not in _titles(analysis)


def test_total_debt_is_not_counted_twice():
    """`LongTermDebt` already includes the part due within a year."""
    analysis = _analyse(
        LongTermDebt=[100e6] * 9, LongTermDebtNoncurrent=[90e6] * 9, LongTermDebtCurrent=[10e6] * 9,
    )
    assert analysis.quarters[-1].get("debt") == 100e6
    halves = _analyse(LongTermDebtNoncurrent=[90e6] * 9, LongTermDebtCurrent=[10e6] * 9)
    assert halves.quarters[-1].get("debt") == 100e6
    # A company with no debt tags at all has none; it is not "unknown".
    assert _analyse().quarters[-1].get("debt") == 0


def test_margin_and_cash_flags_fire_on_their_thresholds():
    steady = _analyse(GrossProfit=[40e6] * 9, NetIncomeLoss=[10e6] * 9, NetCashProvidedByUsedInOperatingActivities=[10e6] * 9)
    assert not {"Gross margin narrowed", "Gross margin widened", "Profit ran ahead of cash"} & _titles(steady)

    squeezed = _analyse(
        GrossProfit=[40e6] * 8 + [37e6], NetIncomeLoss=[10e6] * 9,
        NetCashProvidedByUsedInOperatingActivities=[10e6] * 8 + [5e6],
    )
    assert {"Gross margin narrowed", "Profit ran ahead of cash"} <= _titles(squeezed)


def test_share_count_flags_both_directions():
    shares = "WeightedAverageNumberOfDilutedSharesOutstanding"
    assert "Share count fell" in _titles(_analyse(**{shares: [100e6] * 5 + [98e6] * 4}))
    assert "Share count rose" in _titles(_analyse(**{shares: [100e6] * 5 + [103e6] * 4}))
    assert not {"Share count fell", "Share count rose"} & _titles(_analyse(**{shares: [100e6] * 9}))


def test_a_tag_change_keeps_one_revenue_series():
    old = [100e6] * 5 + [None] * 4
    new = [None] * 5 + [110e6] * 4
    analysis = ff.analyse(
        _company(Revenues=old, RevenueFromContractWithCustomerExcludingAssessedTax=new),
        "TEST", "0000000001", today=date(2026, 11, 1),
    )
    assert [q.get("revenue") for q in analysis.quarters] == [100e6] * 5 + [110e6] * 4


def test_the_most_recently_filed_value_wins():
    """A later filing restates its comparatives — after a stock split, for
    one. The restated figure is the one consistent with the newer quarters."""
    facts = _company(Revenues=[100e6] * 9)
    rows = facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
    rows.append(_fact("2025-07-01", "2025-09-30", 95e6, filed="2026-10-20"))
    analysis = ff.analyse(facts, "TEST", "0000000001", today=date(2026, 11, 1))
    assert analysis.quarters[4].get("revenue") == 95e6
    # The label still comes from the filing that first reported the period.
    assert analysis.quarters[4].filed == date(2025, 9, 30)


def test_stale_and_missing_data_is_refused_rather_than_shown_as_current():
    with pytest.raises(ff.NoQuarterlyData, match="too old"):
        ff.analyse(_company(Revenues=[100e6] * 9), "TEST", "0000000001", today=date(2027, 9, 1))
    with pytest.raises(ff.NoQuarterlyData):
        ff.analyse({"facts": {"ifrs-full": {}}}, "TSM", "0001046179", today=TODAY)
    with pytest.raises(ff.NoQuarterlyData):
        ff.analyse(_company(Revenues=[100e6] + [None] * 8), "TEST", "0000000001", today=date(2024, 11, 1))


def test_run_note_states_streaks_and_extremes_only():
    assert ff._run_note([1, 2, 3, 4, 5]) == "Highest of the last 5 quarters."
    assert ff._run_note([5, 4, 3, 2, 1]) == "Lowest of the last 5 quarters."
    assert ff._run_note([9, 1, 2, 3, 4]) == "Up 3 quarters in a row."
    assert ff._run_note([3, 5, 2, 4, 3]) is None
    assert ff._run_note([1, 2, None]) is None


# ── The endpoint ─────────────────────────────────────────────────────────────


@pytest.fixture
def sec_stub(monkeypatch):
    calls = []

    async def fake_get_json(url: str):
        calls.append(url)
        if url.endswith("company_tickers.json"):
            return {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
                    "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE"}}
        if "CIK0001045810" in url:
            return NVDA
        return None

    monkeypatch.setattr(sec, "_get_json", fake_get_json)
    monkeypatch.setattr(sec, "_tickers", {})
    monkeypatch.setattr(sec, "_analyses", {})
    monkeypatch.setattr(ff, "MAX_LATEST_AGE_DAYS", 10_000)   # the fixture does not age
    return calls


def test_endpoint_returns_the_analysis_and_caches_it(sec_stub):
    from app.api.routes.filings import get_company_filings

    response = asyncio.run(get_company_filings("nvda"))
    assert response.symbol == "NVDA" and response.cik == "0001045810"
    assert response.latest.label == "Q2 FY2027" and response.latest == response.quarters[-1]
    assert response.latest.values["revenue"] == 96_221_000_000
    assert "purchase_commitments" not in response.latest.values      # absent, not null
    assert {metric.group for metric in response.metrics} == {
        "Growth", "Profitability", "Cash", "Balance sheet", "Shareholders",
    }
    assert response.findings[0].severity == "watch"

    asyncio.run(get_company_filings("NVDA"))
    assert len(sec_stub) == 2, "the second request must be served from cache"


def test_endpoint_errors_say_what_is_wrong(sec_stub):
    from fastapi import HTTPException

    from app.api.routes.filings import get_company_filings

    with pytest.raises(HTTPException) as unknown:
        asyncio.run(get_company_filings("ZZZZ"))
    assert unknown.value.status_code == 404 and "not in the SEC's list" in unknown.value.detail

    # A class share is looked up the way the SEC lists it; no facts → 404.
    with pytest.raises(HTTPException) as no_facts:
        asyncio.run(get_company_filings("BRK.B"))
    assert no_facts.value.status_code == 404
    assert any("CIK0001067983" in url for url in sec_stub)


def test_an_unreachable_sec_is_a_502_not_a_404(monkeypatch):
    from fastapi import HTTPException

    from app.api.routes.filings import get_company_filings

    async def down(url: str):
        raise sec.SecUnavailable("timeout")

    monkeypatch.setattr(sec, "_get_json", down)
    monkeypatch.setattr(sec, "_tickers", {})
    monkeypatch.setattr(sec, "_analyses", {})
    with pytest.raises(HTTPException) as failure:
        asyncio.run(get_company_filings("NVDA"))
    assert failure.value.status_code == 502
