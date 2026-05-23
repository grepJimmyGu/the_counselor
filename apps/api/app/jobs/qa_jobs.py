from __future__ import annotations

"""QA tripwire jobs.

check_schema_drift_job  — runs daily at 03:00 UTC, compares Base.metadata
                          column types/nullability against the live DB.

Each violation logs `INVARIANT_BROKEN: schema_drift ...` so the existing
`railway logs | grep INVARIANT_BROKEN` workflow surfaces them with zero
new infrastructure. The pattern mirrors `DEFERRED_TRIGGER:` already in
the codebase.

The check is non-destructive — it reads `information_schema` (Postgres)
or sqlite_master (SQLite) and compares against the model. The orphan-heal
in `sync_user` is the only place we mutate; tripwires only report.

Severity tags inside each violation:
  FATAL — incompatible: ORM operations will 500.
  WARN  — silent drift: writes still succeed but invariants are weakened.
  DIFF  — type widens harmlessly (model VARCHAR(500) vs prod TEXT).
  INFO  — prod has columns the model doesn't know about (zombies).
"""

import logging
import os
from typing import Any, Optional

from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.dialects import postgresql, sqlite

logger = logging.getLogger(__name__)

_LOG_PREFIX = "INVARIANT_BROKEN: schema_drift"
_FATAL = "FATAL"
_WARN = "WARN"
_DIFF = "DIFF"
_INFO = "INFO"


def _normalize_db_url(url: str) -> str:
    """Mirror the rewrite in app/db/session.py — Railway hands us `postgresql://`
    but the app ships psycopg3, not psycopg2 (SQLAlchemy's default driver)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def _compile_type(t: Any, dialect: Any) -> str:
    """Compile a SQLAlchemy type to its dialect SQL form, lower-cased.

    Examples (postgresql dialect):
      String(36)              -> "varchar(36)"
      DateTime(timezone=True) -> "timestamp with time zone"
      Boolean                 -> "boolean"
    """
    try:
        return t.compile(dialect=dialect).lower()
    except Exception:
        return str(t).lower()


def _is_harmless_widening(model_type: str, prod_type: str) -> bool:
    """Return True if prod's type strictly accepts every value the model writes.

    Writes succeed; drift is cosmetic. Cases:
      model=varchar(500) prod=text           text accepts anything
      model=varchar(80)  prod=varchar(100)   prod accepts longer strings
      model=float        prod=double precision  SQLAlchemy `Float` always
                                                compiles to FLOAT; Postgres
                                                always stores as double
                                                precision. Numerically
                                                equivalent, pure noise.
    """
    if prod_type == "text" and model_type.startswith("varchar"):
        return True
    if model_type.startswith("varchar(") and prod_type.startswith("varchar("):
        try:
            m_len = int(model_type[len("varchar("):-1])
            p_len = int(prod_type[len("varchar("):-1])
            return p_len > m_len
        except ValueError:
            return False
    if model_type == "float" and prod_type == "double precision":
        return True
    return False


def detect_schema_drift(
    db_url: str,
    metadata: Optional[MetaData] = None,
) -> tuple[int, list[str]]:
    """Compare *metadata* (defaults to Base.metadata) to the live DB at *db_url*.

    Returns (exit_code, violations). The metadata override exists so tests can
    pin a known schema instead of importing the full app model graph.
    """
    if metadata is None:
        from app.db.session import Base
        import app.models  # noqa: F401  triggers SQLAlchemy class registration
        metadata = Base.metadata

    engine = create_engine(_normalize_db_url(db_url), future=True)
    dialect = postgresql.dialect() if engine.dialect.name == "postgresql" else sqlite.dialect()
    insp = inspect(engine)
    prod_tables = set(insp.get_table_names())
    violations: list[str] = []

    for table_name, table in metadata.tables.items():
        if table_name not in prod_tables:
            violations.append(
                f"{_FATAL} table=`{table_name}` missing in DB (model declares it; "
                f"create_all should have made it)"
            )
            continue

        prod_cols = {c["name"]: c for c in insp.get_columns(table_name)}
        model_cols = {c.name: c for c in table.columns}

        for cname in model_cols.keys() - prod_cols.keys():
            violations.append(
                f"{_FATAL} table=`{table_name}` column=`{cname}` missing in DB "
                f"(model declares it)"
            )

        for cname in prod_cols.keys() - model_cols.keys():
            violations.append(
                f"{_INFO} table=`{table_name}` column=`{cname}` exists in DB but "
                f"not in model (legacy column? zombie from a removed feature?)"
            )

        for cname in model_cols.keys() & prod_cols.keys():
            model_col = model_cols[cname]
            prod_col = prod_cols[cname]

            expected = _compile_type(model_col.type, dialect)
            actual = _compile_type(prod_col["type"], dialect)
            if expected != actual:
                severity = _DIFF if _is_harmless_widening(expected, actual) else _WARN
                violations.append(
                    f"{severity} table=`{table_name}` column=`{cname}` "
                    f"type: model={expected} prod={actual}"
                )

            model_nullable = bool(model_col.nullable)
            prod_nullable = bool(prod_col["nullable"])
            if model_nullable != prod_nullable:
                if model_nullable and not prod_nullable:
                    violations.append(
                        f"{_FATAL} table=`{table_name}` column=`{cname}` "
                        f"nullable: model=YES prod=NO (NULL writes will 500)"
                    )
                else:
                    violations.append(
                        f"{_WARN} table=`{table_name}` column=`{cname}` "
                        f"nullable: model=NO prod=YES (silent data integrity gap)"
                    )

    has_blocker = any(v.startswith((_FATAL, _WARN)) for v in violations)
    return (1 if has_blocker else 0), violations


def check_schema_drift_job() -> None:
    """APScheduler entry point. Logs INVARIANT_BROKEN lines for FATAL/WARN drift.

    Safe to call repeatedly — read-only, idempotent.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.warning("%s skipped — DATABASE_URL not set", _LOG_PREFIX)
        return

    try:
        _, violations = detect_schema_drift(db_url)
    except Exception as exc:
        logger.warning("%s errored: %r", _LOG_PREFIX, exc)
        return

    for v in violations:
        if v.startswith((_FATAL, _WARN)):
            logger.warning("%s %s", _LOG_PREFIX, v)


