"""PRD-43e §3.1/§3.3 — My Rules.

The user's first visible systematic framework. For many people this is the
destination, not a waypoint: §3.3 requires it to feel complete without a
Playbook, and constraint 6 forbids ever forcing someone up the ladder.

Every handler is `def` — these are plain DB reads and writes with no external
call, and there is nothing to gain from occupying the event loop.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.rule import Rule
from app.models.user import User
from app.services import rules_service as svc

router = APIRouter(prefix="/api/rules", tags=["rules"])
_log = logging.getLogger("livermore.rules")


class RuleView(BaseModel):
    id: str
    rule_type: str
    scope: str
    name: str
    conditions: Dict[str, Any] = {}
    source: str
    source_analysis_id: Optional[str] = None
    sample_size: Optional[int] = None
    historical_effect: Optional[str] = None
    confidence: Optional[str] = None
    status: str
    evidence: Optional[str] = None
    included_in_validated_playbook: List[str] = []
    created_at: Optional[str] = None

    # Derived, so the surface never has to re-implement the ladder — and so a
    # behavioural rule can never be rendered with an empty `validated` chip,
    # which reads as a deficiency in something already finished.
    is_terminal: bool = False
    can_be_tested: bool = False


class CreateRuleRequest(BaseModel):
    rule_type: str
    name: str = Field(min_length=1, max_length=160)
    conditions: Dict[str, Any] = {}
    scope: str = "mechanical"
    source: str = "user"
    source_analysis_id: Optional[str] = None
    sample_size: Optional[int] = None
    historical_effect: Optional[str] = None
    confidence: Optional[str] = None


def _view(rule: Rule) -> RuleView:
    return RuleView(
        id=rule.id,
        rule_type=rule.rule_type,
        scope=rule.scope,
        name=rule.name,
        conditions=rule.conditions or {},
        source=rule.source,
        source_analysis_id=rule.source_analysis_id,
        sample_size=rule.sample_size,
        historical_effect=rule.historical_effect,
        confidence=rule.confidence,
        status=rule.status,
        evidence=rule.evidence,
        included_in_validated_playbook=list(rule.included_in_validated_playbook or []),
        created_at=rule.created_at.isoformat() if rule.created_at else None,
        is_terminal=svc.is_terminal(rule),
        can_be_tested=svc.can_be_tested(rule),
    )


@router.get("", response_model=List[RuleView])
def list_rules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[RuleView]:
    """Grouped by category in the service, so the order is a contract rather
    than whatever the database happens to return."""
    user_id: str = current_user.id          # trap #17
    return [_view(r) for r in svc.list_rules(db, user_id)]


@router.post("", response_model=RuleView, status_code=201)
def create_rule(
    payload: CreateRuleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleView:
    user_id: str = current_user.id
    try:
        rule = svc.create_rule(
            db, user_id,
            rule_type=payload.rule_type,
            name=payload.name,
            conditions=payload.conditions,
            scope=payload.scope,
            source=payload.source,
            source_analysis_id=payload.source_analysis_id,
            sample_size=payload.sample_size,
            historical_effect=payload.historical_effect,
            confidence=payload.confidence,
        )
    except ValueError as exc:
        # The threshold message is written for a person — "use a value someone
        # would choose on purpose" — so it is surfaced rather than swallowed.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _view(rule)


@router.post("/{rule_id}/promote", response_model=RuleView)
def promote_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleView:
    """behavioural → mechanical. The user has decided their habit is really a
    claim about markets, which RESTARTS the evidence rather than inheriting
    it: nothing measured about their own record transfers to a universe."""
    user_id: str = current_user.id
    rule = svc.get_rule(db, user_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="No such rule.")
    return _view(svc.promote_to_mechanical(db, rule))


# Trap #7: a 204 route must declare `response_class=Response` and return one.
# With a `-> None` return annotation FastAPI tries to serialise `null`, trips
# an import-time assertion, and the entire app fails to start.
@router.delete("/{rule_id}", status_code=204, response_class=Response)
def delete_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    user_id: str = current_user.id
    if not svc.delete_rule(db, user_id, rule_id):
        raise HTTPException(status_code=404, detail="No such rule.")
    return Response(status_code=204)
