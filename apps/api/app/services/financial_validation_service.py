from __future__ import annotations

from typing import Optional

from app.services.fmp_client import FMPClient, FMPNotConfiguredError, FMPRateLimitError


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    try:
        if a is None or b is None or b == 0:
            return None
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


def _yoy_growth(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    return _safe_div(current - prior, abs(prior)) if prior and prior != 0 and current is not None else None


class FinancialCheckMetrics:
    """All computed financial check metrics for a single symbol."""

    def __init__(self) -> None:
        # Growth
        self.revenue_yoy: Optional[float] = None
        self.revenue_3y_cagr: Optional[float] = None
        self.eps_yoy: Optional[float] = None
        self.operating_income_growth: Optional[float] = None
        self.eps_growth_years: int = 0  # consecutive years of EPS growth

        # Profitability
        self.gross_margin: Optional[float] = None
        self.operating_margin: Optional[float] = None
        self.net_margin: Optional[float] = None
        self.roe: Optional[float] = None
        self.roa: Optional[float] = None

        # Cash flow
        self.operating_cf: Optional[float] = None
        self.capex: Optional[float] = None
        self.free_cash_flow: Optional[float] = None
        self.fcf_margin: Optional[float] = None
        self.fcf_conversion: Optional[float] = None  # FCF / net income

        # Balance sheet
        self.cash: Optional[float] = None
        self.total_debt: Optional[float] = None
        self.net_debt: Optional[float] = None
        self.debt_to_equity: Optional[float] = None
        self.current_ratio: Optional[float] = None
        self.interest_coverage: Optional[float] = None

        # Valuation
        self.pe_ratio: Optional[float] = None
        self.ps_ratio: Optional[float] = None
        self.pb_ratio: Optional[float] = None
        self.peg_ratio: Optional[float] = None
        self.fcf_yield: Optional[float] = None
        self.dividend_yield: Optional[float] = None
        self.market_cap: Optional[float] = None

        # Historical series for mini-charts (latest N quarters)
        self.revenue_series: list[dict] = []
        self.margin_series: list[dict] = []
        self.fcf_series: list[dict] = []


def _extract_income_metrics(statements: list[dict], metrics: FinancialCheckMetrics) -> None:
    if not statements:
        return
    latest = statements[0]
    prior = statements[1] if len(statements) > 1 else None

    revenue = latest.get("revenue") or latest.get("totalRevenue")
    prior_revenue = (prior.get("revenue") or prior.get("totalRevenue")) if prior else None
    metrics.revenue_yoy = _yoy_growth(revenue, prior_revenue)

    # 3Y CAGR if 4+ years available
    if len(statements) >= 4 and revenue and statements[3].get("revenue"):
        r3 = statements[3].get("revenue")
        if r3 and r3 > 0:
            try:
                metrics.revenue_3y_cagr = (revenue / r3) ** (1/3) - 1
            except (ValueError, ZeroDivisionError):
                pass

    eps = latest.get("eps") or latest.get("epsDiluted")
    prior_eps = (prior.get("eps") or prior.get("epsDiluted")) if prior else None
    metrics.eps_yoy = _yoy_growth(eps, prior_eps)

    # Count consecutive EPS growth years
    eps_values = [s.get("eps") or s.get("epsDiluted") for s in statements]
    count = 0
    for i in range(len(eps_values) - 1):
        if eps_values[i] and eps_values[i+1] and eps_values[i] > eps_values[i+1]:
            count += 1
        else:
            break
    metrics.eps_growth_years = count

    op_income = latest.get("operatingIncome")
    prior_op = prior.get("operatingIncome") if prior else None
    metrics.operating_income_growth = _yoy_growth(op_income, prior_op)

    # Interest coverage = EBIT / interest expense (positive expense is typically negative in FMP)
    interest_expense = latest.get("interestExpense")
    if interest_expense is not None:
        interest_expense = abs(interest_expense)  # FMP returns negative; normalise
    if op_income is not None and interest_expense and interest_expense > 0:
        metrics.interest_coverage = round(op_income / interest_expense, 2)

    gross_profit = latest.get("grossProfit")
    metrics.gross_margin = _safe_div(gross_profit, revenue)
    metrics.operating_margin = _safe_div(op_income, revenue)
    net_income = latest.get("netIncome")
    metrics.net_margin = _safe_div(net_income, revenue)

    # Revenue series for chart (most recent 8)
    for s in reversed(statements[:8]):
        rev = s.get("revenue") or s.get("totalRevenue")
        gp = s.get("grossProfit")
        metrics.revenue_series.append({
            "date": s.get("date", ""),
            "revenue": rev,
            "gross_margin": _safe_div(gp, rev),
            "operating_margin": _safe_div(s.get("operatingIncome"), rev),
        })


def _extract_cashflow_metrics(statements: list[dict], income: list[dict], metrics: FinancialCheckMetrics) -> None:
    if not statements:
        return
    latest = statements[0]
    op_cf = latest.get("operatingCashFlow")
    capex = latest.get("capitalExpenditure")
    if capex is not None:
        capex = abs(capex)
    metrics.operating_cf = op_cf
    metrics.capex = capex
    metrics.free_cash_flow = (op_cf - capex) if (op_cf is not None and capex is not None) else None

    revenue = income[0].get("revenue") if income else None
    net_income = income[0].get("netIncome") if income else None
    metrics.fcf_margin = _safe_div(metrics.free_cash_flow, revenue)
    metrics.fcf_conversion = _safe_div(metrics.free_cash_flow, net_income)

    for s in reversed(statements[:8]):
        oc = s.get("operatingCashFlow")
        cap = abs(s.get("capitalExpenditure") or 0)
        fcf = (oc - cap) if (oc is not None) else None
        metrics.fcf_series.append({"date": s.get("date", ""), "fcf": fcf, "operating_cf": oc})


def _extract_balance_sheet_metrics(statements: list[dict], metrics: FinancialCheckMetrics) -> None:
    if not statements:
        return
    latest = statements[0]
    cash = latest.get("cashAndCashEquivalents") or latest.get("cash")
    debt = latest.get("totalDebt") or (
        (latest.get("longTermDebt") or 0) + (latest.get("shortTermDebt") or 0)
    )
    metrics.cash = cash
    metrics.total_debt = debt
    metrics.net_debt = (debt - cash) if (debt is not None and cash is not None) else None
    equity = latest.get("totalStockholdersEquity")
    metrics.debt_to_equity = _safe_div(debt, equity)
    curr_assets = latest.get("totalCurrentAssets")
    curr_liab = latest.get("totalCurrentLiabilities")
    metrics.current_ratio = _safe_div(curr_assets, curr_liab)


class FinancialValidationService:
    def __init__(self) -> None:
        self._client = FMPClient()

    async def compute(self, symbol: str, key_metrics: dict) -> FinancialCheckMetrics:
        m = FinancialCheckMetrics()
        sym = symbol.upper()
        try:
            income = await self._client.get_income_statement(sym, limit=5)
            cashflow = await self._client.get_cash_flow(sym, limit=5)
            balance = await self._client.get_balance_sheet(sym, limit=3)
        except (FMPNotConfiguredError, FMPRateLimitError):
            return m  # return empty metrics if FMP not available

        _extract_income_metrics(income, m)
        _extract_cashflow_metrics(cashflow, income, m)
        _extract_balance_sheet_metrics(balance, m)

        # Valuation from key_metrics dict
        def _kf(k: str) -> Optional[float]:
            v = key_metrics.get(k)
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        m.pe_ratio = _kf("peRatioTTM")
        m.ps_ratio = _kf("priceToSalesRatioTTM")
        m.pb_ratio = _kf("pbRatioTTM")
        m.fcf_yield = _kf("freeCashFlowYieldTTM")
        m.dividend_yield = _kf("dividendYieldPercentageTTM")
        m.roe = _kf("roeTTM")

        # PEG = P/E / EPS growth rate (only if positive growth)
        if m.pe_ratio and m.eps_yoy and m.eps_yoy > 0:
            m.peg_ratio = m.pe_ratio / (m.eps_yoy * 100)

        return m
