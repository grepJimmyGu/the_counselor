"""One emailed password-reset code.

`user_id` is deliberately not a foreign key to users.id (see apps/api/CLAUDE.md,
trap 1). The code itself is never stored, only a keyed hash of it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PasswordResetCode(Base):
    __tablename__ = "password_reset_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Wrong guesses made against this code.
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Set when the code can no longer be used: it reset a password, ran out
    # of guesses, or was replaced by a newer one.
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
