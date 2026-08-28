"""PRD-43b P0 — the numeric core: split-framed bars, markouts, excursions.

Three things in here are marked *mandatory* by §6, and each corresponds to a
way this engine can produce a confident wrong number rather than an error:

- a markout spanning a split, which reports the split as the return;
- a same-day episode given an MAE invented from the day's range;
- an exit markout whose sign is not inverted, which grades good exits as bad.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.mirror.reconstruction import build_episodes
from app.services.timing.bars import BarSeries
from app.services.timing.excursion import excursion
from app.services.timing.markout import (
    MARKOUT_HORIZONS,
    aggregate_markouts,
    fill_markouts,
)


def _series(closes, *, start=date(2026, 1, 5), symbol="NVDA", splits=None,
            highs=None, lows=None):
    """Consecutive WEEKDAY bars. Weekends are skipped so that any test which
    accidentally measures calendar days instead of trading days fails."""
    rows, d = [], start
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        rows.append({
            "trading_date": d,
            "open": c, "close": c,
            "high": highs[i] if highs else c,
            "low": lows[i] if lows else c,
            "volume": 1_000_000,
            "split_coefficient": (splits or {}).get(i, 1.0),
        })
        d += timedelta(days=1)
    return BarSeries.from_rows(symbol, rows)


def _t(kind, symbol, units, price, day, *, account="a1"):
    return {"account_id": account, "type": kind, "symbol": symbol,
            "units": units, "price": price, "fee": 0.0, "trade_date": day}


# ── the split frame ─────────────────────────────────────────────────────────


def test_with_no_splits_the_adjusted_series_is_the_raw_series():
    s = _series([100.0, 101.0, 102.0])
    assert [s.close(i) for i in range(3)] == [100.0, 101.0, 102.0]
    assert s.restate(100.0, s.dates[0]) == 100.0


def test_bars_BEFORE_a_split_are_restated_into_the_post_split_frame():
    """`split_coefficient` on a bar means the split took effect THAT day, so
    it applies to every bar strictly before it — the same rule the ledger uses
    (`portfolio_ledger_service._apply_splits`), deliberately not a second one."""
    s = _series([1000.0, 1000.0, 100.0, 101.0], splits={2: 10.0})
    assert [s.close(i) for i in range(4)] == [100.0, 100.0, 100.0, 101.0]


def test_a_fill_price_is_restated_into_the_SAME_frame_as_the_bars():
    """The half everyone forgets. Adjusting the series alone and comparing it
    to a raw fill price is exactly as wrong as not adjusting at all."""
    s = _series([1000.0, 1000.0, 100.0, 101.0], splits={2: 10.0})
    assert s.restate(1000.0, s.dates[0]) == 100.0     # pre-split fill
    assert s.restate(101.0, s.dates[3]) == 101.0      # post-split fill


def test_horizons_are_TRADING_days_off_the_bar_index_not_calendar_days():
    """SnapTrade gives a date with no timestamp, so every horizon is an index
    offset. A calendar-day implementation lands on a weekend and either
    returns nothing or silently reads the wrong bar."""
    s = _series([10.0] * 8, start=date(2026, 1, 8))   # Thu; spans a weekend
    i = s.pos(date(2026, 1, 8))
    assert s.dates[i + 1] == date(2026, 1, 9)         # Fri
    assert s.dates[i + 2] == date(2026, 1, 12)        # Mon, not Sat


# ── markout ─────────────────────────────────────────────────────────────────


def test_entry_markout_is_the_plain_forward_return():
    s = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    m = fill_markouts(s, s.dates[0], 100.0, side="entry")
    assert round(m.markouts[1], 6) == 0.01
    assert round(m.markouts[3], 6) == 0.03
    assert round(m.markouts[5], 6) == 0.05


def test_EXIT_markout_is_NEGATED_because_a_rise_after_you_sell_is_a_bad_exit():
    """§6 calls this 'the one everyone gets backwards'. Same bars, same fill,
    opposite sign — and the sign is the entire meaning of the number."""
    s = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    entry = fill_markouts(s, s.dates[0], 100.0, side="entry")
    exit_ = fill_markouts(s, s.dates[0], 100.0, side="exit")
    assert round(entry.markouts[5], 6) == 0.05
    assert round(exit_.markouts[5], 6) == -0.05


def test_a_markout_spanning_a_SPLIT_matches_the_unsplit_equivalent():
    """MANDATORY (§6). A 10:1 split inside a 5-day window, priced raw, reports
    roughly −90% — a timing catastrophe that never happened, landing in the
    aggregate profile as if it were a decision."""
    plain = _series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    split = _series([1000.0, 1010.0, 102.0, 103.0, 104.0, 105.0], splits={2: 10.0})

    got = fill_markouts(split, split.dates[0], 1000.0, side="entry")
    want = fill_markouts(plain, plain.dates[0], 100.0, side="entry")
    assert round(got.markouts[5], 9) == round(want.markouts[5], 9) == 0.05

    # And the number the naive path would have produced, so the fixture is
    # proven to actually exercise the split.
    naive = (split.close(5) - 1000.0) / 1000.0
    assert naive < -0.85


def test_a_horizon_past_the_end_of_the_series_is_EXCLUDED_and_counted():
    """Never truncated to the last available bar — that silently turns a 20-day
    markout into a 6-day one and reports it in the 20-day row."""
    s = _series([100.0] * 7)
    m = fill_markouts(s, s.dates[0], 100.0, side="entry")
    assert m.markouts[5] == 0.0
    assert m.markouts[10] is None
    assert m.markouts[20] is None
    assert m.unavailable[20] == "beyond_window"


def test_a_fill_on_a_non_trading_day_anchors_to_the_next_bar():
    s = _series([100.0] * 6, start=date(2026, 1, 8))
    m = fill_markouts(s, date(2026, 1, 10), 100.0, side="entry")   # Saturday
    assert m.anchor_date == date(2026, 1, 12)


# ── the aggregate profile ───────────────────────────────────────────────────


def test_the_profile_reports_N_and_QUARTILES_at_every_horizon():
    """The v1 exploratory script omitted both, which is precisely what let a
    noise profile read as a finding — the audit's #1 defect."""
    s = _series([100.0] * 25)
    rows = [fill_markouts(s, s.dates[0], 100.0, side="entry") for _ in range(5)]
    prof = aggregate_markouts(rows)
    by_h = {h.horizon: h for h in prof.horizons}
    assert set(by_h) == set(MARKOUT_HORIZONS)
    assert by_h[1].n == 5
    assert by_h[1].q1 is not None and by_h[1].q3 is not None


