"""Cross-boundary guard: every condition-builder phrase must be parseable.

THE CONTRACT. `apps/web/src/lib/condition-groups.ts` is the 6-category builder
behind the home box's "Conditions" button. Picking an option appends its
`phrase` to the query AND contributes a `rule` to the live match count. On
submit, the QUERY TEXT is what gets parsed — so if a phrase isn't in the
backend vocabulary, the panel shows a confident match count and then screens
something different. Silent, and invisible in both codebases' own tests.

That is not hypothetical: when the builder was first written, 13 of its 47
phrases did not round-trip. This test is why they were caught.

Rule of thumb when adding an option:
  - `rule: {...}`  -> the phrase must yield rules via `screen_rule_parser`
  - `rule: null`   -> the phrase must yield filters via `screen_filter_parser`
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.screen_filter_parser import extract_filters
from app.services.screen_rule_parser import extract_rules

_GROUPS_TS = (
    Path(__file__).resolve().parents[3]
    / "apps" / "web" / "src" / "lib" / "condition-groups.ts"
)
_ENTRY_RX = re.compile(r'phrase:\s*"([^"]+)",\s*\n?\s*rule:\s*(null|\{)')


def _entries():
    if not _GROUPS_TS.exists():  # frontend not present (api-only checkout)
        pytest.skip(f"{_GROUPS_TS} not found")
    found = _ENTRY_RX.findall(_GROUPS_TS.read_text())
    assert found, "parsed no options — did condition-groups.ts change shape?"
    return found


def test_every_builder_phrase_round_trips() -> None:
    broken = []
    for phrase, rule_token in _entries():
        if rule_token == "null":
            ok = extract_filters(phrase)[0] is not None
            kind = "fundamental (screen_filter_parser)"
        else:
            ok = bool(extract_rules(phrase)[0])
            kind = "technical (screen_rule_parser)"
        if not ok:
            broken.append(f"{phrase!r} -> no match in {kind}")

    assert not broken, (
        "Condition-builder phrases the backend cannot parse. The panel would "
        "show a match count, then screen something else on submit:\n  "
        + "\n  ".join(broken)
    )


def test_the_builder_actually_has_all_six_columns() -> None:
    """v3.1 §4 specifies six categories; a dropped column is a silent
    regression that no frontend test would notice."""
    keys = set(re.findall(r'key:\s*"([a-z]+)"', _GROUPS_TS.read_text()))
    assert keys == {
        "technical", "quote", "stage", "financials", "fundamentals", "special"
    }, f"unexpected column set: {sorted(keys)}"
