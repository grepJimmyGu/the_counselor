from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, Plan
from app.schemas.identity import (
    LoginRequest,
    OAuthGoogleRequest,
    PatchMeRequest,
    SignupRequest,
    TokenResponse,
    UserPublic,
)
from app.services.auth_service import (
    create_session_token,
    hash_password,
    new_user_id,
    validate_handle,
    verify_google_id_token,
    verify_password_safe,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token_response(user: User) -> TokenResponse:
    token = create_session_token(user.id, user.plan.tier)
    pub = UserPublic(
        id=user.id,
        handle=user.handle,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        locale=user.locale,
    )
    return TokenResponse(user=pub, session_token=token)


def _get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower()).first()


def _create_user_with_plan(
    db: Session,
    *,
    email: str,
    password_hash: Optional[str] = None,
    display_name: Optional[str] = None,
    locale: str = "en",
    oauth_provider: Optional[str] = None,
    oauth_subject: Optional[str] = None,
    avatar_url: Optional[str] = None,
    email_verified_at: Optional[datetime] = None,
) -> User:
    user = User(
        id=new_user_id(),
        email=email.lower(),
        password_hash=password_hash,
        display_name=display_name,
        locale=locale,
        oauth_provider=oauth_provider,
        oauth_subject=oauth_subject,
        avatar_url=avatar_url,
        email_verified_at=email_verified_at,
    )
    plan = Plan(user_id=user.id, tier="scout", status="active")
    db.add(user)
    db.add(plan)
    db.commit()
    db.refresh(user)
    return user


# ── Password signup / login ───────────────────────────────────────────────────

@router.post("/password/signup", status_code=201)
def password_signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = _get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    hashed = hash_password(body.password)
    user = _create_user_with_plan(
        db,
        email=body.email,
        password_hash=hashed,
        display_name=body.display_name,
        locale=body.locale,
    )
    return _make_token_response(user)


@router.post("/password/login")
def password_login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = _get_user_by_email(db, body.email)
    # Always run bcrypt to normalise timing even if user doesn't exist
    stored_hash = existing.password_hash if existing else None
    if not verify_password_safe(body.password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if existing is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    existing.last_login_at = datetime.utcnow()
    db.commit()
    return _make_token_response(existing)


# ── Google OAuth callback ─────────────────────────────────────────────────────

@router.post("/oauth/google/callback")
def google_oauth_callback(
    body: OAuthGoogleRequest, db: Session = Depends(get_db)
) -> dict:
    try:
        payload = verify_google_id_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    google_sub = payload.get("sub")
    email = payload.get("email", "").lower()
    name = payload.get("name")
    picture = payload.get("picture")
    email_verified = payload.get("email_verified", False)

    # Look up by oauth_subject first (most reliable)
    user = db.query(User).filter(
        User.oauth_provider == "google", User.oauth_subject == google_sub
    ).first()

    is_new = False
    if user is None:
        # Check if email already exists (may be a password account)
        existing_by_email = _get_user_by_email(db, email)
        if existing_by_email and existing_by_email.password_hash is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "An account with this email already exists. "
                    "Sign in with your password instead."
                ),
            )
        if existing_by_email:
            # Existing Google-only user whose oauth_subject wasn't set yet — update
            existing_by_email.oauth_provider = "google"
            existing_by_email.oauth_subject = google_sub
            existing_by_email.last_login_at = datetime.utcnow()
            db.commit()
            user = existing_by_email
        else:
            user = _create_user_with_plan(
                db,
                email=email,
                oauth_provider="google",
                oauth_subject=google_sub,
                display_name=name,
                avatar_url=picture,
                email_verified_at=datetime.utcnow() if email_verified else None,
            )
            is_new = True
    else:
        # Update profile fields from Google on each login
        user.display_name = user.display_name or name
        user.avatar_url = user.avatar_url or picture
        user.last_login_at = datetime.utcnow()
        db.commit()

    token = create_session_token(user.id, user.plan.tier)
    pub = UserPublic(
        id=user.id,
        handle=user.handle,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        locale=user.locale,
    )
    return {"user": pub.model_dump(), "session_token": token, "is_new": is_new}


# ── Legacy sync-user endpoint (NextAuth Google OAuth — kept for backward compat) ──

from fastapi import Header  # noqa: E402
from pydantic import BaseModel  # noqa: E402


class _SyncUserRequest(BaseModel):
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: str = "google"
    provider_user_id: str


class _UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime


def _verify_internal_key(x_internal_key: Optional[str] = Header(default=None)) -> None:
    from app.core.config import get_settings
    settings = get_settings()
    required = settings.internal_api_key
    if not required:
        raise HTTPException(status_code=503, detail="INTERNAL_API_KEY not configured.")
    if x_internal_key != required:
        raise HTTPException(status_code=401, detail="Invalid internal key.")


@router.post("/sync-user", response_model=_UserResponse, dependencies=[Depends(_verify_internal_key)])
def sync_user(body: _SyncUserRequest, db: Session = Depends(get_db)) -> _UserResponse:
    """Upsert a user on OAuth sign-in from Next.js server-side auth."""
    now = datetime.utcnow()
    user = db.query(User).filter(
        User.oauth_provider == body.provider,
        User.oauth_subject == body.provider_user_id,
    ).first()

    if user is None:
        user = _get_user_by_email(db, body.email)

    if user:
        user.display_name = body.display_name or user.display_name
        user.avatar_url = body.avatar_url or user.avatar_url
        user.last_login_at = now
        if not user.oauth_subject:
            user.oauth_provider = body.provider
            user.oauth_subject = body.provider_user_id
        db.commit()
    else:
        user = _create_user_with_plan(
            db,
            email=body.email,
            display_name=body.display_name,
            avatar_url=body.avatar_url,
            oauth_provider=body.provider,
            oauth_subject=body.provider_user_id,
            email_verified_at=now,
        )

    return _UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


@router.get("/me", dependencies=[Depends(_verify_internal_key)])
def legacy_get_me(
    provider_user_id: str,
    provider: str = "google",
    db: Session = Depends(get_db),
) -> _UserResponse:
    """Legacy lookup by provider + provider_user_id (called from Next.js)."""
    user = db.query(User).filter(
        User.oauth_subject == provider_user_id,
        User.oauth_provider == provider,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return _UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )
