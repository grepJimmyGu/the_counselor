"""Reading a transaction log back to the person who made it.

Every number here is something the user did. The tests are about the ways
that arithmetic could quietly lie: matching a sell to the wrong lot, counting
a truncated history as a loss, or asserting a behavioural pattern from two
trades.
"""

from __future__ import annotations

from datetime import date

from app.services.trading_behavior import summarize


def _t(kind, symbol, units, price, day, *, fee=0.0, account="a1"):
    return {
        "account_id": account, "type": kind, "symbol": symbol,
        "units": units, "price": price, "fee": fee, "trade_date": day,
    }


# ── the basic round trip ────────────────────────────────────────────────────


def test_a_buy_then_a_sell_is_one_completed_decision():
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05"),
    ])
    assert out.round_trips == 1
    assert out.realised_pnl == 200.0
    assert out.wins == 1 and out.losses == 0
    assert out.avg_holding_days == 31


def test_fees_come_out_of_the_profit():
    """A dashboard that reports gross P/L flatters the user. Both legs' fees
    belong to the round trip they were paid on."""
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05", fee=5.0),
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05", fee=5.0),
    ])
    assert out.realised_pnl == 190.0
    assert out.fees_paid == 10.0


def test_matching_is_fifo():
    """Two lots at different prices, one sale. The oldest shares go first —
    any other choice invents a cost basis the user never had."""
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("BUY", "NVDA", 10, 200.0, "2026-02-05"),
        _t("SELL", "NVDA", 10, 150.0, "2026-03-05"),
    ])
    assert out.round_trips == 1
    assert out.realised_pnl == 500.0          # sold the $100 lot, not the $200
    assert out.open_lots == 1


def test_one_sale_can_close_two_lots():
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("BUY", "NVDA", 10, 200.0, "2026-02-05"),
        _t("SELL", "NVDA", 20, 150.0, "2026-03-05"),
    ])
    assert out.round_trips == 2
    assert out.realised_pnl == 0.0            # +500 then −500
    assert out.wins == 1 and out.losses == 1


def test_a_partial_sale_leaves_the_rest_open():
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 4, 120.0, "2026-02-05"),
    ])
    assert out.round_trips == 1
    assert out.realised_pnl == 80.0
    assert out.open_lots == 1


def test_accounts_never_cross_match():
    """The same ticker at two brokers is two positions. Crossing them would
    report a round trip that never happened."""
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05", account="a1"),
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05", account="a2"),
    ])
    assert out.round_trips == 0
    assert out.unmatched_sells == 1
    assert out.open_lots == 1


# ── the truncated window ────────────────────────────────────────────────────


def test_a_sell_with_no_buy_is_named_rather_than_guessed():
    """THE HONESTY TEST.

    Pull a year of history and you will see sells of positions opened before
    it. Dropping them silently understates activity; matching them anyway
    invents a cost basis. They are counted and named so the P/L below can be
    read for what it is.
    """
    out = summarize([
        _t("SELL", "AAPL", 50, 200.0, "2026-03-01"),
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05"),
    ])
    assert out.unmatched_sells == 1
    assert out.unmatched_sell_symbols == ["AAPL"]
    # The orphan sale contributes nothing to P/L — no basis, no claim.
    assert out.realised_pnl == 200.0
    assert out.round_trips == 1


def test_the_orphan_sale_still_counts_as_activity():
    """It happened. It is not a round trip, but pretending the user never
    sold AAPL would be a different lie."""
    out = summarize([_t("SELL", "AAPL", 50, 200.0, "2026-03-01")])
    assert out.total_sells == 1
    assert out.symbols_traded == 1
    assert out.round_trips == 0


# ── the disposition effect ──────────────────────────────────────────────────


def test_holding_periods_split_by_outcome():
    """The finding this module exists for: winners sold in days, losers held
    for months. Measured, not asserted."""
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-01"),
        _t("SELL", "NVDA", 10, 110.0, "2026-01-06"),     # +, 5 days
        _t("BUY", "MSFT", 10, 100.0, "2026-01-01"),
        _t("SELL", "MSFT", 10, 90.0, "2026-04-01"),      # −, 90 days
    ])
    assert out.avg_holding_days_winners == 5
    assert out.avg_holding_days_losers == 90
    assert out.holds_losers_longer is True


def test_the_pattern_is_not_claimed_without_both_sides():
    """A history with no losses cannot support "you hold losers longer".
    Returning None is the honest answer, and the UI must not render a claim
    from it."""
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-01"),
        _t("SELL", "NVDA", 10, 110.0, "2026-01-06"),
    ])
    assert out.avg_holding_days_losers is None
    assert out.holds_losers_longer is None


