"""
Signal Provider Protocol and Concrete Implementations
======================================================
Each provider returns a *sparse*, date-indexed pd.Series for one symbol over
a requested date range.  Consumers (the engine, cross-sectional ranker) are
responsible for reindexing and forward-filling between the sparse observations.

Look-ahead prevention
---------------------
Fundamental data is always dated at  fiscal_period_end + report_date_lag  days
(default 45).  This represents the earliest realistic date on which an investor
could have acted on the information (i.e., after the 10-Q/10-K is filed).

Registry
--------
Use ``get_signal_provider(signal_source_name)`` to obtain a provider by name
without hard-coding the mapping in the engine.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Protocol ──────────────────────────────────────────────────────────────────
# We use a regular base class with the Protocol shape so that runtime
# isinstance() checks and duck-typed mocks both work without a typing import
# in every consumer.

class SignalProvider:
    """
    Structural protocol: any class that exposes ``name: str`` and
    ``async get_signal_frame(db, symbol, start, end) -> pd.Series`` satisfies it.
    """
    name: str

    async def get_signal_frame(
        self,
        db: Session,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.Series:
        """
        Return a date-indexed pd.Series of the signal value for *symbol* over
        [start, end].  Observations are sparse; the caller forward-fills.
        Index dtype: datetime64[ns].  Values: float (NaN where unavailable).
        """
        raise NotImplementedError


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_date(val) -> Optional[date]:
    """Coerce a FMP date string or date object to a Python date."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _piotroski_from_stmts(
    income: list[dict],
    cashflow: list[dict],
    balance: list[dict],
) -> list[tuple[date, int]]:
    """
    Compute Piotroski F-Score for each annual period where enough data exists.
    Returns [(period_end_date, f_score), ...] sorted oldest-first.

    Only the 9 canonical Piotroski signals are scored; each missing signal
    contributes 0 (conservative).
    """
    results = []

    def _f(d: dict, *keys: str) -> Optional[float]:
        for k in keys:
            v = d.get(k)
            if v is not None and v != "":
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return None

    # Align statements by date; use income-statement date as anchor
    inc_by_date = {_to_date(r.get("date")): r for r in income if _to_date(r.get("date"))}
    cf_by_date  = {_to_date(r.get("date")): r for r in cashflow if _to_date(r.get("date"))}
    bs_by_date  = {_to_date(r.get("date")): r for r in balance if _to_date(r.get("date"))}

    sorted_dates = sorted(inc_by_date.keys())
    for i, period_end in enumerate(sorted_dates):
        inc = inc_by_date[period_end]
        cf  = cf_by_date.get(period_end, {})
        bs  = bs_by_date.get(period_end, {})

        total_assets = _f(bs, "totalAssets")
        net_income   = _f(inc, "netIncome")
        ocf          = _f(cf, "operatingCashFlow", "netCashProvidedByOperatingActivities")
        revenue      = _f(inc, "revenue")
        gross_profit = _f(inc, "grossProfit")
        shares       = _f(inc, "weightedAverageShsOut", "weightedAverageShsOutDil")
        lt_debt      = _f(bs, "longTermDebt")
        curr_assets  = _f(bs, "totalCurrentAssets")
        curr_liab    = _f(bs, "totalCurrentLiabilities")

        roa = _safe_div(net_income, total_assets)

        score = 0
        # F1 ROA > 0
        if roa is not None and roa > 0:
            score += 1
        # F2 OCF > 0
        if ocf is not None and ocf > 0:
            score += 1
        # F4 Accruals: OCF / assets > ROA
        ocf_assets = _safe_div(ocf, total_assets)
        if ocf_assets is not None and roa is not None and ocf_assets > roa:
            score += 1

        # Prior period signals (require i > 0)
        if i > 0:
            prev_date = sorted_dates[i - 1]
            prev_bs  = bs_by_date.get(prev_date, {})
            prev_inc = inc_by_date.get(prev_date, {})

            prev_ta     = _f(prev_bs, "totalAssets")
            prev_ni     = _f(prev_inc, "netIncome")
            prev_lt     = _f(prev_bs, "longTermDebt")
            prev_ca     = _f(prev_bs, "totalCurrentAssets")
            prev_cl     = _f(prev_bs, "totalCurrentLiabilities")
            prev_rev    = _f(prev_inc, "revenue")
            prev_gp     = _f(prev_inc, "grossProfit")
            prev_shares = _f(prev_inc, "weightedAverageShsOut", "weightedAverageShsOutDil")

            prev_roa = _safe_div(prev_ni, prev_ta)

            # F3 ΔROA > 0
            if roa is not None and prev_roa is not None and roa > prev_roa:
                score += 1
            # F5 ΔLeverage < 0
            lev      = _safe_div(lt_debt, total_assets)
            prev_lev = _safe_div(prev_lt, prev_ta)
            if lev is not None and prev_lev is not None and lev < prev_lev:
                score += 1
            # F6 ΔLiquidity > 0
            cr      = _safe_div(curr_assets, curr_liab)
            prev_cr = _safe_div(prev_ca, prev_cl)
            if cr is not None and prev_cr is not None and cr > prev_cr:
                score += 1
            # F7 No new share issuance
            if shares is not None and prev_shares is not None and shares <= prev_shares * 1.01:
                score += 1
            # F8 ΔGross margin > 0
            gm      = _safe_div(gross_profit, revenue)
            prev_gm = _safe_div(prev_gp, prev_rev)
            if gm is not None and prev_gm is not None and gm > prev_gm:
                score += 1
            # F9 ΔAsset turnover > 0
            at      = _safe_div(revenue, total_assets)
            prev_at = _safe_div(prev_rev, prev_ta)
            if at is not None and prev_at is not None and at > prev_at:
                score += 1

        results.append((period_end, score))

    return results


