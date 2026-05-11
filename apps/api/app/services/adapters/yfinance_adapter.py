from __future__ import annotations

from datetime import date

from app.schemas.fundamental import CompanyProfile, KeyMetrics


class YFinanceAdapter:
    """
    Dev/fallback adapter using yfinance (unofficial Yahoo Finance).
    Used when FMP is rate-limited, not configured, or in local development.
    Not guaranteed SLA — Yahoo Finance API can change without notice.
    """

    async def get_profile(self, symbol: str) -> CompanyProfile:
        import yfinance as yf  # lazy import — not installed in all envs

        ticker = yf.Ticker(symbol.upper())
        info = ticker.info or {}

        employees = None
        try:
            employees = int(info.get("fullTimeEmployees") or 0) or None
        except (ValueError, TypeError):
            pass

        return CompanyProfile(
            symbol=symbol.upper(),
            name=info.get("longName") or info.get("shortName") or symbol,
            sector=info.get("sector") or None,
            industry=info.get("industry") or None,
            exchange=info.get("exchange") or None,
            country=info.get("country") or None,
            currency=info.get("currency") or None,
            description=info.get("longBusinessSummary") or None,
            ceo=None,  # yfinance doesn't reliably provide CEO
            employees=employees,
            website=info.get("website") or None,
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            dividend_yield=info.get("dividendYield"),
            beta=info.get("beta"),
            week_52_high=info.get("fiftyTwoWeekHigh"),
            week_52_low=info.get("fiftyTwoWeekLow"),
            is_etf=info.get("quoteType", "").upper() == "ETF",
            is_actively_trading=True,
            peers=[],  # yfinance doesn't provide peers
            data_source="yfinance",
            as_of_date=date.today(),
        )

    async def get_key_metrics(self, symbol: str) -> KeyMetrics:
        import yfinance as yf

        ticker = yf.Ticker(symbol.upper())
        info = ticker.info or {}

        def _f(key: str) -> float | None:
            v = info.get(key)
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        return KeyMetrics(
            symbol=symbol.upper(),
            as_of_date=date.today(),
            pe_ratio=_f("trailingPE"),
            pb_ratio=_f("priceToBook"),
            ps_ratio=_f("priceToSalesTrailing12Months"),
            free_cash_flow_yield=None,  # not directly available
            dividend_yield=_f("dividendYield"),
            roe=_f("returnOnEquity"),
            roa=_f("returnOnAssets"),
            debt_to_equity=_f("debtToEquity"),
            current_ratio=_f("currentRatio"),
            revenue_per_share=_f("revenuePerShare"),
            book_value_per_share=_f("bookValue"),
            data_source="yfinance",
        )

    async def get_peers(self, symbol: str) -> list[str]:
        return []  # yfinance does not provide peers
