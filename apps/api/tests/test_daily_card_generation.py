"""Generate once per trading day, then serve the same card forever.

The lifecycle Jimmy specified: first share of the day generates from the prior
close, writes one row per `(trading_date, lang)`, and every later viewer gets
that exact row. These tests pin the three things that would hurt most if wrong
— an invented figure reaching a cached card, a double generation under
concurrent first-shares, and a model outage taking the share button down.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.migrations import run_startup_migrations
from app.db.session import Base
from app.models.daily_card import DailyCard
from app.services.card_copy import CardCopy
from app.services.card_labels import EN, ZH
from app.services.daily_brief_service import (
    BriefMover,
    BriefQuote,
    BriefSector,
    DailyBrief,
)
from app.services.daily_card_generation import (
    card_to_dict,
    generate_copy,
    get_existing,
    get_or_create_card,
)
from app.services.daily_card_service import build_card_payload
from app.services.evaluation_scoring import ThreeDimensionalScore

SCORE = ThreeDimensionalScore(health=92, valuation=78, trend=90, final=87, label="Attractive")


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    run_startup_migrations(engine)
    s = sessionmaker(bind=engine, autoflush=False, future=True)()
    yield s
    s.close()
    engine.dispose()


def _brief(**over) -> DailyBrief:
    b = DailyBrief(as_of="2026-07-31T21:00:00")
    b.indices = [BriefQuote("^GSPC", "S&P 500", 7757.64, 1.66)]
    b.vix = BriefQuote("^VIX", "VIX", 14.9, -6.83)
    b.sectors = [BriefSector("Technology", 5.5, 0.19), BriefSector("Energy", -1.1, -0.05)]
    b.flow_into = BriefSector("Technology", 5.5, 0.19)
    b.flow_out_of = BriefSector("Energy", -1.1, -0.05)
    b.unusual = BriefMover("MSFT", "Microsoft", 15.51)
    for k, v in over.items():
        setattr(b, k, v)
    return b


def _stub_gateway(monkeypatch, *, enabled=True, response=None, raises=None):
    import app.services.llm_adapter as adapter

    class _G:
        is_enabled = enabled
        settings = type("S", (), {"llm_model": "gpt-5"})()

        async def generate_json(self, *, system_prompt, user_prompt, **kw):
            if raises:
                raise raises
            return response or {}

    monkeypatch.setattr(adapter, "get_llm_gateway", lambda: _G())
    return _G()


# ── generate once ───────────────────────────────────────────────────────────


def test_first_share_creates_a_row(db, monkeypatch):
    _stub_gateway(monkeypatch, response={"headline": "Software carries the tape"})
    row = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    assert row is not None
    assert row.trading_date == "2026-07-31"
    assert json.loads(row.copy)["headline"] == "Software carries the tape"
    assert row.model == "gpt-5"


def test_second_share_reuses_the_row_and_does_not_regenerate(db, monkeypatch):
    """Immutable: a forwarded link must show what the sharer saw, even if
    today's prose would be better."""
    calls = []

    import app.services.llm_adapter as adapter

    class _G:
        is_enabled = True
        settings = type("S", (), {"llm_model": "gpt-5"})()

        async def generate_json(self, **kw):
            calls.append(1)
            return {"headline": "first generation" if len(calls) == 1 else "second generation"}

    monkeypatch.setattr(adapter, "get_llm_gateway", lambda: _G())

    first = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    second = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    assert first.id == second.id
    assert len(calls) == 1
    assert json.loads(second.copy)["headline"] == "first generation"


def test_languages_are_separate_rows(db, monkeypatch):
    _stub_gateway(monkeypatch, response={"headline": "x"})
    en = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    zh = asyncio.run(get_or_create_card(db, brief=_brief(), lang=ZH, score=SCORE))
    assert en.id != zh.id
    assert {en.lang, zh.lang} == {EN, ZH}


def test_an_unknown_language_falls_back_to_english(db, monkeypatch):
    _stub_gateway(monkeypatch, response={})
    row = asyncio.run(get_or_create_card(db, brief=_brief(), lang="fr", score=SCORE))
    assert row.lang == EN


