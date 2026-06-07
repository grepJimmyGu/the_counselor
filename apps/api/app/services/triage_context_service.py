"""Triage context bundle composer (PR-D of the 2026-06-07 reliability stack).

When `/health` flips to degraded, the PR-C email already wakes Jimmy up.
The natural next step is "open a fresh Claude session, paste a prompt,
diagnose." PR-D shortens that loop by composing the prompt + context
bundle on the backend so Jimmy literally copies one block into Claude.

The composer:
  - Reads the current `/health` snapshot via the shared
    `compute_health_state()` from `app.main`
  - Matches the most recent `last_error` against the known traps in
    `apps/api/CLAUDE.md` (keyword-based, intentionally simple)
  - Reads the last N commit SHAs + subjects so the agent knows what
    just shipped (often the trigger)
  - Renders the whole thing as a markdown block that's safe to drop
    into a Claude session as-is

Design choices:
  - **No external API calls** — everything is local file reads or
    in-process state. Triage must work even when external services are
    flaky (which is often *why* we're triaging).
  - **No log lines yet** — Railway log access requires the Railway CLI
    or a stored credential; both add complexity and a credential
    rotation surface. The agent can curl `/health` itself once the
    triage prompt is open. Future work could add a `recent_logs`
    section if we wire log forwarding.
  - **Keyword-based trap matching, not ML** — the trap titles are short
    and stable; a 30-line keyword map is more reliable than fuzzy
    matching and easier to update when we add trap #23+.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("livermore.triage")


# Keyword → (trap number, title). When the last_error text contains any
# of the keywords, the matching trap surfaces in the prompt's "Suspected
# traps" list. Order matters only for readability — multiple matches OK.
# Keep this list short; the goal is "good hints," not "perfect oracle."
_TRAP_KEYWORD_MAP: list[tuple[tuple[str, ...], int, str]] = [
    (("bound to a different event loop", "event loop"), 22, "asyncio primitives bind to first event loop"),
    (("RuntimeError",), 22, "asyncio primitives bind to first event loop"),
    (("Waiting for application startup",), 11, "Production hangs at 'Waiting for application startup'"),
    (("Application startup complete",), 21, "async def lifespan tasks with sync DB block the loop"),
    (("InFailedSqlTransaction",), 3, "try/except DDL in shared engine.begin block"),
    (("DetachedInstanceError",), 17, "intermediate commits expire ORM instances"),
    (("DiskFull", "No space left",), 10, "Postgres disk headroom on backfill"),
    (("ResponseValidationError",), 7, "FastAPI 0.115 response-model strictness"),
    (("could not extend file",), 10, "Postgres disk headroom on backfill"),
    (("connection timed out", "connect timeout", "Connection refused"), 11, "Postgres process wedge"),
    (("date >= varchar", "operator does not exist: date >="), 20, "string→date SQLAlchemy comparison"),
    (("rollback",), 12, ":bind::type Postgres cast in text() silently failed"),
    (("string_type", "value is not a valid",), 7, "FastAPI 0.115 response-model strictness"),
]


def _match_traps_for_error(error_text: Optional[str]) -> list[tuple[int, str]]:
    """Return (trap_number, title) tuples for traps that match the error
    text. De-duplicated by trap number. Empty list if no error or no match."""
    if not error_text:
        return []
    text = error_text.lower()
    seen: set[int] = set()
    matches: list[tuple[int, str]] = []
    for keywords, num, title in _TRAP_KEYWORD_MAP:
        if num in seen:
            continue
        for kw in keywords:
            if kw.lower() in text:
                matches.append((num, title))
                seen.add(num)
                break
    return matches


def _recent_commits(limit: int = 5) -> list[tuple[str, str]]:
    """Return [(short_sha, subject)] for the last N commits. Empty list
    on any failure — git history is best-effort context, never required."""
    repo_root = Path(__file__).resolve().parents[3]  # apps/api/app/services → repo root
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "log", f"-{limit}", "--pretty=%h\x1f%s"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        logger.exception("triage _recent_commits failed")
        return []

    commits: list[tuple[str, str]] = []
    for line in result.stdout.strip().split("\n"):
        if "\x1f" in line:
            sha, subject = line.split("\x1f", 1)
            commits.append((sha, subject))
    return commits


def compose_triage_context(health_payload: dict[str, Any]) -> str:
    """Compose the markdown triage prompt + context bundle.

    `health_payload` is the dict returned by `compute_health_state()` —
    passed in so callers don't have to import `app.main` (avoids a
    circular import at module load time).
    """
    pulse = health_payload.get("pulse_warmup", {}) or {}
    status = health_payload.get("status", "ok")
    age_seconds = pulse.get("age_seconds")
    age_str = "unknown" if age_seconds is None else f"{age_seconds // 60} min {age_seconds % 60} s"
    consecutive_failures = pulse.get("consecutive_failures", 0)
    last_error = pulse.get("last_error") or "(none recorded)"
    last_success_at = pulse.get("last_success_at") or "never"

    traps = _match_traps_for_error(pulse.get("last_error"))
    if traps:
        trap_lines = "\n".join(f"  - **Trap #{num}** — {title}" for num, title in traps)
    else:
        trap_lines = "  - (no keyword matches — read `apps/api/CLAUDE.md` traps top-to-bottom)"

    commits = _recent_commits()
    if commits:
        commit_lines = "\n".join(f"  - `{sha}` — {subj}" for sha, subj in commits)
    else:
        commit_lines = "  - (no commits read — `git log` failed; check the file directly)"

    return f"""# Livermore triage — `/health` is **{status.upper()}**

You're triaging a Livermore production incident. The health monitor cron
detected a degraded warmup. Diagnose the root cause and propose a fix.

**Read first:** `apps/api/CLAUDE.md` (the trap catalog). Many incidents in
this codebase repeat a known trap pattern; the matcher below has a guess.

## /health snapshot

- **Status:** {status}
- **Last successful warmup tick:** {last_success_at} ({age_str} ago)
- **Consecutive failures since last success:** {consecutive_failures}
- **Last recorded error:** `{last_error}`

## Suspected traps (keyword match against `last_error`)

{trap_lines}

## Recent commits (most recent first)

{commit_lines}

## Your task

1. Read the suspected trap(s) in `apps/api/CLAUDE.md`. Confirm or rule out.
2. If no trap matches: search `docs/KNOWN_ISSUES.md` for the symptom.
3. Curl `/health` for an updated snapshot: `curl -s https://thecounselor-production.up.railway.app/health | python3 -m json.tool`
4. Propose a one-paragraph diagnosis + a surgical fix (file path + line + change).
5. **Do NOT push code.** Return the diagnosis + fix as a markdown report.
   Jimmy will review and approve before any commit.

## Discipline reminders

- Bug-fix commit message must follow the **symptom → cause → fix** rule
  (`CLAUDE.md` "Bug fixes" section).
- Every bug fix pairs with a regression test (`CLAUDE.md` "Test discipline").
- If your fix introduces a new latent failure mode, propose a new trap
  entry to add to `apps/api/CLAUDE.md`.
"""
