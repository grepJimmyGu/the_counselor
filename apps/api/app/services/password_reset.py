"""Resetting a forgotten password with a code sent by email.

The code is six digits, typed back into the app or the site. A link would be
the usual choice; a code is used because it needs no page to land on, and
works the same in the iOS app and on the web.

Six digits is a million possibilities, so the limits below are what make it
safe, not the code's length:
  - a code lasts CODE_LIFETIME and allows MAX_ATTEMPTS wrong guesses
  - an account can be sent MAX_PER_HOUR codes an hour and MAX_PER_DAY a day
  - asking for a new code closes the old one
At those limits a guesser gets 15 tries an hour at one account.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.password_reset import PasswordResetCode
from app.models.user import User
from app.services.auth_service import hash_password

CODE_LENGTH = 6
CODE_LIFETIME = timedelta(minutes=15)
MAX_ATTEMPTS = 5
MAX_PER_HOUR = 3
MAX_PER_DAY = 6
# Rows older than this are of no use to the daily limit and are deleted.
_KEEP = timedelta(days=2)

logger = logging.getLogger("livermore.auth")


def _hash(user_id: str, code: str) -> str:
    key = get_settings().nextauth_secret.encode()
    return hmac.new(key, f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _open_codes(db: Session, user_id: str, now: datetime):
    return (
        db.query(PasswordResetCode)
        .filter(
            PasswordResetCode.user_id == user_id,
            PasswordResetCode.closed_at.is_(None),
            PasswordResetCode.expires_at > now,
        )
        .order_by(PasswordResetCode.created_at.desc())
    )


def issue_code(db: Session, user: User, now: Optional[datetime] = None) -> Optional[str]:
    """Create a reset code for `user` and return it, or None if the account
    has been sent as many as it is allowed for now. The caller emails it."""
    now = now or datetime.utcnow()
    user_id = user.id
    db.query(PasswordResetCode).filter(
        PasswordResetCode.user_id == user_id,
        PasswordResetCode.created_at < now - _KEEP,
    ).delete(synchronize_session=False)

    def sent_since(cutoff: datetime) -> int:
        return (
            db.query(PasswordResetCode)
            .filter(PasswordResetCode.user_id == user_id, PasswordResetCode.created_at > cutoff)
            .count()
        )

    if sent_since(now - timedelta(hours=1)) >= MAX_PER_HOUR or sent_since(now - timedelta(days=1)) >= MAX_PER_DAY:
        db.commit()
        logger.info("password reset throttled: user_id=%s", user_id)
        return None

    # Only the newest code works, so an older email cannot be used after a
    # newer one was asked for.
    for older in _open_codes(db, user_id, now):
        older.closed_at = now
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    db.add(PasswordResetCode(
        id=str(uuid.uuid4()),
        user_id=user_id,
        code_hash=_hash(user_id, code),
        created_at=now,
        expires_at=now + CODE_LIFETIME,
    ))
    db.commit()
    return code


def check_code(db: Session, user: User, code: str, now: Optional[datetime] = None) -> Optional[PasswordResetCode]:
    """The account's open code if `code` matches it, else None. A wrong guess
    is counted, and the last one allowed closes the code."""
    now = now or datetime.utcnow()
    current = _open_codes(db, user.id, now).first()
    if current is None:
        return None
    if hmac.compare_digest(current.code_hash, _hash(user.id, code.strip())):
        return current
    current.attempts += 1
    if current.attempts >= MAX_ATTEMPTS:
        current.closed_at = now
    db.commit()
    return None


def set_password(db: Session, user: User, used: PasswordResetCode, new_password: str, now: Optional[datetime] = None) -> None:
    """Give `user` the new password and close the code that allowed it."""
    # Whole seconds, because that is all a session token records: a token
    # minted later in this same second must not look older than the reset.
    now = (now or datetime.utcnow()).replace(microsecond=0)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    # Typing back a code sent to the address is proof the address is theirs.
    if user.email_verified_at is None:
        user.email_verified_at = now
    user.last_login_at = now
    used.closed_at = now
    db.commit()
