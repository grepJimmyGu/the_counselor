"""PRD-43e §3.1 — creating and holding Rules.

A lens finding's only next step used to be the composer, which presumes you
think in universes and Boolean conditions. A `Rule` is the rung between:
the smallest systematic decision a retail user needs to understand.

Three domain rules live here rather than in a route, because all three are
easy to get wrong in a way that produces a FALSE CLAIM rather than an error:

1. **`behavioural` is terminal at `saved`.** A claim about what the user has
   been doing is complete as it stands. `mark_tested` refuses it outright.
2. **No rule is ever `validated`.** Validation belongs to the Playbook — see
   `app/models/rule.py` for why a conjunction's evidence cannot be distributed
   over its members.
3. **Thresholds must be round.** `RSI < 57.43` is a number out of an
   optimiser, and rounding it silently at save would keep the false
   precision's provenance while hiding it. The save fails and says why.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rule import (
    RULE_SCOPES, RULE_SOURCES, RULE_STATUSES, RULE_TYPES, Rule,
)

__all__ = [
    "create_rule", "list_rules", "get_rule", "delete_rule", "set_status",
    "mark_tested", "promote_to_mechanical", "note_included_in_validated_playbook",
    "is_terminal", "can_be_tested", "validate_conditions",
]

# The order My Rules groups by (§3.3) — the sequence of a decision, not
# alphabetical: what to trade, when in, how much, when out, and the standing
# constraints over all of it.
_TYPE_ORDER = {t: i for i, t in enumerate(
    ("selection", "entry", "sizing", "exit", "portfolio")
)}

# ⚠ §2.5 requires "round thresholds" without defining round. The rule, stated
# so it can be argued with rather than discovered: a threshold must equal
# itself at one decimal place, and any magnitude >= 10 must be whole. So 60,
# 2.5, 0.5 and 200 pass; 57.43 and 57.4 do not. Chosen because the values that
# look fitted are precisely the ones carrying more precision than the decision
# they encode.
_WHOLE_ABOVE = 10.0


def _is_round(value: float) -> bool:
    if round(value, 1) != value:
        return False
    if abs(value) >= _WHOLE_ABOVE and value != int(value):
        return False
    return True


def validate_conditions(conditions: Any) -> None:
    """Walk the whole condition tree, not just its top level.

    A validator that reads one level is a validator someone routes around by
    nesting one deeper.
    """
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                if key in ("right", "value", "threshold") and isinstance(
                    val, (int, float)
                ) and not isinstance(val, bool):
                    if not _is_round(float(val)):
                        raise ValueError(
                            f"Threshold {val} is not round. Use a value someone "
                            f"would choose on purpose — 60, not 57.43."
                        )
                else:
                    walk(val)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(conditions)


def create_rule(
    db: Session,
    user_id: str,
    *,
    rule_type: str,
    name: str,
    conditions: Optional[Dict[str, Any]] = None,
    scope: str = "mechanical",
    source: str = "user",
    source_analysis_id: Optional[str] = None,
    sample_size: Optional[int] = None,
    historical_effect: Optional[str] = None,
    confidence: Optional[str] = None,
) -> Rule:
    if rule_type not in RULE_TYPES:
        raise ValueError(f"Unknown rule_type {rule_type!r}. One of {RULE_TYPES}.")
    if scope not in RULE_SCOPES:
        raise ValueError(f"Unknown scope {scope!r}. One of {RULE_SCOPES}.")
    if source not in RULE_SOURCES:
        raise ValueError(f"Unknown source {source!r}. One of {RULE_SOURCES}.")
    if not (name or "").strip():
        raise ValueError("A rule needs a name.")

    conditions = conditions if conditions is not None else {}
    validate_conditions(conditions)

    rule = Rule(
        id=str(uuid.uuid4()),
        user_id=user_id,
        rule_type=rule_type,
        scope=scope,
        name=name.strip(),
        conditions=conditions,
        source=source,
        source_analysis_id=source_analysis_id,
        sample_size=sample_size,
        historical_effect=historical_effect,
        confidence=confidence,
        status="saved",
        evidence=None,
        included_in_validated_playbook=[],
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def list_rules(db: Session, user_id: str) -> List[Rule]:
    """A user's rules, in the order My Rules groups them."""
    rows = db.execute(
        select(Rule).where(Rule.user_id == user_id)
    ).scalars().all()
    return sorted(
        rows,
        key=lambda r: (_TYPE_ORDER.get(r.rule_type, 99), r.created_at, r.name),
    )


def get_rule(db: Session, user_id: str, rule_id: str) -> Optional[Rule]:
    rule = db.get(Rule, rule_id)
    return rule if rule is not None and rule.user_id == user_id else None


def delete_rule(db: Session, user_id: str, rule_id: str) -> bool:
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        return False
    db.delete(rule)
    db.commit()
    return True


# ── the ladder ──────────────────────────────────────────────────────────────


def is_terminal(rule: Rule) -> bool:
    """`behavioural` rules are finished at `saved` — legitimately, finally, and
    never nagged toward validation."""
    return rule.scope == "behavioural" and rule.status == "saved"


def can_be_tested(rule: Rule) -> bool:
    return rule.scope == "mechanical"


def set_status(db: Session, rule: Rule, status: str) -> Rule:
    if status not in RULE_STATUSES:
        raise ValueError(
            f"Unknown status {status!r}. One of {RULE_STATUSES} — note that "
            f"'validated' belongs to a Playbook, never to a rule."
        )
    rule.status = status
    db.commit()
    db.refresh(rule)
    return rule


def mark_tested(db: Session, rule: Rule, *, effect: Optional[str] = None) -> Rule:
    """Rule-level validation ran — on the USER'S OWN episodes.

    Hence `tested_on_personal_record` and never anything stronger: the record
    generates the hypothesis, market history tests it, and the two claims never
    appear as one.
    """
    if rule.scope == "behavioural":
        raise ValueError(
            "A behavioural rule cannot be tested — it is a claim about what "
            "this user did, and it is complete at 'saved'."
        )
    rule.status = "tested"
    rule.evidence = "tested_on_personal_record"
    if effect:
        rule.historical_effect = effect
    db.commit()
    db.refresh(rule)
    return rule


def promote_to_mechanical(db: Session, rule: Rule) -> Rule:
    """The user decides their habit is really a claim about markets.

    That RESTARTS the evidence rather than inheriting it — nothing measured
    about their own record transfers to a claim about a universe.
    """
    rule.scope = "mechanical"
    rule.status = "saved"
    rule.evidence = None
    db.commit()
    db.refresh(rule)
    return rule


def note_included_in_validated_playbook(
    db: Session, rule: Rule, playbook_id: str,
) -> Rule:
    """PROVENANCE ONLY. Deliberately touches neither `status` nor `evidence`.

    A Playbook validating says where a rule has been, not that the rule is
    validated — see `app/models/rule.py`.
    """
    current = list(rule.included_in_validated_playbook or [])
    if playbook_id not in current:
        current.append(playbook_id)
        rule.included_in_validated_playbook = current
        db.commit()
        db.refresh(rule)
    return rule