# ── Chat guardrails: LLM-judge auditor (Stage 7 / ticket #9) ─────────────────


_AUDITOR_LOG_PREFIX = "CHAT_AUDIT"


async def audit_chat_responses_job() -> None:
    """Nightly cron at 02:00 UTC. Samples N recent conversations and asks an
    'auditor' LLM whether each assistant response is grounded in the tool
    outputs it used. Flagged conversations emit `CHAT_AUDIT_FLAGGED` log
    lines; the weekly digest job aggregates.

    Spec reference: build_specs/07_chat_v2_research_partner.md §3.7
    ('Async: LLM-judge auditor'). Costs ~$3/mo at expected volume
    (gpt-4o-mini, 50 audits/day).

    Safe to call repeatedly — read-only sampling, no DB mutation.
    """
    import json as _json
    from datetime import datetime, timedelta

    from app.db.session import SessionLocal
    from app.models.chat import ChatMessage
    from app.services.llm_adapter import (
        ChatDone as _ChatDone,
        ChatToken as _ChatToken,
        LLMAdapterError as _AdapterErr,
        get_llm_gateway as _gw,
    )

    SAMPLE_SIZE = 50
    WINDOW_HOURS = 24

    gateway = _gw()
    if not gateway.is_enabled:
        logger.info("%s skipped — LLM not configured", _AUDITOR_LOG_PREFIX)
        return

    cutoff = datetime.utcnow() - timedelta(hours=WINDOW_HOURS)
    db = SessionLocal()
    try:
        # Pull assistant messages from the last 24h that have a preceding
        # user message and at least one tool message (i.e., tool-grounded
        # responses where citation matters).
        assistants = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.role == "assistant",
                ChatMessage.created_at >= cutoff,
                ChatMessage.content.isnot(None),
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(SAMPLE_SIZE * 3)  # over-sample; many will have no tools
            .all()
        )

        sampled = 0
        flagged = 0
        for a in assistants:
            if sampled >= SAMPLE_SIZE:
                break
            # Find the preceding user message + any tool messages in the
            # same conversation BEFORE this assistant row.
            preceding = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.conversation_id == a.conversation_id,
                    ChatMessage.created_at < a.created_at,
                )
                .order_by(ChatMessage.created_at.desc())
                .limit(10)
                .all()
            )
            user_msg = next((m for m in preceding if m.role == "user"), None)
            tool_msgs = [m for m in preceding if m.role == "tool"]
            if user_msg is None or not tool_msgs:
                continue  # not a tool-grounded response; skip

            sampled += 1
            tool_summary = " | ".join(
                (m.tool_results or {}).get("content", "")[:500] for m in reversed(tool_msgs)
            )
            auditor_prompt = (
                f'The user asked: "{user_msg.content[:500]}"\n\n'
                f'The chat responded: "{a.content[:1200]}"\n\n'
                f'The chat used these tool outputs: {tool_summary[:2000]}\n\n'
                "List any factual claims in the response that are NOT "
                "supported by the tool outputs. Output strict JSON: "
                '{"unsupported_claims": [{"claim": "...", "reason": "..."}]}.'
                " If everything is supported, return "
                '{"unsupported_claims": []}.'
            )

            try:
                chunks = []
                async for ev in gateway.chat_completion_with_tools(
                    messages=[
                        {"role": "system", "content": "You are a strict factual auditor."},
                        {"role": "user", "content": auditor_prompt},
                    ],
                    tools=[],
                ):
                    if isinstance(ev, _ChatToken):
                        chunks.append(ev.text)
                    elif isinstance(ev, _ChatDone):
                        break
            except _AdapterErr as exc:
                logger.warning("%s audit LLM error conv=%s: %r",
                               _AUDITOR_LOG_PREFIX, a.conversation_id, exc)
                continue

            raw = "".join(chunks).strip()
            try:
                # Extract the first JSON object from the response.
                start = raw.find("{")
                end = raw.rfind("}") + 1
                parsed = _json.loads(raw[start:end]) if start >= 0 else {}
                unsupported = parsed.get("unsupported_claims", []) or []
            except Exception:
                unsupported = []

            if unsupported:
                flagged += 1
                logger.warning(
                    "%s_FLAGGED conv=%s n_unsupported=%d sample=%s",
                    _AUDITOR_LOG_PREFIX,
                    a.conversation_id,
                    len(unsupported),
                    _json.dumps(unsupported[:3], default=str)[:400],
                )

        logger.info(
            "%s done sampled=%d flagged=%d window_hours=%d",
            _AUDITOR_LOG_PREFIX, sampled, flagged, WINDOW_HOURS,
        )
    finally:
        db.close()


