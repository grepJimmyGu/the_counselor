from __future__ import annotations

from datetime import date
from typing import Optional

from app.schemas.fundamental import CompanyProfile, KeyMetrics


def _yield_from_rate(rate: Optional[float], price: Optional[float]) -> Optional[float]:
    """Annual dividend per share ÷ price, as a **fraction** (0.0116 = 1.16%).

    Deliberately not `info["dividendYield"]`: yfinance changed that key's
    meaning between releases — older ones returned a fraction (0.0116), 0.2.x
    returns a percent (1.16) — so forwarding it makes the stored scale depend
    on whichever version the container happens to have installed. Silent, and
    invisible until a screen returns the wrong names.

    `dividendRate` is unambiguous: annual dollars per share. Same arithmetic
    and same units as `fmp_adapter._dividend_yield`.
    """
    try:
        r = float(rate)
        px = float(price)
    except (TypeError, ValueError):
        return None
    if r <= 0 or px <= 0:
        return None
    return r / px


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
            # NOT `info["dividendYield"]`. yfinance changed that key's meaning
            # between versions — older releases returned a fraction (0.0116),
            # 0.2.x returns a percent (1.16) — so forwarding it makes the scale
            # depend on whichever version the container happens to have.
            # `dividendRate` is unambiguous: annual dollars per share. Same
            # arithmetic as `fmp_adapter._dividend_yield`, same units out.
            dividend_yield=_yield_from_rate(
                info.get("dividendRate"),
                info.get("currentPrice") or info.get("regularMarketPrice"),
            ),
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
            dividend_yield=_yield_from_rate(
                _f("dividendRate"), _f("currentPrice") or _f("regularMarketPrice")
            ),
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
