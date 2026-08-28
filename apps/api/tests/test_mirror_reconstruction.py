"""PRD-43a §3.8 — the reconstruction both engines read.

Two views over one transaction history. `TradeEpisode` is a position's whole
life (43b asks markouts and excursions *of a position*); `PortfolioSnapshot`
is what was held on each date (43c replays sizing against it). Building them
twice would be the Principle-1 violation the packet bans, so they are built
once, here.

The tests below are mostly about the two ways this can be quietly wrong: an
episode boundary in the wrong place, and a backward walk that keeps producing
numbers after it has stopped agreeing with the broker.
"""

from __future__ import annotations

from datetime import date

from app.services.mirror.reconstruction import (
    build_episodes,
    build_snapshots,
    is_cash_equivalent,
    reconstruct,
)


def _t(kind, symbol, units, price, day, *, account="a1"):
    return {
        "account_id": account, "type": kind, "symbol": symbol,
        "units": units, "price": price, "fee": 0.0, "trade_date": day,
    }


class _Pos:
    """Stands in for `snaptrade_service.BrokerPosition`."""

    def __init__(self, symbol, units, *, account="a1", cash_equivalent=False):
        self.account_id = account
        self.symbol = symbol
        self.units = units
        self.average_purchase_price = None
        self.last_price = None
        self.open_pnl = None
        self.cash_equivalent = cash_equivalent


# ── episodes: where the boundary goes ───────────────────────────────────────


def test_an_accumulation_and_a_scale_out_are_ONE_episode():
    """THE CANONICAL CASE from §3.8.1.

    `BUY 100 / BUY 50 / SELL 50 / SELL 75 / SELL 25` is one position that was
    built in two purchases and sold in three. A FIFO matcher correctly makes
    this several lot pairs; an episode is the thing markouts are asked *of*,
    and "what happened after you were in this" has one answer, not five.
    """
    eps, _ = build_episodes([
        _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
        _t("BUY", "NVDA", 50, 20.0, "2026-01-20"),
        _t("SELL", "NVDA", 50, 30.0, "2026-02-01"),
        _t("SELL", "NVDA", 75, 30.0, "2026-02-10"),
        _t("SELL", "NVDA", 25, 30.0, "2026-02-20"),
    ])

    assert len(eps) == 1
    ep = eps[0]
    assert ep.units_total == 150
    assert len(ep.entries) == 2 and len(ep.exits) == 3
    assert ep.opened_on == date(2026, 1, 5)
    assert ep.closed_on == date(2026, 2, 20)
    assert ep.holding_days == 46


def test_the_entry_price_is_WEIGHTED_not_averaged():
    """100 @ $10 and 50 @ $20 is $13.33, not $15. The simple mean is the
    error that survives every test built on equal-sized fills, so the fixture
    is deliberately unequal."""
    eps, _ = build_episodes([
        _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
        _t("BUY", "NVDA", 50, 20.0, "2026-01-20"),
        _t("SELL", "NVDA", 150, 30.0, "2026-02-01"),
    ])
    assert round(eps[0].avg_entry_price, 4) == round(2000.0 / 150.0, 4)
    assert eps[0].avg_exit_price == 30.0
    assert round(eps[0].realised_return, 4) == round(30.0 / (2000.0 / 150.0) - 1, 4)


def test_selling_out_and_buying_back_opens_a_SECOND_episode():
    """§3.8.1's boundary rule. Exiting NVDA and re-entering six weeks later is
    two decisions; merging them averages away the exit being measured — which
    is the exact thing 43b exists to look at."""
    eps, _ = build_episodes([
        _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
        _t("SELL", "NVDA", 100, 12.0, "2026-02-01"),
        _t("BUY", "NVDA", 80, 15.0, "2026-03-15"),
        _t("SELL", "NVDA", 80, 18.0, "2026-04-01"),
    ])
    assert len(eps) == 2
    assert eps[0].opened_on == date(2026, 1, 5)
    assert eps[1].opened_on == date(2026, 3, 15)
    assert eps[1].avg_entry_price == 15.0


def test_a_position_still_held_is_an_OPEN_episode():
    """`closed_on is None` is the marker 43b reads to keep an unfinished
    position out of realised-outcome aggregates."""
    eps, _ = build_episodes([
        _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
        _t("SELL", "NVDA", 40, 12.0, "2026-02-01"),
    ])
    assert len(eps) == 1
    assert eps[0].closed_on is None
    assert eps[0].realised_return is None
    assert eps[0].holding_days is None
    assert eps[0].units_open == 60


