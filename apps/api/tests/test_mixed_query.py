"""PRD-29 — mixed fundamental + technical search queries.

"Small caps that are oversold" is one sentence carrying two independent asks.
Before this, the box ran the technical half over the whole S&P 500 and silently
ignored the fundamental half. These tests pin the extraction, the sector-alias
trap, and the disclosure rules (nothing silently truncated, nothing silently
widened).
"""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.data.screen_filter_vocab import SECTOR_ALIASES
from app.models.symbol import SymbolCache
from app.schemas.search import SearchIntent
from app.services.screen_filter_parser import extract_filters
from app.services.screener_service import ScreenerService
from app.services.search_dispatch_service import (
    FundamentalNarrowing,
    build_screen_result,
)


# ── extraction ────────────────────────────────────────────────────────────


def test_extracts_market_cap_tier() -> None:
    filters, applied = extract_filters("small caps that are oversold")
    assert filters is not None
    assert filters.market_cap_category == "small"
    assert "small-cap" in applied


def test_extracts_sector_and_cap_together() -> None:
    filters, applied = extract_filters("large cap healthcare names above the 200-day")
    assert filters.market_cap_category == "large"
    assert filters.sector == "healthcare"
    assert len(applied) == 2


def test_extracts_explicit_pe_bound() -> None:
    filters, _ = extract_filters("tech stocks with a P/E under 15")
    assert filters.max_pe == 15.0
    assert filters.sector == "technology"


def test_extracts_reversed_pe_phrasing() -> None:
    filters, _ = extract_filters("banks under a 12 p/e")
    assert filters.max_pe == 12.0
    assert filters.sector == "financials"


def test_extracts_dividend_yield_number() -> None:
    filters, applied = extract_filters("utilities yielding more than 4%")
    assert filters.min_dividend_yield == 0.04
    assert filters.sector == "utilities"
    assert any("4%" in a for a in applied)


def test_purely_technical_query_extracts_nothing() -> None:
    """The fundamental extractor must not invent a constraint — a technical-only
    query has to keep running over the full standing universe."""
    filters, applied = extract_filters("rsi below 30 and macd crossing up")
    assert filters is None
    assert applied == []


def test_does_not_match_inside_a_longer_word() -> None:
    """'retail' must not fire from 'retailers', 'oil' not from 'toil'."""
    filters, _ = extract_filters("stocks that toiled all year")
    assert filters is None


def test_absurd_pe_is_ignored() -> None:
    filters, _ = extract_filters("p/e under 999999")
    assert filters is None or filters.max_pe is None


# ── the sector-alias trap ─────────────────────────────────────────────────


def test_every_canonical_sector_has_at_least_one_spelling() -> None:
    for canonical, spellings in SECTOR_ALIASES.items():
        assert spellings, f"{canonical} has no stored spelling"


def test_healthcare_matches_BOTH_stored_spellings(db: Session) -> None:
    """Production stores 'Healthcare' AND 'Health Care'. Matching one spelling
    silently drops the companies stored under the other — the bug this test
    exists to prevent."""
    db.add_all([
        SymbolCache(symbol="AAA", name="A", sector="Healthcare", is_active=True,
                    market_cap=9e9),
        SymbolCache(symbol="BBB", name="B", sector="Health Care", is_active=True,
                    market_cap=8e9),
        SymbolCache(symbol="CCC", name="C", sector="Energy", is_active=True,
                    market_cap=7e9),
    ])
    db.commit()

    filters, _ = extract_filters("healthcare stocks")
    symbols, total = ScreenerService().matching_symbols(db, filters)
    assert set(symbols) == {"AAA", "BBB"}, "both spellings must match"
    assert total == 2


def test_cap_is_disclosed_not_silent(db: Session) -> None:
    db.add_all([
        SymbolCache(symbol=f"S{i}", name=f"n{i}", sector="Energy",
                    is_active=True, market_cap=float(1000 - i))
        for i in range(5)
    ])
    db.commit()

    filters, _ = extract_filters("energy stocks")
    symbols, total = ScreenerService().matching_symbols(db, filters, cap=2)
    assert len(symbols) == 2
    assert total == 5, "total must report the true match count, not the cap"
    # Largest first, so a capped universe keeps the most liquid names.
    assert symbols == ["S0", "S1"]


# ── result shaping + disclosure ───────────────────────────────────────────


def _parsed(rules):
    sj = SimpleNamespace(model_dump=lambda: {"strategy_type": "custom_build",
                                             "universe": ["AAPL"], "rules": rules})
    return SimpleNamespace(strategy_json=sj, approximation_note=None,
                           suggested_reformulation=None, clarification_questions=[])


_RULES = [{"primitive_id": "rsi", "operator": "lt", "threshold": 30}]


def test_mixed_query_narrows_the_universe_to_symbols() -> None:
    result = build_screen_result(
        "small caps that are oversold",
        _parsed(_RULES),
        fundamental=FundamentalNarrowing(
            symbols=["AAA", "BBB"], applied=["small-cap"], total=2
        ),
    )
    assert result.intent == SearchIntent.SCREEN
    assert result.screen.universe_id == "symbols"
    assert result.screen.symbols == ["AAA", "BBB"]
    assert result.screen.fundamental_filters == ["small-cap"]
    assert "small-cap" in result.note


def test_technical_only_query_keeps_the_standing_universe() -> None:
    result = build_screen_result("oversold names", _parsed(_RULES), fundamental=None)
    assert result.screen.universe_id == "sp500"
    assert result.screen.symbols == []


def test_truncation_is_reported_to_the_user() -> None:
    result = build_screen_result(
        "large caps that are oversold",
        _parsed(_RULES),
        fundamental=FundamentalNarrowing(
            symbols=["A", "B"], applied=["large-cap"], total=900,
            truncated_from=900,
        ),
    )
    assert result.screen.universe_truncated_from == 900
    assert "900" in result.note


def test_fundamental_half_matching_nothing_does_NOT_widen_back() -> None:
    """If 'micro-cap utilities' matches no company, returning S&P 500 results
    would contradict the query. Ask instead."""
    result = build_screen_result(
        "micro cap utilities that are oversold",
        _parsed(_RULES),
        fundamental=FundamentalNarrowing(symbols=[], applied=["micro-cap"], total=0),
    )
    assert result.intent == SearchIntent.AMBIGUOUS
    assert "micro-cap" in result.note