def test_win_rate_and_the_ratio_that_actually_matters():
    """A high win rate with outsized losers is a losing method, and almost
    nobody knows this number about themselves."""
    out = summarize([
        _t("BUY", "A", 1, 100.0, "2026-01-01"),
        _t("SELL", "A", 1, 110.0, "2026-01-10"),     # +10
        _t("BUY", "B", 1, 100.0, "2026-01-01"),
        _t("SELL", "B", 1, 110.0, "2026-01-10"),     # +10
        _t("BUY", "C", 1, 100.0, "2026-01-01"),
        _t("SELL", "C", 1, 60.0, "2026-01-10"),      # −40
    ])
    assert out.win_rate == 2 / 3
    assert out.avg_win == 10.0
    assert out.avg_loss == 40.0
    assert out.win_loss_ratio == 0.25            # makes 1, loses 4
    assert out.realised_pnl == -20.0             # "winning" 67% of the time


# ── what got traded ─────────────────────────────────────────────────────────


def test_top_symbols_by_activity_and_by_outcome():
    out = summarize([
        _t("BUY", "NVDA", 10, 100.0, "2026-01-01"),
        _t("SELL", "NVDA", 10, 150.0, "2026-02-01"),
        _t("BUY", "NVDA", 10, 100.0, "2026-03-01"),
        _t("SELL", "NVDA", 10, 120.0, "2026-04-01"),
        _t("BUY", "KO", 10, 50.0, "2026-01-01"),
        _t("SELL", "KO", 10, 40.0, "2026-02-01"),
    ], top_n=2)
    assert out.top_symbols_by_trades[0].symbol == "NVDA"
    assert out.top_symbols_by_pnl[0].symbol == "NVDA"
    assert out.worst_symbols_by_pnl[0].symbol == "KO"
    assert out.worst_symbols_by_pnl[0].realised_pnl == -100.0


def test_dividends_and_fees_are_not_decisions():
    """A dividend is not something you chose. Mixing it into the trade
    history makes the list of decisions unreadable."""
    out = summarize([
        {"account_id": "a1", "type": "DIVIDEND", "symbol": "KO",
         "amount": 42.0, "trade_date": "2026-01-15"},
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05"),
    ])
    assert out.total_buys == 1 and out.total_sells == 1
    assert out.symbols_traded == 1               # KO never traded


# ── things that would otherwise crash or lie ────────────────────────────────


def test_an_empty_log_reports_nothing_rather_than_zeroes_that_look_real():
    out = summarize([])
    assert out.round_trips == 0
    assert out.win_rate is None
    assert out.avg_holding_days is None
    assert out.holds_losers_longer is None


def test_out_of_order_input_is_matched_chronologically():
    """SnapTrade returns newest-first. FIFO on that order would sell shares
    before they were bought."""
    out = summarize([
        _t("SELL", "NVDA", 10, 150.0, "2026-03-05"),
        _t("BUY", "NVDA", 10, 200.0, "2026-02-05"),
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
    ])
    assert out.realised_pnl == 500.0             # the January lot went first
    assert out.unmatched_sells == 0


def test_a_trade_with_no_price_is_counted_but_never_priced():
    """Some brokers report a transfer-in as a BUY with no price. Inventing a
    basis for it is how a dashboard starts lying."""
    out = summarize([
        {"account_id": "a1", "type": "BUY", "symbol": "NVDA",
         "units": 10, "price": None, "trade_date": "2026-01-05"},
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05"),
    ])
    assert out.total_buys == 1
    assert out.round_trips == 0
    assert out.unmatched_sells == 1


def test_a_missing_date_does_not_become_a_same_day_trade():
    out = summarize([
        {"account_id": "a1", "type": "BUY", "symbol": "NVDA",
         "units": 10, "price": 100.0, "trade_date": None},
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05"),
    ])
    assert out.round_trips == 1
    assert out.realised_pnl == 200.0
    assert out.avg_holding_days is None          # not 0


def test_timestamps_and_plain_dates_both_parse():
    out = summarize([
        {"account_id": "a1", "type": "BUY", "symbol": "NVDA", "units": 1,
         "price": 100.0, "trade_date": "2026-01-05T14:30:00Z"},
        _t("SELL", "NVDA", 1, 110.0, "2026-01-15"),
    ])
    assert out.round_trips == 1
    assert out.avg_holding_days == 10
    assert out.window_start == date(2026, 1, 5)
