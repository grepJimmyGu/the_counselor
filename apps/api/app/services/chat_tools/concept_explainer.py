"""concept_explainer chat tool — Q&A on investment concepts.

Reads `apps/api/docs/chat_concepts.md` at runtime so non-engineers can
add or edit entries by editing markdown — no code change, no redeploy.

The doc convention: one concept per `## Heading` line, the immediately
following text block (until the next `##`) is the explanation. `###`
section markers are ignored. Aliases supported via `## Name (Alias)`
where Alias is matched case-insensitively alongside Name.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# Path: this file is at `apps/api/app/services/chat_tools/concept_explainer.py`.
# The doc lives at `apps/api/docs/chat_concepts.md`, which is parents[3]/docs.
_CONCEPTS_DOC = Path(__file__).resolve().parents[3] / "docs" / "chat_concepts.md"


class ConceptEntry(BaseModel):
    """One canonical concept with its names + explanation. Returned to the LLM."""

    canonical_name: str
    aliases: List[str]
    explanation: str


class ConceptExplainerResponse(BaseModel):
    """Return shape of `explain_concept`. `match` is None when no entry was
    found — the LLM uses that to fall back to its own knowledge or refuse."""

    query: str
    match: Optional[ConceptEntry]
    available_concepts: List[str]


def _parse_concepts_doc(text: str) -> Dict[str, ConceptEntry]:
    """Parse the markdown doc into a name -> entry dict.

    The dict key is the canonical name lowercased; aliases also map to the
    same entry. Heading-only lines (no body) are dropped.
    """
    by_key: Dict[str, ConceptEntry] = {}
    current_heading: Optional[str] = None
    current_body: List[str] = []

    def _flush() -> None:
        if not current_heading:
            return
        body_text = "\n".join(current_body).strip()
        if not body_text:
            return
        # Pull aliases out of "Name (Alias1, Alias2)" headings.
        m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", current_heading)
        if m:
            canonical = m.group(1).strip()
            aliases = [a.strip() for a in m.group(2).split(",")]
        else:
            canonical = current_heading.strip()
            aliases = []
        entry = ConceptEntry(
            canonical_name=canonical,
            aliases=aliases,
            explanation=body_text,
        )
        by_key[canonical.lower()] = entry
        for alias in aliases:
            by_key[alias.lower()] = entry

    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            _flush()
            current_heading = line[3:].strip()
            current_body = []
        elif line.startswith("### "):
            # Section divider — ignored, but breaks the current body so a
            # heading-less section doesn't accidentally absorb the next one.
            _flush()
            current_heading = None
            current_body = []
        elif current_heading is not None:
            current_body.append(line)

    _flush()
    return by_key


@lru_cache(maxsize=1)
def _load_concepts() -> Dict[str, ConceptEntry]:
    """Load + parse chat_concepts.md. Cached for the process lifetime.

    The cache is intentional — the doc rarely changes during runtime, and
    re-parsing on every chat turn would be wasteful. To pick up a doc edit,
    restart the API.
    """
    try:
        text = _CONCEPTS_DOC.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return _parse_concepts_doc(text)


async def explain_concept(concept: str) -> ConceptExplainerResponse:
    """Look up a concept by name or alias in chat_concepts.md.

    Matching is case-insensitive and tolerates leading/trailing whitespace.
    Multi-word queries match the canonical name verbatim ("max drawdown"
    must match "Max Drawdown", not "Drawdown") — the LLM is responsible
    for normalising user phrasing before calling this tool.
    """
    by_key = _load_concepts()
    key = concept.strip().lower()
    match = by_key.get(key)
    return ConceptExplainerResponse(
        query=concept,
        match=match,
        available_concepts=sorted({e.canonical_name for e in by_key.values()}),
    )


# OpenAI function-calling tool definition. Surfaced to the LLM verbatim.
CONCEPT_EXPLAINER_DEF: Dict[str, Any] = {
    "name": "concept_explainer",
    "description": (
        "Look up the plain-English explanation of an investment concept "
        "(e.g., 'Sharpe ratio', 'mean reversion', 'overfitting'). Returns "
        "the canonical entry from Livermore's curated concept library plus "
        "the full list of available concepts if no exact match is found. "
        "Use for questions like 'what is X' / 'explain X' / 'define X'. "
        "Do NOT use for stock-specific lookups — use stock_lookup for that."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "concept": {
                "type": "string",
                "description": (
                    "The concept name to look up. Examples: 'Sharpe Ratio', "
                    "'Max Drawdown', 'Momentum', 'Overfitting'. Single phrase, "
                    "no surrounding words like 'what is' or 'explain'."
                ),
            },
        },
        "required": ["concept"],
        "additionalProperties": False,
    },
    "handler": explain_concept,
}
