"""Health monitor cron job (PR-C of the 2026-06-07 reliability stack).

Polls the in-process `/health` state every minute. When the pulse warmup
flips to degraded, fires an email alert to `OPS_ALERT_RECIPIENT`. When
it recovers, fires a "recovered" follow-up so Jimmy knows the incident
is over without checking manually.

Design notes (load-bearing):

  - **Boot window**: skip alerts for the first `BOOT_WINDOW_SECONDS`
    after process start. The warmup hasn't fired its first tick yet, so
    the state legitimately reads "degraded" but it's not an outage.
  - **Cooldown**: when degraded persists, don't spam. The first onset
    fires immediately; reminders are throttled to one per
    `ops_health_alert_cooldown_minutes`. (Default 60 — adjustable.)
  - **State**: module-level dict, same pattern as `_pulse_warmup_state`
    in `app.main`. We don't persist across container restarts — a new
    container starts in the boot window and re-alerts after that if
    things are still bad. Acceptable tradeoff for ops simplicity.
  - **Failure isolation**: any exception in this job is caught at the
    top level + logged with `logger.exception` (trap #20). A cron that
    can't run is worse than a cron that misses one tick.
  - **Disable switch**: `OPS_HEALTH_ALERTS_ENABLED=false` (the default)
    skips the entire job. Lets you ship the wiring without committing
    to a notification flow until you've set the recipient.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.core.config import get_settings

logger = logging.getLogger("livermore.health_monitor")

# How long after process start to suppress alerts (the warmup needs ~5
# min to fire its first tick). Public so tests can override.
BOOT_WINDOW_SECONDS = 300

# Set once at module import — the alert job uses this to compute "are we
# still in the boot window." Module import happens as part of
# `_start_scheduler` registration on app startup, so this matches the
# process start time closely.
_PROCESS_START_AT = time.monotonic()


_state: dict[str, Any] = {
    # The status reported on the most recent tick. None until the first
    # tick has run. Used to detect transitions (ok → degraded fires the
    # onset alert; degraded → ok fires the recovery alert).
    "last_status": None,
    # Timestamp of the most recent onset alert sent (for cooldown).
    "last_alert_at": None,
    # Timestamp the most recent "degraded" stretch began. Used for the
    # recovery email's duration line.
    "degraded_since": None,
}


def _reset_state_for_tests() -> None:
    """Test-only — clear module state so each test starts deterministic."""
    _state["last_status"] = None
    _state["last_alert_at"] = None
    _state["degraded_since"] = None


def _in_boot_window() -> bool:
    return (time.monotonic() - _PROCESS_START_AT) < BOOT_WINDOW_SECONDS


def _cooldown_elapsed(cooldown_seconds: int) -> bool:
    last_alert = _state["last_alert_at"]
    if last_alert is None:
        return True
    return (time.monotonic() - last_alert) >= cooldown_seconds


def health_monitor_job() -> None:
    """Run one polling tick. Safe under APScheduler — never raises."""
    try:
        _tick()
    except Exception:
        logger.exception("health_monitor_job tick failed")


def _tick() -> None:
    settings = get_settings()
    if not settings.ops_health_alerts_enabled:
        return

    # Late import — avoids circular import at module load and lets tests
    # patch `app.main.compute_health_state` cleanly.
    from app.main import compute_health_state

    payload = compute_health_state()
    current_status: str = payload.get("status", "ok")
    prev_status: Optional[str] = _state["last_status"]

    if _in_boot_window():
        # Don't alert; do still update last_status so we don't fire a
        # spurious "recovered" the first tick out of the boot window.
        _state["last_status"] = current_status
        if current_status == "degraded" and _state["degraded_since"] is None:
            # Track the start of a possible incident for the recovery
            # email's duration line, even though we won't fire onset
            # until after boot.
            _state["degraded_since"] = time.monotonic()
        return

    cooldown_seconds = max(60, settings.ops_health_alert_cooldown_minutes * 60)

    if current_status == "degraded":
        if prev_status != "degraded":
            # Fresh onset — alert immediately, record degraded_since for
            # the eventual recovery email's duration line.
            _state["degraded_since"] = time.monotonic()
            _maybe_send_alert(payload, is_first=True)
        else:
            # Persistent degraded — alert only if the cooldown has elapsed.
            if _cooldown_elapsed(cooldown_seconds):
                _maybe_send_alert(payload, is_first=False)
    elif current_status == "ok":
        if prev_status == "degraded":
            # Recovery — send the recovered-email, reset incident state.
            duration_seconds = 0
            if _state["degraded_since"] is not None:
                duration_seconds = int(time.monotonic() - _state["degraded_since"])
            _maybe_send_recovery(payload, duration_seconds)
            _state["degraded_since"] = None
            _state["last_alert_at"] = None

    _state["last_status"] = current_status


def _maybe_send_alert(payload: dict[str, Any], is_first: bool) -> None:
    """Fire the degraded-onset (or reminder) email."""
    from app.emails.health_degraded import render_health_degraded
    from app.services.ops_email_service import send_ops_email

    msg = render_health_degraded(payload)
    sent = send_ops_email(subject=msg["subject"], html=msg["html"], text=msg["text"])
    if sent or is_first:
        # Record the attempt either way so cooldown applies even if
        # Resend was misconfigured (avoids tight retry loops).
        _state["last_alert_at"] = time.monotonic()


def _maybe_send_recovery(payload: dict[str, Any], duration_seconds: int) -> None:
    from app.emails.health_degraded import render_health_recovered
    from app.services.ops_email_service import send_ops_email

    msg = render_health_recovered(payload, duration_seconds)
    send_ops_email(subject=msg["subject"], html=msg["html"], text=msg["text"])
