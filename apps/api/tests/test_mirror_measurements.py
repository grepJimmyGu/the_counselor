"""M1 (exit gap) and M4 (execution quality) — pricing decisions in dollars.

Both are upper bounds by construction, and most of these tests are about the
places where a bound quietly becomes a claim: a number reported only when it
flatters the thesis, a percentile computed on a day with no range, a
counterfactual priced off a stale bar without saying so.
"""

from __future__ import annotations

from datetime import date, datetime

from app.services.mirror.measurements import (
    execution_quality, exit_gap, load_bars_on, load_latest_closes,
)


def _t(kind, symbol, units, price, day, *, account="a1"):
    return {
        "account_id": account, "type": kind, "symbol": symbol,
        "units": units, "price": price, "fee": 0.0, "trade_date": day,
    }


def _closes(**kw):
    return {s.upper(): (date(2026, 8, 26), v) for s, v in kw.items()}


# ── M1: the exit gap ────────────────────────────────────────────────────────


def test_selling_before_a_run_is_priced_at_what_you_gave_up():
    """Sold 100 NVDA at $100; it is $150 now. Holding was worth $5,000 more."""
    out = exit_gap([_t("SELL", "NVDA", 100, 100.0, "2026-02-01")], _closes(NVDA=150.0))
    assert out.dollars == 5000.0
    assert out.sells_measured == 1
    assert out.remedy == "exit_rule"


def test_an_exit_that_saved_money_is_reported_as_saving_money():
    """THE HONESTY TEST.

    Sold at $100, it is $60 now — the exit was worth +$4,000 to them. A
    module that only reports the flattering direction is measuring its own
    thesis, not the user, and this is the number most easily suppressed.
    """
    out = exit_gap([_t("SELL", "NVDA", 100, 100.0, "2026-02-01")], _closes(NVDA=60.0))
    assert out.dollars == -4000.0
    assert out.remedy is None            # nothing to fix
    assert out.largest_symbol is None    # and nothing to name


def test_buys_do_not_enter_the_arithmetic_at_all():
    """The closed form drops them, which is what lets M1 survive a broker
    that only retains 90 days of history. Buying badly is a different
    measurement; this one is only about exits."""
    sells_only = exit_gap(
        [_t("SELL", "NVDA", 100, 100.0, "2026-02-01")], _closes(NVDA=150.0),
    )
    with_buys = exit_gap(
        [
            _t("BUY", "NVDA", 100, 10.0, "2026-01-01"),
            _t("BUY", "NVDA", 500, 999.0, "2026-01-15"),
            _t("SELL", "NVDA", 100, 100.0, "2026-02-01"),
        ],
        _closes(NVDA=150.0),
    )
    assert sells_only.dollars == with_buys.dollars == 5000.0


def test_gains_and_losses_across_symbols_net():
    out = exit_gap(
        [
            _t("SELL", "NVDA", 100, 100.0, "2026-02-01"),   # +5,000
            _t("SELL", "KO", 100, 60.0, "2026-02-01"),      # -1,000
        ],
        _closes(NVDA=150.0, KO=50.0),
    )
    assert out.dollars == 4000.0
    assert out.largest_symbol == "NVDA"
    assert out.largest_dollars == 5000.0


def test_a_gap_too_small_to_matter_routes_nowhere():
    """$40 recoverable on $180,000 of sales is arithmetic, not a finding, and
    routing someone to a remedy for it spends the only attention they gave
    us."""
    out = exit_gap(
        [_t("SELL", "NVDA", 1000, 180.0, "2026-02-01")], _closes(NVDA=180.04),
    )
    assert round(out.dollars, 2) == 40.0     # 1000 x $0.04, float noise and all
    assert out.is_material is False
    assert out.remedy is None


def test_a_symbol_with_no_price_history_is_excluded_and_named():
    """Delisted, or never warmed into the cache. We do not know what it is
    worth now, and for this measurement the current price IS the number —
    guessing it would be guessing the whole answer."""
    out = exit_gap(
        [
            _t("SELL", "NVDA", 100, 100.0, "2026-02-01"),
            _t("SELL", "DEFUNCT", 500, 12.0, "2026-03-01"),
        ],
        _closes(NVDA=150.0),
    )
    assert out.dollars == 5000.0
    assert out.excluded == [("DEFUNCT", "no_price_history")]
    assert out.sells_total == 2 and out.sells_measured == 1