# ── Fundamental Signal Provider ───────────────────────────────────────────────

class FundamentalSignalProvider(SignalProvider):
    """
    Returns a sparse date-indexed Series of the requested fundamental metric.
    Each value is dated at  fiscal_period_end + report_date_lag  days to prevent
    look-ahead bias.  Forward-fill between disclosures is the caller's job.

    Supported signal names
    ----------------------
    "fcf_yield"             free cash flow / market cap (from cashflow + profile)
    "book_to_market"        total equity / market cap (from balance sheet + profile)
    "ebitda_ev"             EBITDA / enterprise value  (from income + key metrics)
    "f_score"               Piotroski F-Score (0–9) computed from annual statements
    "buyback_yield_ttm"     share repurchases / market cap (cashflow + profile)
    "estimate_revision_3m"  3-quarter EPS momentum proxy for analyst estimate revision
                            = (EPS_t - EPS_{t-3}) / |EPS_{t-3}|. Positive = upward
                            revisions; dated at period_end + report_date_lag.
    """

    SUPPORTED = frozenset(
        {"fcf_yield", "book_to_market", "ebitda_ev", "f_score",
         "buyback_yield_ttm", "estimate_revision_3m"}
    )

    def __init__(self, signal: str, report_date_lag: int = 45) -> None:
        if signal not in self.SUPPORTED:
            raise ValueError(
                f"FundamentalSignalProvider: unknown signal '{signal}'. "
                f"Supported: {sorted(self.SUPPORTED)}"
            )
        self.name = signal
        self._lag_days = report_date_lag
        from app.services.fmp_client import FMPClient
        self._fmp = FMPClient()

    async def get_signal_frame(
        self, db: Session, symbol: str, start: date, end: date
    ) -> pd.Series:
        sym = symbol.upper()
        try:
            if self.name == "f_score":
                return await self._f_score_series(sym, start, end)
            elif self.name == "estimate_revision_3m":
                return await self._estimate_revision_series(sym, start, end)
            else:
                return await self._metric_series(sym, start, end)
        except Exception as exc:
            logger.warning("FundamentalSignalProvider(%s) failed for %s: %s", self.name, sym, exc)
            return pd.Series(dtype=float)

    async def _f_score_series(self, symbol: str, start: date, end: date) -> pd.Series:
        income   = await self._fmp.get_income_statement(symbol, limit=10)
        cashflow = await self._fmp.get_cash_flow(symbol, limit=10)
        balance  = await self._fmp.get_balance_sheet(symbol, limit=10)

        scored = _piotroski_from_stmts(income, cashflow, balance)
        if not scored:
            return pd.Series(dtype=float)

        disclosure_dates = [
            pd.Timestamp(period_end + timedelta(days=self._lag_days))
            for period_end, _ in scored
        ]
        values = [float(score) for _, score in scored]
        series = pd.Series(values, index=disclosure_dates, name=self.name)
        return series.loc[
            (series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))
        ]

    async def _estimate_revision_series(
        self, symbol: str, start: date, end: date
    ) -> pd.Series:
        """
        3-quarter EPS momentum as a proxy for analyst estimate revision trend.

        revision = (EPS_t - EPS_{t-3}) / |EPS_{t-3}|

        Positive value → upward EPS trend (estimates likely being revised up).
        Dated at fiscal_period_end + report_date_lag to prevent look-ahead.
        """
        income = await self._fmp.get_income_statement(symbol, limit=20)
        if not income:
            return pd.Series(dtype=float)

        def _eps(row: dict) -> Optional[float]:
            for k in ("epsDiluted", "eps", "earningsPerShareBasic"):
                v = row.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass
            return None

        # Sort oldest → newest
        rows_dated = sorted(
            [(r, _to_date(r.get("date"))) for r in income],
            key=lambda x: x[1] or date.min,
        )
        rows_dated = [(r, d) for r, d in rows_dated if d is not None]

        records: list[tuple[pd.Timestamp, float]] = []
        for i in range(3, len(rows_dated)):
            row, period_end = rows_dated[i]
            prev_row, _ = rows_dated[i - 3]
            curr_eps = _eps(row)
            prev_eps = _eps(prev_row)
            if curr_eps is None or prev_eps is None or prev_eps == 0:
                continue
            revision = (curr_eps - prev_eps) / abs(prev_eps)
            disclosure_ts = pd.Timestamp(period_end + timedelta(days=self._lag_days))
            records.append((disclosure_ts, revision))

        if not records:
            return pd.Series(dtype=float)

        records.sort(key=lambda x: x[0])
        idx, vals = zip(*records)
        series = pd.Series(list(vals), index=list(idx), name=self.name)
        return series.loc[
            (series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))
        ]

    async def _metric_series(self, symbol: str, start: date, end: date) -> pd.Series:
        # Fetch the statements we need
        cashflow = await self._fmp.get_cash_flow(symbol, limit=10)
        balance  = await self._fmp.get_balance_sheet(symbol, limit=5)
        income   = await self._fmp.get_income_statement(symbol, limit=10)

        def _f(d: dict, *keys: str) -> Optional[float]:
            for k in keys:
                v = d.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass
            return None

        records: list[tuple[pd.Timestamp, float]] = []

        # Use cashflow as the primary date anchor for flow-based signals;
        # balance sheet for stock-based signals; income for EBITDA.
        anchor = cashflow if self.name in ("fcf_yield", "buyback_yield_ttm") else balance
        cf_by_date = {_to_date(r.get("date")): r for r in cashflow}
        bs_by_date = {_to_date(r.get("date")): r for r in balance}
        inc_by_date = {_to_date(r.get("date")): r for r in income}

        for row in anchor:
            period_end = _to_date(row.get("date"))
            if period_end is None:
                continue
            market_cap = _f(row, "marketCap") or 1e10  # fallback to avoid div/0

            value: Optional[float] = None

            if self.name == "fcf_yield":
                cf = cf_by_date.get(period_end, row)
                fcf = _f(cf, "freeCashFlow", "freeCashFlowTTM")
                value = _safe_div(fcf, market_cap)

            elif self.name == "buyback_yield_ttm":
                cf = cf_by_date.get(period_end, row)
                # FMP: commonStockRepurchased is negative (cash outflow)
                repurchases = _f(cf, "commonStockRepurchased", "repurchaseOfCommonStock")
                if repurchases is not None:
                    value = _safe_div(abs(repurchases), market_cap)

            elif self.name == "book_to_market":
                bs = bs_by_date.get(period_end, row)
                equity = _f(bs, "totalStockholdersEquity", "totalEquity")
                value = _safe_div(equity, market_cap)

            elif self.name == "ebitda_ev":
                inc = inc_by_date.get(period_end, {})
                ebitda = _f(inc, "ebitda", "ebitdaTTM")
                # Enterprise value may live in income or balance sheet rows
                ev = _f(inc, "enterpriseValue") or _f(row, "enterpriseValue") or market_cap
                value = _safe_div(ebitda, ev)

            if value is not None:
                disclosure_ts = pd.Timestamp(period_end + timedelta(days=self._lag_days))
                records.append((disclosure_ts, value))

        if not records:
            return pd.Series(dtype=float)

        records.sort(key=lambda x: x[0])
        idx, vals = zip(*records)
        series = pd.Series(list(vals), index=list(idx), name=self.name)
        return series.loc[
            (series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))
        ]


