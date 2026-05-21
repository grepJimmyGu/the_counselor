"""Saved strategies service (Stage 1a, Path A).

Operates on the new SavedStrategy table. The Scout tier has two distinctive
behaviors enforced here at the service boundary:

  1. Cap: 10 saves (the SavedStrategy.is_public flag is irrelevant to the cap;
     a save is a save).
  2. Force-public: any save by a Scout is automatically is_public=True, no
     matter what the request body says. Strategist+ may set is_public=False.

Quota enforcement raises a 402 with code='saved_strategies_quota_reached'.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.entitlement_errors import upgrade_error
from app.models.saved_strategy import SavedStrategy
from app.models.user import User
from app.services.entitlements import (
    get_entitlements,
    get_or_create_current_weekly_usage,
)

_log = logging.getLogger(__name__)


class SaveStrategyRequest(BaseModel):
    # min_length=3 mirrors PublishStrategyRequest in community_publish_service.
    # Mismatched limits would let a Scout save a 1-char title (passes here) and
    # silently fail to auto-publish (raises ValidationError there) — the
    # community feed would then be missing entries that the user thinks are
    # live. Keep these aligned.
    title: str = Field(..., min_length=3, max_length=120)
    strategy_json: dict
    is_public: bool = False
    backtest_record_id: Optional[str] = None


def _count_user_saves(db: Session, user_id: str) -> int:
    return db.query(SavedStrategy).filter(SavedStrategy.user_id == user_id).count()


def save_strategy(
    db: Session,
    user: User,
    payload: SaveStrategyRequest,
) -> SavedStrategy:
    """Persist a new SavedStrategy for *user*. Enforces tier cap + Scout
    auto-public. Raises HTTPException(402) on cap exhaustion."""
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ent = get_entitlements(user, weekly)

    count = _count_user_saves(db, user.id)
    if count >= ent.saved_strategies_max:
        raise upgrade_error(
            "saved_strategies_quota_reached",
            current_tier=ent.tier,
            current_value=str(count),
            limit_value=str(ent.saved_strategies_max),
        )

    # Scout-tier override: ignore is_public=False from the request body.
    is_public = True if ent.saved_strategies_always_public else payload.is_public

    strategy = SavedStrategy(
        id=str(uuid4()),
        user_id=user.id,
        title=payload.title,
        strategy_json=payload.strategy_json,
        is_public=is_public,
        backtest_record_id=payload.backtest_record_id,
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)

    # Stage 4: auto-publish for tiers where saved_strategies_always_public=True
    # (Scout). Publishing is a snapshot, so subsequent edits to the saved row
    # don't leak — the user explicitly publishes again if they want to update.
    # Failure to auto-publish must NOT block the save (best-effort).
    if ent.saved_strategies_always_public:
        try:
            from app.services.community_publish_service import (
                PublishStrategyRequest,
                publish_strategy,
            )
            publish_strategy(
                db, user,
                PublishStrategyRequest(
                    title=payload.title,
                    description=None,
                    strategy_json=payload.strategy_json,
                    backtest_record_id=payload.backtest_record_id,
                ),
            )
        except Exception as exc:
            # Don't break the user's save flow if auto-publish fails — but
            # don't swallow silently either. Loud logging here is what would
            # have caught the min_length=1 vs 3 mismatch before production.
            _log.warning(
                "auto-publish failed for user=%s strategy=%s title=%r: %s",
                user.id, strategy.id, payload.title, exc,
            )
            db.rollback()
            # Re-fetch the saved strategy in case the rollback dropped it from
            # the session.
            strategy = db.get(SavedStrategy, strategy.id) or strategy

    return strategy


def list_user_strategies(db: Session, user_id: str) -> list[SavedStrategy]:
    """All saves for a user, newest first."""
    return (
        db.query(SavedStrategy)
        .filter(SavedStrategy.user_id == user_id)
        .order_by(SavedStrategy.created_at.desc())
        .all()
    )


def get_strategy(db: Session, strategy_id: str) -> Optional[SavedStrategy]:
    return db.get(SavedStrategy, strategy_id)


def delete_strategy(db: Session, user_id: str, strategy_id: str) -> bool:
    """Delete *strategy_id* if owned by *user_id*. Returns True if deleted."""
    strategy = db.get(SavedStrategy, strategy_id)
    if strategy is None or strategy.user_id != user_id:
        return False
    db.delete(strategy)
    db.commit()
    return True