def test_a_sell_with_no_price_has_no_counterfactual():
    """A transfer out or a corporate action arrives as a SELL with no price.
    It is not a decision to exit and has no 'what if you had held' to price."""
    out = exit_gap(
        [{"account_id": "a1", "type": "SELL", "symbol": "NVDA",
          "units": 100, "price": None, "trade_date": "2026-02-01"}],
        _closes(NVDA=150.0),
    )
    assert out.dollars == 0.0
    assert out.excluded == [("NVDA", "no_price_on_trade")]


def test_a_symbol_the_ledger_gave_up_on_is_skipped_here_too():
    """A split we could not reconcile makes the UNITS unreliable, and units
    multiply straight through this measurement."""
    out = exit_gap(
        [
            _t("SELL", "NVDA", 100, 100.0, "2026-02-01"),
            _t("SELL", "MSFT", 10, 100.0, "2026-02-01"),
        ],
        _closes(NVDA=150.0, MSFT=200.0),
        skip_symbols={"MSFT"},
    )
    assert out.dollars == 5000.0
    assert out.symbols_measured == 1


def test_the_as_of_date_is_the_bar_we_actually_priced_against():
    """`price_bars` is a cache. "Worth $N today" over a six-month-old bar is
    a different claim, and the date has to reach the screen."""
    out = exit_gap(
        [_t("SELL", "NVDA", 100, 100.0, "2026-02-01")],
        {"NVDA": (date(2026, 3, 15), 150.0)},
    )
    assert out.as_of == date(2026, 3, 15)


def test_no_sells_is_zero_and_immaterial_rather_than_a_finding():
    out = exit_gap([_t("BUY", "NVDA", 100, 100.0, "2026-02-01")], _closes(NVDA=150.0))
    assert out.dollars == 0.0
    assert out.is_material is False
    assert out.remedy is None


# ── M4: execution quality ───────────────────────────────────────────────────


def _bars(**kw):
    return {(s.upper(), date(2026, 2, 1)): v for s, v in kw.items()}


def test_a_fill_at_the_top_of_the_range_is_priced_against_the_midpoint():
    """Bought 100 at $110 on a $90-$110 day. The midpoint was $100, so the
    fill cost $1,000 against a price you could plausibly have got — unlike
    the low, which you could not."""
    out = execution_quality(
        [_t("BUY", "NVDA", 100, 110.0, "2026-02-01")], _bars(NVDA=(110.0, 90.0)),
    )
    assert out.buy_percentile == 1.0
    assert out.dollars == 1000.0
    assert out.remedy == "entry_timing"


def test_a_good_buy_is_credited_not_penalised():
    out = execution_quality(
        [_t("BUY", "NVDA", 100, 90.0, "2026-02-01")], _bars(NVDA=(110.0, 90.0)),
    )
    assert out.buy_percentile == 0.0
    assert out.dollars == -1000.0        # you beat the midpoint
    assert out.remedy is None


def test_a_sell_is_scored_the_other_way_round():
    """Low in the range is good for a buy and bad for a sell. Scoring both
    the same direction would call a disciplined seller undisciplined."""
    out = execution_quality(
        [_t("SELL", "NVDA", 100, 90.0, "2026-02-01")], _bars(NVDA=(110.0, 90.0)),
    )
    assert out.sell_percentile == 0.0
    assert out.dollars == 1000.0         # sold below the middle: it cost you
    assert out.remedy == "entry_timing"


def test_a_day_with_no_range_does_not_divide_by_zero():
    """A halt or a limit-up day has high == low. There is no 'where in the
    range' when there is no range."""
    out = execution_quality(
        [_t("BUY", "NVDA", 100, 100.0, "2026-02-01")], _bars(NVDA=(100.0, 100.0)),
    )
    assert out.fills_measured == 0
    assert out.buy_percentile is None
    assert out.dollars == 0.0


