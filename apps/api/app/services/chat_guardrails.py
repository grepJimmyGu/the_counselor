"""Chat guardrails (Stage 7 / ticket #9).

Two runtime checks applied to every completed assistant response in the chat
loop, plus an async nightly auditor that samples conversations and grades
them with an LLM-as-judge.

Components in this module:

  * `classify_refusal(text)` — pure regex-based detector. If the assistant
    text matches one of four canonical refusal shapes, returns the category
    name; else None. Cheap, deterministic, no false-positive cost beyond
    a debug log line.

  * `detect_uncited_numerics(text)` — pure. Finds numeric tokens
    (percentages, dollar amounts, decimals, ratios) and checks for a
    nearby <cite> marker. Returns the numerics that lack one.

  * `attempt_citation_reprompt(messages, response_text, ...)` — async.
    One-shot LLM call asking it to rewrite the prior response with citation
    chips on every numeric claim. Returns the new text on success, None
    on failure.

  * `log_*_event(...)` — emit grep-able structured log lines so the
    weekly digest job (qa_jobs.py) can aggregate without a DB lookup.

The spec calls the citation enforcement a "reprompt loop." For v1 we
attempt ONE reprompt then accept-with-warning if it still fails — bounded
cost, no risk of pathological LLM loops.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from app.services.llm_adapter import (
    ChatDone,
    ChatToken,
    LLMAdapterError,
    get_llm_gateway,
)


_log = logging.getLogger("livermore.chat.guardrails")


# ── Refusal classification ────────────────────────────────────────────────────


# Each tuple is (refusal_category, ordered regex patterns). First match wins.
# The patterns target the canonical refusal shapes from the system prompt;
# variant phrasings (paraphrases) will be caught by the LLM-as-judge auditor.
_REFUSAL_PATTERNS: List[tuple] = [
    (
        "trade_execution",
        [
            re.compile(r"\bi (?:can't|cannot) (?:execute|place) (?:a )?trades?\b", re.IGNORECASE),
            re.compile(r"\bi (?:don't|do not) execute trades?\b", re.IGNORECASE),
            re.compile(r"\blivermore (?:is research-only|doesn't (?:execute|place) trades?)\b", re.IGNORECASE),
        ],
    ),
    (
        "personalized_advice",
        [
            re.compile(r"\bi (?:can't|cannot) tell you whether to (?:buy|sell|invest)\b", re.IGNORECASE),
            re.compile(r"\bi (?:can't|cannot) give (?:you )?personalized (?:financial )?advice\b", re.IGNORECASE),
            re.compile(r"\bthat depends on your (?:goals|risk tolerance|situation)\b", re.IGNORECASE),
        ],
    ),
    (
        "forward_prediction",
        [
            re.compile(r"\bi (?:can't|cannot) predict (?:future )?(?:prices?|movements?|direction)\b", re.IGNORECASE),
            re.compile(r"\bi (?:can't|cannot) tell you (?:where|what) (?:the )?(?:price|market) will (?:go|be)\b", re.IGNORECASE),
            re.compile(r"\bi (?:don't|do not) make forward(?:-looking)? predictions\b", re.IGNORECASE),
        ],
    ),
    (
        "off_topic",
        [
            re.compile(r"\bi (?:can only|only) (?:help|discuss) (?:with )?(?:investment|markets?|strategies)\b", re.IGNORECASE),
            re.compile(r"\bthat's (?:not|outside) (?:my )?(?:scope|domain)\b", re.IGNORECASE),
        ],
    ),
]


def classify_refusal(text: str) -> Optional[str]:
    """Return the refusal category name if `text` matches a known refusal
    shape, otherwise None. Order: trade_execution → personalized_advice →
    forward_prediction → off_topic. First match wins."""
    if not text:
        return None
    for category, patterns in _REFUSAL_PATTERNS:
        for pat in patterns:
            if pat.search(text):
                return category
    return None


# ── Citation enforcement ──────────────────────────────────────────────────────


# Match numeric tokens in chat output. Includes percentages, dollar amounts,
# decimals, integers with units, and ratios. Excludes years (4-digit
# 19xx/20xx) by anchoring after a leading word boundary AND requiring
# either a percent / dollar / "x" suffix or a decimal point.
#
# Heuristic: a "numeric claim" is something the user might verify. "5 of 30"
# isn't a claim worth citing; "Sharpe 1.4" is. We focus on:
#   - 12.3%       (percentage)
#   - $1.5B       (dollar amount with magnitude suffix)
#   - 0.83        (ratio)
#   - 1.5x        (multiplier)
#   - -12%        (negative percentage)
_NUMERIC_TOKEN = re.compile(
    r"(?:(?<=\s)|(?<=^)|(?<=\())"           # word-leading
    r"-?\$?\d+(?:\.\d+)?"                    # the number itself
    r"(?:%|x|[KMBkmb])?"                     # optional magnitude/unit
    r"(?=[\s.,;:!?\)]|$)"                    # word-trailing
)

# A <cite> chip is a marker the LLM produces near each numeric claim. We accept
# both shorthand and full forms — the chat endpoint will normalize for the
# frontend renderer.
_CITE_TAG = re.compile(r"<cite\s[^>]*>|<cite>")

# Distance window (in characters) within which a <cite> must appear to "cover"
# a numeric token. 80 chars ≈ one or two clauses — generous enough to allow
# natural prose ("Sharpe 1.4, derived from the backtest [cite]") and tight
# enough to catch citation-bombing at the end.
_CITE_WINDOW_CHARS = 80


def detect_uncited_numerics(text: str) -> List[str]:
    """Return numeric tokens in `text` that don't have a nearby <cite> chip.

    "Nearby" = within _CITE_WINDOW_CHARS of the token's end. The window is
    one-sided forward — citation usually trails the claim. Edge case: years
    like "2022" are excluded by the year-shaped filter (a 4-digit integer
    with no unit and not preceded by $ or trailing %/x).
    """
    if not text:
        return []

    cite_spans = [m.start() for m in _CITE_TAG.finditer(text)]
    uncited: List[str] = []
    for m in _NUMERIC_TOKEN.finditer(text):
        token = m.group(0)
        if _looks_like_year(token):
            continue
        end = m.end()
        # Is there a cite tag starting within the window AFTER this token?
        has_cite = any(end <= cite_start < end + _CITE_WINDOW_CHARS for cite_start in cite_spans)
        if not has_cite:
            uncited.append(token)
    return uncited


def _looks_like_year(token: str) -> bool:
    """Skip 4-digit integers in the 19xx/20xx range — they're almost always
    years, not numeric claims. False-negatives (e.g., a portfolio of 2024
    shares) are acceptable; false-positives (treating a real claim as a year)
    are not."""
    raw = token.strip("$%xKkMmBb-")
    if "." in raw:
        return False
    try:
        n = int(raw)
    except ValueError:
        return False
    return 1900 <= n <= 2099


# ── Citation reprompt (async) ─────────────────────────────────────────────────


async def attempt_citation_reprompt(
    messages: List[dict],
    response_text: str,
    uncited: List[str],
    *,
    model: Optional[str] = None,
) -> Optional[str]:
    """One-shot LLM call asking it to add citation chips for the uncited
    numerics. Returns the rewritten text on success, None if the LLM fails
    or returns a response still missing citations.

    Bounded cost: ONE additional LLM round-trip per turn that has uncited
    numerics. Not a loop — accept-with-warning if the rewrite fails too.
    """
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return None  # No LLM → can't reprompt; caller logs + accepts.

    reprompt = (
        "Your previous response contained numeric claims without citation chips: "
        + ", ".join(f"`{t}`" for t in uncited)
        + ". Rewrite the response so every numeric claim is followed by a "
        "`<cite source=\"<tool_name>\" id=\"<arg_or_id>\"/>` chip pointing to "
        "the tool output that produced the number. Do NOT add new numbers; "
        "only annotate existing ones. If a number came from your own "
        "knowledge (not a tool), preface it with 'approximately' and add "
        "`<cite source=\"general_knowledge\"/>`. Return the full rewritten "
        "text only — no preface, no explanation."
    )

    augmented = messages + [
        {"role": "assistant", "content": response_text},
        {"role": "user", "content": reprompt},
    ]

    rewrite_chunks: List[str] = []
    try:
        async for event in gateway.chat_completion_with_tools(
            messages=augmented,
            tools=[],  # no tool calls allowed during reprompt — text only
            model=model,
        ):
            if isinstance(event, ChatToken):
                rewrite_chunks.append(event.text)
            elif isinstance(event, ChatDone):
                break
    except LLMAdapterError:
        return None

    rewritten = "".join(rewrite_chunks).strip()
    if not rewritten:
        return None

    # If the rewrite still has uncited numerics, the LLM failed to comply.
    # Caller accepts-with-warning rather than retrying.
    if detect_uncited_numerics(rewritten):
        return None

    return rewritten


# ── Logging emitters ──────────────────────────────────────────────────────────


def log_refusal_event(
    *,
    category: str,
    user_message: str,
    assistant_response: str,
    tool_calls_attempted: List[str],
    user_id: Optional[str],
    anon_session_id: Optional[str],
    tier: str,
    conversation_id: str,
) -> None:
    """Emit a structured chat_refusal log line per spec §3.6.

    The full event is logged as a single line JSON for `railway logs |
    grep chat_refusal | jq` ergonomics. User message is redacted to the
    first 120 chars to avoid leaking long pasted prompts into logs.
    """
    payload = {
        "event": "chat_refusal",
        "refusal_category": category,
        "user_message_redacted": user_message[:120],
        "assistant_redirect_len": len(assistant_response),
        "tool_calls_attempted": tool_calls_attempted,
        "user_id": user_id or "anonymous",
        "anon_session_id": anon_session_id,
        "tier": tier,
        "conversation_id": conversation_id,
    }
    _log.info("chat_refusal %s", json.dumps(payload, default=str))


def log_uncited_event(
    *,
    uncited: List[str],
    conversation_id: str,
    reprompt_succeeded: bool,
    user_id: Optional[str],
    anon_session_id: Optional[str],
    tier: str,
) -> None:
    """Emit a structured numeric_uncited log line. The digest job aggregates
    these to surface chronic citation failures."""
    payload = {
        "event": "numeric_uncited",
        "uncited_tokens": uncited,
        "uncited_count": len(uncited),
        "reprompt_succeeded": reprompt_succeeded,
        "conversation_id": conversation_id,
        "user_id": user_id or "anonymous",
        "anon_session_id": anon_session_id,
        "tier": tier,
    }
    _log.warning("numeric_uncited %s", json.dumps(payload, default=str))


def append_redaction_warning(text: str, uncited: List[str]) -> str:
    """Append a short warning to a response whose uncited numerics couldn't
    be repaired via reprompt. The chat keeps the numbers (less disruptive
    than redacting them mid-response) but warns the user explicitly."""
    if not uncited:
        return text
    note = (
        "\n\n_(Note: some figures above could not be sourced to specific "
        "tool outputs — verify against the linked data before acting.)_"
    )
    return text + note
