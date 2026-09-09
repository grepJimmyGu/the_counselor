"""What the service computes must reach the browser.

⚠ THE BUG THIS FILE EXISTS FOR (2026-09-09, shipped in #361).

`GET /api/mirror/timing` built its response as
`LeakView(key=..., n=..., dollars=...)` while the service had grown a
`trades` list on every `Leak`. Pydantic dropped what the constructor didn't
name, so the client received leaks with no `trades`, and
`mirror-when-section.tsx` — whose TS contract declared the field REQUIRED —
ran `h.trades.map(...)` against `undefined`. React unmounted and Next's error
boundary replaced the entire /account/brokerage page with "This page couldn't
load", about a second after it rendered.

`ExitGapView` had the identical hole: `sold_early_dollars` /
`sold_well_dollars` were computed, never serialised, so the copy that splits
the net into its two sides silently never rendered in production.

2,826 backend tests and 705 frontend tests were green through both. The
backend suite asserted on the service dataclasses; the frontend suite used
fixtures that already had the fields. Nothing compared the two. That gap is
what these tests close — and they close the CLASS, not the two fields: a
field added to a service dataclass must be serialised or be named here as
deliberately internal.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from app.api.routes.mirror import LeakTradeView, LeakView, _leak_view
from app.api.routes.snaptrade import ExitGapView
from app.services.mirror.measurements import ExitGap
from app.services.timing.report import Leak, LeakTrade


def _trade(**over):
    base = dict(
        symbol="NVDA",
        opened_on=date(2026, 1, 5),
        closed_on=date(2026, 3, 5),
        units=100.0,
        entry_price=90.0,
        exit_price=120.0,
        realised_return=0.33,
        mae=-0.08,
        mfe=0.61,
        after_exit_5d=0.04,
        after_exit_20d=0.11,
        dollars=2800.0,
    )
    base.update(over)
    return LeakTrade(**base)


# ── the regression ──────────────────────────────────────────────────────────


def test_the_trades_behind_a_leak_reach_the_client():
    """THE BUG. The evidence table under each habit renders from these rows;
    without them the client read `undefined` and took the page down."""
    view = _leak_view(Leak(key="giveback", n=2, dollars=4349.0,
                           trades=[_trade(), _trade(symbol="AMD")]))

    payload = view.model_dump()
    assert [t["symbol"] for t in payload["trades"]] == ["NVDA", "AMD"]

    row = payload["trades"][0]
    assert row["units"] == 100.0
    assert row["mfe"] == 0.61
    assert row["after_exit_20d"] == 0.11
    assert row["dollars"] == 2800.0


def test_dates_serialise_as_the_iso_strings_the_client_keys_rows_off():
    """`opened_on` is the React key for each row, and the TS contract types it
    `string` — a `date` object would reach JSON as something else again."""
    payload = _leak_view(Leak(key="giveback", n=1, dollars=1.0,
                              trades=[_trade()])).model_dump()
    assert payload["trades"][0]["opened_on"] == "2026-01-05"
    assert payload["trades"][0]["closed_on"] == "2026-03-05"


def test_a_position_still_open_serialises_without_a_close_date():
    payload = _leak_view(Leak(key="giveback", n=1, dollars=1.0,
                              trades=[_trade(closed_on=None,
                                             exit_price=None)])).model_dump()
    assert payload["trades"][0]["closed_on"] is None
    assert payload["trades"][0]["exit_price"] is None


def test_a_leak_with_no_trades_serialises_as_an_empty_list_never_absent():
    """`[]` means "we looked and there is nothing"; a missing key is what the
    client cannot survive."""
    payload = _leak_view(Leak(key="panic_exit", n=0, dollars=0.0)).model_dump()
    assert payload["trades"] == []
    assert LeakView(key="k", n=0, dollars=0.0).model_dump()["trades"] == []


def test_the_exit_gap_reports_both_sides_of_its_net():
    """Without these the surface shows only the residual — an accusatory
    figure handed to someone with as many good exits as bad."""
    view = ExitGapView(
        dollars=35816.0,
        sold_early_dollars=73770.0,
        sold_well_dollars=-37954.0,
        is_material=True,
        sells_measured=40,
        sells_total=44,
        symbols_measured=18,
    )
    payload = view.model_dump()
    assert payload["sold_early_dollars"] == 73770.0
    assert payload["sold_well_dollars"] == -37954.0
    # And the residual still is what the two sides make.
    assert round(payload["sold_early_dollars"] + payload["sold_well_dollars"],
                 2) == payload["dollars"]


# ── the class guard ─────────────────────────────────────────────────────────
#
# Each entry below is a field the service computes and the client is NOT meant
# to see. Adding a field to one of these dataclasses fails these tests until
# you either serialise it or name it here — which is the decision that was
# skipped when `trades` was added.

_INTERNAL_LEAK_FIELDS = {
    "detail",           # operator-facing prose; the surface writes its own copy
}

_INTERNAL_EXIT_GAP_FIELDS = {
    "gross_sold",       # the denominator behind `is_material`, not a claim
    "remedy",           # routed into the aggregate `remedies` list, not here
}


def _field_names(dc) -> set:
    return {f.name for f in dataclasses.fields(dc)}


def test_every_leak_field_is_serialised_or_declared_internal():
    missing = _field_names(Leak) - set(LeakView.model_fields) - _INTERNAL_LEAK_FIELDS
    assert not missing, (
        f"{sorted(missing)} computed on Leak but absent from LeakView. "
        "Serialise it, or add it to _INTERNAL_LEAK_FIELDS with the reason."
    )


def test_every_leak_trade_field_is_serialised():
    """No internal fields here by design — a LeakTrade IS the evidence row."""
    missing = _field_names(LeakTrade) - set(LeakTradeView.model_fields)
    assert not missing, f"{sorted(missing)} absent from LeakTradeView"


def test_every_exit_gap_field_is_serialised_or_declared_internal():
    missing = (
        _field_names(ExitGap)
        - set(ExitGapView.model_fields)
        - _INTERNAL_EXIT_GAP_FIELDS
    )
    assert not missing, (
        f"{sorted(missing)} computed on ExitGap but absent from ExitGapView. "
        "Serialise it, or add it to _INTERNAL_EXIT_GAP_FIELDS with the reason."
    )
