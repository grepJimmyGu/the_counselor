"""Card prose — the prompt contract and the numeric guard.

The model writes sentences and nothing else. These tests pin what the prompt
tells it and, more importantly, what happens when it ignores that.
"""
from __future__ import annotations

import json

from app.services.card_copy import build_prompt, validate_copy
from app.services.card_labels import EN, ZH
from app.services.daily_brief_service import (
    BriefMover,
    BriefQuote,
    BriefSector,
    DailyBrief,
)
from app.services.daily_card_service import build_card_payload
from app.services.evaluation_scoring import ThreeDimensionalScore

SCORE = ThreeDimensionalScore(health=92, valuation=78, trend=90, final=87, label="Attractive")


def _payload(lang=EN):
    b = DailyBrief(as_of="2026-07-31T21:00:00")
    b.indices = [
        BriefQuote("^DJI", "Dow Jones", 44_500.12, 1.19),
        BriefQuote("^GSPC", "S&P 500", 7_757.64, 1.66),
        BriefQuote("^IXIC", "NASDAQ Composite", 26_690.62, 2.78),
    ]
    b.vix = BriefQuote("^VIX", "VIX", 14.90, -6.83)
    b.sectors = [
        BriefSector("Technology", 5.50, 0.19),
        BriefSector("Communication", -2.70, -0.14),
    ]
    b.flow_into = BriefSector("Technology", 5.50, 0.19)
    b.flow_out_of = BriefSector("Communication", -2.70, -0.14)
    b.unusual = BriefMover("MSFT", "Microsoft", 15.51)
    return build_card_payload(b, lang=lang, score=SCORE)


# ── the prompt ──────────────────────────────────────────────────────────────


def test_prompt_forbids_figures_and_proper_nouns():
    system, _ = build_prompt(_payload())
    assert "NEVER write a number" in system
    assert "NEVER name a sector" in system


def test_chinese_prompt_is_written_in_chinese():
    """A Chinese card generated from an English system prompt reads
    translated. The instruction language sets the register."""
    system, _ = build_prompt(_payload(ZH))
    assert "每日美股复盘" in system
    assert any("一" <= ch <= "鿿" for ch in system)


def test_data_block_carries_figures_as_rendered_strings():
    """The model quotes "+1.19%" rather than reformatting 1.19 and disagreeing
    with the card beside it."""
    _, user = build_prompt(_payload())
    assert "+1.19%" in user and "26,690.62" in user


def test_absent_news_instructs_collapse_not_invention():
    _, user = build_prompt(_payload(), news=None)
    assert "NEWS: none available" in user
    assert "Do not invent" in user


def test_news_present_is_named_as_the_only_basis():
    _, user = build_prompt(_payload(), news=[{"title": "Microsoft beats", "url": "x"}])
    assert "the only basis" in user
    assert "Microsoft beats" in user


# ── the guard ───────────────────────────────────────────────────────────────


def test_clean_copy_passes_through():
    p = _payload()
    got = validate_copy(
        {
            "headline": "Software carries the tape",
            "subtitle": "One earnings report reset the mood.",
            "stock_points": ["Biggest one-day move in the index", "Cloud growth reaccelerated"],
            "drivers": [{"title": "Confidence returns", "body": "Spending fears eased."}],
        },
        p,
    )
    assert got.headline == "Software carries the tape"
    assert len(got.stock_points) == 2
    assert got.drivers[0]["title"] == "Confidence returns"
    assert got.rejected == []


def test_a_supplied_figure_is_allowed():
    p = _payload()
    got = validate_copy({"headline": "MSFT soars +15.51% and drags the tape up"}, p)
    assert "15.51" in got.headline
    assert got.rejected == []


def test_an_invented_figure_drops_that_field():
    """The failure this whole design exists to prevent: a number on a card
    built to be forwarded that we never computed."""
    p = _payload()
    got = validate_copy(
        {"headline": "MSFT soars 18.4%", "subtitle": "A clean line with no figures."},
        p,
    )
    assert got.headline == ""
    assert "headline" in got.rejected
    # One bad sentence must not cost the whole card.
    assert got.subtitle == "A clean line with no figures."