def test_the_profile_uses_MEDIANS_so_one_outlier_cannot_define_it():
    s = _series([100.0, 101.0] + [100.0] * 23)
    normal = [fill_markouts(s, s.dates[0], 100.0, side="entry") for _ in range(4)]
    huge = _series([100.0, 500.0] + [100.0] * 23)
    normal.append(fill_markouts(huge, huge.dates[0], 100.0, side="entry"))
    prof = aggregate_markouts(normal)
    by_h = {h.horizon: h for h in prof.horizons}
    assert round(by_h[1].median, 6) == 0.01          # not the 4.0 outlier


def test_a_profile_whose_quartiles_straddle_zero_everywhere_reports_NO_PATTERN():
    """The first real account looked like this: medians of −0.03/−1.45/−1.32/
    −0.45/+1.01% with interquartile ranges of ±5–10%. A legitimate and probably
    common outcome, and the surface must be able to say so rather than let a
    diagnosis be read out of the medians alone."""
    rows = []
    for direction in (1, -1):
        for mag in (0.02, 0.08):
            s = _series([100.0] + [100.0 * (1 + direction * mag)] * 24)
            rows.append(fill_markouts(s, s.dates[0], 100.0, side="entry"))
    prof = aggregate_markouts(rows)
    assert all(h.straddles_zero for h in prof.horizons)
    assert prof.has_consistent_pattern is False


# ── excursion ───────────────────────────────────────────────────────────────