# ── Chat guardrails: weekly digest ────────────────────────────────────────────


def chat_guardrails_digest_job() -> None:
    """Sunday 09:00 UTC weekly digest. v1: a structured log line summarizing
    the week — counts of refusals by category, counts of numeric_uncited
    events, top-flagged conversations from the auditor. Operator greps:

        railway logs --service the_counselor | grep CHAT_DIGEST

    v2 (deferred): emit as an email via the existing Resend wrapper. Wiring
    is straightforward (`from app.services.email_service import send_email`)
    but needs `EMAIL_DIGEST_RECIPIENT` env var which we haven't set yet.
    Logging covers the operator's primary need; email is a UX upgrade.
    """
    # v1 stub: emit a heartbeat so we know the job ran. Aggregation against
    # Railway log scrape is the operator workflow until v2 reads from a
    # structured chat_guardrail_events table (deferred ticket).
    logger.info(
        "CHAT_DIGEST week_ending=%s — aggregate from this command: "
        "`railway logs --service the_counselor --since 7d | "
        "grep -E 'chat_refusal|numeric_uncited|CHAT_AUDIT_FLAGGED' | "
        "jq -s 'group_by(.event) | map({event: .[0].event, count: length})'`",
        _today_iso(),
    )


def _today_iso() -> str:
    from datetime import date
    return date.today().isoformat()


# ── Chat-tool error auditor (2026-05-23) ──────────────────────────────────────


_TOOL_ERROR_LOG_PREFIX = "CHAT_TOOL_ERROR"


