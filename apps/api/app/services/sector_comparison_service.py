"""Sector vs SPY cumulative-return comparison series — Phase 1d.

Powers the inline expansion under each sector tile in the Market Pulse
sector heatmap (`SectorComparisonChart.tsx`). Returns a normalized
cumulative-return series for a `(sector_etf, SPY)` pair over a requested
window, plus the totals used by the "Returns table" beneath the chart.

All data sourced from the `price_bars` table — no external API calls at
request time. The 3-yr (~756 trading days) `1Y` warmup window
established by the existing market-pulse warmup pipeline is sufficient
for 1M / 6M / YTD / 1Y / 3Y windows; longer requested ranges (5Y / MAX)
silently clamp to "all available bars" without erroring.

Caching: not added in this service. The route layer applies a small
in-memory cache (~5 min) so the same `(symbol, range)` hit twice in
quick succession (sector tile re-click) doesn't re-query the DB.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar

_log = logging.getLogger("livermore.sector_comparison")

# **2026-05-22 — index-vs-index benchmark.** The chart label reads "VS.
# S&P 500"; previously we paired the sector ETF against SPY (the ETF
# tracking the index). Now we benchmark against ^GSPC (the actual
# index). If ^GSPC isn't backfilled yet (`price_bars` has zero rows in
# the requested window), we transparently fall back to SPY + log a
# WARN so the chart never breaks. Run `apps/api/scripts/backfill_gspc.py`
# to populate the price_bars table from FMP's historical EOD endpoint
# and the fallback path stops firing.
_BENCHMARK_PRIMARY = "^GSPC"
_BENCHMARK_FALLBACK = "SPY"


# Trading-day approximations for the supported windows. Calendar-day
# conversion (used to compute the cutoff date for each window) is in
# `_cutoff_for_range`; the trading-day numbers are only used to size the
# query bound + the YTD calculation when "YTD" is requested.
_RANGE_TRADING_DAYS: dict[str, int] = {
    "1M": 22,
    "6M": 130,
    "YTD": 0,       # special-cased — computed from start of current year
    "1Y": 252,
    "3Y": 756,
}

_RANGE_TO_DAYS_LOOKBACK: dict[str, int] = {
    "1M": 30,
    "6M": 183,
    "1Y": 365,
    "3Y": 1095,
}


@dataclass
class ReturnPoint:
    """One point on the chart — date + sector cumulative return + SPY
    cumulative return, both as decimal fractions (0.082 = +8.2%)."""
    date: str           # ISO date "YYYY-MM-DD"
    sector: float
    spy: float


@dataclass
class SectorComparisonResponse:
    symbol: str
    sector_name: str
    range: str          # "1M" | "6M" | "YTD" | "1Y" | "3Y"
    series: list[ReturnPoint] = field(default_factory=list)
    # Totals used by the per-row PerfCell columns in the returns table.
    # `None` if insufficient bars for that window.
    sector_day: Optional[float] = None
    sector_ytd: Optional[float] = None
    sector_1y: Optional[float] = None
    sector_3y: Optional[float] = None
    spy_day: Optional[float] = None
    spy_ytd: Optional[float] = None
    spy_1y: Optional[float] = None
    spy_3y: Optional[float] = None


def _cutoff_for_range(range_: str, today: date) -> date:
    """Return the start-date cutoff for the requested window.

    For YTD: the start of the current calendar year.
    For everything else: today minus the calendar-day approximation
    from `_RANGE_TO_DAYS_LOOKBACK` (1M=30, 6M=183, 1Y=365, 3Y=1095). The
    overshoot vs the trading-day target is intentional — DB rows are
    filtered by `trading_date >= cutoff` and then truncated by the
    actual returned series, so a slight over-fetch is harmless.
    """
    if range_ == "YTD":
        return date(today.year, 1, 1)
    return today - timedelta(days=_RANGE_TO_DAYS_LOOKBACK[range_])


def _fetch_series(
    db: Session, symbol: str, cutoff: date
) -> list[tuple[date, float]]:
    """Return `[(trading_date, adj_close), ...]` ascending, filtered to
    `trading_date >= cutoff`. Empty list if no bars match."""
    rows = (
        db.execute(
            select(PriceBar.trading_date, PriceBar.adjusted_close)
            .where(PriceBar.symbol == symbol)
            .where(PriceBar.trading_date >= cutoff)
            .order_by(PriceBar.trading_date.asc())
        ).fetchall()
    )
    return [(r[0], float(r[1])) for r in rows if r[1] is not None]


def _cum_returns(prices: list[float]) -> list[float]:
    """Normalize a price series to cumulative return from start
    (returns[0] = 0)."""
    if not prices:
        return []
    base = prices[0]
    if base <= 0:
        return [0.0] * len(prices)
    return [p / base - 1.0 for p in prices]


def _perf_n_days(prices_asc: list[float], n: int) -> Optional[float]:
    """Return `prices[-1] / prices[-(n+1)] - 1` if enough bars; else None."""
    if len(prices_asc) < n + 1:
        return None
    base = prices_asc[-(n + 1)]
    if base <= 0:
        return None
    return prices_asc[-1] / base - 1.0


def _perf_since(prices_asc: list[float], dates_asc: list[date], since: date) -> Optional[float]:
    """Return cumulative return from the first bar on/after `since` to
    the latest bar. None if no bar is past `since`."""
    if not prices_asc:
        return None
    # First bar at-or-after the cutoff
    base_price: Optional[float] = None
    for d, p in zip(dates_asc, prices_asc):
        if d >= since:
            base_price = p
            break
    if base_price is None or base_price <= 0:
        return None
    return prices_asc[-1] / base_price - 1.0


# ── Sector → display name lookup ────────────────────────────────────────────
# Mirrors `US_SECTORS` / `CN_SECTORS` in `market_pulse_service.py`. Kept
# local so this service can render a good label without taking a runtime
# dep on that module.
_SECTOR_NAMES: dict[str, str] = {
    "XLK":  "Technology",
    "XLC":  "Communication",
    "XLY":  "Consumer Disc.",
    "XLP":  "Consumer Staples",
    "XLV":  "Healthcare",
    "XLF":  "Financials",
    "XLI":  "Industrials",
    "XLE":  "Energy",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLU":  "Utilities",
    "KWEB": "CN Internet",
    "FXI":  "CN Large Cap",
    "MCHI": "CN Broad",
    "CQQQ": "CN Tech",
    "FLCH": "CN Financials",
    "CHIE": "CN Energy",
    "CNYA": "CN A-Shares",
}


# How far behind the series it is charted against the index may be before
# it is treated as stale. Covers a long weekend plus a holiday; anything
# more is a refresh that has stopped, not a calendar gap.
_BENCHMARK_MAX_LAG_DAYS = 5


def _load_benchmark(
    db: Session, cutoff: date, need_through: Optional[date] = None
) -> tuple[str, list[tuple[date, float]]]:
    """Return `(symbol, bars)` for the S&P 500 benchmark series.

    Tries `^GSPC` first (the actual index) and falls back to `SPY` (the
    ETF proxy) when ^GSPC cannot do the job:

      - it has no bars in the window, or
      - it is STALE: `need_through` is the last date of the series it will
        be charted against, and ^GSPC stops more than
        `_BENCHMARK_MAX_LAG_DAYS` before it.

    The second case matters because the chart keeps only dates both series
    share. A benchmark that stopped updating does not merely look old — it
    silently truncates the other line to its own last date (2026-11: the
    index refresh had not run since 2026-09-10, so every sector chart ended
    there and read months out of date while the table beside it was right).

    Logs at WARN on either fallback so the operator knows.
    """
    bars = _fetch_series(db, _BENCHMARK_PRIMARY, cutoff)
    stale = bool(
        bars and need_through is not None
        and (need_through - bars[-1][0]).days > _BENCHMARK_MAX_LAG_DAYS
    )
    if bars and not stale:
        return _BENCHMARK_PRIMARY, bars

    fallback = _fetch_series(db, _BENCHMARK_FALLBACK, cutoff)
    if fallback and (not bars or fallback[-1][0] > bars[-1][0]):
        if stale:
            _log.warning(
                "sector_comparison: %s is stale (last bar %s, needed through %s); "
                "using %s. The index refresh has stopped — see "
                "app.main._warmup_gspc / refresh_market_data_job.",
                _BENCHMARK_PRIMARY, bars[-1][0].isoformat(),
                need_through.isoformat() if need_through else "?", _BENCHMARK_FALLBACK,
            )
        else:
            _log.warning(
                "sector_comparison: %s has no bars in window cutoff=%s; "
                "falling back to %s. Run apps/api/scripts/backfill_gspc.py "
                "to populate the index series.",
                _BENCHMARK_PRIMARY, cutoff.isoformat(), _BENCHMARK_FALLBACK,
            )
        return _BENCHMARK_FALLBACK, fallback
    if bars:
        # Stale, and the ETF is no fresher: the index is still the better
        # label for what is on the chart.
        return _BENCHMARK_PRIMARY, bars
    return _BENCHMARK_FALLBACK, fallback


def get_comparison(
    db: Session, symbol: str, range_: str
) -> SectorComparisonResponse:
    """Build a (sector, SPY) cumulative-return comparison response.

    `range_` is one of: 1M / 6M / YTD / 1Y / 3Y. Anything else falls
    back to 1Y. Returns an empty `series` when either symbol has no
    bars within the window — caller decides how to render that.
    """
    if range_ not in _RANGE_TO_DAYS_LOOKBACK and range_ != "YTD":
        range_ = "1Y"

    sym = symbol.upper()
    today = date.today()
    cutoff = _cutoff_for_range(range_, today)

    sector_bars = _fetch_series(db, sym, cutoff)
    benchmark_sym, benchmark_bars = _load_benchmark(
        db, cutoff, need_through=sector_bars[-1][0] if sector_bars else None
    )

    # Align: only keep dates present in BOTH series so the indices line up.
    sector_by_date = {d: p for d, p in sector_bars}
    spy_by_date = {d: p for d, p in benchmark_bars}
    shared_dates = sorted(set(sector_by_date) & set(spy_by_date))

    sector_prices = [sector_by_date[d] for d in shared_dates]
    spy_prices = [spy_by_date[d] for d in shared_dates]

    sector_cum = _cum_returns(sector_prices)
    spy_cum = _cum_returns(spy_prices)

    series = [
        ReturnPoint(date=d.isoformat(), sector=round(s, 6), spy=round(sp, 6))
        for d, s, sp in zip(shared_dates, sector_cum, spy_cum)
    ]

    # Totals — computed from the FULL bar sets (not just the window) so
    # the returns table shows accurate Day / YTD / 1Y / 3Y regardless of
    # which window the chart is currently zoomed into.
    full_sector = _fetch_series(db, sym, date(today.year - 4, 1, 1))
    _, full_spy = _load_benchmark(
        db, date(today.year - 4, 1, 1),
        need_through=full_sector[-1][0] if full_sector else None,
    )

    s_dates = [d for d, _ in full_sector]
    s_prices = [p for _, p in full_sector]
    p_dates = [d for d, _ in full_spy]
    p_prices = [p for _, p in full_spy]

    ytd_start = date(today.year, 1, 1)

    sector_name = _SECTOR_NAMES.get(sym, sym)

    return SectorComparisonResponse(
        symbol=sym,
        sector_name=sector_name,
        range=range_,
        series=series,
        sector_day=_perf_n_days(s_prices, 1),
        sector_ytd=_perf_since(s_prices, s_dates, ytd_start),
        sector_1y=_perf_n_days(s_prices, _RANGE_TRADING_DAYS["1Y"]),
        sector_3y=_perf_n_days(s_prices, _RANGE_TRADING_DAYS["3Y"]),
        spy_day=_perf_n_days(p_prices, 1),
        spy_ytd=_perf_since(p_prices, p_dates, ytd_start),
        spy_1y=_perf_n_days(p_prices, _RANGE_TRADING_DAYS["1Y"]),
        spy_3y=_perf_n_days(p_prices, _RANGE_TRADING_DAYS["3Y"]),
    )
