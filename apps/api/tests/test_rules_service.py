"""PRD-43e §3.1 — the Rule object's domain rules.

Most of these are about a single structural decision: `behavioural` rules are
FINISHED at `saved`. The first live Timing Engine run produced "eight oversold
entries, zero winners" — N=8, which will never pass walk-forward and is still
the most actionable thing the product has said. A ladder whose only endpoint is
validation throws its own best output away.
"""

from __future__ import annotations

import pytest

from app.models.rule import Rule
from app.services import rules_service as svc


def _mk(db, **over):
    payload = {
        "rule_type": "entry",
        "name": "Buy pullbacks above the 200-day",
        "conditions": {"all": [{"left": "rsi14", "op": "<", "right": 60}]},
    }
    payload.update(over)
    return svc.create_rule(db, "u1", **payload)


# ── scope decides the ladder ────────────────────────────────────────────────


def test_a_behavioural_rule_is_FINISHED_at_saved(db):
    """It is a fact about what the user did. A fact needs no significance test,
    and prompting it toward validation reads as a deficiency in something that
    is already complete."""
    r = _mk(db, scope="behavioural", name="Stop entering oversold",
            sample_size=8, source="trade_analysis")
    assert r.status == "saved"
    assert svc.is_terminal(r) is True
    assert svc.can_be_tested(r) is False


def test_a_mechanical_rule_can_reach_tested(db):
    r = _mk(db, scope="mechanical")
    assert svc.is_terminal(r) is False
    assert svc.can_be_tested(r) is True
    svc.mark_tested(db, r, effect="+3.8% median 5D entry improvement")
    assert r.status == "tested"
    assert r.evidence == "tested_on_personal_record"


def test_marking_a_BEHAVIOURAL_rule_tested_is_refused(db):
    """The guard, not a convention. `tested` means rule-level validation ran,
    and there is no population on which to run it for a claim about oneself."""
    r = _mk(db, scope="behavioural", sample_size=8)
    with pytest.raises(ValueError, match="behavioural"):
        svc.mark_tested(db, r, effect="whatever")
    assert r.status == "saved"


def test_a_rule_can_never_reach_validated(db):
    """⚠ Validation belongs to the PLAYBOOK. A Playbook is a conjunction, and
    when it passes, the evidence attaches to the combination — any single rule
    inside might be inert, doing all the work, or actively harmful and
    outvoted. A `validated` rule could be lifted into a different Playbook
    carrying a credential it never earned."""
    from app.models.rule import RULE_STATUSES
    assert "validated" not in RULE_STATUSES
    r = _mk(db)
    with pytest.raises(ValueError):
        svc.set_status(db, r, "validated")


def test_promoting_behavioural_to_mechanical_resets_the_ladder(db):
    """A user may decide their habit is really a market claim. That restarts
    the evidence, it does not inherit it."""
    r = _mk(db, scope="behavioural", sample_size=8)
    svc.promote_to_mechanical(db, r)
    assert r.scope == "mechanical"
    assert r.status == "saved"
    assert r.evidence is None


# ── provenance is not status ────────────────────────────────────────────────


def test_playbook_provenance_never_changes_the_rules_status(db):
    """"Used in 'Momentum Pullback', which validated" is a true statement about
    where a rule has been. It must never render as a checkmark on the rule,
    sort as though it were a validation, or gate anything."""
    r = _mk(db, scope="mechanical")
    before = r.status
    svc.note_included_in_validated_playbook(db, r, "pb-1")
    svc.note_included_in_validated_playbook(db, r, "pb-2")
    assert r.included_in_validated_playbook == ["pb-1", "pb-2"]
    assert r.status == before
    assert r.evidence is None


def test_the_same_playbook_is_not_recorded_twice(db):
    r = _mk(db, scope="mechanical")
    svc.note_included_in_validated_playbook(db, r, "pb-1")
    svc.note_included_in_validated_playbook(db, r, "pb-1")
    assert r.included_in_validated_playbook == ["pb-1"]


