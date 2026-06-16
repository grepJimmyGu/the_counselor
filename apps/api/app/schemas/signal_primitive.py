"""Signal primitive catalog schema — PRD-16a Slice 1.

Defines the data contract for the ~55 signal primitives that Custom Mode
(PRD-16b) composes strategies from. This file is **schema only** — the
hand-authored catalog data lives in `app/data/signal_primitives.py` and
the concrete `SignalProvider` impls land in PRD-16a-2.

Three concentric concepts:

  - `SignalCategory` — coarse classification across all primitives. 8
    values, set in stone for PRD-16a/b/c. Future packets can add new
    categories, but must not remove or rename existing ones (frontend
    filters break otherwise).
  - `Parameter` — one tunable knob on a primitive (e.g. RSI's `period=14`).
    Includes min/max for the composer UI's slider clamps.
  - `SignalPrimitive` — one row in the catalog. Joins the schema above
    to the concrete `SignalProvider` impl via `provider_impl` (a string
    matching the registry key in `signal_provider.py:_REGISTRY`).

Design notes:
  - `evidence_tier` ("A" | "B" | "C") matches the existing template
    evidence framework — A = well-established (RSI, moving averages,
    P/E); B = supported but contested (momentum factor, sentiment); C =
    experimental (custom composites, novel data sources).
  - `resolution` is a list, not a single value, because PRD-16c will
    extend many existing daily primitives with intraday support. Authors
    of new primitives in PRD-16a/16b ship `["daily"]`; PRD-16c flips
    eligible primitives to `["daily", "intraday"]`.
  - `compute_strategy` records whether the value is computed locally
    with pandas (cheap, no external API call) or fetched from Alpha
    Vantage's pre-computed endpoint (expensive locally, cheap as an API
    call). Documented per-primitive so PRD-16a-2's `SignalProvider`
    impls know the right path.

The schema is intentionally minimal. The full editorial product — the
~55 plain-English descriptions — lives in `app/data/signal_primitives.py`.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class SignalCategory(str, Enum):
    """Coarse classification surface for the catalog browser's sidebar.

    Set in stone for PRD-16a/b/c. Adding a new category requires
    extending the frontend `<SignalCatalogBrowser>` sidebar; removing
    one breaks every saved strategy that referenced a primitive in
    that category. Don't.
    """

    TREND = "trend"
    """SMA, EMA, MACD, ADX, AROON family — measures direction + strength."""

    MEAN_REVERSION = "mean_reversion"
    """RSI, Bollinger, Stochastic — measures overbought/oversold extremes."""

    MOMENTUM = "momentum"
    """ROC, MOM, breakout, cross-sectional rank — measures price acceleration."""

    VOLUME = "volume"
    """OBV, AD, VWAP, avg dollar volume — measures conviction behind price."""

    VOLATILITY = "volatility"
    """ATR, NATR, realized vol — measures uncertainty / risk regime."""

    FUNDAMENTAL = "fundamental"
    """FCF yield, P/B, Piotroski — measures business quality + value."""

    SENTIMENT = "sentiment"
    """News sentiment, insider activity — measures non-price information flow."""

    CROSS_SECTIONAL = "cross_sectional"
    """Universe-relative ranking primitives — measures position in a peer group."""


class OutputKind(str, Enum):
    """Semantic shape of the signal a primitive emits at each timestep.

    PRD-22a. Drives the composer rule-builder dispatch (PRD-22c) and the
    KB-lookup Jaccard enrichment (PRD-22b). Defaults to VALUE so every v1
    primitive stays backward-compatible — the composer's existing
    `[primitive] [< | >] [threshold]` widget is the VALUE widget.

    `str, Enum` (matching `SignalCategory`) so it JSON-serializes to its
    string value in the catalog payload.
    """

    VALUE = "value"
    """Scalar at each bar. Composer renders [primitive] [< | >] [threshold]."""

    EVENT = "event"
    """Boolean true ONLY at the bar of transition. No threshold input."""

    REGIME = "regime"
    """Categorical classifier (trending/ranging/etc). Single-select chip."""

    LEVEL = "level"
    """Boolean true WHILE a condition holds (persists). No threshold input."""

    DISTANCE = "distance"
    """Signed percentage gap. Range slider input (between min% and max%)."""

    CROSS = "cross"
    """EVENT specialization: line A crosses line B. Direction picker."""

    DIVERGENCE = "divergence"
    """Pattern: indicator swings disagree with price swings. Lookback + direction."""


class IntentGroup(str, Enum):
    """Trader-facing intent the user is *reading for* — the chip taxonomy that
    fronts the catalog in the composer (PRD-22c reading layer). Cuts lightly
    across `SignalCategory` (e.g. the 52-week-extrema family lives under
    BREAKOUT though its category is MOMENTUM). One per primitive; the composer
    groups the catalog by this for the "what are you reading?" chips.

    `str, Enum` (matching `SignalCategory`/`OutputKind`) so it JSON-serializes
    to its string value in the catalog payload.
    """

    TREND = "trend"
    """Direction + strength of the prevailing trend (MAs, ADX, AROON, SAR)."""

    MOMENTUM = "momentum"
    """Acceleration + momentum shifts (MACD, ROC, MOM, 12-1)."""

    OVERBOUGHT_OVERSOLD = "overbought_oversold"
    """Stretched extremes that tend to revert (RSI, Stochastic, Bollinger)."""

    BREAKOUT = "breakout"
    """Breakouts + distance to 52-week extremes (Donchian, 52w family)."""

    VOLATILITY = "volatility"
    """Volatility regime, squeezes, trailing stops (ATR, TTM, Chandelier)."""

    VOLUME = "volume"
    """Conviction behind price (OBV, VWAP, RVOL, liquidity)."""

    VALUE_QUALITY = "value_quality"
    """Business value + quality from the financials (FCF yield, P/B, F-score)."""

    SENTIMENT_EVENTS = "sentiment_events"
    """News, insiders, analyst + earnings events (sentiment, surprise, revisions)."""

    RELATIVE_STRENGTH = "relative_strength"
    """Strength ranked against a peer universe (cross-sectional rank, rotation)."""


class Parameter(BaseModel):
    """One tunable knob on a signal primitive.

    Renders as a numeric input or slider in the PRD-16b composer; the
    `min_value` / `max_value` clamp the user's input. `default` is what
    the composer pre-fills and what the preview endpoint uses when no
    override is supplied.
    """

    name: str = Field(..., description="Identifier — e.g. 'period', 'fast_ema'")
    default: Any = Field(..., description="Default value the composer pre-fills")
    min_value: Optional[float] = Field(
        default=None,
        description="Lower clamp for slider; None = unbounded below",
    )
    max_value: Optional[float] = Field(
        default=None,
        description="Upper clamp for slider; None = unbounded above",
    )
    description: str = Field(
        ...,
        description="Plain-English label (e.g. 'Look-back window in days')",
    )


class SignalPrimitive(BaseModel):
    """One row in the signal catalog.

    Every field is required (except `long_description`); the
    `tests/test_signal_catalog.py` validators enforce minimums on
    description length, `parameters` non-emptiness, etc.

    `provider_impl` is the registry key (`signal_provider.py:_REGISTRY`)
    that the `SignalProvider` impl will live under once PRD-16a-2 lands
    them. For PRD-16a-1 (this slice) the catalog is metadata-only —
    composing a strategy against an unimplemented primitive yields a
    KeyError from `get_signal_provider()`, by design. PRD-16a-2 closes
    that gap.
    """

    id: str = Field(..., description="Unique slug — e.g. 'rsi_14', 'sma_200'")
    category: SignalCategory
    family: str = Field(
        ...,
        description=(
            "Coarser group than `id` — e.g. RSI / STOCHRSI both share family='RSI'. "
            "Used by the catalog browser to collapse related entries."
        ),
    )
    name: str = Field(..., description="Display name (e.g. 'RSI (Relative Strength Index)')")
    description: str = Field(
        ...,
        min_length=30,
        description="1-sentence plain-English description. ≥30 chars (test-enforced).",
    )
    long_description: Optional[str] = Field(
        default=None,
        description="Optional paragraph — shown when the user expands the card.",
    )
    parameters: List[Parameter] = Field(
        ...,
        min_length=1,
        description="At least one tunable knob (the composer needs something to expose).",
    )
    default_thresholds: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Default entry / exit thresholds, e.g. {'upper': 70, 'lower': 30}. "
            "Empty dict for primitives that have no canonical threshold."
        ),
    )
    asset_compat: List[Literal["equity", "etf", "commodity", "fx", "crypto"]] = Field(
        ...,
        min_length=1,
        description="Asset classes this primitive sensibly applies to.",
    )
    evidence_tier: Literal["A", "B", "C"] = Field(
        ...,
        description=(
            "A = well-established (RSI, MA, P/E). "
            "B = supported but contested (momentum, sentiment). "
            "C = experimental / novel."
        ),
    )
    provider_impl: str = Field(
        ...,
        description=(
            "Registry key in `signal_provider.py:_REGISTRY`. "
            "PRD-16a-1 catalog references provider_impl strings that "
            "PRD-16a-2 wires up; lookups for unwired keys throw KeyError."
        ),
    )
    data_source: Literal["price", "fundamental", "sentiment", "event"] = Field(
        ...,
        description="What category of data the SignalProvider needs to fetch.",
    )
    resolution: List[Literal["daily", "intraday"]] = Field(
        default=["daily"],
        description=(
            "Which data resolutions this primitive supports. PRD-16a/b ships "
            "['daily'] only; PRD-16c extends eligible primitives with 'intraday'."
        ),
    )
    is_ranking: bool = Field(
        default=False,
        description="True for cross-sectional primitives that rank a universe.",
    )
    compute_strategy: Literal["local", "av_endpoint"] = Field(
        default="local",
        description=(
            "'local' — compute with pandas (cheap, no API call). "
            "'av_endpoint' — fetch Alpha Vantage's pre-computed series "
            "(expensive locally, single API call)."
        ),
    )

    # ── PRD-22a semantics layer (additive; runtime no-op) ─────────────────────
    output_kind: OutputKind = Field(
        default=OutputKind.VALUE,
        description=(
            "Semantic shape of the emitted signal. Drives the composer's "
            "kind-specific rule-builder (PRD-22c) + KB-lookup Jaccard "
            "(PRD-22b). v1 default = VALUE preserves the existing widget."
        ),
    )
    output_channels: List[str] = Field(
        default_factory=lambda: ["value"],
        description=(
            "Named channels this primitive emits. Multi-channel primitives "
            "(MACD, ADX, Stoch, Bollinger) declare several; the default "
            "['value'] matches v1 single-channel semantics. These names are a "
            "PUBLIC CONTRACT once shipped — never rename, only deprecate."
        ),
    )
    composes: List[str] = Field(
        default_factory=list,
        description=(
            "Parent primitive_ids this is derived from (e.g. a future "
            "macd_signal_cross composes=['macd']). Default = standalone. "
            "PRD-22b is the first consumer."
        ),
    )

    # ── PRD-22c reading layer (additive; intent-first composer) ───────────────
    intent_group: Optional[IntentGroup] = Field(
        default=None,
        description=(
            "Trader-facing intent chip this primitive lives under (the "
            "'what are you reading?' grouping in the composer). Backfilled for "
            "EVERY primitive by the reading-layer normalization pass in "
            "`app/data/signal_primitives.py`; None only pre-normalization."
        ),
    )
    reading: Optional[str] = Field(
        default=None,
        description=(
            "Short plain-English 'what a trader reads when this triggers' "
            "headline for the rule card — punchier than `description`. "
            "Direction-aware copy (up/down) is added by the composer widget; "
            "this is the direction-neutral base. None → UI falls back to "
            "`description`."
        ),
    )


class SignalPrimitivesResponse(BaseModel):
    """Response for `GET /api/signal-primitives` — the full catalog
    payload the frontend caches. `version_hash` is content-addressable;
    a change in any primitive's metadata produces a new hash, which the
    frontend uses to invalidate its localStorage cache."""

    primitives: List[SignalPrimitive]
    categories: List[SignalCategory]
    version_hash: str = Field(
        ...,
        description=(
            "Content hash over the catalog data. Identical hash → "
            "identical catalog → frontend can reuse cached payload."
        ),
    )
