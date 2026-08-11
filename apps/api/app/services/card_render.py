"""Draw the daily share card as a PNG.

Pillow rather than an SVG rasteriser, and rather than an image model.

*Not an image model*: it cannot render `+15.51%` reliably, and a wrong figure
on a card built to be forwarded is the worst failure this feature has.

*Not cairosvg*: it needs system Cairo libraries on the Railway image, which is
deployment risk for no gain here — the layout is fixed and I control every
coordinate, so SVG's main advantage (declarative layout) buys little.

*Not Playwright*: perfect fidelity, but a ~400MB browser on a container whose
memory is already the binding cost constraint.

3:4 portrait per both prompts, sized for a phone screenshot. Every colour is
from Jimmy's spec. The illustration layer (arrows, sticky notes, doodles) is
deliberately absent — those are static assets to be generated once, and a card
with clean typography and no doodles reads as restrained, while a card with
half-placed doodles reads as broken.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.card_fonts import FontUnavailable, resolve_font

logger = logging.getLogger("livermore.card_render")

# 3:4, sized so text stays crisp when a phone downscales it.
WIDTH, HEIGHT = 1080, 1440
MARGIN = 72
# The footer band is reserved before anything flows. Without this the stock,
# score and takeaway blocks ran straight through the attribution and off the
# canvas — the sections overlapped rather than the page growing, so nothing in
# the code noticed. A section that doesn't fit is DROPPED, matching the rest of
# the card: no source, or no room, means the module collapses rather than
# rendering on top of another.
#
# Sized to what the footer actually draws — rule, source line, link line,
# disclaimer — not a round number. At 150 it reserved 50px nothing used, and
# the takeaway block (the spec's headline conclusion) was dropped to protect
# empty space.
FOOTER_H = 112

# Jimmy's palette, both prompts.
INK = (17, 17, 17)
INK_SOFT = (102, 102, 102)
RULE = (234, 234, 234)
GROUND = (243, 236, 224)  # warm oatmeal — clearly not white, per the spec
ACCENT = (139, 69, 19)  # #8B4513
HIGHLIGHT = (244, 211, 94)  # #F4D35E
UP = (58, 122, 84)  # muted green
DOWN = (176, 74, 48)  # muted red-orange


def _font(lang: str, size: int, *, bold: bool = False):
    from PIL import ImageFont

    return ImageFont.truetype(resolve_font(lang, bold=bold), size)


def _arrow(d, x: int, y: int, w: int = 46) -> None:
    """Draw the flow arrow rather than typing one.

    `→` (U+2192) is absent from Helvetica and rendered as an empty box on the
    ENGLISH card — the same missing-glyph failure as CJK tofu, and a reminder
    that "it's only ASCII-ish" is not a font guarantee. Two lines always work.
    """
    mid = y + 16
    d.line([(x, mid), (x + w, mid)], fill=INK_SOFT, width=3)
    d.line([(x + w - 14, mid - 9), (x + w, mid)], fill=INK_SOFT, width=3)
    d.line([(x + w - 14, mid + 9), (x + w, mid)], fill=INK_SOFT, width=3)


def _tone(direction: Optional[str]) -> Tuple[int, int, int]:
    """`None` means the row must not be coloured — VIX is a level, and "VIX
    down" is not good news the way "S&P up" is."""
    if direction == "up":
        return UP
    if direction == "down":
        return DOWN
    return INK


def _wrap(draw, text: str, font, max_w: int) -> List[str]:
    """Greedy wrap that also breaks mid-run for CJK.

    Chinese has no spaces, so a space-only wrap emits one enormous line that
    runs off the canvas — invisible in an English test and obvious to the
    first Chinese reader.
    """
    if not text:
        return []
    has_spaces = " " in text.strip()
    lines: List[str] = []
    if has_spaces:
        cur = ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    else:
        cur = ""
        for ch in text:
            if draw.textlength(cur + ch, font=font) <= max_w or not cur:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    return lines


