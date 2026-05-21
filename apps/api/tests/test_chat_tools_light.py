"""Unit tests for the 3 light chat tools + the dispatcher (Stage 7 / ticket #3).

Each tool gets coverage on:
  - happy path (correct match / sensible default)
  - missing-input handling (concept not in doc, empty query, out-of-range step)
  - response-shape invariants the chat endpoint (ticket #5) relies on

Plus the dispatcher gets tests on:
  - dispatches by name + passes arguments correctly
  - raises UnknownToolError for unregistered names
  - get_openai_tool_specs strips the Python handler

No mocking needed — these tools are pure (no LLM, no DB, no network for
ticket #3). Tickets #4 and #5 will introduce mocked LLM tests.
"""
from __future__ import annotations

import pytest

from app.services.chat_tools import (
    TOOL_REGISTRY,
    UnknownToolError,
    dispatch_tool_call,
    get_openai_tool_specs,
)
from app.services.chat_tools.concept_explainer import (
    ConceptExplainerResponse,
    _parse_concepts_doc,
    explain_concept,
)
from app.services.chat_tools.onboarding_tutor import (
    OnboardingTutorResponse,
    run_onboarding_tutor,
)
from app.services.chat_tools.template_search import (
    TemplateSearchResponse,
    search_templates,
)


# ── concept_explainer ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_concept_finds_canonical_name():
    """Exact name match — the most common case."""
    response = await explain_concept("Sharpe Ratio")

    assert isinstance(response, ConceptExplainerResponse)
    assert response.query == "Sharpe Ratio"
    assert response.match is not None
    assert response.match.canonical_name == "Sharpe Ratio"
    assert "annualized return" in response.match.explanation.lower()


@pytest.mark.asyncio
async def test_explain_concept_is_case_insensitive():
    """Users type 'sharpe ratio' as often as 'Sharpe Ratio' — both work."""
    response = await explain_concept("sharpe ratio")
    assert response.match is not None
    assert response.match.canonical_name == "Sharpe Ratio"


@pytest.mark.asyncio
async def test_explain_concept_resolves_alias():
    """`## CAGR (Annualized Return)` — the alias must match too."""
    response = await explain_concept("Annualized Return")
    assert response.match is not None
    assert "CAGR" in response.match.canonical_name


@pytest.mark.asyncio
async def test_explain_concept_no_match_returns_none_plus_options():
    """If we don't know the concept, return None and the available list so
    the LLM can either suggest similar entries or fall back gracefully."""
    response = await explain_concept("Banana Coefficient")

    assert response.match is None
    assert len(response.available_concepts) > 0
    assert "Sharpe Ratio" in response.available_concepts


@pytest.mark.asyncio
async def test_explain_concept_strips_whitespace():
    """Trailing whitespace from the LLM's tool-call argument shouldn't miss."""
    response = await explain_concept("  Max Drawdown  ")
    assert response.match is not None
    assert response.match.canonical_name == "Max Drawdown"


def test_parse_concepts_doc_handles_aliases_and_sections():
    """Parser unit test — sections are ignored, aliases register both keys."""
    sample = """
# Title

### Section A

## Sharpe Ratio
First explanation.

### Section B

## CAGR (Annualized Return)
Second explanation with aliases.

## Heading Only

## Another (Alias1, Alias2)
Third explanation with multiple aliases.
"""
    parsed = _parse_concepts_doc(sample)

    assert "sharpe ratio" in parsed
    assert parsed["sharpe ratio"].canonical_name == "Sharpe Ratio"

    # CAGR + alias both map
    assert "cagr" in parsed
    assert "annualized return" in parsed
    assert parsed["cagr"] is parsed["annualized return"]

    # Heading-only entries (no body) are dropped
    assert "heading only" not in parsed

    # Multi-alias entries register all aliases
    assert "another" in parsed
    assert "alias1" in parsed
    assert "alias2" in parsed


# ── template_search ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_template_search_finds_by_name():
    """Direct name fragment is the strongest signal."""
    response = await search_templates("trend following")

    assert isinstance(response, TemplateSearchResponse)
    assert len(response.matches) > 0
    assert response.matches[0].id == "trend-following"
    assert response.matches[0].category == "Momentum"


@pytest.mark.asyncio
async def test_template_search_finds_by_category():
    """Category-only query returns multiple matches from that category."""
    response = await search_templates("momentum")

    assert len(response.matches) > 1
    ids = {m.id for m in response.matches}
    # Should include several momentum templates
    assert "trend-following" in ids or "cross-sectional-momentum" in ids


@pytest.mark.asyncio
async def test_template_search_respects_limit():
    """Pagination — limit caps the number of returned matches."""
    response = await search_templates("momentum", limit=2)
    assert len(response.matches) <= 2


