"""Screener preset filter definitions — Phase 1f.

Powers the 9 algorithmic-screen cards on `/stocks` (Market Pulse v2's
Section 6) and the `/stocks/screener?preset=<slug>` deep-link flow.

Design:
  * Each preset is a `PresetSpec` with metadata + a filter function that
    takes a SQLAlchemy `Session` and returns a list of `SymbolCache`
    rows. The filter functions live here so the screener route can
    reuse them for both the summary (counts + sample tickers) and the
    full results endpoint.
  * 6 free (Scout-tier) presets, 2 Strategist-gated, 1 Quant-gated.
  * Filter logic intentionally stays in declarative SQL; no external
    services or LLM calls. Phase 1f-extra can layer sentiment / news /
    community signals onto the gated presets once those pipelines have
    enough coverage to be reliable as a screen.
  * For v1 the "gated" presets use sensible approximations that capture
    the spirit of the screen without requiring infrastructure we don't
    yet have in production (news sentiment per symbol, community vote
    rollup, real-time volume_ratio for stocks). Docstrings call out
    the approximations.

Tier-required dict (`PRESET_TIER`) is the single source of truth that
both the route's gating check + the frontend's badge consume.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.symbol import SymbolCache

Tier = Literal["scout", "strategist", "quant"]


# ── Preset metadata ────────────────────────────────────────────────────────


@dataclass
class PresetSpec:
    slug: str
    title: str
    description: str
    icon: str          # lucide-react icon name (frontend uses this verbatim)
    tier: Tier
    # The filter function returns a base query (no sort / limit). Caller
    # decides how to paginate.
    build_query: Callable[[Session], object]


# ── Curated ticker baskets ────────────────────────────────────────────────
# Used by presets that map to a theme rather than a fundamental filter.
# Kept small and well-known so the screener's `WHERE symbol IN (...)`
# stays fast and predictable.

_AI_BASKET: list[str] = [
    "NVDA", "AMD", "GOOGL", "MSFT", "AVGO", "TSM", "META", "ORCL",
    "CRWD", "PLTR", "AMZN", "NFLX", "ASML", "INTC", "IBM", "ADBE",
    "NOW", "SNOW", "MDB", "DDOG", "PANW", "ANET", "MU", "MRVL",
]

# Tickers commonly held as bellwethers for "positive catalyst" / news flow.
# v1 approximation: known momentum / event-driven names. Phase 1f-extra
# replaces this with a query against the news sentiment table.
_POSITIVE_CATALYST_BASKET: list[str] = [
    "TSLA", "COIN", "PLTR", "RIVN", "NVDA", "META", "AMZN", "GOOG",
    "AAPL", "MSFT", "AVGO", "SMCI", "TSLA", "AMD", "CRWD",
]

# "Community confirmed" v1 approximation: large-cap tickers most active
# on stock-research platforms. Phase 1f-extra replaces this with a
# query against community vote / watchlist rollup tables.
_COMMUNITY_CONFIRMED_BASKET: list[str] = [
    "NVDA", "AAPL", "AMZN", "TSLA", "GOOGL", "MSFT", "META", "AMD",
    "AVGO", "NFLX", "BRK.B", "JPM", "WMT", "COST", "HD",
]

# "Rising attention" v1 approximation: small/mid-cap names with high
# investor mindshare on stock screeners. Phase 1f-extra replaces this
# with a real-time volume_ratio query against the stocks universe.
_RISING_ATTENTION_BASKET: list[str] = [
    "PLTR", "SOFI", "COIN", "RBLX", "RIOT", "MARA", "AFRM", "DKNG",
    "RKLB", "FUBO", "IONQ", "BBAI", "ROKU", "U", "NET",
]


# ── Query builders ─────────────────────────────────────────────────────────
#
# Each builder returns a SQLAlchemy Select object. The route layer
# applies `.limit()` and counts via `func.count()`.


def _base_active_query():
    return select(SymbolCache).where(SymbolCache.is_active.is_(True))


def _trending_ai_query(db: Session):
    return (
        _base_active_query()
        .where(SymbolCache.symbol.in_(_AI_BASKET))
        .order_by(SymbolCache.market_cap.desc().nulls_last())
    )


def _top_growth_query(db: Session):
    """Approximation: large-cap tech/comm-services names with market_cap
    > $50B (high-growth proxies). Phase 1f-extra layers real 3y revenue
    growth + ROIC when fundamentals coverage hits parity."""
    return (
        _base_active_query()
        .where(SymbolCache.sector.in_(["Information Technology", "Communication Services", "Consumer Discretionary"]))
        .where(SymbolCache.market_cap >= 50_000_000_000)
        .order_by(SymbolCache.market_cap.desc().nulls_last())
    )


def _top_small_cap_query(db: Session):
    """Small-cap (market_cap_category='small'): $300M–$2B."""
    return (
        _base_active_query()
        .where(SymbolCache.market_cap_category == "small")
        .order_by(SymbolCache.market_cap.desc().nulls_last())
    )


def _top_rated_query(db: Session):
    """Approximation: mega/large-cap with reasonable P/E (<30). Phase
    1f-extra wires real analyst consensus + Livermore quant rating."""
    return (
        _base_active_query()
        .where(SymbolCache.market_cap_category.in_(["mega", "large"]))
        .where(SymbolCache.pe_ratio.isnot(None))
        .where(SymbolCache.pe_ratio < 30)
        .order_by(SymbolCache.market_cap.desc().nulls_last())
    )


def _top_dividend_query(db: Session):
    """Dividend yield > 4%, sorted by yield descending. Real filter — no
    approximation needed."""
    return (
        _base_active_query()
        .where(SymbolCache.dividend_yield.isnot(None))
        .where(SymbolCache.dividend_yield >= 0.04)
        .order_by(SymbolCache.dividend_yield.desc().nulls_last())
    )


def _top_value_query(db: Session):
    """P/E < 15 and market_cap >= $2B. Sorted by P/E ascending (cheapest
    first)."""
    return (
        _base_active_query()
        .where(SymbolCache.pe_ratio.isnot(None))
        .where(SymbolCache.pe_ratio > 0)
        .where(SymbolCache.pe_ratio < 15)
        .where(SymbolCache.market_cap >= 2_000_000_000)
        .order_by(SymbolCache.pe_ratio.asc().nulls_last())
    )


def _positive_catalyst_query(db: Session):
    return (
        _base_active_query()
        .where(SymbolCache.symbol.in_(_POSITIVE_CATALYST_BASKET))
        .order_by(SymbolCache.market_cap.desc().nulls_last())
    )


def _community_confirmed_query(db: Session):
    return (
        _base_active_query()
        .where(SymbolCache.symbol.in_(_COMMUNITY_CONFIRMED_BASKET))
        .order_by(SymbolCache.market_cap.desc().nulls_last())
    )


def _rising_attention_query(db: Session):
    return (
        _base_active_query()
        .where(SymbolCache.symbol.in_(_RISING_ATTENTION_BASKET))
        .order_by(SymbolCache.market_cap.desc().nulls_last())
    )


# ── Preset registry ────────────────────────────────────────────────────────


PRESETS: dict[str, PresetSpec] = {
    "trending-ai": PresetSpec(
        slug="trending-ai",
        title="Trending AI Stocks",
        description="AI-themed equities — semiconductors, hyperscalers, infra software, model labs.",
        icon="BrainCircuit",
        tier="scout",
        build_query=_trending_ai_query,
    ),
    "top-growth": PresetSpec(
        slug="top-growth",
        title="Top Growth Stocks",
        description="Mega/large-cap tech, communication & discretionary — revenue compounders.",
        icon="TrendingUp",
        tier="scout",
        build_query=_top_growth_query,
    ),
    "top-small-cap": PresetSpec(
        slug="top-small-cap",
        title="Top Small Cap Stocks",
        description="Market cap $300M–$2B. Higher risk / higher growth potential.",
        icon="Rocket",
        tier="scout",
        build_query=_top_small_cap_query,
    ),
    "top-rated": PresetSpec(
        slug="top-rated",
        title="Top Rated Stocks",
        description="Mega/large-cap names trading at reasonable P/E — quality + value blend.",
        icon="Star",
        tier="scout",
        build_query=_top_rated_query,
    ),
    "top-dividend": PresetSpec(
        slug="top-dividend",
        title="Top Dividend Stocks",
        description="Dividend yield ≥ 4%, sorted high → low. Income-focused.",
        icon="Coins",
        tier="scout",
        build_query=_top_dividend_query,
    ),
    "top-value": PresetSpec(
        slug="top-value",
        title="Top Value Stocks",
        description="P/E < 15 and market cap ≥ $2B. Sorted cheapest-first.",
        icon="Gem",
        tier="scout",
        build_query=_top_value_query,
    ),
    "positive-catalyst": PresetSpec(
        slug="positive-catalyst",
        title="Positive Catalyst Watchlist",
        description="Stocks with recent positive catalysts. v1 uses a curated basket; news-sentiment integration is next.",
        icon="Newspaper",
        tier="strategist",
        build_query=_positive_catalyst_query,
    ),
    "community-confirmed": PresetSpec(
        slug="community-confirmed",
        title="News Confirmed by Community",
        description="Headlines the community is amplifying. v1 uses a curated basket; vote-rollup integration is next.",
        icon="MessageSquareText",
        tier="strategist",
        build_query=_community_confirmed_query,
    ),
    "rising-attention": PresetSpec(
        slug="rising-attention",
        title="Rising Attention Stocks",
        description="Sentiment + volume both surging — unusual interest, early signal. v1 uses a curated basket; volume_ratio integration is next.",
        icon="Eye",
        tier="quant",
        build_query=_rising_attention_query,
    ),
}


def get_preset(slug: str) -> Optional[PresetSpec]:
    return PRESETS.get(slug)


def all_presets() -> list[PresetSpec]:
    """Preset list in fixed display order (matches the SCREENS array in
    Screener.tsx so the visual order stays consistent)."""
    return [
        PRESETS["trending-ai"],
        PRESETS["top-growth"],
        PRESETS["top-small-cap"],
        PRESETS["top-rated"],
        PRESETS["top-dividend"],
        PRESETS["top-value"],
        PRESETS["positive-catalyst"],
        PRESETS["community-confirmed"],
        PRESETS["rising-attention"],
    ]
