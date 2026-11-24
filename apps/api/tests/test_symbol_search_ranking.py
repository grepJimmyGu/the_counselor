"""Symbol search puts the ticker you typed first (2026-11-23).

Jimmy could not find Anthropic (ANT) by typing "ANT": the search read the
first 10 rows matching the ticker prefix OR the name containing "ant"
anywhere, in no order, and ten warrants ("Warr*ant*s") filled the list.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from sqlalchemy.orm import Session

from app.models.symbol import SymbolCache
from app.services.symbol_service import SymbolService

WARRANTS = [
    ("AMDDW", "SINTX Technologies Inc - Warrants (14/05/2023)"),
    ("CRUBW", "Crucible Acquisition Corp - Warrants(26/12/2025)"),
    ("AACIW", "Armada Acquisition Corp. I Warrant"),
    ("AAGRW", "African Agriculture Holdings Inc. Warrant"),
    ("ABLLW", "Abacus Life Inc. Warrant"),
    ("ABPWW", "Abpro Holdings Inc. Warrant"),
    ("ACAAW", "Averin Capital Acquisition Corp. Warrants"),
    ("ACABW", "Atlantic Coastal Acquisition Corp. II Warrant"),
    ("AACTW", "Ares Acquisition Corp. II Warrant"),
    ("ADRTW", "Ault Disruptive Technologies Corp. Warrant"),
    ("AFARW", "Aura FAT Projects Acquisition Corp Warrant"),
]


def _seed(db: Session, rows) -> None:
    for symbol, name in rows:
        db.add(SymbolCache(symbol=symbol, name=name))
    db.commit()


def _search(db: Session, query: str, remote=None):
    client = AsyncMock()
    client.search_symbols = AsyncMock(return_value=remote or [])
    service = SymbolService(client)
    return [r.symbol for r in asyncio.run(service.search(db, query))], client


def test_REGRESSION_the_ticker_typed_comes_first_not_ten_warrants(db: Session) -> None:
    # Warrants first, so an unordered read would meet them before ANT.
    _seed(db, WARRANTS + [("ANT", "Anthropic PBC"), ("ANTE", "AirNet Technology Inc."),
                          ("GIANT", "Giant Holdings"), ("ANTX", "AN2 Therapeutics")])

    found, client = _search(db, "ANT")

    assert found[0] == "ANT"
    # Then tickers starting with it, shortest first; then names with a word
    # starting with it; warrants ("Warrant") only after those.
    assert found[1:3] == ["ANTE", "ANTX"]
    assert found.index("GIANT") > found.index("ANTX")
    assert len(found) == 10
    client.search_symbols.assert_not_called()


def test_lowercase_and_spaces_find_the_same_ticker(db: Session) -> None:
    _seed(db, [("ANT", "Anthropic PBC"), ("NVDA", "NVIDIA Corporation")])
    assert _search(db, " ant ")[0][0] == "ANT"
    assert _search(db, "nvidia")[0][0] == "NVDA"


def test_a_name_that_starts_with_the_query_beats_one_that_only_contains_it(db: Session) -> None:
    _seed(db, [("PLNT", "Planet Fitness"), ("XPLAN", "Explanation Corp"), ("APLN", "Apple Lane")])
    found, _ = _search(db, "plan")
    # PLNT does not start with "PLAN" as a ticker, but its name does.
    assert found[:2] == ["PLNT", "XPLAN"]


def test_nothing_local_still_asks_the_provider(db: Session) -> None:
    remote = [{"symbol": "ZZZQ", "name": "Zed Corp", "region": "United States", "currency": "USD",
               "instrument_type": "Equity", "exchange": None, "timezone": None,
               "alpha_vantage_match_score": 0.9}]
    found, client = _search(db, "ZZZQ", remote=remote)
    assert found == ["ZZZQ"]
    client.search_symbols.assert_awaited_once()


def test_an_empty_query_returns_nothing(db: Session) -> None:
    _seed(db, [("ANT", "Anthropic PBC")])
    found, client = _search(db, "   ")
    assert found == []
    client.search_symbols.assert_not_called()
