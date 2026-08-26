"""The ledger — making a broker's transaction feed matchable across a split.

The claims under test are all about a single refusal: when the numbers do not
reconcile, say so rather than publish one. A 10:1 split matched on raw units
produces a 90% loss that never happened, and a fabricated loss reads exactly
like a real finding — which is why "we could not tell" has to be a first-class
outcome rather than an exception handler.
"""

from __future__ import annotations

from datetime import date

from app.services.mirror.portfolio_ledger_service import (
    SplitEvent, build_ledger, load_splits,
)
from app.services.trading_behavior import summarize


def _t(kind, symbol, units, price, day, *, account="a1"):
    return {
        "account_id": account, "type": kind, "symbol": symbol,
        "units": units, "price": price, "fee": 0.0, "trade_date": day,
    }


def _split(symbol, day, coef):
    return SplitEvent(symbol=symbol, on_date=date.fromisoformat(day), coefficient=coef)


# ── the broker did NOT restate: adjust ──────────────────────────────────────


def test_a_position_held_through_a_split_reconciles_after_adjustment():
    """THE BUG THIS SLICE EXISTS FOR.

    Buy 10 at $1,000, split 10:1, sell 100 at $100. The money is unchanged —
    $10,000 in, $10,000 out — but raw units say ten bought and a hundred sold.
    """
    rows = [
        _t("BUY", "NVDA", 10, 1000.0, "2026-01-05"),
        _t("SELL", "NVDA", 100, 100.0, "2026-06-05"),
    ]
    splits = {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]}

    ledger = build_ledger(rows, splits)
    out = summarize(ledger.transactions)

    assert ledger.resolutions[0].reason == "adjusted"
    assert ledger.resolutions[0].applied is True
    assert out.round_trips == 1
    assert out.unmatched_sells == 0
    assert abs(out.realised_pnl) < 0.01          # not a 90% loss


def test_the_adjustment_moves_units_but_never_the_money():
    """`units * factor` and `price / factor` leave the dollars alone. This is
    a matching fix, not a P/L correction, and a test that lets it become one
    is how a silent restatement of someone's returns would ship."""
    rows = [
        _t("BUY", "NVDA", 10, 1000.0, "2026-01-05"),
        _t("SELL", "NVDA", 100, 120.0, "2026-06-05"),
    ]
    ledger = build_ledger(rows, {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]})
    buys = [t for t in ledger.transactions if t["type"] == "BUY"]

    assert buys[0]["units"] == 100
    assert buys[0]["price"] == 100.0
    assert buys[0]["units"] * buys[0]["price"] == 10_000.0

    out = summarize(ledger.transactions)
    assert out.realised_pnl == 2000.0            # 100 x (120 - 100)


def test_a_trade_on_the_split_date_is_already_post_split():
    """The split coefficient sits on the bar for the day it happened, and a
    trade that day fills at the new price. Adjusting it would double-count."""
    rows = [
        _t("BUY", "NVDA", 100, 100.0, "2026-03-02"),
        _t("SELL", "NVDA", 100, 110.0, "2026-06-05"),
    ]
    ledger = build_ledger(rows, {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]})
    buys = [t for t in ledger.transactions if t["type"] == "BUY"]

    assert buys[0]["units"] == 100                # untouched
    assert summarize(ledger.transactions).round_trips == 1


# ── the broker DID restate: change nothing ──────────────────────────────────


def test_a_broker_that_restates_its_own_history_is_left_alone():
    """Some brokers rewrite the old buy as 100 shares at $100. Those rows
    already reconcile, and adjusting them would create the very mismatch this
    module exists to remove. We do not know which kind of broker we are
    talking to, so we look at whether it reconciles rather than asking."""
    rows = [
        _t("BUY", "NVDA", 100, 100.0, "2026-01-05"),   # already restated
        _t("SELL", "NVDA", 100, 120.0, "2026-06-05"),
    ]
    ledger = build_ledger(rows, {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]})

    assert ledger.resolutions[0].reason == "broker_restated"
    assert ledger.resolutions[0].applied is False
    buys = [t for t in ledger.transactions if t["type"] == "BUY"]
    assert buys[0]["units"] == 100
    assert summarize(ledger.transactions).realised_pnl == 2000.0


# ── neither reconciles: refuse ──────────────────────────────────────────────


def test_when_neither_matching_reconciles_the_symbol_is_excluded_and_named():
    """THE HONESTY TEST.

    A sell of a position opened before the window, on a symbol that also
    split. Raw leaves 50 orphaned shares; adjusted leaves 500. We cannot
    attribute the gap, so we publish nothing for this symbol and say why —
    rather than pick the smaller wrong number.
    """
    rows = [_t("SELL", "NVDA", 50, 100.0, "2026-06-05")]
    ledger = build_ledger(rows, {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]})

    assert ledger.resolutions[0].reason == "unreconciled"
    assert ("NVDA", "split_unreconciled") in ledger.coverage.excluded
    assert ledger.coverage.symbols_included == 0
    assert ledger.transactions == []
    assert ledger.coverage.is_complete is False