def test_the_same_ticker_at_two_brokers_is_two_episodes():
    """Per account, per symbol. Crossing accounts would invent a position
    neither broker reports."""
    eps, _ = build_episodes([
        _t("BUY", "NVDA", 100, 10.0, "2026-01-05", account="a1"),
        _t("BUY", "NVDA", 50, 11.0, "2026-01-06", account="a2"),
    ])
    assert len(eps) == 2
    assert {e.account_id for e in eps} == {"a1", "a2"}


def test_a_sell_with_no_open_position_does_not_open_one():
    """A sell of something bought before the feed starts. It cannot open an
    episode — there is no entry to anchor to — and inventing one would give
    43b a markout measured from a price the user never paid."""
    eps, excl = build_episodes([
        _t("SELL", "AAPL", 50, 200.0, "2026-03-01"),
        _t("BUY", "NVDA", 10, 100.0, "2026-01-05"),
        _t("SELL", "NVDA", 10, 120.0, "2026-02-05"),
    ])
    assert [e.symbol for e in eps] == ["NVDA"]
    assert ("AAPL", "sell_without_open_position") in excl


def test_dividends_and_fees_never_open_or_close_an_episode():
    eps, _ = build_episodes([
        _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
        {"account_id": "a1", "type": "DIVIDEND", "symbol": "NVDA",
         "amount": 42.0, "trade_date": "2026-01-15"},
        _t("SELL", "NVDA", 100, 12.0, "2026-02-01"),
    ])
    assert len(eps) == 1
    assert len(eps[0].entries) == 1 and len(eps[0].exits) == 1


# ── the third shared exclusion: units that move without a trade ─────────────


def test_a_journalled_transfer_excludes_the_symbol_rather_than_mis_reconciling():
    """§3.8.4, third bullet — observed in the live feed (JRNLSEC ×10,
    TRANSFER ×3). Units can change outside the trade stream. A walk that
    ignores that produces an episode whose size never matched reality, so the
    symbol is excluded and NAMED, exactly like `split_unreconciled`."""
    eps, excl = build_episodes([
        _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
        {"account_id": "a1", "type": "JRNLSEC", "symbol": "NVDA",
         "units": 50, "trade_date": "2026-01-20"},
        _t("SELL", "NVDA", 150, 12.0, "2026-02-01"),
    ])
    assert [e.symbol for e in eps] == []
    assert ("NVDA", "units_moved_off_market") in excl


def test_an_off_market_move_on_one_symbol_does_not_cost_the_others():
    eps, excl = build_episodes([
        {"account_id": "a1", "type": "TRANSFER", "symbol": "NVDA",
         "units": 50, "trade_date": "2026-01-20"},
        _t("BUY", "MSFT", 10, 100.0, "2026-01-05"),
        _t("SELL", "MSFT", 10, 130.0, "2026-02-05"),
    ])
    assert [e.symbol for e in eps] == ["MSFT"]
    assert ("NVDA", "units_moved_off_market") in excl


# ── cash equivalents ────────────────────────────────────────────────────────


def test_the_brokers_own_flag_is_the_primary_classifier():
    """#354 surfaced `cash_equivalent` from the payload. The broker labels
    its own instruments; that beats any ticker list we could maintain."""
    assert is_cash_equivalent("ANYTHING", position=_Pos("ANYTHING", 1, cash_equivalent=True))
    assert not is_cash_equivalent("NVDA", position=_Pos("NVDA", 1))


def test_the_named_list_covers_symbols_with_no_position_row():
    """A sold-out sweep fund has no position to carry a flag, but its trades
    are still in the activity feed."""
    assert is_cash_equivalent("SWVXX")
    assert is_cash_equivalent("swvxx")
    assert not is_cash_equivalent("NVDA")


def test_a_sweep_fund_appears_in_no_episode_and_no_snapshot():
    """A 40% zero-volatility 'position' would flatten every concentration and
    correlation figure 43c computes."""
    out = reconstruct(
        [
            _t("BUY", "SWVXX", 20000, 1.0, "2026-01-05"),
            _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
        ],
        positions=[_Pos("SWVXX", 20000, cash_equivalent=True), _Pos("NVDA", 100)],
    )
    assert [e.symbol for e in out.episodes] == ["NVDA"]
    assert all("SWVXX" not in s.holdings for s in out.snapshots)
    assert ("SWVXX", "cash_equivalent") in out.coverage.excluded


# ── snapshots: anchored to the broker, degrading with a date ────────────────


def test_the_walk_starts_from_the_broker_and_matches_it_exactly_today():
    """§3.8.2 — `/positions` is the authoritative present. The latest snapshot
    is not derived; it IS what the broker reports."""
    snaps, _ = build_snapshots(
        [_t("BUY", "NVDA", 100, 10.0, "2026-01-05")],
        positions=[_Pos("NVDA", 100)],
        window_end=date(2026, 1, 10),
    )
    assert snaps[-1].on_date == date(2026, 1, 10)
    assert snaps[-1].holdings == {"NVDA": 100}
    assert snaps[-1].reconstructable


