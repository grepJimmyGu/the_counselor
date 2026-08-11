"""Rendering the share card to a PNG.

Assertions are about what a READER would see, not that bytes came back. A card
of empty boxes, a card missing its conclusion, and a card whose sections
overlap all produce a perfectly valid PNG — every bug found while building this
was invisible to "did it return an image".
"""
from __future__ import annotations

import io

import pytest

from app.services import card_fonts
from app.services.card_fonts import FontUnavailable, can_render, resolve_font
from app.services.card_labels import EN, ZH
from app.services.card_render import HEIGHT, WIDTH, render_card_png
from app.services.daily_brief_service import (
    BriefMover,
    BriefQuote,
    BriefSector,
    DailyBrief,
)
from app.services.daily_card_service import build_card_payload
from app.services.evaluation_scoring import ThreeDimensionalScore

SCORE = ThreeDimensionalScore(health=92, valuation=78, trend=90, final=87, label="Attractive")

COPY = {
    "headline": "One earnings report reset the whole mood",
    "subtitle": "Growth carried the tape while defensives were sold.",
    "money_flow_note": "Money left defensive names for technology.",
    "stock_points": ["Biggest single-day move", "Cloud growth reaccelerated"],
    "takeaway_body": "Software pulled money out of defensives and back into growth.",
    "takeaway_highlight": "Confidence is coming back.",
}


def _brief() -> DailyBrief:
    b = DailyBrief(as_of="2026-07-31T21:00:00")
    b.indices = [
        BriefQuote("^DJI", "Dow Jones", 44_500.12, 1.19),
        BriefQuote("^GSPC", "S&P 500", 7_757.64, 1.66),
        BriefQuote("^IXIC", "NASDAQ Composite", 26_690.62, 2.78),
    ]
    b.vix = BriefQuote("^VIX", "VIX", 14.9, -6.83)
    b.sectors = [
        BriefSector("Technology", 5.5, 0.19),
        BriefSector("Industrials", 1.0, 0.08),
        BriefSector("Communication", -2.7, -0.14),
    ]
    b.flow_into = BriefSector("Technology", 5.5, 0.19)
    b.flow_out_of = BriefSector("Communication", -2.7, -0.14)
    b.unusual = BriefMover("MSFT", "Microsoft", 15.51)
    return b


def _card(lang=EN, copy=None):
    return {
        "payload": build_card_payload(_brief(), lang=lang, score=SCORE).to_dict(),
        "copy": COPY if copy is None else copy,
        "lang": lang,
    }


def _open(png: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(png))


# ── shape ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lang", [EN, ZH])
def test_renders_at_the_three_by_four_the_prompts_specify(lang):
    img = _open(render_card_png(_card(lang)))
    assert (img.width, img.height) == (WIDTH, HEIGHT)
    assert round(img.height / img.width, 3) == 1.333


def test_ground_is_warm_beige_not_white():
    """Both prompts are explicit: clearly visible beige, not near-white and not
    grey-white. A corner pixel is the cheapest way to pin it."""
    img = _open(render_card_png(_card())).convert("RGB")
    r, g, b = img.getpixel((4, 4))
    assert (r, g, b) != (255, 255, 255)
    assert r > b, "warm means red channel above blue"
    assert r - b >= 12, "the warmth must be visible, not a tint"


# ── the failures that a byte-count check misses ─────────────────────────────


def test_the_conclusion_block_always_renders():
    """The spec calls this the most important module on the card. It was
    dropped three renders running because the layout flowed first-come-first-
    served and the sections above it took the room. Its band is now reserved
    before anything else flows.

    Detected by the highlight colour: nothing else on the card uses it.
    """
    from app.services.card_render import HIGHLIGHT

    img = _open(render_card_png(_card())).convert("RGB")
    hits = sum(1 for px in img.getdata() if px == HIGHLIGHT)
    assert hits > 20_000, "the takeaway block is missing"


def test_content_does_not_run_past_the_canvas():
    """The first version overlapped the footer and ran off the bottom — the
    sections collided rather than the page growing, so nothing errored."""
    img = _open(render_card_png(_card())).convert("RGB")
    # The last few rows must be clean ground; ink there means overflow.
    bottom = [img.getpixel((x, HEIGHT - 3)) for x in range(0, WIDTH, 7)]
    assert all(px == img.getpixel((4, 4)) for px in bottom)


def test_a_long_headline_cannot_push_the_footer_off():
    long_copy = dict(COPY, headline="A very long headline " * 12)
    img = _open(render_card_png(_card(EN, long_copy))).convert("RGB")
    bottom = [img.getpixel((x, HEIGHT - 3)) for x in range(0, WIDTH, 7)]
    assert all(px == img.getpixel((4, 4)) for px in bottom)


def test_chinese_wraps_instead_of_running_off_the_edge():
    """CJK has no spaces, so a space-only wrap emits one enormous line that
    leaves the canvas — invisible in every English test."""
    zh = dict(COPY, headline="市场情绪彻底反转" * 8)
    img = _open(render_card_png(_card(ZH, zh))).convert("RGB")
    right = [img.getpixel((WIDTH - 3, y)) for y in range(0, HEIGHT, 7)]
    assert all(px == img.getpixel((4, 4)) for px in right)


def test_a_data_only_card_still_renders():
    """LLM off or failed: no prose at all. The figures are the card's reason to
    exist, so it must still draw."""
    img = _open(render_card_png(_card(EN, {})))
    assert (img.width, img.height) == (WIDTH, HEIGHT)


# ── fonts ───────────────────────────────────────────────────────────────────


def test_missing_cjk_font_refuses_rather_than_drawing_tofu(monkeypatch):
    """Tofu passes every check that only asserts the PNG has bytes, and is
    obviously broken to the reader it was forwarded to."""
    monkeypatch.setattr(card_fonts, "_DEV_CJK", ())
    monkeypatch.setattr(card_fonts, "FONT_DIR", card_fonts.FONT_DIR / "__absent__")
    with pytest.raises(FontUnavailable):
        resolve_font(ZH)


def test_can_render_lets_the_button_ask_before_offering_a_language(monkeypatch):
    assert can_render(EN) in (True, False)
    monkeypatch.setattr(card_fonts, "_DEV_CJK", ())
    monkeypatch.setattr(card_fonts, "FONT_DIR", card_fonts.FONT_DIR / "__absent__")
    assert can_render(ZH) is False


def test_latin_and_cjk_resolve_to_different_faces():
    """A Latin font asked to draw 科技 silently emits boxes rather than
    failing, so the two must not collapse to one path."""
    try:
        assert resolve_font(EN) != resolve_font(ZH)
    except FontUnavailable:
        pytest.skip("no CJK font on this machine")
