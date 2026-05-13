from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Internal key dependency ───────────────────────────────────────────────────

def verify_internal_key(x_internal_key: Optional[str] = Header(default=None)) -> None:
    """
    All /api/auth/* endpoints are only callable from the Next.js backend (BFF).
    They must include X-Internal-Key matching the INTERNAL_API_KEY env var.
    If INTERNAL_API_KEY is not set (local dev), the check is skipped.
    """
    settings = get_settings()
    required = settings.internal_api_key
    if not required:
        return  # dev mode — no key required
    if x_internal_key != required:
        raise HTTPException(status_code=401, detail="Invalid internal key.")


# ── Schemas ───────────────────────────────────────────────────────────────────

class SyncUserRequest(BaseModel):
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: str = "google"
    provider_user_id: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    provider: str
    created_at: datetime


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/sync-user", response_model=UserResponse, dependencies=[Depends(verify_internal_key)])
def sync_user(body: SyncUserRequest, db: Session = Depends(get_db)) -> UserResponse:
    """
    Upsert a user on OAuth sign-in. Called server-side from Next.js auth.ts.
    Creates the user on first sign-in; updates display_name and avatar on subsequent logins.
    """
    now = datetime.utcnow()
    row = db.execute(
        text("SELECT id, email, display_name, avatar_url, provider, created_at FROM users WHERE email = :email"),
        {"email": body.email},
    ).fetchone()

    if row:
        db.execute(
            text(
                "UPDATE users SET display_name = :dn, avatar_url = :av, updated_at = :now WHERE email = :email"
            ),
            {"dn": body.display_name, "av": body.avatar_url, "now": now, "email": body.email},
        )
        db.commit()
        r = row._mapping  # type: ignore[attr-defined]
        return UserResponse(
            id=str(r["id"]),
            email=r["email"],
            display_name=r["display_name"],
            avatar_url=r["avatar_url"],
            provider=r["provider"],
            created_at=r["created_at"],
        )

    # New user — insert
    db.execute(
        text(
            "INSERT INTO users (email, display_name, avatar_url, provider, provider_user_id)"
            " VALUES (:email, :dn, :av, :provider, :puid)"
        ),
        {
            "email": body.email,
            "dn": body.display_name,
            "av": body.avatar_url,
            "provider": body.provider,
            "puid": body.provider_user_id,
        },
    )
    db.commit()
    row = db.execute(
        text("SELECT id, email, display_name, avatar_url, provider, created_at FROM users WHERE email = :email"),
        {"email": body.email},
    ).fetchone()
    r = row._mapping  # type: ignore[attr-defined]
    return UserResponse(
        id=str(r["id"]),
        email=r["email"],
        display_name=r["display_name"],
        avatar_url=r["avatar_url"],
        provider=r["provider"],
        created_at=r["created_at"],
    )


@router.get("/me", dependencies=[Depends(verify_internal_key)])
def get_me(email: str, db: Session = Depends(get_db)) -> UserResponse:
    """Look up a user by email — used by Next.js server components."""
    row = db.execute(
        text("SELECT id, email, display_name, avatar_url, provider, created_at FROM users WHERE email = :email"),
        {"email": email},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    r = row._mapping  # type: ignore[attr-defined]
    return UserResponse(
        id=str(r["id"]),
        email=r["email"],
        display_name=r["display_name"],
        avatar_url=r["avatar_url"],
        provider=r["provider"],
        created_at=r["created_at"],
    )