def test_walking_back_across_a_buy_removes_it():
    """Before the 5th you did not hold what you bought on the 5th."""
    snaps, _ = build_snapshots(
        [_t("BUY", "NVDA", 100, 10.0, "2026-01-05")],
        positions=[_Pos("NVDA", 100)],
        window_end=date(2026, 1, 7),
        window_start=date(2026, 1, 3),
    )
    by_date = {s.on_date: s.holdings for s in snaps}
    assert by_date[date(2026, 1, 5)] == {"NVDA": 100}     # held on the day
    assert by_date[date(2026, 1, 4)] == {}                # not before it


def test_walking_back_across_a_sell_restores_it():
    snaps, _ = build_snapshots(
        [
            _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
            _t("SELL", "NVDA", 100, 12.0, "2026-01-08"),
        ],
        positions=[],                                     # flat today
        window_end=date(2026, 1, 10),
        window_start=date(2026, 1, 4),
    )
    by_date = {s.on_date: s.holdings for s in snaps}
    assert by_date[date(2026, 1, 10)] == {}
    assert by_date[date(2026, 1, 7)] == {"NVDA": 100}     # held between them
    assert by_date[date(2026, 1, 4)] == {}


def test_a_sell_of_pre_window_shares_carries_them_BACK_not_negative():
    """This is what backward reconstruction buys us.

    A sell of shares that were bought before the feed begins. There is no buy
    to undo, but undoing the sell restores 50 shares the user really did hold,
    and they stay held all the way back. Nothing is excluded and nothing is
    fabricated.

    A FORWARD walk over this same feed goes to −50 and reports a phantom
    short. Measured on the live account 2026-08-27: forward reconstruction
    produced five phantom open positions (ERO, MU, RKLB, SQQQ, SWVXX) against
    a broker holding no equities at all. Anchoring on `/positions` and walking
    back cannot produce that, because it starts from the truth the phantoms
    contradict.
    """
    snaps, cov = build_snapshots(
        [_t("SELL", "AAPL", 50, 200.0, "2026-03-01")],
        positions=[],
        window_end=date(2026, 3, 5),
        window_start=date(2026, 1, 1),
    )
    by_date = {s.on_date: s.holdings for s in snaps}
    assert by_date[date(2026, 3, 5)] == {}
    assert by_date[date(2026, 2, 28)] == {"AAPL": 50}
    assert by_date[date(2026, 1, 1)] == {"AAPL": 50}
    assert cov.excluded == []
    for s in snaps:
        assert all(u >= 0 for u in s.holdings.values())


def test_the_walk_never_runs_past_the_feed_and_says_where_it_stopped():
    """The ordinary boundary: you cannot reconstruct before your deltas. It is
    reported as a date so 43c can label the axis instead of implying the book
    began at zero."""
    snaps, cov = build_snapshots(
        [_t("BUY", "NVDA", 10, 100.0, "2026-02-01")],
        positions=[_Pos("NVDA", 10)],
        window_end=date(2026, 3, 5),
        window_start=date(2026, 2, 1),
    )
    assert cov.reconstructed_from == date(2026, 2, 1)
    assert min(s.on_date for s in snaps) == date(2026, 2, 1)


def test_a_walk_that_CONTRADICTS_the_broker_drops_the_symbol_everywhere():
    """THE HONESTY TEST.

    The broker reports flat. The feed reports a 100-share buy that was never
    sold. Undoing that buy takes the holding to −100 — not a portfolio, but
    proof the two sources disagree. There is no date at which the number
    becomes trustworthy, so the symbol is removed from every snapshot and
    named, rather than clamped to zero and carried along.

    It does NOT truncate the other symbols' history. An earlier draft of this
    module moved the whole book's start date to the contradiction, and running
    it against the live account on 2026-08-27 showed why that is wrong: 300
    unreconcilable shares of SQQQ cut a two-year book down to 282 days, even
    though SQQQ was already excluded from every snapshot it appeared in. One
    symbol we cannot reconcile says nothing about what NVDA's units were.
    """
    snaps, cov = build_snapshots(
        [_t("BUY", "NVDA", 100, 10.0, "2026-02-01")],
        positions=[],
        window_end=date(2026, 3, 5),
        window_start=date(2026, 1, 1),
    )
    assert ("NVDA", "units_unexplained") in cov.excluded
    assert all("NVDA" not in s.holdings for s in snaps)
    assert cov.reconstructed_from == date(2026, 1, 1)     # range intact
    assert min(s.on_date for s in snaps) == date(2026, 1, 1)
    for s in snaps:
        assert all(u >= 0 for u in s.holdings.values())


