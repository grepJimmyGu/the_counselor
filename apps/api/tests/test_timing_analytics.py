"""PRD-43b §3.2.1 / §3.3 — anchoring, roles, and the type boundary.

The anchoring rule is the one that decides whether every markout in the engine
describes a decision the user actually made.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.mirror.reconstruction import build_episodes
from app.services.timing.analytics import (
    ADD_ON, FINAL_EXIT, OPENING_ENTRY, PARTIAL_EXIT, analyse_episode,
)
from app.services.timing.bars import BarSeries


def _series(closes, start=date(2026, 1, 5), symbol="NVDA"):
    rows, d = [], start
    for c in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        rows.append({"trading_date": d, "open": c, "high": c, "low": c,
                     "close": c, "volume": 1_000_000, "split_coefficient": 1.0})
        d += timedelta(days=1)
    return BarSeries.from_rows(symbol, rows)


def _t(kind, symbol, units, price, day):
    return {"account_id": "a1", "type": kind, "symbol": symbol, "units": units,
            "price": price, "fee": 0.0, "trade_date": day}


def _one(txns):
    eps, excl = build_episodes(txns)
    assert not excl, excl
    return eps[0]


def test_a_two_buy_episode_yields_TWO_entry_markouts_from_DIFFERENT_prices():
    """MANDATORY (§6). An episode with buys on two dates is two decisions. The
    weighted-average cost is one number and it belongs to the position, not to
    either moment."""
    closes = [100.0] * 30
    closes[3] = 110.0        # +3 trading days from the first buy
    closes[13] = 132.0       # +3 trading days from the second buy
    series = _series(closes)
    first, second = series.dates[0], series.dates[10]

    ep = _one([
        _t("BUY", "NVDA", 100, 100.0, first.isoformat()),
        _t("BUY", "NVDA", 50, 120.0, second.isoformat()),
        _t("SELL", "NVDA", 150, 130.0, series.dates[25].isoformat()),
    ])
    a = analyse_episode(ep, series, with_state=False)

    entries = a.entries
    assert [f.role for f in entries] == [OPENING_ENTRY, ADD_ON]
    assert [f.fill_price for f in entries] == [100.0, 120.0]
    assert round(entries[0].markouts[3], 6) == 0.10      # 110 off 100
    assert round(entries[1].markouts[3], 6) == 0.10      # 132 off 120

    # The weighted average is 106.67. If ANY markout were anchored to it at the
    # first fill's date, the opening entry's 3-day markout would be ~3.1%.
    blended = ep.avg_entry_price
    assert round(blended, 2) == 106.67
    naive = (110.0 - blended) / blended
    assert all(
        abs(f.markouts[3] - naive) > 1e-6 for f in entries
    ), "a markout was anchored to the weighted-average price"


def test_the_weighted_average_still_governs_the_EXCURSION():
    """The blend is correct for the position's own properties — MAE/MFE and
    P/L — and wrong only for timing. Both halves of §3.2.1 matter."""
    series = _series([100.0] * 30)
    ep = _one([
        _t("BUY", "NVDA", 100, 100.0, series.dates[0].isoformat()),
        _t("BUY", "NVDA", 50, 120.0, series.dates[10].isoformat()),
        _t("SELL", "NVDA", 150, 130.0, series.dates[25].isoformat()),
    ])
    a = analyse_episode(ep, series, with_state=False)
    # Flat 100 series against a 106.67 blended cost: the whole window is under
    # water relative to the blend, which is exactly what the position experienced.
    assert a.mae < 0
    assert round(a.mae, 4) == round((100.0 - ep.avg_entry_price) / ep.avg_entry_price, 4)


def test_exit_roles_distinguish_a_scale_out_from_the_close():
    series = _series([100.0] * 30)
    ep = _one([
        _t("BUY", "NVDA", 150, 100.0, series.dates[0].isoformat()),
        _t("SELL", "NVDA", 50, 110.0, series.dates[5].isoformat()),
        _t("SELL", "NVDA", 100, 120.0, series.dates[10].isoformat()),
    ])
    a = analyse_episode(ep, series, with_state=False)
    assert [f.role for f in a.exits] == [PARTIAL_EXIT, FINAL_EXIT]


def test_an_OPEN_episode_has_no_final_exit():
    series = _series([100.0] * 30)
    ep = _one([
        _t("BUY", "NVDA", 150, 100.0, series.dates[0].isoformat()),
        _t("SELL", "NVDA", 50, 110.0, series.dates[5].isoformat()),
    ])
    a = analyse_episode(ep, series, with_state=False)
    assert a.final_exit is None
    assert [f.role for f in a.exits] == [PARTIAL_EXIT]


def test_per_episode_aggregates_read_the_OPENING_entry():
    """Averaging in is a different behaviour from opening a position, and the
    entry-timing profile is mostly a statement about openings."""
    series = _series([100.0] * 30)
    ep = _one([
        _t("BUY", "NVDA", 100, 100.0, series.dates[0].isoformat()),
        _t("BUY", "NVDA", 50, 120.0, series.dates[10].isoformat()),
        _t("SELL", "NVDA", 150, 130.0, series.dates[25].isoformat()),
    ])
    a = analyse_episode(ep, series, with_state=False)
    assert a.opening_entry.fill_price == 100.0
    assert a.opening_entry.fill_date == series.dates[0]


def test_a_same_day_episode_keeps_its_markouts_but_loses_its_excursion():
    """The two measurements have different requirements: a markout only needs
    the fill price and later closes, which a same-day round trip has. The
    excursion needs to know where inside the day the user was, which it does
    not. Dropping both would throw away a real measurement."""
    series = _series([100.0, 104.0, 106.0, 108.0, 110.0, 112.0])
    day = series.dates[0].isoformat()
    ep = _one([
        _t("BUY", "NVDA", 10, 100.0, day),
        _t("SELL", "NVDA", 10, 101.0, day),
    ])
    a = analyse_episode(ep, series, with_state=False)
    assert a.mae is None and a.mfe is None
    assert a.excluded_reason == "intraday_resolution_required"
    assert a.opening_entry.markouts[3] is not None
