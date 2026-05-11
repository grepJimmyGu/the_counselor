from __future__ import annotations

from datetime import date

from app.schemas.fundamental import CompanyProfile, KeyMetrics
from app.services.fmp_client import FMPClient


class FMPAdapter:
    def __init__(self) -> None:
        self._client = FMPClient()

    async def get_profile(self, symbol: str) -> CompanyProfile:
        raw = await self._client.get_profile(symbol)
        peers = await self._get_peers_safe(symbol)

        # Parse 52-week range: "164.08-199.62"
        week_52_high, week_52_low = None, None
        rng = raw.get("range", "")
        if rng and "-" in rng:
            parts = rng.split("-")
            try:
                week_52_low = float(parts[0])
                week_52_high = float(parts[1])
            except (ValueError, IndexError):
                pass

        employees = None
        try:
            employees = int(raw.get("fullTimeEmployees") or 0) or None
        except (ValueError, TypeError):
            pass

        return CompanyProfile(
            symbol=symbol.upper(),
            name=raw.get("companyName", symbol),
            sector=raw.get("sector") or None,
            industry=raw.get("industry") or None,
            exchange=raw.get("exchangeShortName") or raw.get("exchange") or None,
            country=raw.get("country") or None,
            currency=raw.get("currency") or None,
            description=raw.get("description") or None,
            ceo=raw.get("ceo") or None,
            employees=employees,
            website=raw.get("website") or None,
            price=raw.get("price"),
            market_cap=raw.get("mktCap"),
            pe_ratio=None,  # comes from key-metrics
            dividend_yield=raw.get("lastDiv"),
            beta=raw.get("beta"),
            week_52_high=week_52_high,
            week_52_low=week_52_low,
            is_etf=bool(raw.get("isEtf", False)),
            is_actively_trading=bool(raw.get("isActivelyTrading", True)),
            peers=peers,
            data_source="fmp",
            as_of_date=date.today(),
        )

    async def get_key_metrics(self, symbol: str) -> KeyMetrics:
        raw = await self._client.get_key_metrics(symbol)

        as_of = None
        try:
            from datetime import datetime
            d = raw.get("date")
            if d:
                as_of = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

        def _f(key: str) -> float | None:
            v = raw.get(key)
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        return KeyMetrics(
            symbol=symbol.upper(),
            as_of_date=as_of,
            pe_ratio=_f("peRatioTTM"),
            pb_ratio=_f("pbRatioTTM"),
            ps_ratio=_f("priceToSalesRatioTTM"),
            ev_to_ebitda=_f("enterpriseValueOverEBITDATTM"),
            free_cash_flow_yield=_f("freeCashFlowYieldTTM"),
            dividend_yield=_f("dividendYieldPercentageTTM"),
            roe=_f("roeTTM"),
            debt_to_equity=_f("debtToEquityTTM"),
            current_ratio=_f("currentRatioTTM"),
            interest_coverage=_f("interestCoverageTTM"),
            net_debt_to_ebitda=_f("netDebtToEBITDATTM"),
            revenue_per_share=_f("revenuePerShareTTM"),
            free_cash_flow_per_share=_f("freeCashFlowPerShareTTM"),
            operating_cash_flow_per_share=_f("operatingCashFlowPerShareTTM"),
            book_value_per_share=_f("bookValuePerShareTTM"),
            data_source="fmp",
        )

    async def get_peers(self, symbol: str) -> list[str]:
        return await self._get_peers_safe(symbol)

    async def _get_peers_safe(self, symbol: str) -> list[str]:
        try:
            return await self._client.get_peers(symbol)
        except Exception:
            return []
