"""Anonymous browser session (Stage 1a).

Enforces the one-fresh-backtest-per-anonymous rule and preserves attribution
through the anonymous → signup → paid funnel. A cookie (`livermore_anon_id`,
90-day) carries the session id across requests.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AnonymousSession(Base):
    """Note: converted_to_user_id is intentionally NOT a FOREIGN KEY. Production
    users.id may have been created as UUID (PR #5 before we reverted the model),
    and Postgres rejects FK constraints between mismatched types. Matches the
    community-tables pattern; app-layer enforces user identity."""

    __tablename__ = "anonymous_sessions"

    # UUID stored in the livermore_anon_id cookie.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # FingerprintJS visitorId, hashed. Optional; used only when IP rate-limit triggers.
    fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    ip_first_seen: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_last_seen: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    locale: Mapped[str] = mapped_column(
        String(8), default="en", server_default="en", nullable=False
    )

    # 0 or 1 — the anonymous one-shot cap.
    runs_used: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Most recent backtest result (links to backtests.id; intentionally not a FK
    # because the backtest may be deleted while the session row persists for analytics).
    last_backtest_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Referrer handle from /s/<slug>?via=<handle> — preserves Creator Program credit
    # through the anonymous → signup → paid funnel.
    via_handle: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    landed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Set when the anonymous user converts.
    converted_to_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    converted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
