"""Prices through the day, for the company page's 1D and 1W charts (2026-11-24).

Jimmy, 2026-11-24: the company page's price is live but its chart stops at
yesterday's close, so today's move can't be seen. This serves the regular
sessions behind two new chart ranges:

    1D  the latest session, in 5-minute bars
    1W  the latest five sessions, in 30-minute bars

Each comes with `previous_close`: the official close of the session before
the first one shown, which is what "today's change" and "this week's change"
are measured from. Completed sessions carry their own official close, so a
chart's day ends on the number the exchange printed rather than on the last
trade before 4 pm.

Sources, both FMP and both already used in production:
  - `/historical-chart/{5min,30min}` for the bars (`fetch_intraday_bars`);
  - `/historical-price-eod/full` for official closes (`get_historical_eod`).
If the closes can't be had, the session's last bar stands in for its close.

Only the regular session is kept (9:30 to 16:00 New York). FMP labels a bar
by its start, so the 15:55 bar is the day's last 5-minute bar.

Nothing here touches the database, so the route holds no connection while
FMP answers (trap 13). The caches are `TTLCache`, which keeps its asyncio
primitives per event loop (trap 22).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from app.core.concurrency import TTLCache
from app.services.fmp_client import FMPClient, FMPNoDataError

_log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)

# A minute: the app redraws the line every minute while a session is open,
# and many people on one stock then cost one FMP call a minute.
CHART_TTL_SECONDS = 60.0
# Official closes change once a day.
CLOSES_TTL_SECONDS = 30 * 60.0


@dataclass(frozen=True)
class RangeSpec:
    interval: str          # as `fetch_intraday_bars` takes it
    minutes: int
    sessions: int          # how many of the latest sessions to show
    lookback_days: int     # calendar days asked for: those sessions, the one
                           # before (for its close) and a long weekend


RANGES: Dict[str, RangeSpec] = {
    "1d": RangeSpec(interval="5min", minutes=5, sessions=1, lookback_days=7),
    "1w": RangeSpec(interval="30min", minutes=30, sessions=5, lookback_days=14),
}


class NoIntradayPrices(Exception):
    """FMP has no regular-session prices for this symbol."""


class IntradayUnavailable(Exception):
    """FMP could not be read."""


@dataclass(frozen=True)
class Bar:
    time: datetime         # the bar's start, UTC
    open: float
    close: float


@dataclass(frozen=True)
class Session:
    date: date
    bars: List[Bar]
    # The exchange's close for a session that has ended; None for today's.
    close: Optional[float] = None


@dataclass(frozen=True)
class IntradayChart:
    symbol: str
    range: str
    interval_minutes: int
    sessions: List[Session]
    previous_close: Optional[float]
    previous_close_date: Optional[date]
    # The end of the newest bar: how far the line goes.
    as_of: Optional[datetime] = None
    # Where `previous_close` came from: "official" or "last_bar".
    previous_close_source: Optional[str] = None


def _to_utc(et_wall_clock: datetime) -> datetime:
    return et_wall_clock.replace(tzinfo=ET).astimezone(timezone.utc)


def _regular_sessions(raw: List[dict]) -> Dict[date, List[dict]]:
    """FMP's bars grouped by New York date, regular hours only, oldest first."""
    by_day: Dict[date, List[dict]] = {}
    for row in sorted(raw, key=lambda r: r["bar_time"]):
        start: datetime = row["bar_time"]
        if start.weekday() >= 5 or not (SESSION_OPEN <= start.time() < SESSION_CLOSE):
            continue
        by_day.setdefault(start.date(), []).append(row)
    return by_day


