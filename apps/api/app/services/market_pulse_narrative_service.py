"""Market Pulse narrative generator — LLM-powered.

Wraps the existing `LLMGateway.generate_structured` pattern (same as
`insights.py` + `sentiment_service.py`) to produce a 2–3 sentence
plain-English read of the current Market Pulse snapshot, plus a
sector-rotation interpretive headline.

System prompt is modeled on the `market-news-analyst` skill's report
format — impact-ranked, plain-English, no price predictions, no jargon.

Cached upstream by `MarketPulseService` (60-min market_pulse cache);
this service has no cache of its own.

When `LLM_PROVIDER` is unset the service returns `None`, and the
frontend falls back to the deterministic `lib/market-pulse-narrative.ts`
template.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.services.llm_adapter import LLMAdapterError, get_llm_gateway

_log = logging.getLogger("livermore.market_pulse_narrative")


# ── Output schema (what the LLM must return + what the route exposes) ────────


class MarketNarrative(BaseModel):
    """Structured narrative from the LLM. Matches the frontend's expected
    `narrative` shape on `MarketPulseResponse`."""

    headline: str = Field(
        ...,
        description=(
            "2-3 sentence plain-English read of the market today. Open with "
            "time-of-day + lead index, then sector winners/losers, then macro. "
            "Cite actual numbers. No price predictions. No jargon."
        ),
        min_length=20,
        max_length=600,
    )
    sector_rotation: str = Field(
        ...,
        description=(
            "Single-line interpretive headline above the sector heatmap, "
            "e.g., 'Tech leading; energy/defensives lagging — growth-on "
            "rotation.' One sentence, < 100 chars."
        ),
        min_length=10,
        max_length=140,
    )
    watch_items: list[str] = Field(
        default_factory=list,
        description=(
            "0-3 short bullets ('what to watch') the user should pay attention "
            "to next. Each ≤ 80 chars."
        ),
        max_length=3,
    )
    as_of: Optional[str] = Field(
        default=None,
        description=(
            "Human-readable date the narrative is summarizing, e.g. "
            "'Wednesday, May 22, 2026'. Populated by the route layer "
            "AFTER the LLM call so the LLM doesn't have to guess at the "
            "calendar; not part of the LLM's response schema."
        ),
    )


# ── Prompt construction ──────────────────────────────────────────────────────


_SYSTEM_PROMPT = """You are the market read for Livermore Alpha, a retail-investor research tool.

Your job is to write a 2-3 sentence narrative summary of TODAY'S market action
based on the structured data the user provides. Style notes:

- Plain English. Don't use jargon ("dispersion", "factor rotation", "carry"
  trade) — say it in normal words.
- Cite ACTUAL NUMBERS from the data: index point values, sector % moves,
  macro readings. Don't make up numbers.
- Lead with the most significant move. If tech +1.4% and energy -0.8% and
  the rest is flat, lead with tech.
- Never predict future direction. Never recommend an action. Describe what
  happened.
- Tone is analyst-grade: confident, direct, no hedging filler ("it should
  be noted that…").
- If data is sparse or stale, say so plainly rather than padding.

Output ONLY valid JSON matching this schema:
{
  "headline": "<2-3 sentences>",
  "sector_rotation": "<one sentence, less than 100 chars, calling the
  rotation pattern>",
  "watch_items": ["<short bullet 1>", "<bullet 2>"]
}

Examples of GOOD output:
{
  "headline": "Tech led the tape Wednesday — Nasdaq +1.2% on NVDA strength,
  while small caps lagged (Russell 2000 -0.3%). Defensives sold off as 10Y
  yield ticked up 5bps; risk-on day overall.",
  "sector_rotation": "Tech and Discretionary leading; Utilities and Energy
  lagging — clear growth-on rotation.",
  "watch_items": [
    "10Y yield approaching 4.55% — watch growth-stock sensitivity",
    "Tech RS vs SPY at 60-day high"
  ]
}
"""


def _build_user_prompt(snapshot: dict[str, Any]) -> str:
    """Render the MarketPulseResponse-derived snapshot into a compact prompt.

    Keeps token usage low by including only the fields the narrative needs:
    index symbols + perf, sector leaders/laggards, macro deltas.
    """
    indices = snapshot.get("indices", [])
    macro = snapshot.get("macro", [])
    sectors = snapshot.get("sectors", [])

    lines: list[str] = []
    lines.append("Today's market snapshot (real values, JSON-serialized):\n")
    lines.append("INDICES (ETF proxy):")
    for c in indices:
        sym = c.get("symbol")
        name = c.get("name") or ""
        price = c.get("price")
        perf = c.get("perf_1d")
        perf_str = f"{perf * 100:+.2f}%" if isinstance(perf, (int, float)) else "n/a"
        lines.append(f"  {sym} ({name}): ${price} ({perf_str})")

    lines.append("\nSECTORS (sorted by CMF desc — first is leader, last is laggard):")
    for c in sectors[:11]:
        sym = c.get("symbol")
        name = c.get("name") or ""
        perf = c.get("perf_1d")
        cmf = c.get("cmf_20")
        perf_str = f"{perf * 100:+.2f}%" if isinstance(perf, (int, float)) else "n/a"
        cmf_str = f"CMF {cmf:+.2f}" if isinstance(cmf, (int, float)) else "n/a"
        lines.append(f"  {sym} {name}: {perf_str}, {cmf_str}")

    lines.append("\nMACRO:")
    for c in macro:
        sym = c.get("symbol")
        label = c.get("label") or ""
        price = c.get("price")
        perf = c.get("perf_1d")
        perf_str = f"{perf * 100:+.2f}%" if isinstance(perf, (int, float)) else "n/a"
        lines.append(f"  {sym} ({label}): {price} ({perf_str})")

    lines.append("\nReturn the narrative now (JSON only).")
    return "\n".join(lines)


# ── Public API ───────────────────────────────────────────────────────────────


async def generate_narrative(snapshot: Any) -> Optional[MarketNarrative]:
    """Produce a narrative from a `MarketPulseResponse` dataclass (or any
    object exposing `indices` / `macro` / `sectors`).

    Returns None when:
      - LLM_PROVIDER is unset (frontend falls back to deterministic)
      - LLM call fails (caller swallows + returns None)
      - LLM output fails schema validation
    """
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        _log.info("market_pulse_narrative: LLM disabled, returning None")
        return None

    # Marshall dataclass / dict / pydantic into a plain dict for the prompt.
    if is_dataclass(snapshot):
        snap_dict = asdict(snapshot)
    elif hasattr(snapshot, "model_dump"):
        snap_dict = snapshot.model_dump()
    elif isinstance(snapshot, dict):
        snap_dict = snapshot
    else:
        raise TypeError(
            f"generate_narrative: unsupported snapshot type {type(snapshot)!r}"
        )

    user_prompt = _build_user_prompt(snap_dict)

    try:
        result = await gateway.generate_structured(
            model=gateway.settings.llm_model,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=MarketNarrative,
            temperature=0.2,
        )
        return result
    except LLMAdapterError as exc:
        _log.warning("market_pulse_narrative LLM error: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        # Schema validation / network / unknown — never block the page.
        _log.warning("market_pulse_narrative unexpected error: %r", exc)
        return None
