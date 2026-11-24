"""Response shapes for GET /api/company/{symbol}/filings."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FilingQuarter(BaseModel):
    """One fiscal quarter, and the filing it was reported in."""
    label: str                              # "Q2 FY2027"
    period_end: str                         # ISO date
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None     # Q1 … Q4
    form: Optional[str] = None              # 10-Q | 10-K
    filed: Optional[str] = None             # ISO date the filing reached the SEC
    filing_url: Optional[str] = None
    # Reported and derived figures by key (see `FilingMetric.key`, plus the
    # raw statement lines). A key is absent when the company does not report it.
    values: dict[str, float] = Field(default_factory=dict)


class FilingMetric(BaseModel):
    """One figure, with how it has moved.

    The series itself is `quarters[i].values[key]` — one place for every
    number, and a quarter with no figure simply lacks the key, so no client
    has to decode a list with holes in it."""
    key: str
    label: str
    group: str                              # Growth | Profitability | Cash | Balance sheet | Shareholders
    unit: str                               # usd | per_share | shares | percent | ratio | days
    better: str                             # up | down | none
    latest: Optional[float] = None
    change_qoq: Optional[float] = None
    change_yoy: Optional[float] = None
    change_kind: str                        # relative | points | absolute
    note: Optional[str] = None


class FilingFinding(BaseModel):
    """Something in the latest quarter that moved enough to state."""
    severity: str                           # watch | good | info
    category: str                           # growth | margins | cash | balance_sheet | shareholders
    title: str
    detail: str
    metrics: list[str] = Field(default_factory=list)


class FilingAnalysisResponse(BaseModel):
    symbol: str
    company_name: str
    cik: str
    source: str = "SEC EDGAR XBRL company facts (10-Q and 10-K filings)"
    latest: FilingQuarter
    quarters: list[FilingQuarter]           # oldest first; the last one is `latest`
    metrics: list[FilingMetric]
    findings: list[FilingFinding]
    computed_at: str
