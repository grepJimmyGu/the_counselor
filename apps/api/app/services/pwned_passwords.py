"""Has this password appeared in a known breach?

Asks Have I Been Pwned's range API, which is built so the password never
leaves the server: only the first five hex characters of its SHA-1 are sent,
and the match is made here against the few hundred suffixes that come back.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx

_RANGE_URL = "https://api.pwnedpasswords.com/range/"
_TIMEOUT_SECONDS = 3.0

logger = logging.getLogger("livermore.auth")


def breach_count(password: str) -> Optional[int]:
    """How many times `password` appears in breach data, or None if the
    lookup could not be made. A caller should treat None as "unknown" and let
    the sign-up through: an outage at a third party must not close sign-ups.
    """
    # SHA-1 because it is the key the range API is indexed by, not because it
    # protects anything: the digest is a lookup key, used once and never stored.
    # Stored passwords are bcrypt (auth_service.hash_password).
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        # Add-Padding makes every response the same size, so the length of
        # the reply says nothing about the prefix asked for.
        response = httpx.get(
            _RANGE_URL + prefix,
            headers={"Add-Padding": "true"},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("breach lookup unavailable: %s", type(exc).__name__)
        return None
    for line in response.text.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip() == suffix:
            return int(count.strip() or 0)
    return 0
