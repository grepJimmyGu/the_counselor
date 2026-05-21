"""strategy_builder_iterate chat tool — multi-turn strategy refinement.

Wraps `app.services.strategy_parser.parse_strategy_message`. The chat tool
adds nothing the parser doesn't already do; it just exposes the parser to
the LLM under the chat tool-calling contract so the LLM can iterate on a
draft strategy across multiple turns.

Per build_specs/07_chat_v2_research_partner.md §3 and §6 ticket #4:
the parser already supports `previous_strategy_json` for multi-turn use;
the chat tool simply passes that through.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.schemas.strategy import StrategyChatResponse, StrategyJSON
from app.services.strategy_parser import parse_strategy_message


async def iterate_strategy(
    user_message: str,
    previous_strategy_json: Optional[dict] = None,
    locale: str = "en",
) -> StrategyChatResponse:
    """Refine an in-progress strategy from a chat turn.

    `previous_strategy_json` is the strategy JSON from the prior turn (if
    any). The parser combines it with the new `user_message` and either
    returns an updated strategy + extracted fields, or asks clarifying
    questions if the message is ambiguous / unsupported.

    Falls back to deterministic parsing if no LLM is configured (existing
    behaviour of `parse_strategy_message` — no change here).
    """
    previous: Optional[StrategyJSON] = None
    if previous_strategy_json is not None:
        # Tolerate dict from the LLM tool-call by validating into the model.
        # If validation fails (LLM hallucinated shape), drop the previous
        # state silently rather than 500ing — the parser will start fresh.
        try:
            previous = StrategyJSON.model_validate(previous_strategy_json)
        except Exception:
            previous = None

    return await parse_strategy_message(
        user_message=user_message,
        previous_strategy_json=previous,
        locale=locale,
    )


STRATEGY_BUILDER_ITERATE_DEF: Dict[str, Any] = {
    "name": "strategy_builder_iterate",
    "description": (
        "Refine an in-progress investment strategy across multiple chat "
        "turns. Use when the user is describing or modifying a strategy "
        "('build a momentum strategy on tech', 'use 50-day instead of "
        "200-day MA', 'add a stop loss'). Returns the updated strategy "
        "JSON plus any clarifying questions if the message is ambiguous "
        "or references unsupported features. Do NOT use to actually run "
        "a backtest — that's backtest_execute. Do NOT use for general "
        "research questions — that's concept_explainer / stock_lookup."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_message": {
                "type": "string",
                "description": (
                    "The user's latest message describing or modifying the "
                    "strategy. Pass it verbatim — the parser does its own "
                    "intent extraction."
                ),
            },
            "previous_strategy_json": {
                "type": "object",
                "description": (
                    "The strategy JSON from the prior turn, if any. Omit "
                    "for the first turn of a new strategy."
                ),
            },
            "locale": {
                "type": "string",
                "enum": ["en", "zh"],
                "description": "Locale for clarification copy. Default 'en'.",
                "default": "en",
            },
        },
        "required": ["user_message"],
        "additionalProperties": False,
    },
    "handler": iterate_strategy,
}
