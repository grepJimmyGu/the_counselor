"""Every home example query must actually parse.

Same cross-language contract as `test_condition_builder_contract.py`, for the
same reason: the query STRING is the source of truth on submit, and the block
lives in TypeScript while the extractors live here. Nothing else connects them.

Why it matters more for this block than most: an example query that doesn't
parse falls through to `parse_strategy_message`, which is built to produce a
complete backtestable strategy and therefore ANSWERS WITH A QUESTION ("Which
strategy type should I use?"). A user who clicks a suggested query and gets
interrogated concludes the product is broken — and they're right.

Three of the first four candidate queries did exactly that, which is what this
test exists to stop from shipping.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.screen_filter_parser import extract_filters
from app.services.screen_rule_parser import extract_rules

_BLOCK = (
    Path(__file__).resolve().parents[2]
    / "web" / "src" / "components" / "home" / "home-example-queries.tsx"
)

# The `queries: [ ... ]` arrays. Kept deliberately dumb — a parser here would be
# another thing to get wrong.
_ARRAY_RX = re.compile(r"queries:\s*\[(.*?)\]", re.S)
_STRING_RX = re.compile(r'"([^"]+)"')


def _queries() -> list:
    src = _BLOCK.read_text(encoding="utf-8")
    out: list = []
    for block in _ARRAY_RX.findall(src):
        out.extend(_STRING_RX.findall(block))
    return out


def test_the_block_is_where_we_think_it_is() -> None:
    # If the component moves, this test would silently pass on zero queries.
    assert _BLOCK.exists(), f"example-query block not found at {_BLOCK}"
    assert _queries(), "no example queries parsed out of the component"


@pytest.mark.parametrize("query", _queries())
def test_every_example_query_extracts_something(query: str) -> None:
    rules, _ = extract_rules(query)
    filters, applied = extract_filters(query)
    assert rules or filters, (
        f"{query!r} extracts NOTHING — clicking it would fall through to the LLM "
        "parser, which asks the user a question instead of returning names. "
        "Either rephrase it into the supported vocabulary or extend the "
        "extractors."
    )


def test_queries_are_lowercase_ish_natural_text() -> None:
    """Guards against someone pasting a rule id or JSON in as a 'query'."""
    for q in _queries():
        assert not q.strip().startswith("{"), f"{q!r} looks like JSON, not a query"
        assert "primitive_id" not in q, f"{q!r} leaks an internal id"