def test_one_bad_symbol_does_not_cost_the_others():
    """Exclusion is per symbol. A user with one unreconcilable name and nine
    clean ones gets nine names of analysis and one line explaining the tenth."""
    rows = [
        _t("SELL", "NVDA", 50, 100.0, "2026-06-05"),      # unreconcilable
        _t("BUY", "MSFT", 10, 100.0, "2026-01-05"),
        _t("SELL", "MSFT", 10, 130.0, "2026-06-05"),
    ]
    ledger = build_ledger(rows, {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]})
    out = summarize(ledger.transactions)

    assert ledger.coverage.excluded == [("NVDA", "split_unreconciled")]
    assert ledger.coverage.symbols_included == 1
    assert ledger.coverage.symbols_total == 2
    assert out.round_trips == 1
    assert out.realised_pnl == 300.0


# ── the ordinary case, and the things that must not change ──────────────────


def test_a_symbol_with_no_split_is_untouched_and_unreported():
    """No split, no decision, no line in the coverage note. The absence of
    news is not news."""
    rows = [
        _t("BUY", "MSFT", 10, 100.0, "2026-01-05"),
        _t("SELL", "MSFT", 10, 130.0, "2026-06-05"),
    ]
    ledger = build_ledger(rows, {})

    assert ledger.resolutions == []
    assert ledger.coverage.is_complete
    assert ledger.coverage.symbols_included == 1
    assert summarize(ledger.transactions).realised_pnl == 300.0


def test_dividends_and_fees_survive_the_ledger():
    """They are not decisions and are never matched, but the fee total is real
    money and `summarize()` still has to see them."""
    rows = [
        _t("BUY", "MSFT", 10, 100.0, "2026-01-05"),
        {"account_id": "a1", "type": "DIVIDEND", "symbol": "KO",
         "amount": 42.0, "trade_date": "2026-02-15"},
        {"account_id": "a1", "type": "FEE", "symbol": None,
         "amount": -5.0, "fee": 5.0, "trade_date": "2026-02-15"},
    ]
    ledger = build_ledger(rows, {})
    kinds = {t["type"] for t in ledger.transactions}
    assert "DIVIDEND" in kinds and "FEE" in kinds


def test_accounts_still_never_cross_when_deciding_about_a_split():
    """The same ticker at two brokers is two positions. If the reconciliation
    check crossed them it could call a genuinely unmatched sell 'reconciled'
    by pairing it with the other broker's buy."""
    rows = [
        _t("BUY", "NVDA", 10, 1000.0, "2026-01-05", account="a1"),
        _t("SELL", "NVDA", 100, 100.0, "2026-06-05", account="a2"),
    ]
    ledger = build_ledger(rows, {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]})
    assert ledger.resolutions[0].reason == "unreconciled"


def test_float_noise_in_a_coefficient_is_not_a_split():
    """1.49999925000037 and 1.499999250000375 are two stored rows for the same
    3:2 split, and a coefficient of exactly 1.0 arrives as 0.9999999. Equality
    comparison on this column is how a no-op becomes an adjustment."""
    rows = [
        _t("BUY", "MSFT", 10, 100.0, "2026-01-05"),
        _t("SELL", "MSFT", 10, 130.0, "2026-06-05"),
    ]
    ledger = build_ledger(
        rows, {"MSFT": [_split("MSFT", "2026-03-02", 1.0000000001)]},
    )
    # A coefficient this close to 1.0 changes nothing, so the match still
    # reconciles on raw units and nothing is adjusted.
    assert ledger.resolutions[0].applied is False
    assert summarize(ledger.transactions).realised_pnl == 300.0


def test_two_splits_compound():
    """A 2:1 and then a 5:1 is a 10:1 for anything bought before both."""
    rows = [
        _t("BUY", "NVDA", 10, 1000.0, "2026-01-05"),
        _t("SELL", "NVDA", 100, 100.0, "2026-09-05"),
    ]
    ledger = build_ledger(rows, {"NVDA": [
        _split("NVDA", "2026-03-02", 2.0), _split("NVDA", "2026-06-02", 5.0),
    ]})
    buys = [t for t in ledger.transactions if t["type"] == "BUY"]
    assert buys[0]["units"] == 100
    assert summarize(ledger.transactions).round_trips == 1


