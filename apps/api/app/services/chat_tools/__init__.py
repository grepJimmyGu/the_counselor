"""Chat tools (Stage 7 / ticket #3).

Each chat tool is a discrete capability the LLM can invoke during a chat
turn — a Python async function with a name, OpenAI function-calling JSON
schema, and a handler. The chat endpoint (ticket #5) iterates the LLM's
streamed `ChatToolCall` events, calls `dispatch_tool_call(...)` to execute,
then re-invokes the LLM with the result.

Tools ship in phases per build_specs/07_chat_v2_research_partner.md §6:
  Phase 1 (this ticket #3): 3 light tools that don't touch user state.
  Phase 1 (ticket #4):      4 heavier tools (strategy_builder, backtest_execute, etc.)
  Phase 2:                  5 more tools (stock_compare, robustness_run, etc.)

This package owns the registry + dispatcher. Individual tool modules own
their schema + handler.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, TypedDict

from app.services.chat_tools.backtest_execute import (
    BACKTEST_EXECUTE_DEF,
    execute_backtest,
)
from app.services.chat_tools.backtest_explain import (
    BACKTEST_EXPLAIN_DEF,
    explain_backtest,
)
from app.services.chat_tools.concept_explainer import (
    CONCEPT_EXPLAINER_DEF,
    explain_concept,
)
from app.services.chat_tools.onboarding_tutor import (
    ONBOARDING_TUTOR_DEF,
    run_onboarding_tutor,
)
from app.services.chat_tools.stock_lookup import (
    STOCK_LOOKUP_DEF,
    lookup_stock,
)
from app.services.chat_tools.strategy_builder_iterate import (
    STRATEGY_BUILDER_ITERATE_DEF,
    iterate_strategy,
)
from app.services.chat_tools.template_search import (
    TEMPLATE_SEARCH_DEF,
    search_templates,
)


class ToolDefinition(TypedDict):
    """OpenAI function-calling schema + the Python handler.

    `name` and `description` are surfaced to the LLM verbatim. `parameters`
    is a JSON-schema object (OpenAI's function-calling format). `handler` is
    invoked as `await handler(**arguments)` after the LLM emits a tool_call
    event with that name.
    """

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Awaitable[Any]]


# Registry — name -> definition. Append a new tool by importing its DEF and
# adding it here. Keeping the registry centralized means there's exactly one
# place to grep when wiring or debugging.
TOOL_REGISTRY: Dict[str, ToolDefinition] = {
    # Light tools (ticket #3)
    "concept_explainer": CONCEPT_EXPLAINER_DEF,
    "template_search": TEMPLATE_SEARCH_DEF,
    "onboarding_tutor": ONBOARDING_TUTOR_DEF,
    # Heavier tools (ticket #4)
    "strategy_builder_iterate": STRATEGY_BUILDER_ITERATE_DEF,
    "backtest_execute": BACKTEST_EXECUTE_DEF,
    "stock_lookup": STOCK_LOOKUP_DEF,
    "backtest_explain": BACKTEST_EXPLAIN_DEF,
}


class UnknownToolError(ValueError):
    """The LLM emitted a tool_call for a tool we don't have registered.

    Caller (the chat endpoint) catches this and reprompts the LLM with the
    list of valid tools rather than crashing the conversation.
    """


def get_openai_tool_specs() -> list[dict]:
    """Return the OpenAI tool-spec list for `chat_completion_with_tools`.

    Strips the Python handler — the LLM only needs name/description/params.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in TOOL_REGISTRY.values()
    ]


async def dispatch_tool_call(name: str, arguments: dict) -> Any:
    """Execute the registered handler for `name` with `arguments`.

    Raises `UnknownToolError` if `name` is not in the registry; the caller
    (chat endpoint) catches and surfaces this to the LLM as a recoverable
    error so the conversation can continue.

    Handler-level exceptions are not caught here — they propagate. The chat
    endpoint decides whether to abort the turn or include the exception
    text in the tool's response payload.
    """
    if name not in TOOL_REGISTRY:
        raise UnknownToolError(
            f"No tool named '{name}'. Valid tools: {sorted(TOOL_REGISTRY)}"
        )
    handler = TOOL_REGISTRY[name]["handler"]
    return await handler(**arguments)


__all__ = [
    "TOOL_REGISTRY",
    "ToolDefinition",
    "UnknownToolError",
    "dispatch_tool_call",
    "get_openai_tool_specs",
    # Light tools
    "explain_concept",
    "search_templates",
    "run_onboarding_tutor",
    # Heavier tools
    "iterate_strategy",
    "execute_backtest",
    "lookup_stock",
    "explain_backtest",
]
