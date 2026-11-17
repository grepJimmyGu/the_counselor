"""Quarterly filing analysis for one company.

GET /api/company/{symbol}/filings

What the latest 10-Q or 10-K says, read against the eight quarters before
it: the figures, each key metric's movement, and the specific things that
changed enough to state. Arithmetic on reported numbers only — see
`app/services/filing_financials.py`.

Not gated and not database-backed: the source is public SEC data, and the
route awaits a slow external call, so it deliberately takes no session
(apps/api/CLAUDE.md trap #13).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas.filing_analysis import (
    FilingAnalysisResponse,
    FilingFinding,
    FilingMetric,
    FilingQuarter,
)
from app.services import sec_company_facts
from app.services.filing_financials import FilingAnalysis, NoQuarterlyData, Quarter

router = APIRouter(prefix="/api/company", tags=["company-filings"])


def _quarter(quarter: Quarter) -> FilingQuarter:
    return FilingQuarter(
        label=quarter.label,
        period_end=quarter.period_end.isoformat(),
        fiscal_year=quarter.fiscal_year,
        fiscal_period=quarter.fiscal_period,
        form=quarter.form,
        filed=quarter.filed.isoformat() if quarter.filed else None,
        filing_url=quarter.filing_url,
        values={key: value for key, value in quarter.values.items() if value is not None},
    )


def to_response(analysis: FilingAnalysis) -> FilingAnalysisResponse:
    quarters = [_quarter(quarter) for quarter in analysis.quarters]
    return FilingAnalysisResponse(
        symbol=analysis.symbol,
        company_name=analysis.company_name,
        cik=analysis.cik,
        latest=quarters[-1],
        quarters=quarters,
        metrics=[
            FilingMetric(**{key: value for key, value in vars(metric).items() if key != "values"})
            for metric in analysis.metrics
        ],
        findings=[FilingFinding(**vars(finding)) for finding in analysis.findings],
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{symbol}/filings", response_model=FilingAnalysisResponse)
async def get_company_filings(symbol: str) -> FilingAnalysisResponse:
    try:
        analysis = await sec_company_facts.filing_analysis(symbol)
    except sec_company_facts.UnknownTicker as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoQuarterlyData as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except sec_company_facts.SecUnavailable as exc:
        raise HTTPException(status_code=502, detail="The SEC's filing data isn't reachable right now.") from exc
    return to_response(analysis)