def audit_chat_tool_errors_job() -> None:
    """Nightly scan of the last 24h of `chat_messages` for tool-failure rows
    matching the dispatch-loop's `{"error": "Tool <name> failed: ..."}` shape.

    Motivation: the 2026-05-23 `stock_lookup` Pydantic-coercion bug was
    silently happening for every real user call. The error landed in
    `chat_messages.tool_results.content` as that exact JSON envelope, and
    the LLM apologized for a "temporary issue" — the user never saw a stack
    trace, and we only found it by manually grepping prod DB.

    This job aggregates the same row pattern, by (tool_name, error excerpt),
    and emits one `CHAT_TOOL_ERROR_DIGEST` log line per (tool, excerpt) pair.
    Operator workflow:

        railway logs --service the_counselor | grep CHAT_TOOL_ERROR_DIGEST

    Sibling to the LLM-judge auditor above. Reads only; no DB mutation.
    Safe to call repeatedly. Cost: zero (no LLM, no external calls — pure
    DB scan).

    Registered in `_start_scheduler` to run nightly (mirrors the LLM-judge
    schedule but a few minutes offset to avoid concurrent DB reads).
    """
    import json as _json
    import re as _re
    from collections import Counter as _Counter
    from datetime import datetime, timedelta

    from app.db.session import SessionLocal
    from app.models.chat import ChatMessage

    WINDOW_HOURS = 24
    # Matches the dispatch loop's serialization in routes/chat.py:
    #     json.dumps({"error": f"Tool {tc.name} failed: {exc!r}"})
    # We extract the tool name + a stable error excerpt (first line, up to
    # 120 chars, so similar Pydantic errors aggregate even with different
    # field values).
    _TOOL_FAIL_RE = _re.compile(r"^Tool (?P<name>[a-z_][a-z0-9_]*) failed: (?P<err>.+)$", _re.DOTALL)

    cutoff = datetime.utcnow() - timedelta(hours=WINDOW_HOURS)
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.role == "tool",
                ChatMessage.created_at >= cutoff,
            )
            .order_by(ChatMessage.created_at.desc())
            .all()
        )

        # Aggregate by (tool_name, normalized_error_excerpt). The error
        # excerpt is the first 120 chars of the error message (post-Tool-X-
        # failed prefix), with field-value substrings collapsed so different
        # ValidationError instances over the same field land in the same bucket.
        agg: _Counter = _Counter()
        sample_by_key: dict = {}

        for r in rows:
            content = (r.tool_results or {}).get("content")
            if not isinstance(content, str):
                continue
            # The dispatch loop writes `{"error": "Tool ... failed: ..."}`.
            # Parse the JSON envelope first.
            try:
                payload = _json.loads(content)
            except (TypeError, ValueError):
                continue
            err_text = payload.get("error") if isinstance(payload, dict) else None
            if not isinstance(err_text, str):
                continue
            m = _TOOL_FAIL_RE.match(err_text)
            if not m:
                continue
            tool_name = m.group("name")
            # Normalize for aggregation: collapse `input_value=...` style
            # variable bits so identical Pydantic errors across calls cluster.
            excerpt = m.group("err")[:200]
            # Collapse `input_value=...` substrings before truncation. Pydantic
            # serializes the offending value with possibly nested commas/parens
            # (e.g. `input_value=datetime.date(2026, 5, 23)`), so a non-greedy
            # `[^,)]+` would stop at the first comma and leave the date variant
            # distinct, defeating the bucket-aggregation. Match through the
            # nearest balanced `]` instead (Pydantic's error suffix is always
            # `..., input_type=X]`).
            excerpt = _re.sub(r"input_value=.+?, input_type=", "input_value=<…>, input_type=", excerpt)
            excerpt = _re.sub(r"id=0x[0-9a-fA-F]+", "id=0x<…>", excerpt)
            key = (tool_name, excerpt)
            agg[key] += 1
            sample_by_key.setdefault(key, err_text[:300])

        if not agg:
            logger.info(
                "%s_DIGEST window_hours=%d total=0 — no tool errors in window",
                _TOOL_ERROR_LOG_PREFIX, WINDOW_HOURS,
            )
            return

        total = sum(agg.values())
        logger.warning(
            "%s_DIGEST window_hours=%d total=%d unique=%d",
            _TOOL_ERROR_LOG_PREFIX, WINDOW_HOURS, total, len(agg),
        )
        # One log line per (tool, error excerpt) pair so claude-main can
        # quickly see what to investigate.
        for (tool_name, excerpt), count in agg.most_common():
            logger.warning(
                "%s tool=%s count=%d excerpt=%r sample=%r",
                _TOOL_ERROR_LOG_PREFIX,
                tool_name,
                count,
                excerpt,
                sample_by_key[(tool_name, excerpt)],
            )
    finally:
        db.close()