def test_prose_may_carry_the_sign_in_words():
    """"VIX fell 6.83%" is correct English for -6.83%. Rejecting it would
    train whoever hit it to switch the guard off."""
    p = _payload()
    got = validate_copy({"market_note": "Fear drained away as VIX fell 6.83%."}, p)
    assert got.market_note
    assert got.rejected == []


def test_scores_are_quotable_but_neighbours_are_not():
    p = _payload()
    ok = validate_copy({"stock_takeaway": "Fundamentals score 92 — the report validated it."}, p)
    assert ok.stock_takeaway and ok.rejected == []
    bad = validate_copy({"stock_takeaway": "Fundamentals score 93."}, p)
    assert bad.stock_takeaway == ""


def test_one_bad_bullet_drops_only_itself():
    p = _payload()
    got = validate_copy(
        {"stock_points": ["Added roughly $450B in value", "Biggest move in the index"]},
        p,
    )
    assert got.stock_points == ["Biggest move in the index"]
    assert "stock_points[]" in got.rejected


def test_a_driver_citing_an_invented_figure_is_dropped():
    p = _payload()
    got = validate_copy(
        {
            "drivers": [
                {"title": "Inflation cooled", "body": "PCE eased to 2.1%."},
                {"title": "Supply stays tight", "body": "Shortages persist."},
            ]
        },
        p,
    )
    assert [d["title"] for d in got.drivers] == ["Supply stays tight"]
    assert "drivers[]" in got.rejected


def test_malformed_response_yields_empty_copy_not_a_crash():
    """A model that returns the wrong shape must degrade to a data-only card,
    not 500 the share button."""
    p = _payload()
    got = validate_copy({"headline": None, "stock_points": "not a list", "drivers": "nope"}, p)
    assert got.headline == "" and got.stock_points == [] and got.drivers == []


def test_rejections_are_recorded_for_the_log():
    """A card missing its headline should be visible, not a mystery."""
    p = _payload()
    got = validate_copy({"headline": "Up 99.9% across the board"}, p)
    assert got.rejected == ["headline"]


def test_copy_serializes_to_plain_json():
    p = _payload()
    got = validate_copy({"headline": "Clean"}, p)
    json.loads(json.dumps(got.to_dict()))


# ── provenance, not arithmetic ──────────────────────────────────────────────


def test_figures_quoted_from_the_news_are_allowed():
    """Jimmy's own example copy says "biggest one-day gain since 2008" and
    "Azure revenue grew 43%". Both are correct, both come from articles we
    handed the model, neither is a number we computed. A guard that rejected
    them would fire on almost every well-written card — and a guard that cries
    wolf gets switched off."""
    p = _payload()
    news = [{"title": "Azure revenue grew 43% as cloud reaccelerated",
             "summary": "The biggest one-day gain since 2008."}]
    got = validate_copy(
        {"stock_points": ["Azure revenue grew 43% year over year",
                          "Biggest one-day gain since 2008"]},
        p,
        news=news,
    )
    assert len(got.stock_points) == 2
    assert got.rejected == []


def test_the_same_figures_are_rejected_without_the_news_behind_them():
    """Provenance is the whole test: 43% is fine when an article says it and a
    fabrication when nothing does."""
    p = _payload()
    got = validate_copy({"stock_points": ["Azure revenue grew 43% year over year"]}, p, news=None)
    assert got.stock_points == []
    assert "stock_points[]" in got.rejected


def test_allowed_set_is_the_union_of_both_sources():
    from app.services.card_copy import allowed_numbers

    p = _payload()
    both = allowed_numbers(p, news=[{"title": "up 43% since 2008"}])
    assert "15.51" in both   # ours
    assert "43" in both      # theirs
    assert "2008" in both
