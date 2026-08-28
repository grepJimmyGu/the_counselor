"""PRD-43b §3.6.3 / §3.7 — aggregates, the setup breakdown, the leak ranking."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.mirror.reconstruction import build_episodes
from app.services.timing.analytics import analyse_episode
from app.services.timing.bars import BarSeries
from app.services.timing.report import build_report


def _series(closes, highs=None, lows=None, start=date(2026, 1, 5)):
    rows, d = [], start
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        rows.append({"trading_date": d, "open": c, "close": c,
                     "high": highs[i] if highs else c,
                     "low": lows[i] if lows else c,
                     "volume": 1_000_000, "split_coefficient": 1.0})
        d += timedelta(days=1)
    return BarSeries.from_rows("NVDA", rows)


def _t(kind, units, price, day):
    return {"account_id": "a1", "type": kind, "symbol": "NVDA", "units": units,
            "price": price, "fee": 0.0, "trade_date": day}


def _analysed(txns, series):
    eps, _ = build_episodes(txns)
    return [analyse_episode(e, series, with_state=False) for e in eps]


def test_winner_and_loser_drawdown_are_reported_SIDE_BY_SIDE_with_their_Ns():
    """The paired statistic that teaches the most — and the one that must never
    be read alone, since a stop set between them can still kill a quarter of
    the winners."""
    series = _series([100.0] * 12,
                     highs=[100, 100, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120],
                     lows=[100, 96, 96, 96, 96, 96, 96, 96, 96, 96, 96, 96])
    rows = _analysed([
        _t("BUY", 10, 100.0, series.dates[0].isoformat()),
        _t("SELL", 10, 115.0, series.dates[6].isoformat()),
    ], series)
    rep = build_report(rows)
    assert rep.excursions.winner_n == 1
    assert rep.excursions.winner_mae is not None
    assert rep.excursions.loser_n == 0


def test_same_day_episodes_are_EXCLUDED_from_excursions_but_still_counted():
    """MANDATORY (§6). They must be absent from the winner/loser aggregates
    while remaining visible in coverage — a reader who does not know they were
    dropped reads the gap as covering the whole record."""
    series = _series([100.0] * 8, highs=[140.0] * 8, lows=[60.0] * 8)
    day = series.dates[0].isoformat()
    rows = _analysed([
        _t("BUY", 10, 100.0, day),
        _t("SELL", 10, 101.0, day),
    ], series)
    rep = build_report(rows)
    assert rep.excursions.same_day_excluded == 1
    assert rep.excursions.winner_n == 0 and rep.excursions.loser_n == 0
    assert rep.coverage.excluded["intraday_resolution_required"] == 1
    assert rep.coverage.episodes_total == 1


def test_every_setup_row_carries_its_N():
    """126 closed trades split three ways is 16-trade cells. A row without its
    sample size cannot be read safely, and low-N rows must never auto-promote."""
    series = _series([100.0] * 30)
    rows = _analysed([
        _t("BUY", 10, 100.0, series.dates[0].isoformat()),
        _t("SELL", 10, 110.0, series.dates[6].isoformat()),
        _t("BUY", 10, 100.0, series.dates[10].isoformat()),
        _t("SELL", 10, 90.0, series.dates[16].isoformat()),
    ], series)
    rep = build_report(rows)
    assert sum(r.n for r in rep.setups) == 2
    assert all(r.n > 0 for r in rep.setups)


def test_the_unclassified_bucket_is_REPORTED_never_absorbed_into_other():
    """~40% of a real record matches no category by design. On the first live
    account the unclassified bucket carried a BETTER win rate than every named
    setup — which is a signal the taxonomy deserves review, and is information
    only if it is visible."""
    series = _series([100.0] * 30)
    rows = _analysed([
        _t("BUY", 10, 100.0, series.dates[0].isoformat()),
        _t("SELL", 10, 110.0, series.dates[6].isoformat()),
    ], series)
    rep = build_report(rows)
    labels = [r.label for r in rep.setups]
    assert "unclassified" in labels
    assert "other" not in labels
    assert rep.coverage.unclassified_share == 1.0


def test_the_biggest_leak_is_chosen_by_DOLLARS_not_by_frequency():
    """Deterministic, and identical across two runs of the same record.

    The fixture is built so the two orderings disagree: ONE expensive premature
    exit against THREE cheap early entries. A ranking by count would name the
    early entries; the dollar ranking names the exit, which is the money.
    """
    # One premature exit: 100 units, sold at 108 after the position had been
    # worth 120, and the stock then ran to 130.
    rich = _series([100.0, 105.0, 110.0, 115.0, 118.0, 120.0] + [130.0] * 22,
                   highs=[100.0, 105.0, 110.0, 115.0, 118.0, 120.0] + [130.0] * 22,
                   lows=[100.0] * 28)
    expensive = _analysed([
        _t("BUY", 100, 100.0, rich.dates[0].isoformat()),
        _t("SELL", 100, 108.0, rich.dates[5].isoformat()),
    ], rich)

    # Three early entries: right idea, wrong week, and tiny size.
    thin = _series([100.0] + [95.0] * 19 + [105.0] * 10)
    cheap = []
    for _ in range(3):
        cheap += _analysed([
            _t("BUY", 1, 100.0, thin.dates[0].isoformat()),
            _t("SELL", 1, 105.0, thin.dates[25].isoformat()),
        ], thin)

    rep = build_report(expensive + cheap)

    assert rep.outcomes.get("premature_exit") == 1
    assert rep.outcomes.get("early_entry") == 3
    assert rep.biggest_leak.key == "premature_exit"
    assert rep.biggest_leak.n == 1
    assert rep.second_leak.key == "early_entry"
    assert rep.second_leak.n == 3
    assert rep.biggest_leak.dollars > rep.second_leak.dollars * 10
    assert all(
        rep.leaks[i].dollars >= rep.leaks[i + 1].dollars
        for i in range(len(rep.leaks) - 1)
    )


def test_an_empty_record_produces_an_empty_report_not_an_error():
    rep = build_report([])
    assert rep.coverage.episodes_total == 0
    assert rep.biggest_leak is None
    assert rep.excursions.winner_n == 0
    assert all(h.n == 0 for h in rep.opening_entry_profile.horizons)


def test_opening_entries_and_add_ons_are_SEPARATE_profiles():
    """Averaging in is a different decision from opening a position; one
    profile over both describes neither."""
    closes = [100.0] * 30
    closes[3] = 90.0        # opening entry drops
    closes[13] = 132.0      # add-on rises
    series = _series(closes)
    rows = _analysed([
        _t("BUY", 100, 100.0, series.dates[0].isoformat()),
        _t("BUY", 50, 120.0, series.dates[10].isoformat()),
        _t("SELL", 150, 130.0, series.dates[25].isoformat()),
    ], series)
    rep = build_report(rows)
    opening = {h.horizon: h for h in rep.opening_entry_profile.horizons}
    addon = {h.horizon: h for h in rep.add_on_profile.horizons}
    assert opening[3].n == 1 and addon[3].n == 1
    assert round(opening[3].median, 6) == -0.10
    assert round(addon[3].median, 6) == 0.10


def test_giveback_dollars_use_the_units_actually_HELD_at_the_peak():
    """The leak ranking is a dollar comparison, so an overstated leak can take
    the top slot from a real one.

    `units_total × avg_entry × (mfe − realised)` silently assumes the whole
    position was still on at the high. An episode that scaled out beforehand
    never had that exposure, and pricing the giveback as though it did inflates
    the most visible number in the section.
    """
    # Peaks at 130 on bar 2, AFTER 80 of the 100 units are already sold.
    series = _series([100.0] * 12,
                     highs=[100.0, 100.0, 130.0] + [100.0] * 9,
                     lows=[100.0] * 12)
    rows = _analysed([
        _t("BUY", 100, 100.0, series.dates[0].isoformat()),
        _t("SELL", 80, 100.0, series.dates[1].isoformat()),
        _t("SELL", 20, 100.0, series.dates[8].isoformat()),
    ], series)
    a = rows[0]
    assert a.mfe_date == series.dates[2]
    assert round(a.mfe, 4) == 0.30

    rep = build_report(rows)
    leak = next((l for l in rep.leaks if l.key == "giveback"), None)
    assert leak is not None, rep.outcomes
    # 20 units were on at the peak, not 100. The naive figure is 5x this one.
    naive = 100 * 100.0 * (a.mfe - a.episode.realised_return)
    assert leak.dollars < naive / 4
    assert round(leak.dollars, 2) == round(
        20 * 100.0 * (a.mfe - a.episode.realised_return), 2)