def _one_episode(txns):
    eps, excl = build_episodes(txns)
    assert not excl, excl
    assert len(eps) == 1
    return eps[0]


def test_MAE_is_never_positive_and_MFE_is_never_negative():
    s = _series([100.0] * 6, highs=[100, 108, 104, 101, 100, 100],
                lows=[100, 96, 92, 99, 100, 100])
    ep = _one_episode([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 100.0, "2026-01-12"),
    ])
    ex = excursion(s, ep)
    assert ex.mae <= 0 <= ex.mfe


def test_a_SAME_DAY_round_trip_has_no_computable_excursion():
    """MANDATORY (§6). Opened and closed inside one session: we know the daily
    range and nothing about where inside it the user was. The range is an upper
    bound on the possible, not a measurement of the experienced — and a −8% MAE
    invented for a position held twenty minutes would propagate straight into
    the winner-vs-loser gap that stop parameters get read from."""
    s = _series([100.0], highs=[130.0], lows=[70.0])
    ep = _one_episode([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 101.0, "2026-01-05"),
    ])
    ex = excursion(s, ep)
    assert ex.mae is None and ex.mfe is None
    assert ex.excluded_reason == "intraday_resolution_required"
    assert ex.profit_capture is None
    # Prove it was not quietly computed from that day's range.
    assert ex.mae != pytest.approx(-0.30)
    assert ex.mfe != pytest.approx(0.30)


def test_an_episode_spanning_a_SPLIT_yields_the_unsplit_excursion():
    """MANDATORY (§6). `high`/`low` are RAW in `price_bars` — `adjusted_close`
    does not help here, which is what makes this the easiest one to miss."""
    plain = _series([100.0] * 5, highs=[100, 110, 105, 100, 100],
                    lows=[100, 90, 95, 100, 100])
    split = _series([100.0] * 5, splits={2: 10.0},
                    highs=[1000, 1100, 105, 100, 100],
                    lows=[1000, 900, 95, 100, 100])
    txns = [_t("BUY", "NVDA", 10, 1000.0, "2026-01-05"),
            _t("SELL", "NVDA", 10, 100.0, "2026-01-09")]
    got = excursion(split, _one_episode(txns))
    want = excursion(plain, _one_episode([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 100.0, "2026-01-09")]))
    assert round(got.mae, 9) == round(want.mae, 9) == -0.10
    assert round(got.mfe, 9) == round(want.mfe, 9) == 0.10


def test_profit_capture_is_None_for_losers_and_never_zero():
    """Zero is a real value meaning 'captured nothing'; None means 'undefined'.
    Collapsing them puts every loser into the capture average at 0.0."""
    s = _series([100.0] * 5, highs=[100] * 5, lows=[100, 90, 90, 90, 90])
    ep = _one_episode([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 92.0, "2026-01-09"),
    ])
    ex = excursion(s, ep)
    assert ex.profit_capture is None


def test_profit_capture_is_realised_over_MFE_for_a_winner():
    s = _series([100.0] * 5, highs=[100, 120, 110, 105, 105], lows=[100] * 5)
    ep = _one_episode([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 110.0, "2026-01-09"),
    ])
    ex = excursion(s, ep)
    assert round(ex.mfe, 6) == 0.20
    assert round(ex.profit_capture, 6) == 0.5      # took 10 of an available 20


def test_precision_is_approximate_when_the_extreme_lands_on_a_BOUNDARY_bar():
    """The entry day's low and the exit day's high are only partially inside
    the holding window — the user was not in the position for all of either."""
    s = _series([100.0] * 4, highs=[100, 100, 100, 130], lows=[100] * 4)
    ep = _one_episode([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 100.0, "2026-01-08"),
    ])
    assert excursion(s, ep).precision == "approximate_boundary"


def test_precision_is_exact_when_both_extremes_land_on_INTERIOR_bars():
    s = _series([100.0] * 4, highs=[100, 115, 100, 100], lows=[100, 100, 85, 100])
    ep = _one_episode([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 100.0, "2026-01-08"),
    ])
    assert excursion(s, ep).precision == "exact"
