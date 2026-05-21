"""PostHog analytics — safe no-op wrapper (Stage 6a).

Call `capture(user_id, event, props)` from anywhere in the app. The wrapper:
  - Lazily imports `posthog` only when POSTHOG_API_KEY is set
  - Silently no-ops if the key is missing OR the package isn't installed
  - Catches all PostHog errors so analytics never breaks a user request

To enable in production:
  1. `pip install posthog` (add to requirements.txt at the same time)
  2. Set env var POSTHOG_API_KEY=phc_...
  3. Optionally override POSTHOG_HOST (default: https://us.posthog.com)
  4. Redeploy. Events start firing on the next request.

Until then: every call site is correct; nothing fires.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import get_settings

_log = logging.getLogger("livermore.analytics")

# Module-level cached client. None until first call, then either a Posthog
# instance or False (meaning we tried and failed to set one up — don't retry).
_client: Any = None


def _get_client() -> Any:
    """Lazy-init. Returns the Posthog client or None if disabled/unavailable."""
    global _client
    if _client is False:
        return None
    if _client is not None:
        return _client

    settings = get_settings()
    key = settings.posthog_api_key
    if not key:
        _client = False
        return None

    try:
        from posthog import Posthog  # type: ignore[import-not-found]
        _client = Posthog(project_api_key=key, host=settings.posthog_host)
        _log.info("posthog_service: initialized")
        return _client
    except ImportError:
        _log.warning("posthog package not installed; analytics disabled")
        _client = False
        return None
    except Exception as exc:
        _log.warning("posthog_service init failed: %s", exc)
        _client = False
        return None


def capture(
    user_id: str,
    event: str,
    properties: Optional[dict] = None,
) -> None:
    """Fire an analytics event. Silent no-op when PostHog isn't configured."""
    client = _get_client()
    if client is None:
        return
    try:
        client.capture(distinct_id=user_id, event=event, properties=properties or {})
    except Exception as exc:
        # Never let analytics fail a user request.
        _log.warning("posthog capture failed for event=%s: %s", event, exc)


def identify(user_id: str, properties: Optional[dict] = None) -> None:
    """Attach traits to a user. Silent no-op when disabled."""
    client = _get_client()
    if client is None:
        return
    try:
        client.identify(distinct_id=user_id, properties=properties or {})
    except Exception as exc:
        _log.warning("posthog identify failed: %s", exc)


def get_feature_flag(
    flag_key: str,
    user_id: str,
    default: Any = None,
) -> Any:
    """Resolve a PostHog feature-flag value for *user_id*. Returns *default*
    if PostHog is disabled, the flag is undefined, or any error occurs.
    Deterministic for a given (user_id, flag_key) on PostHog's side."""
    client = _get_client()
    if client is None:
        return default
    try:
        value = client.get_feature_flag(flag_key, user_id)
        if value is None:
            return default
        return value
    except Exception as exc:
        _log.warning("posthog get_feature_flag failed for %s: %s", flag_key, exc)
        return default
