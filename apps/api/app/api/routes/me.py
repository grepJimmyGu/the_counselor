from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.identity import (
    Entitlements,
    PatchMeRequest,
    PlanPublic,
    UsageThisMonth,
    UserMe,
    UserPublic,
)
from app.services.auth_service import validate_handle
from app.services.entitlements import get_entitlements, get_or_create_current_usage
from app.services import stripe_service

router = APIRouter(prefix="/api/me", tags=["me"])


def _current_usage_schema(user: User, db: Session) -> UsageThisMonth:
    usage = get_or_create_current_usage(db, user.id)
    return UsageThisMonth(
        period_start=str(usage.period_start),
        backtest_runs=usage.backtest_runs,
        robustness_runs=usage.robustness_runs,
        saved_strategies_count=usage.saved_strategies,
    )


@router.get("", response_model=UserMe)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserMe:
    plan = PlanPublic.model_validate(current_user.plan)
    usage = _current_usage_schema(current_user, db)
    return UserMe(
        id=current_user.id,
        handle=current_user.handle,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        locale=current_user.locale,
        email=current_user.email,
        created_at=current_user.created_at,
        plan=plan,
        usage=usage,
    )


@router.get("/entitlements", response_model=Entitlements)
def get_my_entitlements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Entitlements:
    usage = get_or_create_current_usage(db, current_user.id)
    return get_entitlements(current_user, usage)


@router.patch("", response_model=UserPublic)
def patch_me(
    body: PatchMeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    if body.handle is not None:
        normalized = body.handle.lower()
        err = validate_handle(normalized)
        if err:
            raise HTTPException(status_code=422, detail=err)
        # Case-insensitive uniqueness check
        conflict = (
            db.query(User)
            .filter(User.handle == normalized, User.id != current_user.id)
            .first()
        )
        if conflict:
            raise HTTPException(status_code=409, detail="That handle is already taken.")
        current_user.handle = normalized

    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.locale is not None:
        current_user.locale = body.locale
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url

    db.commit()

    # Sync email change to Stripe (fire-and-forget; don't block the response)
    if body.display_name is not None and current_user.plan and current_user.plan.stripe_customer_id:
        stripe_service.update_customer_email(
            current_user.plan.stripe_customer_id, current_user.email
        )

    db.refresh(current_user)
    return UserPublic.model_validate(current_user)
