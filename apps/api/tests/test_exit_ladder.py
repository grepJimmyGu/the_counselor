"""Tests for the shared exit-ladder evaluator.

Two of these pin bugs that were live in production code on 2026-08-18 and are
the reason this module exists. They are marked REGRESSION and should not be
relaxed without reading why they were written.
"""

import pytest

from app.schemas.strategy import ExitTier
from app.services.exit_ladder import (
    Bar,
    evaluate_bar,
    shares_for,
    trigger_type_for,
    weight_delta_for,
)


def tier(pct, action="sell_fraction", fraction=None):
    return ExitTier(trigger_pct=pct, action=action, fraction=fraction)


THIRD = 1.0 / 3.0


# ── Tier identity ───────────────────────────────────────────────────────────


def test_every_tier_has_a_distinct_identity():
    assert trigger_type_for(0) != trigger_type_for(1)


def test_REGRESSION_second_negative_tier_does_not_disarm_the_hard_stop():
    """A ladder may legally contain more than one negative tier — "trim at
    -5%, stop out at -10%" is a standard construction and the strategy
    validator permits it.

    The live monitor used to map EVERY negative tier to the constant string
    "stop_hit" and key its fire-once guard on that string, so the -5% trim
    consumed the identity and the -10% hard stop could never fire for the
    life of the position. Silent and permanent: no error, no alert, and the
    dashboard showed a position that looked protected.
    """
    # Ascending by trigger_pct, as the validator requires.
    ladder = [
        tier(-0.10, action="sell_all"),
        tier(-0.05, fraction=0.5),
        tier(0.15, fraction=THIRD),
    ]

    # Price at -6%: the trim fires, the stop does not.
    first = evaluate_bar(ladder=ladder, entry_price=100.0, bar=Bar.from_close(94.0))
    assert [f.tier_index for f in first] == [1]

    # Price at -12%, with the trim already fired. The stop MUST still fire.
    fired = {f.trigger_type for f in first}
    second = evaluate_bar(
        ladder=ladder,
        entry_price=100.0,
        bar=Bar.from_close(88.0),
        already_fired=fired,
    )
    assert [f.tier_index for f in second] == [0]
    assert second[0].action == "sell_all"


# ── Scale-out convention ────────────────────────────────────────────────────


def test_REGRESSION_scale_out_is_a_fraction_of_the_original_position():
    """Decided 2026-08-18. The backtester previously compounded
    (`w *= 1 - f`), making each tier a fraction of an already-reduced
    position, while the live monitor used fraction-of-initial — so the
    equity curve a user backtested was not the plan the alert stated.

    120 shares, two 1/3 tiers: the second sells 40, not 80/3 = 26.67.
    """
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=THIRD), tier(0.30, fraction=THIRD)]

    tp1 = evaluate_bar(ladder=ladder, entry_price=118.40, bar=Bar.from_close(136.42))
    assert len(tp1) == 1
    assert shares_for(tp1[0], shares_initial=120, shares_remaining=120) == pytest.approx(40.0)

    tp2 = evaluate_bar(
        ladder=ladder,
        entry_price=118.40,
        bar=Bar.from_close(154.10),
        already_fired={tp1[0].trigger_type},
    )
    assert len(tp2) == 1
    assert shares_for(tp2[0], shares_initial=120, shares_remaining=80) == pytest.approx(40.0)


def test_quantity_does_not_depend_on_whether_the_user_confirmed_the_last_sale():
    """The argument that decided the convention. `shares_remaining` only
    decrements when the user confirms a fill, and users do not reliably
    confirm. Fraction-of-initial is path-independent, so a missed
    confirmation cannot change the quantity we state; fraction-of-remaining
    would have returned 40 or 26.67 depending purely on paperwork.
    """
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=THIRD), tier(0.30, fraction=THIRD)]
    fire = evaluate_bar(
        ladder=ladder,
        entry_price=118.40,
        bar=Bar.from_close(154.10),
        already_fired={trigger_type_for(1)},
    )[0]

    confirmed = shares_for(fire, shares_initial=120, shares_remaining=80)
    not_confirmed = shares_for(fire, shares_initial=120, shares_remaining=120)
    assert confirmed == not_confirmed == pytest.approx(40.0)


def test_scale_out_is_capped_at_what_remains():
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=0.9)]
    fire = evaluate_bar(ladder=ladder, entry_price=100.0, bar=Bar.from_close(120.0))[0]
    assert shares_for(fire, shares_initial=100, shares_remaining=30) == pytest.approx(30.0)


def test_weight_delta_is_subtractive_not_compounding():
    """The backtester's unit. Two 1/3 tiers must remove 1/3 of the ENTRY
    weight each — the old `w *= (1 - f)` removed 1/3 then 2/9.
    """
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=THIRD), tier(0.30, fraction=THIRD)]
    tp1 = evaluate_bar(ladder=ladder, entry_price=100.0, bar=Bar.from_close(115.0))[0]
    tp2 = evaluate_bar(
        ladder=ladder,
        entry_price=100.0,
        bar=Bar.from_close(130.0),
        already_fired={tp1.trigger_type},
    )[0]
    assert weight_delta_for(tp1, entry_weight=0.30) == pytest.approx(0.10)
    assert weight_delta_for(tp2, entry_weight=0.30) == pytest.approx(0.10)


# ── Firing behaviour ────────────────────────────────────────────────────────


def test_a_gap_can_fire_several_tiers_on_one_bar():
    """The live monitor used to return after the first triggered tier, so a
    gap that cleared both targets took another poll to report the second.
    The backtester did not. Both now report every tier the bar cleared.
    """
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=THIRD), tier(0.30, fraction=THIRD)]
    fires = evaluate_bar(ladder=ladder, entry_price=100.0, bar=Bar.from_close(135.0))
    assert [f.tier_index for f in fires] == [1, 2]


def test_evaluation_stops_at_sell_all():
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=THIRD)]
    fires = evaluate_bar(ladder=ladder, entry_price=100.0, bar=Bar.from_close(50.0))
    assert [f.tier_index for f in fires] == [0]


def test_already_fired_tiers_do_not_refire():
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=THIRD)]
    fires = evaluate_bar(
        ladder=ladder,
        entry_price=100.0,
        bar=Bar.from_close(120.0),
        already_fired={trigger_type_for(1)},
    )
    assert fires == []


def test_untriggered_ladder_returns_nothing():
    ladder = [tier(-0.08, action="sell_all"), tier(0.15, fraction=THIRD)]
    assert evaluate_bar(ladder=ladder, entry_price=100.0, bar=Bar.from_close(101.0)) == []


@pytest.mark.parametrize("entry", [0.0, None])
def test_missing_entry_price_is_not_an_exception(entry):
    """The monitor reaches this with whatever the user typed. A bad entry
    price must return nothing, not raise into the job loop."""
    ladder = [tier(-0.08, action="sell_all")]
    assert evaluate_bar(ladder=ladder, entry_price=entry, bar=Bar.from_close(50.0)) == []


def test_empty_ladder_returns_nothing():
    assert evaluate_bar(ladder=[], entry_price=100.0, bar=Bar.from_close(50.0)) == []


def test_sell_all_reports_the_full_remaining_position():
    ladder = [tier(-0.08, action="sell_all")]
    fire = evaluate_bar(ladder=ladder, entry_price=100.0, bar=Bar.from_close(90.0))[0]
    assert fire.fraction_of_initial == 1.0
    assert shares_for(fire, shares_initial=120, shares_remaining=80) == pytest.approx(80.0)
