"""Market-level price series must refresh on a schedule, and heal gaps.

Symptom (2026-11-17): `/api/market/data-latency` reported `very_stale`,
1,680 hours — ^GSPC last bar 2026-09-10, sector ETFs as old as 2026-09-08.

Root cause: the index and the Market Pulse ETFs were refreshed only by the
startup warmups. The last deploy was 2026-09-10, so nothing had refreshed
them since except a user happening to open one. And because the index
refresh always asked for "the last 30 days", the next startup would have
left a hole from 2026-09-11 to mid-October that nothing would ever fill.

Fix: a scheduled daily refresh, and a refresh window that starts from the
last stored bar when that is further back than 30 days.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import app.main as m


def test_refresh_starts_30_days_back_when_the_index_is_current():
    today = date(2026, 11, 17)
    assert m._gspc_refresh_start(date(2026, 11, 14), today) == today - timedelta(days=30)


def test_refresh_reaches_back_to_the_last_stored_bar_after_a_long_gap():
    """The regression: with the index stuck on 2026-09-10, asking for the
    last 30 days would start on 2026-10-18 and leave five weeks missing."""
    today = date(2026, 11, 17)
    assert m._gspc_refresh_start(date(2026, 9, 10), today) == date(2026, 9, 10)


def test_refresh_of_an_empty_index_takes_the_default_window():
    today = date(2026, 11, 17)
    assert m._gspc_refresh_start(None, today) == today - timedelta(days=30)


def test_the_refresh_is_scheduled_for_every_trading_day():
    scheduler = MagicMock()
    with patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=scheduler):
        m._start_scheduler()

    jobs = {call.kwargs.get("id"): call for call in scheduler.add_job.call_args_list}
    assert "market_data_refresh" in jobs, "the daily market-data refresh is not scheduled"
    job = jobs["market_data_refresh"]
    assert job.args[0] is m.refresh_market_data_job
    assert job.kwargs["day_of_week"] == "mon-fri"
    # After the US close, in the exchange's own time zone.
    assert job.kwargs["timezone"] == "America/New_York"
    assert job.kwargs["hour"] >= 17
    scheduler.start.assert_called_once()


def test_the_job_refreshes_the_etfs_and_then_the_index():
    order: list[str] = []
    etfs = AsyncMock(side_effect=lambda: order.append("etfs"))
    gspc = AsyncMock(side_effect=lambda: order.append("gspc"))
    with patch.object(m, "_warmup_market_etfs", etfs), patch.object(m, "_warmup_gspc", gspc):
        m.refresh_market_data_job()
    assert order == ["etfs", "gspc"]


def test_a_failing_refresh_does_not_raise_into_the_scheduler():
    with patch.object(m, "_warmup_market_etfs", AsyncMock(side_effect=RuntimeError("AV down"))):
        m.refresh_market_data_job()  # logged, not raised
