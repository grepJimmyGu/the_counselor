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
    from app.services.card_paper import STICKY

    # Tolerance, not equality: the note is drawn on a rotated layer, so its
    # edges are antialiased and an exact-colour count undercounts. Nothing
    # else on the card is this warm and this saturated.
    img = _open(render_card_png(_card())).convert("RGB")
    hits = sum(
        1 for r, g, b in img.getdata()
        if abs(r - STICKY[0]) < 12 and abs(g - STICKY[1]) < 12 and abs(b - STICKY[2]) < 12
    )
    assert hits > 20_000, "the takeaway block is missing"


def test_content_does_not_run_past_the_canvas():
    """The first version overlapped the footer and ran off the bottom — the
    sections collided rather than the page growing, so nothing errored."""
    img = _open(render_card_png(_card())).convert("RGB")
    # Ink in the bleed zone means overflow. Compared by darkness rather than
    # against one reference pixel — the ground carries a deterministic grain
    # now, so exact equality would fail on texture, not on layout.
    bottom = [img.getpixel((x, HEIGHT - 3)) for x in range(0, WIDTH, 7)]
    assert all(sum(px) > 540 for px in bottom), "content reaches the bottom edge"


def test_a_long_headline_cannot_push_the_footer_off():
    long_copy = dict(COPY, headline="A very long headline " * 12)
    img = _open(render_card_png(_card(EN, long_copy))).convert("RGB")
    bottom = [img.getpixel((x, HEIGHT - 3)) for x in range(0, WIDTH, 7)]
    assert all(sum(px) > 540 for px in bottom)


def test_chinese_wraps_instead_of_running_off_the_edge():
    """CJK has no spaces, so a space-only wrap emits one enormous line that
    leaves the canvas — invisible in every English test."""
    zh = dict(COPY, headline="市场情绪彻底反转" * 8)
    img = _open(render_card_png(_card(ZH, zh))).convert("RGB")
    right = [img.getpixel((WIDTH - 3, y)) for y in range(0, HEIGHT, 7)]
    assert all(sum(px) > 540 for px in right), "text runs past the right edge"


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


@pytest.mark.parametrize("lang", [EN, ZH])
def test_bold_actually_draws_bold(lang):
    """A `.ttc` holds several faces in one file and `truetype(path, size)`
    silently takes index 0 — Regular. So `bold=True` returned Regular for every
    headline on every card rendered before this was pinned, and nothing
    errored: the text just quietly wasn't bold.

    Asserted on ink rather than on the face name, because that's the thing a
    reader can see, and it holds whether the weight comes from a second face
    inside a collection or from a separately bundled bold file.
    """
    from PIL import Image, ImageDraw

    from app.services.card_render import _font

    try:
        regular, bold = _font(lang, 58), _font(lang, 58, bold=True)
    except FontUnavailable:
        pytest.skip(f"no font for {lang} on this machine")

    word = "MARKET" if lang == EN else "大盘表现"
    ink = []
    for font in (regular, bold):
        im = Image.new("L", (760, 130), 255)
        ImageDraw.Draw(im).text((10, 10), word, font=font, fill=0)
        ink.append(sum(1 for v in im.getdata() if v < 128))
    assert ink[1] > ink[0] * 1.05, f"bold is not heavier than regular ({ink})"


# ── ornament ────────────────────────────────────────────────────────────────


def test_a_missing_ornament_set_does_not_break_the_card(monkeypatch):
    """Ornament is the one part of this card that is purely decoration, so a
    checkout that has never run the asset build must still render. The figures
    are the card's reason to exist; the doodles are not."""
    from app.services import card_ornaments

    monkeypatch.setattr(card_ornaments, "ORNAMENT_DIR", card_ornaments.ORNAMENT_DIR / "__absent__")
    monkeypatch.setattr(card_ornaments, "_cache", {})
    img = _open(render_card_png(_card()))
    assert (img.width, img.height) == (WIDTH, HEIGHT)


def test_tape_false_leaves_the_corner_to_the_generated_strip():
    """Both notes wore two pieces of tape the first time the generated strip
    was composited — `sticky()` draws its own, and nothing said not to."""
    from PIL import Image

    from app.services.card_paper import sticky

    counts = []
    for tape in (True, False):
        im = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
        sticky(im, (40, 60, 360, 260), tape=tape)
        # Above the note's top edge, only the tape can put pixels — save for a
        # few from the tilt, hence a ratio rather than zero.
        band = im.crop((40, 18, 360, 52))
        counts.append(sum(1 for p in band.getdata() if p[3] > 0))
    assert counts[0] > 200, "the drawn tape is missing"
    assert counts[1] < counts[0] / 4, "tape=False still drew a strip"


def test_latin_and_cjk_resolve_to_different_faces():
    """A Latin font asked to draw 科技 silently emits boxes rather than
    failing, so the two must not collapse to one path."""
    try:
        assert resolve_font(EN) != resolve_font(ZH)
    except FontUnavailable:
        pytest.skip("no CJK font on this machine")