def test_a_fill_outside_its_own_days_range_is_dropped_rather_than_clamped():
    """A fill below the low means the bar and the trade disagree — a stale
    cache, another venue, an extended-hours print. Clamping to 0.0 would bury
    a data problem inside a plausible-looking average."""
    out = execution_quality(
        [_t("BUY", "NVDA", 100, 50.0, "2026-02-01")], _bars(NVDA=(110.0, 90.0)),
    )
    assert out.fills_measured == 0
    assert out.fills_total == 1


def test_a_trade_with_no_bar_is_counted_but_not_measured():
    """Coverage has to be visible: 3 of 40 fills measured is a different
    claim from 40 of 40."""
    out = execution_quality(
        [
            _t("BUY", "NVDA", 100, 110.0, "2026-02-01"),
            _t("BUY", "MSFT", 100, 110.0, "2026-02-01"),
        ],
        _bars(NVDA=(110.0, 90.0)),
    )
    assert out.fills_total == 2
    assert out.fills_measured == 1


def test_middling_fills_route_nowhere():
    """Filling at the midpoint is fine. A remedy offered to someone with no
    problem is the fastest way to make the whole surface ignorable."""
    out = execution_quality(
        [
            _t("BUY", "NVDA", 100, 100.0, "2026-02-01"),
            _t("SELL", "NVDA", 100, 100.0, "2026-02-01"),
        ],
        _bars(NVDA=(110.0, 90.0)),
    )
    assert out.buy_percentile == 0.5 and out.sell_percentile == 0.5
    assert out.dollars == 0.0
    assert out.in_worst_tercile is False
    assert out.remedy is None


def test_bad_buys_alone_are_enough_to_route():
    """Buying badly and selling badly are separate habits with one remedy;
    requiring both would hide the commoner case."""
    out = execution_quality(
        [
            _t("BUY", "NVDA", 100, 108.0, "2026-02-01"),
            _t("SELL", "NVDA", 100, 100.0, "2026-02-01"),
        ],
        _bars(NVDA=(110.0, 90.0)),
    )
    assert out.buy_percentile == 0.9
    assert out.sell_percentile == 0.5
    assert out.in_worst_tercile is True
    assert out.remedy == "entry_timing"


def test_a_costly_pattern_with_no_net_dollars_does_not_route():
    """The percentile is the symptom and the dollars are the reason to care.
    Routing on the symptom alone sends people to a fix worth nothing."""
    out = execution_quality(
        [
            _t("BUY", "NVDA", 1, 110.0, "2026-02-01"),      # +10 cost
            _t("SELL", "NVDA", 100, 100.0, "2026-02-01"),   # 0 at the midpoint
        ],
        _bars(NVDA=(110.0, 90.0)),
    )
    assert out.in_worst_tercile is True
    assert out.dollars == 10.0
    assert out.remedy == "entry_timing"


# ── the loaders ─────────────────────────────────────────────────────────────


def _bar_row(db, symbol, day, *, high=101.0, low=99.0, close=100.0):
    from app.models.price_bar import PriceBar
    db.add(PriceBar(
        symbol=symbol, trading_date=date.fromisoformat(day),
        open=100.0, high=high, low=low, close=close, adjusted_close=close,
        volume=1_000_000, dividend_amount=0.0, split_coefficient=1.0,
        source="alpha_vantage", fetched_at=datetime.utcnow(),
    ))


def test_load_latest_closes_takes_the_newest_bar_per_symbol(db):
    _bar_row(db, "NVDA", "2026-08-01", close=100.0)
    _bar_row(db, "NVDA", "2026-08-26", close=150.0)
    _bar_row(db, "MSFT", "2026-08-20", close=400.0)
    db.commit()

    out = load_latest_closes(db, ["NVDA", "MSFT"])
    assert out["NVDA"] == (date(2026, 8, 26), 150.0)
    assert out["MSFT"] == (date(2026, 8, 20), 400.0)


def test_load_latest_closes_is_bounded_by_the_symbols_asked_for(db):
    """~60 names the user traded, never the universe (HANDOFF §6F)."""
    _bar_row(db, "NVDA", "2026-08-26")
    _bar_row(db, "TSLA", "2026-08-26")
    db.commit()
    assert list(load_latest_closes(db, ["NVDA"])) == ["NVDA"]
    assert load_latest_closes(db, []) == {}


