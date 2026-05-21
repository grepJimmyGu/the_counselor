"""Attribution visit (Stage 4).

Records a watermarked share-URL click. Frontend POSTs to
/api/community/attribution/track on /s/[slug] page mount when ?via=<handle>
is present. A `livermore_vsid` cookie is set so subsequent visits and the
eventual signup can be joined back to the original referrer.

Stage 5's Creator Program uses this table to compute referral payouts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AttributionVisit(Base):
    """Note: referrer_user_id and converted_to_user_id are intentionally NOT
    FKs to users.id (Stage 1a lesson)."""

    __tablename__ = "attribution_visits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # First-party cookie value, 90-day. Joins this row to the eventual signup.
    visitor_session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # The handle from ?via=<handle> on the share URL.
    referrer_handle: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Resolved at track time — denormalized so Stage 5's payout query is fast.
    referrer_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    landed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False,
    )
    landed_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Set on signup (auth.py reads cookie + finds the row).
    converted_to_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Set on customer.subscription.created (Stripe webhook).
    converted_to_paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
