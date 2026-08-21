"""One Livermore user's SnapTrade registration.

SnapTrade issues a `userSecret` at registration and every later call needs
it. It cannot be re-derived — it IS that user's identity to SnapTrade — so
it has to be stored, and a credential to somebody's brokerage connection
should not sit in the database in plaintext. `user_secret_encrypted` holds
a Fernet token; the plaintext exists only in memory, for the duration of a
call. See `app/services/snaptrade_service.py`.

`user_id` carries NO ForeignKey (apps/api/CLAUDE.md trap #1): production
`users.id` may have been created as UUID while the model says String(36),
and a mismatched FK makes `create_all` fail at startup. Identity is
enforced in the app layer, as it is for every other user-scoped table here.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SnapTradeUser(Base):
    __tablename__ = "snaptrade_users"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_snaptrade_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # SnapTrade's own identifier for this user. Not a secret.
    snaptrade_user_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Fernet token. Never logged, never returned by any route, never
    # serialised into a response model.
    user_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    # Last successful holdings read. Lets the UI say how fresh the position
    # data is rather than implying it is live.
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
