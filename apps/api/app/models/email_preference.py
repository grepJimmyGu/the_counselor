"""Email preferences (Stage 6a).

Per-user toggles for marketing email categories. Transactional email
(verify, payment failed, password reset) is sent regardless — legally
required.

Note: user_id is intentionally NOT a FK to users.id (Stage 1a rule).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EmailPreference(Base):
    __tablename__ = "email_preferences"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Transactional email — cannot legally be opted out of. Stored for symmetry.
    transactional: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )

    # Marketing categories — users CAN opt out.
    weekly_digest: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )
    upsell_nudges: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )
    creator_program: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )

    # Set when the user globally unsubscribes (one-click CAN-SPAM link).
    # Resend webhook also sets this on hard bounce + complained.
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
