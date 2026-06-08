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

    # PRD-19 Step 4a: signal alerts + daily digest + silent-days flag.
    #
    # `signal_alerts_enabled` is a GLOBAL kill-switch for signal-change emails
    # (Step 3b's `dispatch_signal_change_email`). The per-strategy mute happens
    # at `SignalAlertSubscription.email_enabled` (Step 4c will route the
    # signed `signal_alerts_<strategy_id>` unsub tokens to it). This flag lets
    # the user nuke ALL signal emails in one toggle from the settings page.
    #
    # `daily_digest_enabled` is the morning-brief opt-in (PRD-19 trigger #2 —
    # distinct from `weekly_digest` above, which is the legacy Stage 6a
    # marketing newsletter). Step 4b's `daily_digest_job` reads this flag.
    #
    # `silent_days_enabled` is the "only when there's news" toggle — when on,
    # the daily digest skips days where no subscribed strategy changed signal.
    # `notification_throttle.should_skip_digest` already implements the check;
    # this flag is the user-facing input it reads.
    #
    # All three default to True so existing users keep getting alerts after
    # the migration. The migration uses ADD COLUMN with server_default true.
    signal_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )
    daily_digest_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False,
    )
    silent_days_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
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