def render_card_png(card: Dict[str, Any]) -> bytes:
    """`card_to_dict(row)` -> PNG bytes.

    Raises `FontUnavailable` rather than drawing empty boxes. A tofu card looks
    fine to any check that only asserts the PNG has bytes, and broken to the
    person it was forwarded to.
    """
    from PIL import Image, ImageDraw

    payload = card.get("payload") or {}
    copy = card.get("copy") or {}
    lang = card.get("lang") or "en"
    labels = payload.get("labels") or {}

    img = Image.new("RGB", (WIDTH, HEIGHT), GROUND)
    d = ImageDraw.Draw(img)

    f_micro = _font(lang, 21)
    f_small = _font(lang, 24)
    f_body = _font(lang, 27)
    f_stat = _font(lang, 38, bold=True)
    f_head = _font(lang, 56, bold=True)
    f_label = _font(lang, 22, bold=True)

    x = MARGIN
    inner = WIDTH - MARGIN * 2
    y = MARGIN

    # ── header: date above the masthead (the byline pattern) ────────────────
    d.text((x, y), payload.get("date_label", ""), font=f_label, fill=ACCENT)
    y += 30
    d.text((x, y), payload.get("masthead", ""), font=f_micro, fill=INK_SOFT)
    y += 44

    # ── headline ────────────────────────────────────────────────────────────
    headline = copy.get("headline") or ""
    if headline:
        for line in _wrap(d, headline, f_head, inner)[:2]:
            d.text((x, y), line, font=f_head, fill=INK)
            y += 66
        y += 6

    subtitle = copy.get("subtitle") or ""
    if subtitle:
        for line in _wrap(d, subtitle, f_body, inner)[:2]:
            d.text((x, y), line, font=f_body, fill=INK_SOFT)
            y += 36
        y += 8

    d.line([(x, y), (x + inner, y)], fill=RULE, width=2)
    y += 24

    # ── the tape: four index tiles, 2x2 ─────────────────────────────────────
    d.text((x, y), labels.get("market_performance", ""), font=f_label, fill=ACCENT)
    y += 32
    col_w = inner // 2
    for i, stat in enumerate((payload.get("indices") or [])[:4]):
        cx = x + (i % 2) * col_w
        cy = y + (i // 2) * 100
        d.text((cx, cy), stat.get("label", ""), font=f_small, fill=INK_SOFT)
        d.text((cx, cy + 28), stat.get("value", "—"), font=f_stat, fill=INK)
        d.text(
            (cx, cy + 70),
            stat.get("change", ""),
            font=f_small,
            fill=_tone(stat.get("direction")),
        )
    y += 200 + 4

    d.line([(x, y), (x + inner, y)], fill=RULE, width=2)
    y += 24

    # ── sectors, two columns ────────────────────────────────────────────────
    d.text((x, y), labels.get("sectors", ""), font=f_label, fill=ACCENT)
    y += 32
    for col, (key, heading) in enumerate(
        (("winners", labels.get("winners", "")), ("losers", labels.get("losers", "")))
    ):
        cx = x + col * col_w
        cy = y
        d.text((cx, cy), heading, font=f_micro, fill=INK_SOFT)
        cy += 28
        for stat in (payload.get(key) or [])[:4]:
            d.text((cx, cy), stat.get("label", ""), font=f_small, fill=INK)
            d.text(
                (cx + col_w - 130, cy),
                stat.get("value", ""),
                font=f_small,
                fill=_tone(stat.get("direction")),
            )
            cy += 34
    y += 28 + 4 * 34 + 10

    # ── money flow ──────────────────────────────────────────────────────────
    if payload.get("flow_from") and payload.get("flow_to"):
        d.text((x, y), labels.get("money_flow", ""), font=f_label, fill=ACCENT)
        y += 30
        fw = d.textlength(payload["flow_from"], font=f_body)
        d.text((x, y), payload["flow_from"], font=f_body, fill=INK)
        _arrow(d, int(x + fw + 20), y)
        d.text((x + fw + 86, y), payload["flow_to"], font=f_body, fill=INK)
        y += 38
    note = copy.get("money_flow_note") or ""
    if note:
        for line in _wrap(d, note, f_small, inner)[:1]:
            d.text((x, y), line, font=f_small, fill=INK_SOFT)
            y += 30
    y += 6

    floor = HEIGHT - MARGIN - FOOTER_H

    # Reserve the conclusion band FIRST. Both prompts call this the most
    # important module on the card ("全图最重要的结论区域"), so it must not be
    # what yields when space runs short. Flowing first-come-first-served
    # dropped it three renders running while the stock bullets above it kept
    # their room — the layout was deciding priority by accident.
    body = copy.get("takeaway_body") or ""
    highlight = copy.get("takeaway_highlight") or ""
    take_lines = _wrap(d, body, f_body, inner - 48)[:2] if body else []
    take_h = (84 + len(take_lines) * 38) if (body or highlight) else 0
    mid_floor = floor - take_h - (16 if take_h else 0)

    # ── stock of the day ────────────────────────────────────────────────────
    stock = payload.get("stock")
    if stock and y + 170 < mid_floor:
        d.line([(x, y), (x + inner, y)], fill=RULE, width=2)
        y += 20
        d.text((x, y), labels.get("stock_of_day", ""), font=f_label, fill=ACCENT)
        y += 32
        d.text((x, y), stock.get("symbol", ""), font=f_stat, fill=INK)
        d.text(
            (x + 220, y + 8),
            stock.get("change", ""),
            font=f_body,
            fill=_tone(stock.get("direction")),
        )
        y += 50
        for point in (copy.get("stock_points") or [])[:3]:
            if y + 30 > mid_floor:
                break
            for line in _wrap(d, f"· {point}", f_small, inner)[:1]:
                d.text((x, y), line, font=f_small, fill=INK)
                y += 30
        # The three-dimensional score, when we have it. Absent rather than
        # zeroed — a score of 0 reads as a verdict, not as missing data.
        if stock.get("score_health") is not None and y + 92 < mid_floor:
            y += 8
            trio = [
                (labels.get("score_health", ""), stock.get("score_health")),
                (labels.get("score_valuation", ""), stock.get("score_valuation")),
                (labels.get("score_trend", ""), stock.get("score_trend")),
            ]
            for i, (lab, val) in enumerate(trio):
                bx = x + i * (inner // 3)
                d.text((bx, y), lab, font=f_micro, fill=INK_SOFT)
                d.text((bx, y + 24), str(val), font=f_stat, fill=ACCENT)
            y += 74
        y += 10

    # ── takeaway, on the highlight block ────────────────────────────────────
    body = copy.get("takeaway_body") or ""
    highlight = copy.get("takeaway_highlight") or ""
    if (body or highlight) and y + 120 < floor:
        block_top = y
        lines = _wrap(d, body, f_body, inner - 48)[:3]
        block_h = min(84 + len(lines) * 38, floor - block_top)
        d.rectangle([(x, block_top), (x + inner, block_top + block_h)], fill=HIGHLIGHT)
        ty = block_top + 18
        d.text((x + 24, ty), labels.get("takeaway", ""), font=f_label, fill=ACCENT)
        ty += 32
        for line in lines:
            d.text((x + 24, ty), line, font=f_body, fill=INK)
            ty += 38
        if highlight:
            d.text((x + 24, ty), highlight, font=f_small, fill=ACCENT)
        y = block_top + block_h + 16

    # ── attribution + disclaimer, pinned to the bottom ──────────────────────
    # Deliberately understated: a source line at the foot of a research
    # notebook, never a CTA. Both prompts are explicit about this.
    fy = HEIGHT - MARGIN - 76
    d.line([(x, fy - 24), (x + inner, fy - 24)], fill=RULE, width=2)
    d.text((x, fy), labels.get("source", ""), font=f_small, fill=INK_SOFT)
    explore = labels.get("explore", "")
    d.text((x, fy + 32), explore, font=f_small, fill=ACCENT)
    ex_w = d.textlength(explore, font=f_small)
    _arrow(d, int(x + ex_w + 14), fy + 30, w=30)
    d.text(
        (x + ex_w + 58, fy + 32),
        payload.get("source_url", ""),
        font=f_small,
        fill=ACCENT,
    )
    d.text(
        (x, HEIGHT - MARGIN + 4),
        payload.get("disclaimer", ""),
        font=f_micro,
        fill=INK_SOFT,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


__all__ = ["render_card_png", "FontUnavailable", "WIDTH", "HEIGHT"]
