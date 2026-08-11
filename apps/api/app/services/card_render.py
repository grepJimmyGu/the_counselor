"""Draw the daily share card as a PNG.

**Hybrid, after three image-model attempts.** Every generation produced the
right *look* and damaged the *data*: the Chinese run corrupted sector labels
(标普500 -> 板普, 道琼斯 -> 道搞金) so Healthcare displayed Utilities' figure;
the English run dropped seven of eight sector percentages and omitted the
compliance disclaimer entirely. Three runs, three different failures, all in
the same tabular section — and no single guard catches them, since a
number-only check passes the Chinese card and fails the English one.

So: **structure and data are drawn here; only ornament is generated.** Most of
what makes the reference feel like a notebook is structural anyway — modular
rounded cards, numbered badges, highlighter marks, tilted sticky notes with
tape. That vocabulary lives in `card_paper` and is deterministic. Generated
doodles composite on top, never underneath a number.

3:4 portrait per both prompts. Palette is Jimmy's throughout.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

from app.services.card_fonts import FontUnavailable, resolve_font
from app.services.card_paper import (
    ACCENT,
    CARD,
    GROUND,
    HIGHLIGHT,
    INK,
    INK_SOFT,
    RULE,
    STICKY,
    arrow,
    badge,
    card,
    date_chip,
    highlighter,
    paper_ground,
    sticky,
    tone,
    underline,
)

logger = logging.getLogger("livermore.card_render")

WIDTH, HEIGHT = 1080, 1440
MARGIN = 60
FOOTER_H = 104


def _font(lang: str, size: int, *, bold: bool = False):
    from PIL import ImageFont

    return ImageFont.truetype(resolve_font(lang, bold=bold), size)


def _wrap(draw, text: str, font, max_w: int) -> List[str]:
    """Greedy wrap that also breaks mid-run for CJK.

    Chinese has no spaces, so a space-only wrap emits one enormous line that
    leaves the canvas — invisible in every English test.
    """
    if not text:
        return []
    lines: List[str] = []
    cur = ""
    if " " in text.strip():
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
    else:
        for ch in text:
            if draw.textlength(cur + ch, font=font) <= max_w or not cur:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines


def render_card_png(card_data: Dict[str, Any]) -> bytes:
    """`card_to_dict(row)` -> PNG bytes.

    Raises `FontUnavailable` rather than drawing empty boxes: tofu passes any
    check that only asserts the PNG has bytes, and is obviously broken to the
    reader it was forwarded to.
    """
    from PIL import ImageDraw

    payload = card_data.get("payload") or {}
    copy = card_data.get("copy") or {}
    lang = card_data.get("lang") or "en"
    labels = payload.get("labels") or {}

    base = paper_ground(WIDTH, HEIGHT).convert("RGBA")
    d = ImageDraw.Draw(base)

    f_chip = _font(lang, 24, bold=True)
    f_micro = _font(lang, 21)
    f_small = _font(lang, 24)
    f_body = _font(lang, 27)
    f_head = _font(lang, 58, bold=True)
    f_sec = _font(lang, 25, bold=True)
    f_stat = _font(lang, 36, bold=True)
    f_big = _font(lang, 44, bold=True)
    f_badge = _font(lang, 22, bold=True)

    x, inner = MARGIN, WIDTH - MARGIN * 2
    y = MARGIN

    # Measure the blocks before drawing any, so leftover height can be shared
    # between the gaps rather than pooling in one.
    _rows = max(len(payload.get("winners") or []), len(payload.get("losers") or []), 1)
    _sector_h = 96 + _rows * 36
    _has_stock = bool(payload.get("stock"))
    _body = copy.get("takeaway_body") or ""
    _hl = copy.get("takeaway_highlight") or ""
    _take_lines = _wrap(d, _body, f_body, inner - 110)[:3] if _body else []
    _take_h = (108 + len(_take_lines) * 38) if (_body or _hl) else 0
    _fixed = 68 + 70 * len(_wrap(d, copy.get("headline") or "", f_head, inner - 30)[:2]) + 4 \
        + 37 * len(_wrap(d, copy.get("subtitle") or "", f_body, inner - 250)[:3]) + 16 \
        + 214 + _sector_h + (196 if _has_stock else 0) + _take_h
    _gaps = 3 + (1 if _has_stock else 0)
    _slack = max(0, (HEIGHT - MARGIN - FOOTER_H) - MARGIN - _fixed)
    GAP = 18 + min(34, _slack // max(_gaps, 1))

    # ── header: date chip, masthead beside it ───────────────────────────────
    right = date_chip(d, (x, y), payload.get("date_label", ""), f_chip)
    d.text((right + 20, y + 12), payload.get("masthead", ""), font=f_small, fill=INK_SOFT)
    y += 68

    # ── headline, marker swipe under the last line ──────────────────────────
    head_lines = _wrap(d, copy.get("headline") or "", f_head, inner - 30)[:2]
    for i, line in enumerate(head_lines):
        if i == len(head_lines) - 1:
            w = d.textlength(line, font=f_head)
            # Trailing ~55% of the line: a swipe over the phrase that lands,
            # not a bar under the sentence.
            start = x + int(w * 0.45)
            highlighter(d, (start - 6, y + int(f_head.size * 0.80), x + int(w) + 10, y + f_head.size + 8))
        d.text((x, y), line, font=f_head, fill=INK)
        y += 70
    y += 4

    for line in _wrap(d, copy.get("subtitle") or "", f_body, inner - 250)[:3]:
        d.text((x, y), line, font=f_body, fill=INK_SOFT)
        y += 37
    y += 16

    # ── (1) market performance ──────────────────────────────────────────────
    card_h = 214
    card(d, (x, y, x + inner, y + card_h))
    hx = badge(d, (x + 22, y + 18), 1, f_badge)
    d.text((hx, y + 24), labels.get("market_performance", "").upper(), font=f_sec, fill=ACCENT)
    ty = y + 76
    tile_w = (inner - 52) // 4
    for i, s in enumerate((payload.get("indices") or [])[:4]):
        tx = x + 26 + i * tile_w
        d.rounded_rectangle((tx, ty, tx + tile_w - 12, ty + 88), radius=12, outline=RULE, width=2)
        d.text((tx + 13, ty + 12), s.get("label", "")[:15], font=f_micro, fill=INK_SOFT)
        d.text((tx + 13, ty + 42), s.get("change", "—"), font=f_stat, fill=tone(s.get("direction")))
    ny = ty + 100
    for line in _wrap(d, copy.get("market_note") or "", f_small, inner - 60)[:1]:
        d.text((x + 26, ny), line, font=f_small, fill=INK_SOFT)
    y += card_h + GAP

    # ── (2) sector performance ──────────────────────────────────────────────
    # The section every generation broke. Drawn from the payload, so a label
    # can never detach from its figure.
    rows = max(len(payload.get("winners") or []), len(payload.get("losers") or []), 1)
    sec_h = 96 + rows * 36
    card(d, (x, y, x + inner, y + sec_h))
    hx = badge(d, (x + 22, y + 18), 2, f_badge)
    d.text((hx, y + 24), labels.get("sectors", "").upper(), font=f_sec, fill=ACCENT)
    col_w = (inner - 52) // 2
    for ci, key in enumerate(("losers", "winners")):
        cx = x + 26 + ci * col_w
        d.text((cx, y + 68), labels.get(key, "").upper(), font=f_micro, fill=INK_SOFT)
        ry = y + 98
        for s in (payload.get(key) or [])[:4]:
            d.text((cx, ry), s.get("label", ""), font=f_small, fill=INK)
            vw = d.textlength(s.get("value", ""), font=f_small)
            d.text((cx + col_w - 46 - vw, ry), s.get("value", ""), font=f_small, fill=tone(s.get("direction")))
            ry += 36
    y += sec_h + GAP

    floor = HEIGHT - MARGIN - FOOTER_H

    # ── (3) stock of the day + the money-flow sticky beside it ──────────────
    stock = payload.get("stock")
    block_h = 196
    if stock and y + block_h < floor - 180:
        left_w = int(inner * 0.5)
        card(d, (x, y, x + left_w, y + block_h))
        hx = badge(d, (x + 22, y + 18), 3, f_badge)
        d.text((hx, y + 24), labels.get("stock_of_day", "").upper(), font=f_sec, fill=ACCENT)
        d.text((x + 26, y + 72), stock.get("symbol", ""), font=f_stat, fill=INK)
        d.text((x + 26, y + 114), stock.get("change", ""), font=f_big, fill=tone(stock.get("direction")))
        for p in (copy.get("stock_points") or [])[:1]:
            for line in _wrap(d, p, f_micro, left_w - 54)[:1]:
                d.text((x + 26, y + 166), line, font=f_micro, fill=INK_SOFT)

        if payload.get("flow_from") and payload.get("flow_to"):
            sx = x + left_w + 22
            bx0, by0, bx1, _ = sticky(base, (sx, y, x + inner, y + block_h), tilt=-1.2)
            d = ImageDraw.Draw(base)
            mf = labels.get("money_flow", "")
            d.text((bx0, by0), mf, font=f_sec, fill=ACCENT)
            underline(d, bx0, by0 + 34, int(d.textlength(mf, font=f_sec)))
            fy = by0 + 50
            d.text((bx0, fy), payload["flow_from"], font=f_small, fill=INK)
            fw = d.textlength(payload["flow_from"], font=f_small)
            arrow(d, int(bx0 + fw + 12), int(fy + 14), w=34)
            d.text((bx0 + fw + 58, fy), payload["flow_to"], font=f_small, fill=INK)
            ny = fy + 40
            for line in _wrap(d, copy.get("money_flow_note") or "", f_micro, bx1 - bx0)[:3]:
                d.text((bx0, ny), line, font=f_micro, fill=INK)
                ny += 27
        y += block_h + GAP

    # ── (4) the conclusion, band reserved so it can never be squeezed out ───
    body = copy.get("takeaway_body") or ""
    hl = copy.get("takeaway_highlight") or ""
    if body or hl:
        lines = _wrap(d, body, f_body, inner - 110)[:3]
        take_h = 108 + len(lines) * 38
        top = min(y, floor - take_h)
        bx0, by0, bx1, _ = sticky(base, (x, top, x + inner, top + take_h), tilt=0.6)
        d = ImageDraw.Draw(base)
        hx = badge(d, (bx0, by0), 4, f_badge)
        d.text((hx, by0 + 6), labels.get("takeaway", "").upper(), font=f_sec, fill=ACCENT)
        ty = by0 + 50
        for line in lines:
            d.text((bx0, ty), line, font=f_body, fill=INK)
            ty += 38
        if hl:
            w = d.textlength(hl, font=f_small)
            highlighter(d, (bx0 - 4, ty + 2, bx0 + int(w) + 12, ty + f_small.size + 12), color=(252, 243, 206))
            d.text((bx0, ty + 4), hl, font=f_small, fill=ACCENT)

    # ── footer ──────────────────────────────────────────────────────────────
    fy = HEIGHT - MARGIN - 74
    d.line([(x, fy - 18), (x + inner, fy - 18)], fill=RULE, width=2)
    d.text((x, fy), labels.get("source", ""), font=f_micro, fill=INK_SOFT)
    ex = labels.get("explore", "")
    d.text((x, fy + 30), ex, font=f_micro, fill=ACCENT)
    ew = d.textlength(ex, font=f_micro)
    arrow(d, int(x + ew + 12), int(fy + 40), w=26, color=ACCENT, width=2)
    url = payload.get("source_url", "")
    d.text((x + ew + 48, fy + 30), url, font=f_micro, fill=ACCENT)
    underline(d, int(x + ew + 48), int(fy + 54), int(d.textlength(url, font=f_micro)), width=2)
    # The compliance line. The image model dropped it entirely on the English
    # run; here it is not optional.
    d.text((x, fy + 64), payload.get("disclaimer", ""), font=_font(lang, 18), fill=INK_SOFT)

    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


__all__ = ["render_card_png", "FontUnavailable", "WIDTH", "HEIGHT", "HIGHLIGHT", "GROUND", "CARD"]