@pytest.mark.asyncio
async def test_template_search_empty_query_returns_no_matches():
    """Empty / whitespace-only query is a no-op rather than returning all."""
    response = await search_templates("   ")
    assert response.matches == []
    assert response.total_in_catalog > 0  # but the catalog itself is non-empty


@pytest.mark.asyncio
async def test_template_search_no_match_returns_empty_list():
    """Junk query → empty matches, but catalog size still reported."""
    response = await search_templates("xyzzy nonexistent")
    assert response.matches == []
    assert response.total_in_catalog > 0


@pytest.mark.asyncio
async def test_template_search_ranks_name_match_above_description_match():
    """A name-match template scores 100; a description-only match scores 20.
    Verify the name match comes first in results."""
    response = await search_templates("pairs trading")
    assert response.matches[0].id == "pairs-trading-long-only"


# ── onboarding_tutor ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_onboarding_tutor_returns_full_script_by_default():
    """No `step` arg → return the whole script for the frontend to paginate."""
    response = await run_onboarding_tutor()

    assert isinstance(response, OnboardingTutorResponse)
    assert response.demo_strategy_id == "nvda-200-ma-demo"
    assert len(response.steps) >= 5  # Welcome + 4 panels + closer at minimum
    assert response.placeholder is True  # Until Jimmy's script lands


@pytest.mark.asyncio
async def test_onboarding_tutor_specific_step_returns_only_that_step():
    """Deep-link case — return one step at index N."""
    response = await run_onboarding_tutor(step=1)
    assert len(response.steps) == 1


@pytest.mark.asyncio
async def test_onboarding_tutor_out_of_range_step_falls_back_to_full_script():
    """LLM may hallucinate step=99. Don't crash; return the full script."""
    response = await run_onboarding_tutor(step=99)
    assert len(response.steps) >= 5


@pytest.mark.asyncio
async def test_onboarding_tutor_step_zero_works():
    """Index 0 is valid (first step) — don't accidentally treat 0 as falsy."""
    response = await run_onboarding_tutor(step=0)
    assert len(response.steps) == 1
    assert "welcome" in response.steps[0].title.lower()


# ── dispatcher + registry ─────────────────────────────────────────────────────


def test_registry_contains_all_phase1_tools():
    """All Phase 1 tools (ticket #3 light + ticket #4 heavier) must be
    registered. When ticket #4 lands its 4 heavier tools, this set grew
    from 3 → 7. Future tickets append; never remove without a deprecation
    plan."""
    assert set(TOOL_REGISTRY.keys()) == {
        # Light (ticket #3)
        "concept_explainer",
        "template_search",
        "onboarding_tutor",
        # Heavier (ticket #4)
        "strategy_builder_iterate",
        "backtest_execute",
        "stock_lookup",
        "backtest_explain",
    }


def test_get_openai_tool_specs_strips_handler():
    """The Python handler is internal — the OpenAI spec must only expose
    name/description/parameters."""
    specs = get_openai_tool_specs()

    assert len(specs) == len(TOOL_REGISTRY)
    for spec in specs:
        assert spec["type"] == "function"
        fn = spec["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        # No handler leak
        assert "handler" not in fn
        assert "handler" not in spec


def test_get_openai_tool_specs_parameters_are_valid_json_schema():
    """Each parameters object must be a JSON-schema-shaped dict for OpenAI."""
    for spec in get_openai_tool_specs():
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert isinstance(params["properties"], dict)


@pytest.mark.asyncio
async def test_dispatch_routes_to_concept_explainer():
    """Smoke test: dispatcher resolves a real tool and returns its response."""
    result = await dispatch_tool_call("concept_explainer", {"concept": "Sharpe Ratio"})
    assert isinstance(result, ConceptExplainerResponse)
    assert result.match is not None


@pytest.mark.asyncio
async def test_dispatch_routes_to_template_search_with_kwargs():
    """Dispatcher must unpack arguments as kwargs (the OpenAI function-calling
    contract). `limit=2` should reach the handler."""
    result = await dispatch_tool_call("template_search", {"query": "momentum", "limit": 2})
    assert isinstance(result, TemplateSearchResponse)
    assert len(result.matches) <= 2


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_raises_unknown_tool_error():
    """A typo'd or hallucinated tool name surfaces as a recoverable error
    (not a generic Python exception) so the chat endpoint can catch + reprompt."""
    with pytest.raises(UnknownToolError, match="No tool named"):
        await dispatch_tool_call("ghost_tool", {})


@pytest.mark.asyncio
async def test_dispatch_passes_through_handler_exceptions():
    """If a tool raises mid-execution, the dispatcher does NOT swallow it.
    Verifying this means the chat endpoint can decide how to surface tool errors."""
    # Simulate by passing a bad kwarg name to template_search.
    with pytest.raises(TypeError):
        await dispatch_tool_call("template_search", {"bogus_kwarg": "value"})