# ── Sentiment Signal Provider ─────────────────────────────────────────────────

class SentimentSignalProvider(SignalProvider):
    """
    Returns the rolling 30-day mean of ``overall_sentiment_signal_score``
    from the ``sentiment_signal_summaries`` table.

    The Series is indexed by the ``as_of_datetime`` of each cached summary and
    represents the score available to an investor on that date.
    """

    name = "sentiment_score"

    async def get_signal_frame(
        self, db: Session, symbol: str, start: date, end: date
    ) -> pd.Series:
        sym = symbol.upper()
        try:
            rows = db.execute(
                text(
                    "SELECT as_of_datetime, overall_sentiment_signal_score "
                    "FROM sentiment_signal_summaries "
                    "WHERE symbol = :sym "
                    "  AND as_of_datetime >= :start "
                    "  AND as_of_datetime <= :end "
                    "ORDER BY as_of_datetime ASC"
                ),
                {"sym": sym, "start": start.isoformat(), "end": end.isoformat()},
            ).fetchall()
        except Exception as exc:
            logger.warning("SentimentSignalProvider: DB query failed for %s: %s", sym, exc)
            return pd.Series(dtype=float)

        if not rows:
            return pd.Series(dtype=float)

        idx  = [pd.Timestamp(r[0]) for r in rows]
        vals = [float(r[1]) if r[1] is not None else float("nan") for r in rows]
        series = pd.Series(vals, index=idx, name=self.name)
        # Rolling 30-day mean (centre on window end so no look-ahead)
        return series.rolling("30D").mean().dropna()