# ── the race ────────────────────────────────────────────────────────────────


def test_losing_the_insert_race_serves_the_winners_card(db, monkeypatch):
    """Two first-shares in the same second: both find no row, both generate,
    one insert loses. The loser must serve the winner's card rather than
    writing a divergent one — the whole point of the unique constraint."""
    _stub_gateway(monkeypatch, response={"headline": "winner"})

    # Simulate the winner committing between our read and our insert.
    winner = DailyCard(
        id="winner-id",
        trading_date="2026-07-31",
        lang=EN,
        payload="{}",
        copy=json.dumps({"headline": "winner"}),
        model="gpt-5",
    )
    db.add(winner)
    db.commit()

    row = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    assert row.id == "winner-id"
    assert db.query(DailyCard).count() == 1


def test_the_unique_constraint_is_real(db):
    for i in (1, 2):
        db.add(
            DailyCard(id=f"id-{i}", trading_date="2026-07-31", lang=EN, payload="{}", copy="{}")
        )
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


# ── degradation ─────────────────────────────────────────────────────────────


def test_llm_disabled_still_produces_a_card(db, monkeypatch):
    """Every figure is deterministic; only the prose needs the model. A card
    with real numbers and no headline beats a share button that errors."""
    _stub_gateway(monkeypatch, enabled=False)
    row = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    assert row is not None
    assert json.loads(row.copy)["headline"] == ""
    assert row.model is None
    # The data half is intact.
    payload = json.loads(row.payload)
    assert payload["indices"][0]["value"] == "7,757.64"
    assert payload["stock"]["change"] == "+15.51%"


def test_a_failed_generation_still_produces_a_card(db, monkeypatch):
    _stub_gateway(monkeypatch, raises=RuntimeError("503 from the provider"))
    row = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    assert row is not None
    assert json.loads(row.copy)["headline"] == ""
    assert json.loads(row.payload)["indices"]


def test_an_invented_figure_never_reaches_the_stored_card(db, monkeypatch):
    """The guard runs BEFORE persistence — otherwise a bad generation would be
    cached and re-served to every viewer for the rest of the day."""
    _stub_gateway(monkeypatch, response={"headline": "MSFT soared 18.4% today"})
    row = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    stored = json.loads(row.copy)
    assert stored["headline"] == ""
    assert "headline" in stored["rejected"]


def test_a_brief_with_no_close_date_is_declined(db, monkeypatch):
    """No date means no key. A row under a blank date could never be found
    again, so declining beats writing one."""
    _stub_gateway(monkeypatch, response={})
    assert asyncio.run(get_or_create_card(db, brief=_brief(as_of=None), lang=EN)) is None
    assert db.query(DailyCard).count() == 0


# ── read path ───────────────────────────────────────────────────────────────


def test_card_to_dict_round_trips(db, monkeypatch):
    _stub_gateway(monkeypatch, response={"headline": "Clean line"})
    row = asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    d = card_to_dict(row)
    assert d["trading_date"] == "2026-07-31"
    assert d["copy"]["headline"] == "Clean line"
    assert d["payload"]["labels"]["takeaway"]


def test_corrupt_json_degrades_to_an_empty_card(db):
    """A corrupt row should render blank, not 500 the share endpoint."""
    row = DailyCard(
        id="x", trading_date="2026-07-31", lang=EN, payload="not json{", copy="{}"
    )
    d = card_to_dict(row)
    assert d["payload"] == {}


def test_get_existing_is_scoped_to_both_date_and_lang(db, monkeypatch):
    _stub_gateway(monkeypatch, response={})
    asyncio.run(get_or_create_card(db, brief=_brief(), lang=EN, score=SCORE))
    assert get_existing(db, "2026-07-31", EN) is not None
    assert get_existing(db, "2026-07-31", ZH) is None
    assert get_existing(db, "2026-07-30", EN) is None


def test_generate_copy_returns_empty_when_disabled(monkeypatch):
    _stub_gateway(monkeypatch, enabled=False)
    copy, model = asyncio.run(generate_copy(build_card_payload(_brief(), lang=EN)))
    assert isinstance(copy, CardCopy) and copy.headline == "" and model is None