def test_a_split_between_two_trades_only_applies_to_the_earlier_one():
    rows = [
        _t("BUY", "NVDA", 10, 1000.0, "2026-01-05"),   # pre-split
        _t("BUY", "NVDA", 50, 100.0, "2026-05-05"),    # post-split
        _t("SELL", "NVDA", 150, 110.0, "2026-09-05"),
    ]
    ledger = build_ledger(rows, {"NVDA": [_split("NVDA", "2026-03-02", 10.0)]})
    buys = sorted(
        (t for t in ledger.transactions if t["type"] == "BUY"),
        key=lambda t: t["trade_date"],
    )
    assert buys[0]["units"] == 100      # 10 x 10
    assert buys[1]["units"] == 50       # untouched
    assert summarize(ledger.transactions).unmatched_sells == 0


def test_an_empty_feed_produces_an_empty_ledger_not_a_crash():
    ledger = build_ledger([], {})
    assert ledger.transactions == []
    assert ledger.coverage.symbols_total == 0
    assert ledger.coverage.is_complete


def test_the_window_is_the_one_the_data_actually_covers():
    """Render the real window, never the nominal one — a 90-day broker asked
    for a year gives you 90 days, and saying '1Y' over it is a lie."""
    rows = [
        _t("BUY", "MSFT", 10, 100.0, "2026-03-05"),
        _t("SELL", "MSFT", 10, 130.0, "2026-06-05"),
    ]
    ledger = build_ledger(rows, {})
    assert ledger.coverage.window_start == date(2026, 3, 5)
    assert ledger.coverage.window_end == date(2026, 6, 5)


# ── reading splits out of price_bars ────────────────────────────────────────


def _bar(db, symbol, day, coef=1.0):
    from datetime import datetime as _dt
    from app.models.price_bar import PriceBar
    db.add(PriceBar(
        symbol=symbol, trading_date=date.fromisoformat(day),
        open=100.0, high=101.0, low=99.0, close=100.0, adjusted_close=100.0,
        volume=1_000_000, dividend_amount=0.0, split_coefficient=coef,
        source="alpha_vantage", fetched_at=_dt.utcnow(),
    ))


def test_load_splits_returns_only_the_days_that_were_splits(db):
    """14 million bars carry `split_coefficient`, and 1,916 of them are not
    1.0. Loading the other 14 million would be the whole point of the query
    missed."""
    _bar(db, "NVDA", "2026-03-01", 1.0)
    _bar(db, "NVDA", "2026-03-02", 10.0)
    _bar(db, "NVDA", "2026-03-03", 1.0)
    db.commit()

    out = load_splits(db, ["NVDA"])
    assert list(out) == ["NVDA"]
    assert len(out["NVDA"]) == 1
    assert out["NVDA"][0].coefficient == 10.0
    assert out["NVDA"][0].on_date == date(2026, 3, 2)


def test_load_splits_ignores_float_noise_around_one(db):
    """Production stores 1.49999925000037 and 1.499999250000375 for the same
    3:2 split, so a coefficient a hair off 1.0 is noise, not an event."""
    _bar(db, "MSFT", "2026-03-02", 1.0000000001)
    _bar(db, "MSFT", "2026-03-03", 0.9999999999)
    db.commit()
    assert load_splits(db, ["MSFT"]) == {}


def test_load_splits_is_bounded_by_the_symbols_asked_for(db):
    """Bounded by what the user actually traded — a few dozen names. This
    query must never widen to the universe."""
    _bar(db, "NVDA", "2026-03-02", 10.0)
    _bar(db, "TSLA", "2026-03-02", 3.0)
    db.commit()
    assert list(load_splits(db, ["NVDA"])) == ["NVDA"]


def test_load_splits_orders_events_oldest_first(db):
    """Compounding two splits depends on order only through multiplication,
    but the rendered list reads as a history and a shuffled one is wrong."""
    _bar(db, "NVDA", "2026-06-02", 5.0)
    _bar(db, "NVDA", "2026-03-02", 2.0)
    db.commit()
    events = load_splits(db, ["NVDA"])["NVDA"]
    assert [e.coefficient for e in events] == [2.0, 5.0]


def test_load_splits_takes_date_objects_not_iso_strings(db):
    """Trap #20: Postgres has no implicit varchar -> date cast, and SQLite
    accepts the string quietly — so a bound `.isoformat()` passes every local
    test and 500s in production."""
    _bar(db, "NVDA", "2026-03-02", 10.0)
    _bar(db, "NVDA", "2025-03-02", 2.0)
    db.commit()
    out = load_splits(db, ["NVDA"], start=date(2026, 1, 1))
    assert [e.coefficient for e in out["NVDA"]] == [10.0]


def test_no_symbols_asks_the_database_nothing(db):
    assert load_splits(db, []) == {}
    assert load_splits(db, ["", None]) == {}