# ── Earnings Event Signal Provider ────────────────────────────────────────────

class EarningsEventSignalProvider(SignalProvider):
    """
    Returns a sparse Series equal to the stock's simplified SUE
    (Standardised Unexpected Earnings) on its earnings disclosure date; NaN elsewhere.

    SUE = (EPS_t - EPS_{t-4}) / |EPS_{t-4}|   (year-over-year quarterly surprise).
    Dated at  fiscal_period_end + report_date_lag  to prevent look-ahead.

    Consumers should forward-fill for N days post-event to carry the signal.
    """

    name = "earnings_surprise"

    def __init__(self, report_date_lag: int = 45) -> None:
        self._lag_days = report_date_lag
        from app.services.fmp_client import FMPClient
        self._fmp = FMPClient()

    async def get_signal_frame(
        self, db: Session, symbol: str, start: date, end: date
    ) -> pd.Series:
        sym = symbol.upper()
        try:
            # Use quarterly income statements (limit=20 ~ 5 years)
            income = await self._fmp.get_income_statement(sym, limit=20)
        except Exception as exc:
            logger.warning("EarningsEventSignalProvider: FMP failed for %s: %s", sym, exc)
            return pd.Series(dtype=float)

        if not income:
            return pd.Series(dtype=float)

        def _eps(row: dict) -> Optional[float]:
            for k in ("eps", "epsDiluted", "earningsPerShareBasic"):
                v = row.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass
            return None

        # Sort oldest→newest; use yoy comparison (4-quarter lag for quarterly data)
        records = [(r, _to_date(r.get("date")), _eps(r)) for r in income]
        records = [(r, d, e) for r, d, e in records if d is not None]
        records.sort(key=lambda x: x[1])

        sue_records: list[tuple[pd.Timestamp, float]] = []
        eps_by_period = [(d, eps) for _, d, eps in records]

        for i in range(4, len(eps_by_period)):
            period_end, curr_eps = eps_by_period[i]
            _, prior_eps = eps_by_period[i - 4]  # year-ago quarter
            if curr_eps is None or prior_eps is None or prior_eps == 0:
                continue
            sue = (curr_eps - prior_eps) / abs(prior_eps)
            disclosure_ts = pd.Timestamp(period_end + timedelta(days=self._lag_days))
            if start <= disclosure_ts.date() <= end:
                sue_records.append((disclosure_ts, sue))

        if not sue_records:
            return pd.Series(dtype=float)

        idx, vals = zip(*sue_records)
        return pd.Series(list(vals), index=list(idx), name=self.name)


# ── Insider Signal Provider ───────────────────────────────────────────────────

