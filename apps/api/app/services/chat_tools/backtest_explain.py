"""backtest_explain chat tool — plain-English explanation of a backtest.

Loads a stored `BacktestRecord` by id, reconstructs the strategy + result,
calls `app.services.insights.build_explanation`, returns the explanation.
The chat tool is mostly a thin loader; the insights service does the real
work and falls back deterministically when no LLM is configured.

Per build_specs/07_chat_v2_research_partner.md §6 ticket #4: this is a
"heavier" tool because it touches DB + LLM, but its scope is narrow —
no new explanation logic, no fan-out, just a focused wrapper so the LLM
can reach the existing explainer from within a chat turn.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.db.session import SessionLocal
from app.models.backtest import BacktestRecord
from app.schemas.backtest import BacktestResult
from app.schemas.insights import ExplanationResponse
from app.schemas.strategy import StrategyJSON
from app.services.insights import build_explanation


class BacktestExplainResponse(BaseModel):
    """Either a full explanation (success=True) or an error message."""

    success: bool
    backtest_id: str
    explanation: Optional[ExplanationResponse] = None
    error: Optional[str] = None


def _strategy_from_record(record: BacktestRecord) -> Optional[StrategyJSON]:
    """Reconstruct the StrategyJSON from a BacktestRecord's stored payload.

    The engine stores the full `BacktestResult.model_dump()` into
    `result_payload`, and `BacktestResult.strategy_json` is part of that —
    so the key is `strategy_json`, not `strategy`. Legacy partial-write
    records may not have it; in that case return None and the caller surfaces
    the "missing payload" error.
    """
    payload = record.result_payload or {}
    strategy_dict = payload.get("strategy_json")
    if strategy_dict is None:
        return None
    try:
        return StrategyJSON.model_validate(strategy_dict)
    except Exception:
        return None


def _result_from_record(record: BacktestRecord) -> Optional[BacktestResult]:
    payload = record.result_payload or {}
    try:
        return BacktestResult.model_validate(payload)
    except Exception:
        return None


async def explain_backtest(
    backtest_id: str,
    locale: str = "en",
) -> BacktestExplainResponse:
    """Look up a stored backtest by id and return its plain-English explanation.

    Wrong / missing id → success=False, error populated. The chat endpoint
    can decide whether to surface the error or ask the LLM to suggest the
    user re-run the backtest first.
    """
    bid = backtest_id.strip()
    if not bid:
        return BacktestExplainResponse(
            success=False,
            backtest_id=backtest_id,
            error="Empty backtest_id.",
        )

    db = SessionLocal()
    try:
        record = db.get(BacktestRecord, bid)
        if record is None:
            return BacktestExplainResponse(
                success=False,
                backtest_id=bid,
                error=(
                    f"No backtest found with id '{bid}'. "
                    "Run a backtest first (via backtest_execute)."
                ),
            )

        strategy = _strategy_from_record(record)
        result = _result_from_record(record)
        if strategy is None or result is None:
            return BacktestExplainResponse(
                success=False,
                backtest_id=bid,
                error=(
                    "Backtest record is missing the strategy or result "
                    "payload — likely a legacy or partial-write record. "
                    "Ask the user to re-run the backtest."
                ),
            )

        try:
            explanation = await build_explanation(strategy, result, locale=locale)
        except Exception as exc:
            return BacktestExplainResponse(
                success=False,
                backtest_id=bid,
                error=f"Explainer failed: {exc}",
            )

        return BacktestExplainResponse(
            success=True,
            backtest_id=bid,
            explanation=explanation,
        )
    finally:
        db.close()


BACKTEST_EXPLAIN_DEF: Dict[str, Any] = {
    "name": "backtest_explain",
    "description": (
        "Get a plain-English explanation of a completed backtest. Use "
        "after `backtest_execute` returns a backtest_id, when the user "
        "asks 'why', 'explain', 'walk me through this result', or "
        "anything about why the strategy performed the way it did. The "
        "explanation comes from Livermore's existing insights engine — "
        "same content the workspace's Review tab shows."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "backtest_id": {
                "type": "string",
                "description": (
                    "The backtest_id returned by `backtest_execute`. Must "
                    "exist in the database — otherwise the tool reports a "
                    "no-such-backtest error."
                ),
            },
            "locale": {
                "type": "string",
                "enum": ["en", "zh"],
                "description": "Locale for explanation copy. Default 'en'.",
                "default": "en",
            },
        },
        "required": ["backtest_id"],
        "additionalProperties": False,
    },
    "handler": explain_backtest,
}