def test_a_same_day_round_trip_is_NETTED_before_the_walk_judges_it():
    """A daily feed cannot tell us intraday sequence, and rows for one date
    arrive in arbitrary order. Undoing them one at a time lets a buy listed
    before its own same-day sell dip the running holding below zero and
    fabricate a contradiction out of a position that reconciles perfectly.

    Found on the live account 2026-08-27, not by a unit test: BHP netted to
    exactly zero units across six rows against a broker holding zero, and was
    still excluded as `units_unexplained` — purely because a 200-share buy and
    a 100-share sell on 2025-10-10 were evaluated in the order the feed
    happened to list them.
    """
    snaps, cov = build_snapshots(
        [
            _t("BUY", "BHP", 200, 48.0, "2026-02-10"),
            _t("SELL", "BHP", 100, 50.0, "2026-02-10"),   # same day, listed after
            _t("SELL", "BHP", 100, 55.0, "2026-03-01"),
        ],
        positions=[],
        window_end=date(2026, 3, 5),
        window_start=date(2026, 1, 1),
    )
    assert cov.excluded == []
    assert cov.reconstructed_from == date(2026, 1, 1)
    by_date = {s.on_date: s.holdings for s in snaps}
    assert by_date[date(2026, 2, 10)] == {"BHP": 100}     # end of day, netted
    assert by_date[date(2026, 2, 9)] == {}


def test_a_same_day_round_trip_is_ONE_episode_not_an_orphan_sell():
    """The episode builder has the same exposure: a sell evaluated before its
    own same-day buy has no open position to close, which would exclude the
    whole symbol as `sell_without_open_position`. Within a date, buys are
    settled first — you cannot sell what you have not bought, and for an
    already-open position the order makes no difference."""
    eps, excl = build_episodes([
        _t("SELL", "BHP", 100, 50.0, "2026-02-10"),      # listed BEFORE its buy
        _t("BUY", "BHP", 100, 48.0, "2026-02-10"),
    ])
    assert excl == []
    assert len(eps) == 1
    assert eps[0].closed_on == date(2026, 2, 10)
    assert eps[0].holding_days == 0


def test_a_contradiction_in_one_symbol_names_only_that_symbol():
    """The boundary is a property of the book, so it moves for everyone — but
    the *exclusion* is a property of the symbol, and a clean position must not
    inherit a neighbour's inconsistency."""
    snaps, cov = build_snapshots(
        [
            _t("BUY", "NVDA", 100, 10.0, "2026-02-01"),
            _t("BUY", "MSFT", 10, 100.0, "2026-01-15"),
        ],
        positions=[_Pos("MSFT", 10)],
        window_end=date(2026, 3, 5),
        window_start=date(2026, 1, 1),
    )
    assert [e[0] for e in cov.excluded] == ["NVDA"]
    assert any(s.holdings.get("MSFT") == 10 for s in snaps)


def test_no_positions_and_no_activity_is_empty_not_an_error():
    snaps, cov = build_snapshots([], positions=[], window_end=date(2026, 3, 5))
    assert snaps == [] or all(s.holdings == {} for s in snaps)
    assert cov.excluded == []


# ── the two views agree ─────────────────────────────────────────────────────


def test_episodes_and_snapshots_agree_on_what_is_still_held():
    """The cheapest cross-check there is, and the one the live account failed
    before this existed: an open episode's remaining units must appear in the
    latest snapshot, because both are supposed to describe the same book."""
    out = reconstruct(
        [
            _t("BUY", "NVDA", 100, 10.0, "2026-01-05"),
            _t("SELL", "NVDA", 40, 12.0, "2026-02-01"),
        ],
        positions=[_Pos("NVDA", 60)],
        window_end=date(2026, 2, 5),
    )
    open_units = {e.symbol: e.units_open for e in out.episodes if e.closed_on is None}
    assert open_units == {"NVDA": 60}
    assert out.snapshots[-1].holdings == {"NVDA": 60}
    assert out.coverage.episodes_open == 1


def test_the_cross_check_reports_disagreement_rather_than_hiding_it():
    """When the episode walk and the broker disagree, that IS the finding —
    it is what the 2026-08-27 reconciliation surfaced. Report it; never
    reconcile by overwriting one with the other."""
    out = reconstruct(
        [_t("BUY", "NVDA", 100, 10.0, "2026-01-05")],
        positions=[],                                    # broker says flat
        window_end=date(2026, 2, 5),
    )
    assert out.coverage.position_disagreements
    syms = [d[0] for d in out.coverage.position_disagreements]
    assert "NVDA" in syms