# ── round thresholds (§2.5) ─────────────────────────────────────────────────


def test_a_fitted_looking_threshold_is_REJECTED_not_rounded(db):
    """§2.5. `RSI < 57.43` is a number that came out of an optimiser, and
    silently rounding it to 57 would hide that while keeping the false
    precision's provenance. The save fails and says why.

    ⚠ The PRD requires round thresholds without defining "round". The rule
    used here, stated so it can be argued with: a threshold must equal itself
    at one decimal place, and any magnitude >= 10 must be a whole number. So
    60, 2.5 and 0.5 pass; 57.43 and 57.4 do not.
    """
    with pytest.raises(ValueError, match="round"):
        _mk(db, conditions={"all": [{"left": "rsi14", "op": "<", "right": 57.43}]})


def test_round_thresholds_are_accepted(db):
    for value in (60, 2.5, 0.5, 200, -10):
        r = _mk(db, conditions={"all": [{"left": "x", "op": "<", "right": value}]})
        assert r.id


def test_a_large_non_whole_threshold_is_refused(db):
    with pytest.raises(ValueError, match="round"):
        _mk(db, conditions={"all": [{"left": "sma", "op": ">", "right": 57.4}]})


def test_thresholds_nested_anywhere_in_the_condition_tree_are_checked(db):
    """A validator that only reads the top level is a validator someone routes
    around by nesting one level deeper."""
    with pytest.raises(ValueError, match="round"):
        _mk(db, conditions={
            "all": [{"any": [{"left": "rsi14", "op": "<", "right": 61.37}]}],
        })


# ── ordinary CRUD, scoped to the owner ──────────────────────────────────────


def test_rules_are_listed_per_user_and_never_across(db):
    _mk(db, name="mine")
    svc.create_rule(db, "u2", rule_type="exit", name="theirs", conditions={})
    mine = svc.list_rules(db, "u1")
    assert [r.name for r in mine] == ["mine"]


def test_listing_groups_by_category_in_a_stable_order(db):
    """My Rules renders grouped by category (§3.3), so the order is part of the
    contract rather than whatever the database returns."""
    for t in ("exit", "selection", "entry"):
        _mk(db, rule_type=t, name=f"{t} rule")
    got = [r.rule_type for r in svc.list_rules(db, "u1")]
    assert got == ["selection", "entry", "exit"]


def test_an_unknown_rule_type_is_refused(db):
    with pytest.raises(ValueError, match="rule_type"):
        _mk(db, rule_type="vibes")


def test_deleting_someone_elses_rule_does_nothing(db):
    r = _mk(db)
    assert svc.delete_rule(db, "u2", r.id) is False
    assert db.get(Rule, r.id) is not None
    assert svc.delete_rule(db, "u1", r.id) is True


# ── saving from a lens finding ──────────────────────────────────────────────


def test_a_finding_carries_its_provenance_onto_the_rule(db):
    """"Why is this rule in my Playbook?" must always have an answer."""
    r = svc.create_rule(
        db, "u1", rule_type="entry", name="Avoid oversold entries",
        conditions={"all": [{"left": "rsi14", "op": ">", "right": 30}]},
        scope="behavioural", source="trade_analysis",
        source_analysis_id="timing-2026-08-28", sample_size=8,
        historical_effect="0 winners in 8, −11.8% median drawdown",
        confidence="low",
    )
    assert r.source == "trade_analysis"
    assert r.source_analysis_id == "timing-2026-08-28"
    assert r.sample_size == 8
    assert r.confidence == "low"


def test_a_hand_written_rule_needs_no_provenance_and_that_is_not_a_defect(db):
    r = _mk(db, source="user")
    assert r.source == "user"
    assert r.source_analysis_id is None
    assert r.sample_size is None


def test_a_rule_from_a_lens_defaults_to_mechanical_unless_told_otherwise(db):
    """A hand-written rule is a claim about the market, not an observation
    about oneself (§3.2)."""
    assert _mk(db, source="user").scope == "mechanical"