def build_chart(
    symbol: str,
    range_key: str,
    raw_bars: List[dict],
    official_closes: Dict[date, float],
    today: date,
) -> IntradayChart:
    """The chart for `range_key` from FMP's bars (naive New York wall clock,
    as `fetch_intraday_bars` returns them) and official daily closes."""
    spec = RANGES[range_key]
    by_day = _regular_sessions(raw_bars)
    if not by_day:
        raise NoIntradayPrices(symbol)
    days = sorted(by_day)
    shown = days[-spec.sessions:]
    first = shown[0]

    # The close the first shown session is measured from. The session before
    # it is known from the bars when FMP sent it; the official close for that
    # day wins, and its last bar stands in when there is none.
    before = [d for d in days if d < first]
    previous_close: Optional[float] = None
    previous_date: Optional[date] = None
    source: Optional[str] = None
    if before:
        previous_date = before[-1]
        if previous_date in official_closes:
            previous_close, source = official_closes[previous_date], "official"
        else:
            previous_close, source = float(by_day[previous_date][-1]["close"]), "last_bar"
    else:
        # FMP sent only the sessions shown. Take the latest official close
        # before them, provided it is close enough to be the session just
        # before (Friday to Tuesday over a holiday weekend is four days).
        earlier = [d for d in official_closes if d < first and (first - d).days <= 4]
        if earlier:
            previous_date = max(earlier)
            previous_close, source = official_closes[previous_date], "official"

    sessions: List[Session] = []
    for day in shown:
        rows = by_day[day]
        bars = [Bar(time=_to_utc(r["bar_time"]), open=float(r["open"]), close=float(r["close"])) for r in rows]
        # Today's close isn't printed until the session ends; an earlier
        # day's is final.
        sessions.append(Session(date=day, bars=bars, close=official_closes.get(day) if day < today else None))

    newest = sessions[-1].bars[-1]
    return IntradayChart(
        symbol=symbol,
        range=range_key,
        interval_minutes=spec.minutes,
        sessions=sessions,
        previous_close=previous_close,
        previous_close_date=previous_date,
        as_of=newest.time + timedelta(minutes=spec.minutes),
        previous_close_source=source,
    )


class IntradayChartService:
    def __init__(
        self,
        client: Optional[Any] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._client = client or FMPClient()
        self._now = now or (lambda: datetime.now(ET))
        self._charts: TTLCache[IntradayChart] = TTLCache(ttl=CHART_TTL_SECONDS, max_entries=512)
        self._closes: TTLCache[Dict[date, float]] = TTLCache(
            ttl=CLOSES_TTL_SECONDS, max_entries=512, keep=bool,
        )

    async def chart(self, symbol: str, range_key: str) -> IntradayChart:
        if range_key not in RANGES:
            raise ValueError(f"Unknown range {range_key!r}")
        key: Tuple[str, str] = (symbol.strip().upper(), range_key)
        return await self._charts.get(key, lambda: self._load(*key))

    async def _load(self, symbol: str, range_key: str) -> IntradayChart:
        spec = RANGES[range_key]
        today = self._now().astimezone(ET).date()
        start = today - timedelta(days=spec.lookback_days)
        try:
            raw = await self._client.fetch_intraday_bars(
                symbol, interval=spec.interval, outputsize="full",
                from_date=start.isoformat(), to_date=today.isoformat(),
            )
        except FMPNoDataError as exc:
            raise NoIntradayPrices(symbol) from exc
        except Exception as exc:
            _log.warning("intraday chart: FMP bars failed for %s %s: %s", symbol, range_key, exc)
            raise IntradayUnavailable(symbol) from exc
        closes = await self._official_closes(symbol, today)
        return build_chart(symbol, range_key, raw, closes, today)

    async def _official_closes(self, symbol: str, today: date) -> Dict[date, float]:
        """The exchange's daily closes for the last three weeks, or {} when
        FMP won't give them (the chart then uses each day's last bar)."""
        async def load() -> Dict[date, float]:
            start = today - timedelta(days=21)
            rows = await self._client.get_historical_eod(symbol, start.isoformat(), today.isoformat())
            closes: Dict[date, float] = {}
            for row in rows or []:
                try:
                    closes[date.fromisoformat(str(row["date"])[:10])] = float(row["close"])
                except (KeyError, TypeError, ValueError):
                    continue
            return closes

        try:
            return await self._closes.get((symbol, today), load)
        except Exception as exc:
            _log.warning("intraday chart: official closes failed for %s: %s", symbol, exc)
            return {}


intraday_chart_service = IntradayChartService()
