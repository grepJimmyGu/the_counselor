"""Quarterly financials, metric trends and flags from SEC 10-Q / 10-K data.

Input is the SEC's own XBRL "company facts" for one company: every number
the company tagged in a filing, with the period it covers, the form it came
from, and the date it was filed. Output is what a careful reader would pull
out of the latest quarterly report:

  - the last several quarters as one table (income, cash flow, balance sheet),
    each quarter linked to the filing it came from;
  - each key metric as a series, with its change from last quarter and from
    a year ago, and plain facts about it ("highest in 8 quarters");
  - findings: the specific things that moved enough to be worth a sentence.

EVERYTHING HERE IS ARITHMETIC ON REPORTED NUMBERS. Nothing is forecast, and
no finding says what a number will do next or what an investor should do.
A finding states what was reported and what it mechanically means (for
example, receivables growing faster than sales means a larger share of the
quarter's revenue has not been collected) — never why management let it
happen. Thresholds decide what is worth flagging; they are named constants
below so they can be argued with.

THREE THINGS ABOUT THE SOURCE THAT SHAPE THE CODE

1. Quarters are not all reported as quarters. Income statements give the
   three-month figure for Q1–Q3 but only the full year in the 10-K, and cash
   flow statements are year-to-date in every 10-Q. So a quarter is taken
   directly when the filing has it, and otherwise derived by subtracting the
   previous year-to-date figure with the same start date (Q4 = year − nine
   months).

2. Companies change tags. Revenue may be `Revenues` one year and
   `RevenueFromContractWithCustomerExcludingAssessedTax` the next. Each
   concept is a list of tags pooled together; when two filings report the
   same period, the most recently filed value wins — which is also what
   keeps per-share figures consistent across a stock split, because later
   filings restate their comparatives.

3. `fy` / `fp` on a fact describe the FILING, not the period: a comparative
   in the Q2 FY2027 10-Q carries fy=2027, fp=Q2 even though it is last
   year's number. A quarter is labelled from the earliest filing that
   reported that period end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

# ── What to read ─────────────────────────────────────────────────────────────

# Flows: reported over a period. Tags in order of preference: for each
# quarter the first tag that has a value is used, so a company that changes
# tag mid-history still gives one unbroken series, and two tags that mean
# slightly different things are never mixed within a quarter.
FLOW_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenuesNetOfInterestExpense",          # banks and brokers
    ],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "research_and_development": ["ResearchAndDevelopmentExpense"],
    "selling_general_admin": ["SellingGeneralAndAdministrativeExpense"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capital_expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "dividends": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "stock_compensation": ["ShareBasedCompensation"],
}

# Stocks: reported at a date.
INSTANT_TAGS: dict[str, list[str]] = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "short_term_investments": [
        "MarketableSecuritiesCurrent", "DebtSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "ShortTermInvestments",
    ],
    "long_term_investments": [
        "MarketableSecuritiesNoncurrent", "DebtSecuritiesNoncurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent", "LongTermInvestments",
    ],
    "receivables": ["AccountsReceivableNetCurrent"],
    "inventory": ["InventoryNet"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    # `LongTermDebt` is the whole of it, current portion included. Only when
    # a company does not tag that are the two halves added together.
    "term_debt": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"],
    "term_debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "term_debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "short_term_borrowings": ["CommercialPaper", "ShortTermBorrowings"],
    "equity": ["StockholdersEquity"],
    "deferred_revenue": ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"],
    "purchase_commitments": [
        "PurchaseObligation", "UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount",
    ],
}

# Averages and per-share figures cannot be subtracted to get a quarter:
# "year minus nine months" of a weighted share count is not a share count.
_NOT_ADDITIVE = {"diluted_shares"}

_PERIODIC_FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}
_QUARTER_DAYS = (75, 105)
_MAX_CUMULATIVE_DAYS = 380
# A dropped investment line makes "cash and investments" unknown only if it
# was ever at least this share of the total.
INVESTMENT_PART_MATERIAL = 0.05
QUARTERS_RETURNED = 9          # the latest quarter, a year before it, and the run between
# A "latest quarter" older than this is not the latest: the company changed
# how it tags revenue, or stopped filing. Better no analysis than a stale one
# presented as current.
MAX_LATEST_AGE_DAYS = 200

# ── When something is worth a sentence ───────────────────────────────────────
GROWTH_SHIFT_POINTS = 0.05     # year-over-year growth moved by 5 points
MARGIN_SHIFT_POINTS = 0.01     # a margin moved by 1 point
RECEIVABLES_GAP_POINTS = 0.10  # receivables outgrew revenue by 10 points in the quarter
DAYS_SHIFT = 5.0               # days-sales-outstanding moved by 5 days
INVENTORY_DAYS_SHIFT = 10.0
CASH_CONVERSION_FLOOR = 0.80   # operating cash flow below 80% of net income
SHARE_COUNT_BUYBACK = -0.01    # diluted shares down 1% in a year
SHARE_COUNT_DILUTION = 0.02    # ... or up 2%
DEBT_JUMP = 0.20               # debt up 20% in the quarter
STOCK_COMP_HEAVY = 0.10        # stock compensation above 10% of revenue
CAPEX_JUMP = 0.50              # capital spending up 50% from a year ago


@dataclass
class Quarter:
    period_end: date
    label: str                       # "Q2 FY2027"
    fiscal_year: Optional[int]
    fiscal_period: Optional[str]     # "Q1" … "Q4"
    form: Optional[str]              # "10-Q" | "10-K"
    filed: Optional[date]
    filing_url: Optional[str]
    days: int = 91
    values: dict[str, Optional[float]] = field(default_factory=dict)

    def get(self, key: str) -> Optional[float]:
        return self.values.get(key)


@dataclass
class MetricTrend:
    key: str
    label: str
    group: str
    unit: str            # usd | per_share | shares | percent | ratio | days
    better: str          # up | down | none — which direction is the good one
    values: list[Optional[float]]    # one per quarter, oldest first
    latest: Optional[float]
    change_qoq: Optional[float]      # relative for money/shares, points or days otherwise
    change_yoy: Optional[float]
    change_kind: str     # relative | points | absolute
    note: Optional[str]  # a fact about the run: a streak, a high, a low


@dataclass
class Finding:
    severity: str        # good | watch | info
    category: str        # growth | margins | cash | balance_sheet | shareholders
    title: str
    detail: str
    metrics: list[str]


@dataclass
class FilingAnalysis:
    symbol: str
    company_name: str
    cik: str
    quarters: list[Quarter]          # oldest first
    metrics: list[MetricTrend]
    findings: list[Finding]


# ── Reading the facts ────────────────────────────────────────────────────────

def _day(text: Optional[str]) -> Optional[date]:
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _pool(us_gaap: dict, tags: list[str]) -> list[dict]:
    """Every fact for a concept, across its tags, in whichever unit it uses."""
    facts: list[dict] = []
    for tag in tags:
        for rows in (us_gaap.get(tag) or {}).get("units", {}).values():
            facts.extend(rows)
    return facts


def _latest_by_period(facts: list[dict]) -> dict[tuple[Optional[date], date], dict]:
    """One fact per (start, end): the most recently filed."""
    best: dict[tuple[Optional[date], date], dict] = {}
    for fact in facts:
        end = _day(fact.get("end"))
        if end is None or fact.get("val") is None:
            continue
        key = (_day(fact.get("start")), end)
        kept = best.get(key)
        if kept is None or (fact.get("filed") or "") >= (kept.get("filed") or ""):
            best[key] = fact
    return best


def quarterly_values(facts: list[dict], derive: bool = True) -> dict[date, float]:
    """Three-month values by period end, reported or derived (see module doc).

    With `derive=False` only figures the filing states for the quarter are
    returned — for concepts that cannot be subtracted."""
    periods = _latest_by_period(facts)
    spans = {key: float(fact["val"]) for key, fact in periods.items() if key[0] is not None}
    result: dict[date, float] = {}

    for (start, end), value in spans.items():
        if _QUARTER_DAYS[0] <= (end - start).days <= _QUARTER_DAYS[1]:
            result[end] = value

    if not derive:
        # An average over the year is close to the mean of the four quarterly
        # averages, so the quarter the 10-K leaves out is four times the
        # year's figure less the other three.
        for (start, end), value in spans.items():
            if end in result or not 350 <= (end - start).days <= _MAX_CUMULATIVE_DAYS:
                continue
            others = [result[other] for other in result if start < other < end]
            if len(others) == 3:
                result[end] = 4 * value - sum(others)
        return result

    # Year-to-date and full-year figures: subtract the previous year-to-date
    # figure that starts on the same day and ends one quarter earlier.
    cumulative = sorted(
        (key for key in spans if _QUARTER_DAYS[1] < (key[1] - key[0]).days <= _MAX_CUMULATIVE_DAYS),
        key=lambda key: (key[1], (key[1] - key[0]).days),
    )
    for start, end in cumulative:
        if end in result:
            continue
        previous = [
            other for other in spans
            if other[0] == start and _QUARTER_DAYS[0] <= (end - other[1]).days <= _QUARTER_DAYS[1]
        ]
        if previous:
            result[end] = spans[(start, end)] - spans[max(previous, key=lambda key: key[1])]
    return result


def instant_values(facts: list[dict]) -> dict[date, float]:
    return {end: float(fact["val"]) for (start, end), fact in _latest_by_period(facts).items()}


def _by_priority(us_gaap: dict, tags: list[str], reader) -> dict[date, float]:
    """One series from several tags: per date, the first tag that has a value."""
    merged: dict[date, float] = {}
    for tag in tags:
        for end, value in reader(_pool(us_gaap, [tag])).items():
            merged.setdefault(end, value)
    return merged


def _period_identity(facts: list[dict], end: date) -> Optional[dict]:
    """The earliest periodic filing that reported this period end."""
    candidates = [
        fact for fact in facts
        if _day(fact.get("end")) == end and fact.get("form") in _PERIODIC_FORMS and fact.get("filed")
    ]
    return min(candidates, key=lambda fact: fact["filed"]) if candidates else None


def _filing_url(cik: str, accession: Optional[str]) -> Optional[str]:
    if not accession:
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"


def build_quarters(company_facts: dict, cik: str) -> list[Quarter]:
    us_gaap = (company_facts.get("facts") or {}).get("us-gaap") or {}
    revenue_facts = _pool(us_gaap, FLOW_TAGS["revenue"])
    revenue = quarterly_values(revenue_facts)
    if not revenue:
        return []

    flows = {
        key: _by_priority(
            us_gaap, tags, lambda facts, key=key: quarterly_values(facts, derive=key not in _NOT_ADDITIVE)
        )
        for key, tags in FLOW_TAGS.items()
    }
    instants = {key: _by_priority(us_gaap, tags, instant_values) for key, tags in INSTANT_TAGS.items()}
    revenue = flows["revenue"]

    # Quarter ends must be about a quarter apart: a stray short period (a
    # stub year, a restated month) is not a quarter of this series.
    ends = sorted(revenue)
    kept = [ends[-1]]
    for end in reversed(ends[:-1]):
        if _QUARTER_DAYS[0] <= (kept[-1] - end).days <= _QUARTER_DAYS[1]:
            kept.append(end)
        if len(kept) == QUARTERS_RETURNED:
            break
    kept.reverse()

    quarters: list[Quarter] = []
    for index, end in enumerate(kept):
        identity = _period_identity(revenue_facts, end)
        fiscal_year = identity.get("fy") if identity else None
        fiscal_period = identity.get("fp") if identity else None
        if fiscal_period == "FY":
            fiscal_period = "Q4"
        label = f"{fiscal_period} FY{fiscal_year}" if fiscal_period and fiscal_year else end.isoformat()
        values: dict[str, Optional[float]] = {key: series.get(end) for key, series in flows.items()}
        values.update({key: series.get(end) for key, series in instants.items()})
        quarters.append(Quarter(
            period_end=end, label=label, fiscal_year=fiscal_year, fiscal_period=fiscal_period,
            form=(identity or {}).get("form"), filed=_day((identity or {}).get("filed")),
            filing_url=_filing_url(cik, (identity or {}).get("accn")),
            days=(end - kept[index - 1]).days if index else 91,
            values=values,
        ))
    # An investment line a company tagged in some quarters and not others is
    # unknown in the gaps, not zero: adding it up as zero would invent a fall
    # in cash out of a change of tag (NVIDIA's marketable securities did
    # this). Unless the line was too small to matter: Alphabet stopped
    # tagging $0.3B of long-term investments in 2025, and calling that
    # "unknown" blanked a $265B cash figure. A line counts only if it was
    # once a material share of cash and investments.
    sometimes = {
        key for key in _INVESTMENT_PARTS
        if any(_is_material_investment(quarter, key) for quarter in quarters)
    }
    for quarter in quarters:
        _derive(quarter, frozenset(sometimes))
    return quarters


_INVESTMENT_PARTS = ("short_term_investments", "long_term_investments")


def _is_material_investment(quarter: Quarter, key: str) -> bool:
    """Whether `key` was at least INVESTMENT_PART_MATERIAL of the quarter's
    cash plus tagged investments."""
    value = quarter.get(key)
    if value is None:
        return False
    whole = sum(quarter.get(part) or 0 for part in ("cash",) + _INVESTMENT_PARTS)
    return whole <= 0 or value / whole >= INVESTMENT_PART_MATERIAL


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _derive(q: Quarter, sometimes: frozenset = frozenset()) -> None:
    """Figures that are arithmetic on what the filing reports.

    `sometimes` names balance-sheet parts the company reports in at least
    one quarter of the window; a quarter missing one of them has an unknown
    total rather than a smaller one.
    """
    v = q.values
    revenue = v.get("revenue")
    if v.get("gross_profit") is None and revenue is not None and v.get("cost_of_revenue") is not None:
        v["gross_profit"] = revenue - v["cost_of_revenue"]
    v["gross_margin"] = _ratio(v.get("gross_profit"), revenue)
    v["operating_margin"] = _ratio(v.get("operating_income"), revenue)
    v["net_margin"] = _ratio(v.get("net_income"), revenue)
    if v.get("eps_diluted") is not None:
        v["eps_diluted"] = round(v["eps_diluted"], 2)

    rd, sga = v.get("research_and_development"), v.get("selling_general_admin")
    v["operating_expenses"] = (rd or 0) + (sga or 0) if (rd is not None or sga is not None) else None

    cfo, capex = v.get("operating_cash_flow"), v.get("capital_expenditure")
    v["free_cash_flow"] = cfo - capex if cfo is not None and capex is not None else None
    v["free_cash_flow_margin"] = _ratio(v.get("free_cash_flow"), revenue)
    net_income = v.get("net_income")
    v["cash_conversion"] = _ratio(cfo, net_income) if net_income and net_income > 0 else None

    def total(parts: list[str], required: Optional[str] = None) -> Optional[float]:
        if required is not None and v.get(required) is None:
            return None
        if any(part in sometimes and v.get(part) is None for part in parts):
            return None
        present = [v[part] for part in parts if v.get(part) is not None]
        return sum(present) if present or required is None else None

    investments = total(["short_term_investments", "long_term_investments"])
    cash = v.get("cash")
    v["cash_and_investments"] = cash + (investments or 0) if cash is not None and investments is not None else None

    # Debt: the tagged total when there is one, otherwise the long-term part
    # plus whatever falls due within a year. A missing current portion or
    # missing commercial paper is read as none outstanding — companies stop
    # tagging a line when it reaches zero.
    if v.get("term_debt") is not None:
        term_debt: Optional[float] = v["term_debt"]
    elif v.get("term_debt_noncurrent") is not None:
        term_debt = v["term_debt_noncurrent"] + (v.get("term_debt_current") or 0)
    elif v.get("term_debt_current") is not None:
        term_debt = v["term_debt_current"]
    else:
        # No debt tag is not a filed zero. Berkshire Hathaway reports its
        # notes payable under its own tags, and "none tagged means none
        # owed" gave it $0 of debt. Unknown, and net cash with it.
        term_debt = None
    v["debt"] = term_debt + (v.get("short_term_borrowings") or 0) if term_debt is not None else None
    v["net_cash"] = (
        v["cash_and_investments"] - v["debt"]
        if v["cash_and_investments"] is not None and v["debt"] is not None else None
    )

    daily_sales = _ratio(revenue, q.days)
    v["days_sales_outstanding"] = _ratio(v.get("receivables"), daily_sales)
    daily_cost = _ratio(v.get("cost_of_revenue"), q.days)
    v["days_inventory"] = _ratio(v.get("inventory"), daily_cost)
    v["stock_compensation_share"] = _ratio(v.get("stock_compensation"), revenue)

    buybacks, dividends = v.get("buybacks"), v.get("dividends")
    v["returned_to_shareholders"] = (
        (buybacks or 0) + (dividends or 0) if (buybacks is not None or dividends is not None) else None
    )


def _add_growth(quarters: list[Quarter]) -> None:
    for index, quarter in enumerate(quarters):
        year_ago = quarters[index - 4] if index >= 4 else None
        base = year_ago.get("revenue") if year_ago else None
        now = quarter.get("revenue")
        quarter.values["revenue_growth_yoy"] = now / base - 1 if now is not None and base and base > 0 else None


# ── Metric trends ────────────────────────────────────────────────────────────

# key, label, group, unit, which direction is the good one
METRICS: list[tuple[str, str, str, str, str]] = [
    ("revenue", "Revenue", "Growth", "usd", "up"),
    ("revenue_growth_yoy", "Revenue growth, year over year", "Growth", "percent", "up"),
    ("net_income", "Net income", "Growth", "usd", "up"),
    ("eps_diluted", "Earnings per share, diluted", "Growth", "per_share", "up"),
    ("gross_margin", "Gross margin", "Profitability", "percent", "up"),
    ("operating_margin", "Operating margin", "Profitability", "percent", "up"),
    ("net_margin", "Net margin", "Profitability", "percent", "up"),
    ("operating_expenses", "R&D and SG&A", "Profitability", "usd", "none"),
    ("operating_cash_flow", "Operating cash flow", "Cash", "usd", "up"),
    ("capital_expenditure", "Capital spending", "Cash", "usd", "none"),
    ("free_cash_flow", "Free cash flow", "Cash", "usd", "up"),
    ("free_cash_flow_margin", "Free cash flow margin", "Cash", "percent", "up"),
    ("cash_conversion", "Operating cash flow ÷ net income", "Cash", "ratio", "up"),
    ("cash_and_investments", "Cash and investments", "Balance sheet", "usd", "up"),
    ("debt", "Debt", "Balance sheet", "usd", "down"),
    ("net_cash", "Net cash (cash less debt)", "Balance sheet", "usd", "up"),
    ("receivables", "Receivables", "Balance sheet", "usd", "none"),
    ("days_sales_outstanding", "Days of sales uncollected", "Balance sheet", "days", "down"),
    ("inventory", "Inventory", "Balance sheet", "usd", "none"),
    ("days_inventory", "Days of inventory", "Balance sheet", "days", "down"),
    ("deferred_revenue", "Deferred revenue", "Balance sheet", "usd", "up"),
    ("diluted_shares", "Diluted shares", "Shareholders", "shares", "down"),
    ("returned_to_shareholders", "Buybacks and dividends", "Shareholders", "usd", "none"),
    ("stock_compensation_share", "Stock compensation ÷ revenue", "Shareholders", "percent", "down"),
]


def _change(now: Optional[float], then: Optional[float], kind: str) -> Optional[float]:
    if now is None or then is None:
        return None
    if kind == "relative":
        # A base at or below zero has no meaningful percentage change.
        return now / then - 1 if then > 0 else None
    return now - then


def _run_note(values: list[Optional[float]]) -> Optional[str]:
    """A fact about the series: an extreme, or an unbroken run."""
    known = [value for value in values if value is not None]
    if len(known) < 4 or values[-1] is None:
        return None
    latest = values[-1]
    if latest == max(known) and known.count(latest) == 1:
        return f"Highest of the last {len(known)} quarters."
    if latest == min(known) and known.count(latest) == 1:
        return f"Lowest of the last {len(known)} quarters."
    run, direction = 0, 0
    for later, earlier in zip(reversed(values), reversed(values[:-1])):
        if later is None or earlier is None or later == earlier:
            break
        step = 1 if later > earlier else -1
        if direction and step != direction:
            break
        direction, run = step, run + 1
    if run >= 3:
        return f"{'Up' if direction > 0 else 'Down'} {run} quarters in a row."
    return None


def build_metrics(quarters: list[Quarter]) -> list[MetricTrend]:
    trends: list[MetricTrend] = []
    for key, label, group, unit, better in METRICS:
        values = [quarter.get(key) for quarter in quarters]
        if all(value is None for value in values):
            continue
        kind = {"percent": "points", "ratio": "absolute", "days": "absolute"}.get(unit, "relative")
        if key == "net_cash":
            kind = "absolute"   # it crosses zero, where a percentage means nothing
        latest = values[-1]
        trends.append(MetricTrend(
            key=key, label=label, group=group, unit=unit, better=better, values=values, latest=latest,
            change_qoq=_change(latest, values[-2] if len(values) >= 2 else None, kind),
            change_yoy=_change(latest, values[-5] if len(values) >= 5 else None, kind),
            change_kind=kind, note=_run_note(values),
        ))
    return trends


# ── Findings ─────────────────────────────────────────────────────────────────

def _money(value: float) -> str:
    sign, amount = ("-" if value < 0 else ""), abs(value)
    if amount >= 1e9:
        return f"{sign}${amount / 1e9:.1f}B"
    if amount >= 1e6:
        return f"{sign}${amount / 1e6:.0f}M"
    return f"{sign}${amount:,.0f}"


def _pct(value: float, signed: bool = False) -> str:
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def _points(value: float) -> str:
    return f"{abs(value) * 100:.1f} point{'s' if abs(value) * 100 != 1 else ''}"


def _moved(value: float) -> str:
    return "up" if value > 0 else "down"


def build_findings(quarters: list[Quarter]) -> list[Finding]:
    if len(quarters) < 2:
        return []
    now, prior = quarters[-1], quarters[-2]
    year_ago = quarters[-5] if len(quarters) >= 5 else None
    findings: list[Finding] = []

    def rel(key: str, base: Optional[Quarter]) -> Optional[float]:
        return _change(now.get(key), base.get(key) if base else None, "relative")

    def diff(key: str, base: Optional[Quarter]) -> Optional[float]:
        return _change(now.get(key), base.get(key) if base else None, "points")

    # Revenue: level, and whether year-over-year growth is speeding up.
    revenue = now.get("revenue")
    revenue_qoq, revenue_yoy = rel("revenue", prior), rel("revenue", year_ago)
    if revenue is not None and (revenue_qoq is not None or revenue_yoy is not None):
        parts = []
        if revenue_yoy is not None:
            parts.append(f"{_pct(revenue_yoy, True)} from a year ago")
        if revenue_qoq is not None:
            parts.append(f"{_pct(revenue_qoq, True)} from last quarter")
        detail = f"Revenue was {_money(revenue)}, {' and '.join(parts)}."
        severity = "info"
        growth_now, growth_before = now.get("revenue_growth_yoy"), prior.get("revenue_growth_yoy")
        if growth_now is not None and growth_before is not None:
            shift = growth_now - growth_before
            if abs(shift) >= GROWTH_SHIFT_POINTS:
                verb = "sped up" if shift > 0 else "slowed"
                detail += f" Year-over-year growth {verb} from {_pct(growth_before)} to {_pct(growth_now)}."
                severity = "good" if shift > 0 and growth_now > 0 else "watch"
        if revenue_yoy is not None and revenue_yoy < 0:
            severity = "watch"
        fell = (revenue_yoy if revenue_yoy is not None else revenue_qoq or 0) < 0
        if fell:
            title = "Revenue fell"
        elif severity == "watch":
            title = "Revenue growth slowed"
        elif severity == "good":
            title = "Revenue growth sped up"
        else:
            title = "Revenue grew"
        findings.append(Finding(severity, "growth", title, detail, ["revenue", "revenue_growth_yoy"]))

    # Gross margin.
    margin = now.get("gross_margin")
    margin_qoq, margin_yoy = diff("gross_margin", prior), diff("gross_margin", year_ago)
    shifts = [shift for shift in (margin_qoq, margin_yoy) if shift is not None]
    if margin is not None and any(abs(shift) >= MARGIN_SHIFT_POINTS for shift in shifts):
        def said(shift: float, against: str) -> str:
            if abs(shift) < 0.0005:
                return f"unchanged from {against}"
            return f"{_moved(shift)} {_points(shift)} from {against}"

        parts = []
        if margin_qoq is not None:
            parts.append(said(margin_qoq, "last quarter"))
        if margin_yoy is not None:
            parts.append(said(margin_yoy, "a year ago"))
        narrowed = any(shift <= -MARGIN_SHIFT_POINTS for shift in shifts)
        findings.append(Finding(
            "watch" if narrowed else "good", "margins",
            "Gross margin narrowed" if narrowed else "Gross margin widened",
            f"Gross margin was {_pct(margin)}, {' and '.join(parts)}. "
            + ("Each dollar of sales cost more to deliver." if narrowed else "Each dollar of sales cost less to deliver."),
            ["gross_margin"],
        ))

    # Operating leverage: did costs grow slower or faster than sales?
    opex_yoy, op_margin_yoy = rel("operating_expenses", year_ago), diff("operating_margin", year_ago)
    if (opex_yoy is not None and revenue_yoy is not None and op_margin_yoy is not None
            and abs(op_margin_yoy) >= MARGIN_SHIFT_POINTS and year_ago is not None):
        widened = op_margin_yoy > 0
        findings.append(Finding(
            "good" if widened else "watch", "margins",
            # Named for the margin, which sets the severity. Naming it for
            # the cost line produced "Costs grew faster than sales" filed as
            # an improvement whenever the margin widened anyway.
            "Operating margin widened" if widened else "Operating margin narrowed",
            f"Operating margin went from {_pct(year_ago.get('operating_margin') or 0)} a year ago to "
            f"{_pct(now.get('operating_margin') or 0)}. R&D and SG&A changed {_pct(opex_yoy, True)} "
            f"against {_pct(revenue_yoy, True)} for revenue.",
            ["operating_margin", "operating_expenses"],
        ))

    # Receivables against sales.
    receivables_qoq = rel("receivables", prior)
    dso_now, dso_before = now.get("days_sales_outstanding"), prior.get("days_sales_outstanding")
    if receivables_qoq is not None and revenue_qoq is not None and dso_now is not None and dso_before is not None:
        gap, days = receivables_qoq - revenue_qoq, dso_now - dso_before
        # Many businesses collect more slowly in the same quarter every year
        # (a product launch late in the quarter). Where a year-ago figure
        # exists, the build has to show against that quarter too.
        dso_year_ago = year_ago.get("days_sales_outstanding") if year_ago else None
        beyond_seasonal = dso_year_ago is None or dso_now - dso_year_ago >= DAYS_SHIFT
        if gap >= RECEIVABLES_GAP_POINTS and days >= DAYS_SHIFT and beyond_seasonal:
            findings.append(Finding(
                "watch", "balance_sheet", "Receivables grew faster than sales",
                f"Receivables rose {_pct(receivables_qoq)} in the quarter to {_money(now.get('receivables') or 0)}; "
                f"revenue changed {_pct(revenue_qoq, True)}. Uncollected sales went from {dso_before:.0f} to {dso_now:.0f} days' worth "
                + (f"({dso_year_ago:.0f} in the same quarter a year ago): " if dso_year_ago is not None else "")
                + "more of the quarter's revenue has been booked but not yet paid for.",
                ["receivables", "days_sales_outstanding"],
            ))
        elif days <= -DAYS_SHIFT and (dso_year_ago is None or dso_now - dso_year_ago <= -DAYS_SHIFT):
            findings.append(Finding(
                "good", "balance_sheet", "Customers paid faster",
                f"Uncollected sales fell from {dso_before:.0f} to {dso_now:.0f} days' worth; receivables are {_money(now.get('receivables') or 0)}.",
                ["receivables", "days_sales_outstanding"],
            ))

    # Inventory against cost of sales.
    dio_now, dio_before = now.get("days_inventory"), prior.get("days_inventory")
    inventory_qoq = rel("inventory", prior)
    if dio_now is not None and dio_before is not None and inventory_qoq is not None:
        days = dio_now - dio_before
        dio_year_ago = year_ago.get("days_inventory") if year_ago else None
        if dio_year_ago is not None:
            days = dio_now - dio_year_ago    # against the same quarter, not the last one
            dio_before = dio_year_ago
        if abs(days) >= INVENTORY_DAYS_SHIFT:
            built = days > 0
            findings.append(Finding(
                "watch" if built else "info", "balance_sheet",
                "Inventory built up" if built else "Inventory ran down",
                f"Inventory changed {_pct(inventory_qoq, True)} in the quarter to {_money(now.get('inventory') or 0)}: "
                f"{dio_now:.0f} days of cost of sales, against {dio_before:.0f} "
                + ("in the same quarter a year ago." if dio_year_ago is not None else "last quarter."),
                ["inventory", "days_inventory"],
            ))

    # Cash behind the profit.
    conversion, cfo, net_income = now.get("cash_conversion"), now.get("operating_cash_flow"), now.get("net_income")
    if conversion is not None and cfo is not None and net_income is not None and conversion < CASH_CONVERSION_FLOOR:
        findings.append(Finding(
            "watch", "cash", "Profit ran ahead of cash",
            f"Operating cash flow was {_money(cfo)} against net income of {_money(net_income)} — "
            f"{conversion * 100:.0f} cents of cash for each dollar of reported profit.",
            ["cash_conversion", "operating_cash_flow"],
        ))
    free_cash_flow = now.get("free_cash_flow")
    if free_cash_flow is not None and free_cash_flow < 0:
        findings.append(Finding(
            "watch", "cash", "Free cash flow was negative",
            f"Operating cash flow of {_money(cfo or 0)} did not cover capital spending of {_money(now.get('capital_expenditure') or 0)}.",
            ["free_cash_flow"],
        ))

    # Capital spending.
    capex_yoy, capex = rel("capital_expenditure", year_ago), now.get("capital_expenditure")
    if capex_yoy is not None and capex is not None and capex_yoy >= CAPEX_JUMP and revenue and capex / revenue >= 0.03:
        findings.append(Finding(
            "info", "cash", "Capital spending stepped up",
            f"Capital spending was {_money(capex)}, {_pct(capex_yoy, True)} from a year ago and {_pct(capex / revenue)} of revenue.",
            ["capital_expenditure"],
        ))

    # Net income from outside operations.
    operating_income = now.get("operating_income")
    if net_income is not None and operating_income is not None and operating_income > 0 and net_income > operating_income:
        findings.append(Finding(
            "info", "growth", "Net income exceeded operating income",
            f"Net income was {_money(net_income)} on operating income of {_money(operating_income)}: "
            f"{_money(net_income - operating_income)} more came from outside operations (investment gains, interest or tax items) than tax took away.",
            ["net_income"],
        ))

    # Share count.
    shares_yoy = rel("diluted_shares", year_ago)
    if shares_yoy is not None:
        buybacks = now.get("buybacks")
        if shares_yoy <= SHARE_COUNT_BUYBACK:
            findings.append(Finding(
                "good", "shareholders", "Share count fell",
                f"Diluted shares are {_pct(abs(shares_yoy))} lower than a year ago"
                + (f"; {_money(buybacks)} went to buybacks this quarter." if buybacks else "."),
                ["diluted_shares", "returned_to_shareholders"],
            ))
        elif shares_yoy >= SHARE_COUNT_DILUTION:
            findings.append(Finding(
                "watch", "shareholders", "Share count rose",
                f"Diluted shares are {_pct(shares_yoy)} higher than a year ago: each share owns a smaller part of the company.",
                ["diluted_shares"],
            ))

    # Paying out more than it brought in.
    returned = now.get("returned_to_shareholders")
    if returned and free_cash_flow is not None and free_cash_flow > 0 and returned > free_cash_flow:
        findings.append(Finding(
            "info", "shareholders", "Returned more than it generated",
            f"Buybacks and dividends were {_money(returned)} against free cash flow of {_money(free_cash_flow)}; "
            "the difference came from cash on hand or borrowing.",
            ["returned_to_shareholders", "free_cash_flow"],
        ))

    # Stock compensation.
    comp_share = now.get("stock_compensation_share")
    if comp_share is not None and comp_share >= STOCK_COMP_HEAVY:
        findings.append(Finding(
            "watch", "shareholders", "Stock compensation is a large cost",
            f"Stock compensation was {_money(now.get('stock_compensation') or 0)}, {_pct(comp_share)} of revenue. "
            "It is a real cost that operating cash flow adds back.",
            ["stock_compensation_share"],
        ))

    # Debt.
    debt_qoq, debt = rel("debt", prior), now.get("debt")
    if debt_qoq is not None and debt is not None and debt_qoq >= DEBT_JUMP:
        findings.append(Finding(
            "watch", "balance_sheet", "Debt rose",
            f"Debt rose {_pct(debt_qoq)} in the quarter to {_money(debt)}.", ["debt", "net_cash"],
        ))
    net_cash_now, net_cash_before = now.get("net_cash"), prior.get("net_cash")
    if net_cash_now is not None and net_cash_before is not None and (net_cash_now < 0) != (net_cash_before < 0):
        to_debt = net_cash_now < 0
        findings.append(Finding(
            "watch" if to_debt else "good", "balance_sheet",
            "Moved to net debt" if to_debt else "Moved to net cash",
            f"Cash and investments less debt went from {_money(net_cash_before)} to {_money(net_cash_now)}.",
            ["net_cash"],
        ))

    # Purchase commitments, when the company tags them.
    commitments, commitments_before = now.get("purchase_commitments"), prior.get("purchase_commitments")
    if commitments is not None and commitments_before is not None and commitments_before > 0:
        change = commitments / commitments_before - 1
        if abs(change) >= 0.25:
            findings.append(Finding(
                "watch" if change > 0 else "info", "balance_sheet",
                "Purchase commitments rose" if change > 0 else "Purchase commitments fell",
                f"Purchase commitments were {_money(commitments)}, {_pct(change, True)} from {_money(commitments_before)} a quarter earlier. "
                "These are orders the company has promised to pay for.",
                ["purchase_commitments"],
            ))

    order = {"watch": 0, "good": 1, "info": 2}
    findings.sort(key=lambda finding: order.get(finding.severity, 3))
    return findings


# ── The whole thing ──────────────────────────────────────────────────────────

class NoQuarterlyData(ValueError):
    """The company files, but not in a form this reader understands."""


def analyse(company_facts: dict, symbol: str, cik: str, today: Optional[date] = None) -> FilingAnalysis:
    quarters = build_quarters(company_facts, cik)
    if quarters and ((today or date.today()) - quarters[-1].period_end).days > MAX_LATEST_AGE_DAYS:
        raise NoQuarterlyData(
            f"The most recent quarterly revenue in {symbol}'s SEC data is for the period ended "
            f"{quarters[-1].period_end.isoformat()}, which is too old to present as the latest quarter."
        )
    if len(quarters) < 2:
        raise NoQuarterlyData(
            f"{symbol} has no quarterly 10-Q / 10-K revenue data in the SEC's XBRL records. "
            "Foreign filers (20-F, 6-K) and very recent listings are not covered."
        )
    _add_growth(quarters)
    return FilingAnalysis(
        symbol=symbol.upper(), company_name=company_facts.get("entityName") or symbol.upper(), cik=str(cik),
        quarters=quarters, metrics=build_metrics(quarters), findings=build_findings(quarters),
    )