class InsiderSignalProvider(SignalProvider):
    """
    Returns the rolling 30-day net insider-buy in dollars for a symbol.

    Data source: FMP /insider-trading endpoint (requires FMP key).
    Falls back to an empty Series if the endpoint is unavailable.

    Convention: positive = net buying, negative = net selling.
    """

    name = "insider_net_buy"

    def __init__(self) -> None:
        from app.services.fmp_client import FMPClient
        self._fmp = FMPClient()

    async def get_signal_frame(
        self, db: Session, symbol: str, start: date, end: date
    ) -> pd.Series:
        sym = symbol.upper()
        try:
            # FMP insider-trading endpoint returns a list of transactions
            data = await self._fmp._get(
                "/insider-trading",
                {"symbol": sym, "limit": 200},
            )
        except Exception as exc:
            logger.warning(
                "InsiderSignalProvider: FMP insider-trading failed for %s: %s", sym, exc
            )
            return pd.Series(dtype=float)

        if not data or not isinstance(data, list):
            return pd.Series(dtype=float)

        records: list[tuple[pd.Timestamp, float]] = []
        for row in data:
            tx_date = _to_date(row.get("transactionDate") or row.get("filingDate"))
            if tx_date is None or not (start <= tx_date <= end):
                continue
            tx_type = (row.get("transactionType") or "").upper()
            shares = row.get("securitiesTransacted") or 0
            price  = row.get("price") or row.get("reportedPrice") or 0
            net_value = float(shares) * float(price)
            # Purchases positive, sales negative
            if "SALE" in tx_type or "S-" in tx_type:
                net_value = -abs(net_value)
            else:
                net_value = abs(net_value)
            records.append((pd.Timestamp(tx_date), net_value))

        if not records:
            return pd.Series(dtype=float)

        records.sort(key=lambda x: x[0])
        idx, vals = zip(*records)
        series = pd.Series(list(vals), index=list(idx), name=self.name)
        # Rolling 30-day net buy (sum of transactions in trailing 30 days)
        return series.rolling("30D").sum()


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, SignalProvider] = {
    # Fundamental
    "fcf_yield":        FundamentalSignalProvider("fcf_yield"),
    "book_to_market":   FundamentalSignalProvider("book_to_market"),
    "ebitda_ev":        FundamentalSignalProvider("ebitda_ev"),
    "f_score":          FundamentalSignalProvider("f_score"),
    "buyback_yield_ttm":     FundamentalSignalProvider("buyback_yield_ttm"),
    "estimate_revision_3m":  FundamentalSignalProvider("estimate_revision_3m"),
    # Sentiment
    "sentiment_score":  SentimentSignalProvider(),
    # Events
    "earnings_surprise": EarningsEventSignalProvider(),
    # Insider
    "insider_net_buy":  InsiderSignalProvider(),
}

# PRD-16a-2 — fold ~46 technical-indicator providers into the registry
# lazily. We can't import `technical_signal_providers` at module-top
# because that module imports `SignalProvider` from this file — circular.
# Instead, the FIRST `get_signal_provider()` call (or anyone reading
# `_REGISTRY`) ensures the technical providers are registered. Subsequent
# calls are no-ops (the flag short-circuits).

_TECHNICAL_PROVIDERS_REGISTERED: bool = False


def _ensure_technical_providers_registered() -> None:
    """Fold the technical providers into `_REGISTRY` on first need.
    Idempotent — the flag prevents re-import."""
    global _TECHNICAL_PROVIDERS_REGISTERED
    if _TECHNICAL_PROVIDERS_REGISTERED:
        return
    _TECHNICAL_PROVIDERS_REGISTERED = True  # set BEFORE the import to
    # short-circuit any re-entry mid-import (defense for the same kind
    # of cycle we hit before).
    from app.services.backtester.technical_signal_providers import (
        get_technical_providers,
    )
    for name, provider in get_technical_providers().items():
        if name not in _REGISTRY:
            _REGISTRY[name] = provider


def get_signal_provider(name: str) -> SignalProvider:
    """
    Return the registered SignalProvider for *name*.

    Raises KeyError when the name is not registered.  Use this instead of
    instantiating providers directly so that configuration (lag days, etc.)
    is centralised.

    Triggers lazy registration of PRD-16a-2's technical providers on
    first call (no-op after that). Same-loaded module, same `_REGISTRY`
    dict — the trick avoids the circular-import that would happen if we
    tried to register at module-top.
    """
    _ensure_technical_providers_registered()
    try:
        return _REGISTRY[name]
    except KeyError:
        supported = sorted(_REGISTRY)
        raise KeyError(
            f"Unknown signal provider '{name}'. Supported: {supported}"
        ) from None


def all_registered_provider_names() -> list[str]:
    """Helper for tests / introspection. Triggers the lazy-registration
    side effect so callers see the full registry."""
    _ensure_technical_providers_registered()
    return sorted(_REGISTRY.keys())
