"""The strategy's current position, read instead of guessed.

`_extract_signal` answers "what does this strategy say to hold right now."
Both of its branches used to guess, and both guesses were wrong:

  - Single-asset inferred from the last CLOSED trade
    (`holding_period_days > 0 and return_pct != 0`), which answers "has this
    strategy ever completed a normal trade." A strategy that went to cash two
    months ago still reported LONG, so the signal stuck and almost never
    flipped — subscribing to alerts was subscribing to silence.

  - The basket branch returned the WHOLE universe as holdings behind a
    `# Simplified` comment, so a defensive overlay reported every holding as
    held whichever ones had failed their moving average.

The fix is not cleverer inference. The engine has been building a weights
matrix all along; its last row IS the answer. It just never left the engine.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from app.jobs.signal_cron import (
    SIGNAL_READER_VERSION,
    _extract_signal,
    _is_legacy_signal,
    _signal_display,
)


def _sj(strategy_type: str, universe):
    return NS(strategy_type=strategy_type, universe=universe)


def _result(current_weights, trade_log=None):
    return NS(current_weights=current_weights, trade_log=trade_log or [])


# ── single asset ────────────────────────────────────────────────────────────


def test_REGRESSION_a_flat_strategy_no_longer_reports_long():
    """The bug, stated as a case.

    A winner closed three weeks ago with the strategy flat since. The old
    reader saw `holding_period_days > 0 and return_pct != 0` and said LONG.
    The weights row says 0.0 — the strategy wants nothing.
    """
    stale_win = [NS(holding_period_days=12, return_pct=0.08)]
    sig = _extract_signal(
        _result({"NVDA": 0.0}, trade_log=stale_win),
        _sj("moving_average_filter", ["NVDA"]),
    )
    assert sig["position"] == "cash"
    assert sig["ticker"] == "NVDA"


def test_a_held_position_reports_long():
    sig = _extract_signal(
        _result({"NVDA": 1.0}), _sj("moving_average_filter", ["NVDA"]),
    )
    assert sig["position"] == "long"


def test_a_partial_weight_is_still_long():
    """A scaled-down position is a position. Only zero means out."""
    sig = _extract_signal(
        _result({"NVDA": 0.35}), _sj("moving_average_filter", ["NVDA"]),
    )
    assert sig["position"] == "long"


def test_a_symbol_absent_from_the_matrix_is_cash():
    """The engine drops a symbol it has no prices for. Absent is not held."""
    sig = _extract_signal(
        _result({"MSFT": 1.0}), _sj("moving_average_filter", ["NVDA"]),
    )
    assert sig["position"] == "cash"


# ── baskets and overlays ────────────────────────────────────────────────────


def test_REGRESSION_an_overlay_names_which_holding_fell_out():
    """The `# Simplified` placeholder, and why Path 1 never worked.

    A defensive overlay's whole purpose is telling you which holdings to move
    to cash. The old reader returned the entire universe as "holdings", so
    that question had no answer anywhere in the product.
    """
    sig = _extract_signal(
        _result({"NVDA": 0.25, "MSFT": 0.0, "KO": 0.25, "XOM": 0.0}),
        _sj("portfolio_defensive_overlay", ["NVDA", "MSFT", "KO", "XOM"]),
    )
    by_ticker = {h["ticker"]: h["position"] for h in sig["holdings"]}
    assert by_ticker == {
        "NVDA": "long", "MSFT": "cash", "KO": "long", "XOM": "cash",
    }


def test_the_payload_matches_the_shape_prd_13b_specified():
    """PRD-13b §5 defined this three months ago:
        {"holdings": [{"ticker", "position", "rule"}]}
    We carry `weight` instead of `rule` — the number the ticket needs — and
    keep ticker + position exactly as specified."""
    sig = _extract_signal(
        _result({"NVDA": 0.5, "MSFT": 0.0}),
        _sj("portfolio_defensive_overlay", ["NVDA", "MSFT"]),
    )
    for row in sig["holdings"]:
        assert set(row) == {"ticker", "position", "weight"}
    assert sig["type"] == "portfolio_defensive_overlay"


def test_a_fully_defensive_portfolio_reports_every_holding_as_cash():
    """All-zero is a real answer — the overlay pulled everything to cash. It
    must not be mistaken for "no data"."""
    sig = _extract_signal(
        _result({"NVDA": 0.0, "MSFT": 0.0}),
        _sj("portfolio_defensive_overlay", ["NVDA", "MSFT"]),
    )
    assert all(h["position"] == "cash" for h in sig["holdings"])


# ── stored results keep their old answer ────────────────────────────────────


def test_a_result_without_weights_falls_back_rather_than_flipping():
    """A backtest computed before this field existed has no weights. It must
    keep reporting what it always reported — flipping it to "cash" on a
    re-read would look like a signal change that never happened."""
    old_win = [NS(holding_period_days=12, return_pct=0.08)]
    sig = _extract_signal(
        _result(None, trade_log=old_win),
        _sj("moving_average_filter", ["NVDA"]),
    )
    assert sig["position"] == "long"          # the OLD answer, preserved
    assert "v" not in sig                     # and marked as legacy


# ── the first corrected run must not email everybody ────────────────────────


def test_a_legacy_stored_signal_is_recognised():
    """Every signal stored today was written by the old reader and is wrong
    for most strategies. The cron seeds those silently instead of emitting."""
    assert _is_legacy_signal({"position": "long", "ticker": "NVDA"}) is True
    assert _is_legacy_signal({"holdings": [{"ticker": "NVDA"}]}) is True


def test_a_current_signal_is_not_legacy():
    fresh = _extract_signal(
        _result({"NVDA": 1.0}), _sj("moving_average_filter", ["NVDA"]),
    )
    assert fresh["v"] == SIGNAL_READER_VERSION
    assert _is_legacy_signal(fresh) is False


def test_a_strategy_that_never_computed_is_not_legacy():
    """`None` means brand new, not stale. Its first event is a real first
    event and has always been emitted — this guard must not swallow it."""
    assert _is_legacy_signal(None) is False


# ── the display string still reads ──────────────────────────────────────────


def test_display_survives_the_new_payloads():
    long_sig = _extract_signal(
        _result({"NVDA": 1.0}), _sj("moving_average_filter", ["NVDA"]),
    )
    assert _signal_display(long_sig, None) == "LONG NVDA"

    basket = _extract_signal(
        _result({"NVDA": 0.5, "MSFT": 0.5}),
        _sj("portfolio_defensive_overlay", ["NVDA", "MSFT"]),
    )
    assert "NVDA" in _signal_display(basket, None)


# ── the engine actually fills it ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_engine_populates_current_weights() -> None:
    """End to end, against the real engine.

    Everything above tests the READER. This tests that the writer exists —
    that `weights.iloc[-1]` reaches the result rather than dying in the
    method. A rising series under a 50-day MA filter is held at the end.
    """
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock, patch

    import numpy as np
    import pandas as pd

    from app.schemas.strategy import (
        CashManagement, PositionSizing, RiskManagement, StrategyJSON, StrategyRule,
    )
    from app.services.backtester.engine import BacktestEngine

    engine = BacktestEngine()
    close = pd.DataFrame(
        {"AAA": np.linspace(100, 200, 250)},
        index=pd.date_range("2023-01-02", periods=250, freq="B"),
    )
    frames = {"AAA": pd.DataFrame(
        {"adjusted_close": close["AAA"].values, "high": (close["AAA"] * 1.01).values},
        index=close.index,
    )}
    strategy = StrategyJSON(
        strategy_name="Weights smoke",
        strategy_type="moving_average_filter",
        universe=["AAA"], benchmark="AAA",
        start_date=date(2023, 1, 2), end_date=date(2023, 12, 29),
        initial_capital=100_000, rebalance_frequency="monthly",
        transaction_cost_bps=0, slippage_bps=0,
        rules=[StrategyRule(ma_window=50)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(), cash_management=CashManagement(),
    )
    with patch.object(
        engine, "_load_prices",
        new=AsyncMock(return_value=(frames, frames["AAA"])),
    ):
        result = await engine.run(MagicMock(), strategy)

    assert result.current_weights is not None, (
        "the engine did not populate current_weights — the weights matrix "
        "is still dying inside run()"
    )
    assert "AAA" in result.current_weights
    # A monotonically rising series is above its 50-day MA at the end.
    assert result.current_weights["AAA"] > 0

    # And the reader agrees with it, with no inference involved.
    sig = _extract_signal(result, _sj("moving_average_filter", ["AAA"]))
    assert sig["position"] == "long"


# ── the downstream consumers of the corrected payload ───────────────────────


def test_REGRESSION_a_basket_counts_only_what_it_holds():
    """Found while tracing the chain, not by a failing test.

    The corrected overlay payload lists EVERY holding and marks each `long`
    or `cash`. `_basket_tickers` returned every name that had a ticker, so:

      - the signal card said "holds 12 names" for a portfolio the strategy
        had cut to 9, and
      - `classify_change` compares ticker SETS, so a holding going to cash
        changed nothing — the exact event a defensive overlay exists to
        report was invisible.
    """
    from app.services.signal_service import _basket_tickers

    payload = {
        "v": SIGNAL_READER_VERSION,
        "holdings": [
            {"ticker": "NVDA", "position": "long", "weight": 0.5},
            {"ticker": "MSFT", "position": "cash", "weight": 0.0},
            {"ticker": "KO", "position": "long", "weight": 0.5},
            {"ticker": "XOM", "position": "cash", "weight": 0.0},
        ],
    }
    assert _basket_tickers(payload) == {"NVDA", "KO"}


def test_a_legacy_basket_payload_still_counts_every_name():
    """Presence in the list WAS the claim before positions existed. Re-reading
    an old signal must not make a portfolio look suddenly empty."""
    from app.services.signal_service import _basket_tickers

    assert _basket_tickers({"holdings": [{"ticker": "NVDA"}, {"ticker": "MSFT"}]}) == {
        "NVDA", "MSFT",
    }


def test_a_holding_falling_out_is_reported_as_a_change():
    """The event the whole overlay exists to produce."""
    from app.services.signal_service import classify_change, signals_equal

    def _p(*pairs):
        return {"v": SIGNAL_READER_VERSION, "holdings": [
            {"ticker": t, "position": p, "weight": 0.5 if p == "long" else 0.0}
            for t, p in pairs
        ]}

    before = _p(("NVDA", "long"), ("MSFT", "long"))
    after = _p(("NVDA", "long"), ("MSFT", "cash"))
    assert not signals_equal(before, after)
    assert classify_change(before, after) in {"rotation", "rebalance", "flip_to_cash"}
