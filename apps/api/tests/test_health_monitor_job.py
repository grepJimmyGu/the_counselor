"""Tests for the ops health monitor cron (PR-C).

Pins the alert state machine:
  - Disabled flag short-circuits the job
  - First degraded transition fires the onset email
  - Persistent degraded respects the cooldown (no duplicate within
    `ops_health_alert_cooldown_minutes`)
  - Recovery transition fires the "recovered" email + clears state
  - Boot window suppresses alerts but tracks degraded_since
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.jobs import health_monitor_job as job_mod
from app.jobs.health_monitor_job import (
    _reset_state_for_tests,
    _state,
    health_monitor_job,
)


@pytest.fixture(autouse=True)
def _reset_module_state():
    _reset_state_for_tests()
    # Make sure each test starts past the boot window so most tests
    # don't have to think about it. Boot-window-specific tests will
    # override this.
    job_mod._PROCESS_START_AT = time.monotonic() - 600  # 10 min ago
    yield
    _reset_state_for_tests()


@pytest.fixture(autouse=True)
def _enable_alerts(monkeypatch):
    """Default to enabled + recipient set so the cron actually runs.
    Disabled-flag test overrides this."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ops_health_alerts_enabled", True)
    monkeypatch.setattr(settings, "ops_alert_recipient", "jimmy@example.com")
    monkeypatch.setattr(settings, "ops_health_alert_cooldown_minutes", 60)
    yield


def _patch_health(payload):
    """Patch the in-process /health computation to return `payload`."""
    return patch("app.main.compute_health_state", return_value=payload)


def _ok_payload():
    return {
        "status": "ok",
        "pulse_warmup": {
            "healthy": True,
            "last_success_at": "2026-06-07T13:38:17+00:00",
            "age_seconds": 60,
            "consecutive_failures": 0,
            "last_error": None,
        },
    }


def _degraded_payload():
    return {
        "status": "degraded",
        "pulse_warmup": {
            "healthy": False,
            "last_success_at": "2026-06-07T13:00:00+00:00",
            "age_seconds": 2300,
            "consecutive_failures": 5,
            "last_error": "RuntimeError: cross-loop lock",
        },
    }


def test_disabled_flag_short_circuits_the_job(monkeypatch):
    """When OPS_HEALTH_ALERTS_ENABLED is false, the job does nothing —
    no /health computation, no email send, no state changes."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ops_health_alerts_enabled", False)
    with _patch_health(_degraded_payload()) as patched_health, patch(
        "app.services.ops_email_service.send_ops_email"
    ) as patched_send:
        # We expect compute_health_state to NOT even be called.
        health_monitor_job()
        patched_health.assert_not_called()
        patched_send.assert_not_called()
    # State should remain at its initial sentinel.
    assert _state["last_status"] is None


def test_first_degraded_tick_fires_onset_alert():
    """ok → (no prior state) → degraded triggers the onset email
    immediately, no cooldown gating because there's nothing to throttle
    against yet."""
    with _patch_health(_degraded_payload()), patch(
        "app.services.ops_email_service.send_ops_email", return_value=True
    ) as patched_send:
        health_monitor_job()
        assert patched_send.call_count == 1, (
            "first degraded tick must fire exactly one onset email"
        )
    assert _state["last_status"] == "degraded"
    assert _state["degraded_since"] is not None
    assert _state["last_alert_at"] is not None


def test_persistent_degraded_respects_cooldown():
    """Two consecutive degraded ticks 1 min apart must result in only
    ONE email — the second is throttled because cooldown (60 min by
    default) hasn't elapsed."""
    with _patch_health(_degraded_payload()), patch(
        "app.services.ops_email_service.send_ops_email", return_value=True
    ) as patched_send:
        health_monitor_job()  # onset
        health_monitor_job()  # persistent, should be throttled
        assert patched_send.call_count == 1, (
            f"persistent degraded should throttle to 1 email; got "
            f"{patched_send.call_count}"
        )


def test_persistent_degraded_fires_reminder_after_cooldown(monkeypatch):
    """If degraded persists past the cooldown window, the next tick fires
    a reminder email."""
    with _patch_health(_degraded_payload()), patch(
        "app.services.ops_email_service.send_ops_email", return_value=True
    ) as patched_send:
        health_monitor_job()  # onset
        # Simulate cooldown elapsing by backdating last_alert_at.
        _state["last_alert_at"] = time.monotonic() - (61 * 60)  # 61 min ago
        health_monitor_job()  # should fire reminder
        assert patched_send.call_count == 2


def test_recovery_fires_recovered_email_and_resets_state():
    """degraded → ok flips state, sends recovery email, clears the
    incident counters so a new incident later starts fresh."""
    with _patch_health(_degraded_payload()), patch(
        "app.services.ops_email_service.send_ops_email", return_value=True
    ):
        health_monitor_job()  # onset

    with _patch_health(_ok_payload()), patch(
        "app.services.ops_email_service.send_ops_email", return_value=True
    ) as patched_send_ok:
        health_monitor_job()  # recovery
        assert patched_send_ok.call_count == 1, "recovery must fire 1 email"
        # Verify recovery template (not onset) by inspecting subject
        call_kwargs = patched_send_ok.call_args.kwargs
        assert "recovered" in call_kwargs["subject"].lower()

    assert _state["last_status"] == "ok"
    assert _state["degraded_since"] is None
    assert _state["last_alert_at"] is None


def test_boot_window_suppresses_alerts_but_tracks_degraded_since():
    """During the boot window (first 5 min after process start), the
    job sees degraded but does NOT email. It does still mark
    `degraded_since` so the eventual recovery email can compute
    incident duration honestly."""
    # Move the process start back to "just now" so we're in the window.
    job_mod._PROCESS_START_AT = time.monotonic()

    with _patch_health(_degraded_payload()), patch(
        "app.services.ops_email_service.send_ops_email"
    ) as patched_send:
        health_monitor_job()
        patched_send.assert_not_called()

    assert _state["last_status"] == "degraded"
    assert _state["degraded_since"] is not None


def test_ok_to_ok_is_no_op():
    """Healthy → still healthy: no email, no state thrash."""
    with _patch_health(_ok_payload()), patch(
        "app.services.ops_email_service.send_ops_email"
    ) as patched_send:
        health_monitor_job()
        health_monitor_job()
        patched_send.assert_not_called()
    assert _state["last_alert_at"] is None
    assert _state["degraded_since"] is None
