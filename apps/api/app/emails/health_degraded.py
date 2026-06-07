"""Email templates for the ops health alerter (PR-C).

Two shapes:
  - **degraded onset** — fired the first time `/health` flips to degraded
    after being healthy
  - **recovery** — fired when `/health` flips back to ok after being
    degraded

Plain HTML — no React Email build step. Mirrors the `welcome.py` style.
No unsubscribe link / CAN-SPAM footer because this is an ops alert to
Jimmy, not marketing to a user — different deliverability rules.
"""
from __future__ import annotations

import os
from typing import Any


def _site_url() -> str:
    return os.environ.get("NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com")


def _backend_url() -> str:
    # Configurable so dev / staging emails point at the right host.
    return os.environ.get(
        "OPS_ALERT_BACKEND_URL",
        "https://thecounselor-production.up.railway.app",
    )


def render_health_degraded(payload: dict[str, Any]) -> dict[str, str]:
    """Render the "warmup degraded" alert.

    `payload` is the /health response — pulls `pulse_warmup.age_seconds`,
    `consecutive_failures`, and `last_error` to give Jimmy a quick scan
    of what to look at without opening the dashboard.
    """
    pulse = payload.get("pulse_warmup", {}) or {}
    age = pulse.get("age_seconds")
    fails = pulse.get("consecutive_failures", 0)
    last_err = pulse.get("last_error") or "(none recorded)"
    last_success = pulse.get("last_success_at") or "never"

    age_str = "unknown" if age is None else f"{age // 60} min {age % 60} s ago"

    subject = "[Livermore] /health degraded — pulse warmup is stale"

    text = f"""Livermore /health flipped to DEGRADED.

Last successful pulse warmup tick: {last_success} ({age_str})
Consecutive failures since last success: {fails}
Last recorded error: {last_err}

Quick links:
  - /health endpoint:    {_backend_url()}/health
  - Market Pulse page:   {_site_url()}/stocks
  - Railway dashboard:   https://railway.app/dashboard

This alert fires when the warmup has either gone silent for > 10 min
or failed 3 consecutive ticks. Repeat alerts are throttled — you'll
get one reminder per cooldown window if it stays degraded, and a
"recovered" email when /health returns to OK.

Run the triage skill: paste the /health JSON above into a new Claude
session and ask for a diagnosis. See LEARNINGS.md "Cold paths are
invisible in dev" for the framing.
"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject}</title></head>
<body style="margin:0;padding:24px;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.55;color:#0f172a;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" width="560" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #fcd34d;border-radius:12px;">
    <tr><td style="padding:24px 28px 8px 28px;border-bottom:1px solid #fef3c7;">
      <p style="margin:0 0 4px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:#b45309;">Livermore Ops Alert</p>
      <h1 style="margin:0;font-size:18px;font-weight:700;color:#92400e;">/health flipped to DEGRADED</h1>
    </td></tr>
    <tr><td style="padding:20px 28px 12px 28px;">
      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
        <tr><td style="padding:6px 0;font-size:13px;color:#475569;">Last good tick</td><td style="padding:6px 0;font-size:13px;font-weight:600;color:#0f172a;text-align:right;">{age_str}</td></tr>
        <tr><td style="padding:6px 0;font-size:13px;color:#475569;border-top:1px solid #f1f5f9;">Consecutive failures</td><td style="padding:6px 0;font-size:13px;font-weight:600;color:#0f172a;text-align:right;border-top:1px solid #f1f5f9;">{fails}</td></tr>
        <tr><td style="padding:6px 0;font-size:13px;color:#475569;border-top:1px solid #f1f5f9;vertical-align:top;">Last error</td><td style="padding:6px 0;font-size:12px;color:#0f172a;text-align:right;border-top:1px solid #f1f5f9;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;word-break:break-all;">{last_err}</td></tr>
      </table>
    </td></tr>
    <tr><td style="padding:8px 28px 24px 28px;">
      <p style="margin:0 0 10px;font-size:13px;color:#334155;">Quick links:</p>
      <p style="margin:0;font-size:13px;line-height:1.9;">
        <a href="{_backend_url()}/health" style="color:#0ea5e9;text-decoration:none;font-weight:600;">/health endpoint →</a><br>
        <a href="{_site_url()}/stocks" style="color:#0ea5e9;text-decoration:none;font-weight:600;">Market Pulse page →</a><br>
        <a href="https://railway.app/dashboard" style="color:#0ea5e9;text-decoration:none;font-weight:600;">Railway dashboard →</a>
      </p>
    </td></tr>
    <tr><td style="padding:14px 28px;border-top:1px solid #e2e8f0;background:#f8fafc;border-radius:0 0 12px 12px;">
      <p style="margin:0;font-size:11px;color:#64748b;line-height:1.55;">
        This alert fires when the warmup has either gone silent for &gt; 10 min or failed 3 consecutive ticks. Repeats are throttled to one per cooldown window; a "recovered" email follows when /health returns to OK.
      </p>
    </td></tr>
  </table>
</body>
</html>"""

    return {"subject": subject, "html": html, "text": text}


def render_health_recovered(payload: dict[str, Any], degraded_for_seconds: int) -> dict[str, str]:
    """Render the "recovered" follow-up.

    Sent when /health goes ok after being degraded — closes the loop so
    Jimmy knows the incident is over without having to check manually.
    """
    pulse = payload.get("pulse_warmup", {}) or {}
    age = pulse.get("age_seconds")
    age_str = "just now" if age is None or age < 60 else f"{age // 60} min ago"

    duration_min = max(1, degraded_for_seconds // 60)

    subject = "[Livermore] /health recovered — warmup is healthy again"

    text = f"""Livermore /health is back to OK.

Total time degraded: ~{duration_min} min
Most recent successful warmup tick: {age_str}

If you want the post-mortem context, the prior degraded alert email
holds the last_error string + timing. Optionally codify the cause:
docs/KNOWN_ISSUES.md and docs/BUILDING_LIVERMORE_JOURNAL.md.

/health: {_backend_url()}/health
"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject}</title></head>
<body style="margin:0;padding:24px;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.55;color:#0f172a;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" width="560" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #86efac;border-radius:12px;">
    <tr><td style="padding:24px 28px 12px 28px;border-bottom:1px solid #d1fae5;">
      <p style="margin:0 0 4px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:#15803d;">Livermore Ops Recovery</p>
      <h1 style="margin:0;font-size:18px;font-weight:700;color:#166534;">/health is back to OK</h1>
    </td></tr>
    <tr><td style="padding:18px 28px 8px 28px;">
      <p style="margin:0 0 8px;font-size:13px;color:#334155;">Total time degraded: <strong>~{duration_min} min</strong></p>
      <p style="margin:0;font-size:13px;color:#334155;">Most recent successful warmup tick: <strong>{age_str}</strong></p>
    </td></tr>
    <tr><td style="padding:8px 28px 24px 28px;">
      <p style="margin:0;font-size:12px;color:#64748b;">If you want the post-mortem context, the prior degraded alert email holds the last_error string + timing. Optionally codify the cause: <code>docs/KNOWN_ISSUES.md</code> and <code>docs/BUILDING_LIVERMORE_JOURNAL.md</code>.</p>
    </td></tr>
  </table>
</body>
</html>"""

    return {"subject": subject, "html": html, "text": text}
