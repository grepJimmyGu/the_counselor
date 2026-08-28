"""PRD-43e §3.3 — the My Rules endpoints.

Handler-level, matching the project's TestClient-free style. What is under
test is mostly ownership and the ladder: a rule is the user's own, and the
surface must never be handed a shape that lets it render a behavioural rule
as though it were missing a validation.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.orm import Session

from app.api.routes.rules import (
    CreateRuleRequest, create_rule, delete_rule, list_rules, promote_rule,
)
from app.services import rules_service as svc


def _req(**over) -> CreateRuleRequest:
    payload = {
        "rule_type": "entry",
        "name": "Buy pullbacks above the 200-day",
        "conditions": {"all": [{"left": "rsi14", "op": "<", "right": 60}]},
    }
    payload.update(over)
    return CreateRuleRequest(**payload)


def test_every_handler_is_def_not_async(db: Session):
    """These are plain DB reads and writes with no external call — there is
    nothing to gain from occupying the event loop, and trap #21 is what
    happens when a handler holds it."""
    for fn in (list_rules, create_rule, promote_rule, delete_rule):
        assert not inspect.iscoroutinefunction(fn), fn.__name__


def test_creating_and_listing_a_rule(db: Session, make_user):
    user = make_user()
    view = create_rule(_req(), current_user=user, db=db)
    assert view.status == "saved"
    assert view.scope == "mechanical"
    assert [r.id for r in list_rules(current_user=user, db=db)] == [view.id]


def test_a_behavioural_rule_reports_itself_TERMINAL_to_the_surface(db: Session, make_user):
    """So the card can render "finished" rather than an empty `validated` chip.
    An unfilled state reads as a deficiency in something already complete, and
    §3.1.1 forbids ever showing a behavioural rule a "validate this" prompt."""
    user = make_user()
    view = create_rule(
        _req(scope="behavioural", name="Stop entering oversold",
             source="trade_analysis", sample_size=8,
             historical_effect="0 winners in 8"),
        current_user=user, db=db,
    )
    assert view.is_terminal is True
    assert view.can_be_tested is False
    assert view.evidence is None


def test_a_mechanical_rule_reports_that_it_can_be_tested(db: Session, make_user):
    user = make_user()
    view = create_rule(_req(), current_user=user, db=db)
    assert view.is_terminal is False
    assert view.can_be_tested is True


def test_a_fitted_threshold_is_a_400_with_a_message_a_person_can_act_on(
    db: Session, make_user,
):
    user = make_user()
    with pytest.raises(HTTPException) as exc:
        create_rule(
            _req(conditions={"all": [{"left": "rsi14", "op": "<", "right": 57.43}]}),
            current_user=user, db=db,
        )
    assert exc.value.status_code == 400
    assert "57.43" in exc.value.detail
    assert "on purpose" in exc.value.detail


def test_one_user_never_sees_anothers_rules(db: Session, make_user):
    a, b = make_user(email="a@x.com"), make_user(email="b@x.com")
    create_rule(_req(name="a's rule"), current_user=a, db=db)
    assert list_rules(current_user=b, db=db) == []


def test_deleting_someone_elses_rule_is_a_404_not_a_deletion(db: Session, make_user):
    a, b = make_user(email="a@x.com"), make_user(email="b@x.com")
    view = create_rule(_req(), current_user=a, db=db)
    with pytest.raises(HTTPException) as exc:
        delete_rule(view.id, current_user=b, db=db)
    assert exc.value.status_code == 404
    assert len(list_rules(current_user=a, db=db)) == 1

    got = delete_rule(view.id, current_user=a, db=db)
    assert isinstance(got, Response) and got.status_code == 204
    assert list_rules(current_user=a, db=db) == []


def test_promoting_restarts_the_evidence_rather_than_inheriting_it(
    db: Session, make_user,
):
    user = make_user()
    view = create_rule(
        _req(scope="behavioural", sample_size=8), current_user=user, db=db,
    )
    promoted = promote_rule(view.id, current_user=user, db=db)
    assert promoted.scope == "mechanical"
    assert promoted.status == "saved"
    assert promoted.evidence is None
    assert promoted.can_be_tested is True


def test_promoting_a_rule_you_do_not_own_is_a_404(db: Session, make_user):
    a, b = make_user(email="a@x.com"), make_user(email="b@x.com")
    view = create_rule(_req(scope="behavioural"), current_user=a, db=db)
    with pytest.raises(HTTPException) as exc:
        promote_rule(view.id, current_user=b, db=db)
    assert exc.value.status_code == 404


def test_playbook_provenance_is_exposed_without_becoming_a_status(
    db: Session, make_user,
):
    """A rule card may say "used in a Playbook that validated". It must never
    render that as a checkmark on the rule, or sort as though it were one."""
    user = make_user()
    view = create_rule(_req(), current_user=user, db=db)
    rule = svc.get_rule(db, user.id, view.id)
    svc.note_included_in_validated_playbook(db, rule, "pb-1")

    again = list_rules(current_user=user, db=db)[0]
    assert again.included_in_validated_playbook == ["pb-1"]
    assert again.status == "saved"
    assert again.evidence is None