def test_load_bars_on_returns_only_the_days_actually_traded(db):
    """The query spans min..max date for indexing, then filters to the exact
    pairs — a user who traded twice a year apart must not pull a year of bars
    into the result."""
    _bar_row(db, "NVDA", "2026-01-05", high=110.0, low=90.0)
    _bar_row(db, "NVDA", "2026-06-05", high=210.0, low=190.0)
    _bar_row(db, "NVDA", "2026-03-05", high=150.0, low=140.0)   # not traded
    db.commit()

    out = load_bars_on(db, [("NVDA", date(2026, 1, 5)), ("NVDA", date(2026, 6, 5))])
    assert set(out) == {("NVDA", date(2026, 1, 5)), ("NVDA", date(2026, 6, 5))}
    assert out[("NVDA", date(2026, 1, 5))] == (110.0, 90.0)


def test_load_bars_on_with_nothing_asked_hits_the_database_not_at_all(db):
    assert load_bars_on(db, []) == {}


# ── the roll-up ─────────────────────────────────────────────────────────────


from app.services.mirror.measurements import ExecutionQuality, ExitGap, recoverable


def _gap(dollars, gross=100_000.0):
    return ExitGap(dollars=dollars, gross_sold=gross, sells_measured=1)


def _xq(buy=0.0, sell=0.0):
    q = ExecutionQuality(buy_dollars=buy, sell_dollars=sell)
    q.dollars = buy + sell
    return q


def test_the_roll_up_is_the_three_things_that_actually_compose():
    out = recoverable(_gap(5000.0), 300.0, _xq(buy=800.0, sell=400.0))
    assert out.exit_gap == 5000.0
    assert out.fees == 300.0
    assert out.execution == 800.0            # buys only
    assert out.dollars == 6100.0
    assert out.components == ["exit_gap", "fees", "execution"]


def test_the_sell_half_of_execution_never_enters_the_roll_up():
    """THE SECOND DOUBLE-COUNT, the one PRD-43a §3.4 does not name.

    M1 prices "you never sold". M4's sell half prices "you sold better that
    day". You cannot both keep the shares and sell them well — those are
    alternatives, and adding them charges the same sale twice.
    """
    without = recoverable(_gap(5000.0), 0.0, _xq(buy=0.0, sell=0.0))
    with_bad_sells = recoverable(_gap(5000.0), 0.0, _xq(buy=0.0, sell=9999.0))
    assert without.dollars == with_bad_sells.dollars == 5000.0


def test_buying_badly_still_counts_because_it_composes_with_never_selling():
    out = recoverable(_gap(5000.0), 0.0, _xq(buy=800.0))
    assert out.dollars == 5800.0


def test_the_disposition_effect_is_not_in_here_at_all():
    """M2 is the PATTERN behind M1, not a separate loss. `recoverable()`
    takes no argument that could carry it — the exclusion is structural
    rather than a line someone can forget to remove."""
    import inspect
    params = set(inspect.signature(recoverable).parameters)
    assert params == {"gap", "fees_paid", "execution"}


def test_an_immaterial_gap_contributes_nothing():
    out = recoverable(_gap(40.0, gross=180_000.0), 100.0, _xq())
    assert out.exit_gap == 0.0
    assert out.dollars == 100.0
    assert "exit_gap" not in out.components


def test_a_component_that_went_the_users_way_is_not_netted_against_the_rest():
    """Exits that saved money must not cancel fees that were still paid.
    Netting lets one good habit hide a costly one, and the roll-up is meant
    to be the sum of things worth fixing — not a score."""
    out = recoverable(_gap(-4000.0), 300.0, _xq(buy=-200.0))
    assert out.exit_gap == 0.0
    assert out.execution == 0.0
    assert out.dollars == 300.0
    assert out.components == ["fees"]


def test_nothing_wrong_produces_zero_rather_than_a_small_reassuring_number():
    out = recoverable(_gap(-1000.0), 0.0, _xq(buy=-50.0, sell=-50.0))
    assert out.dollars == 0.0
    assert out.components == []
