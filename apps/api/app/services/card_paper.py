"""The notebook grammar — the drawing vocabulary the card is built from.

Everything here is deterministic. The design language in Jimmy's reference is
mostly *structure*, not illustration: modular rounded cards, numbered badges,
highlighter marks behind key phrases, tilted sticky notes with tape. Three
image-model attempts corrupted the data while producing that structure; these
primitives produce it with numbers that cannot be wrong.

Generated doodles composite on top of this, not instead of it.

Seeded RNG on purpose: the paper grain and the sticky-note tilt must be
identical every render, or the same card regenerated after a redeploy would
differ from the one someone already shared.
"""
from __future__ import annotations

import random
from typing import Optional, Tuple

# Jimmy's palette.
INK = (17, 17, 17)
INK_SOFT = (102, 102, 102)
RULE = (226, 222, 214)
GROUND = (245, 238, 224)
CARD = (250, 245, 234)
ACCENT = (139, 69, 19)
HIGHLIGHT = (244, 211, 94)
STICKY = (250, 227, 141)
UP = (46, 125, 80)
DOWN = (192, 76, 42)

_SEED = 20260811


def paper_ground(width: int, height: int):
    """Warm oatmeal with a faint, DETERMINISTIC grain.

    Flat fill reads as a slide; grain reads as paper. Kept very low contrast —
    the spec says texture is acceptable but must stay clean.
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), GROUND)
    d = ImageDraw.Draw(img)
    rng = random.Random(_SEED)
    for _ in range(int(width * height / 900)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        shade = rng.choice(((238, 231, 216), (250, 244, 232)))
        d.point((x, y), fill=shade)
    return img


def card(d, box: Tuple[int, int, int, int], *, radius: int = 22, fill=CARD, border=RULE) -> None:
    """A modular container: rounded, hairline border, a whisper of shadow.

    The single biggest structural difference between a report and a notebook —
    the reference groups everything into these, and flat text on a background
    reads as a slide however good the type is.
    """
    x0, y0, x1, y1 = box
    # Shadow first, offset and barely darker than the ground.
    d.rounded_rectangle((x0 + 2, y0 + 3, x1 + 2, y1 + 3), radius=radius, fill=(233, 226, 211))
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=border, width=2)


def badge(d, xy: Tuple[int, int], n: int, font, *, r: int = 17) -> int:
    """A numbered section chip. Returns the x to continue the heading from.

    Every numbered section gets one. The image model numbered exactly one of
    four sections when asked; here it is not optional.
    """
    x, y = xy
    d.ellipse((x, y, x + r * 2, y + r * 2), outline=ACCENT, width=2)
    label = str(n)
    w = d.textlength(label, font=font)
    d.text((x + r - w / 2, y + r - font.size * 0.62), label, font=font, fill=ACCENT)
    return x + r * 2 + 14


def highlighter(d, box: Tuple[int, int, int, int], *, color=HIGHLIGHT) -> None:
    """A marker swipe behind text. Drawn BEFORE the text, with soft ends so it
    reads as a pen stroke rather than a filled rectangle."""
    x0, y0, x1, y1 = box
    h = y1 - y0
    d.rounded_rectangle((x0, y0, x1, y1), radius=int(h * 0.35), fill=color)


def underline(d, x: int, y: int, w: int, *, color=ACCENT, width: int = 3) -> None:
    """A hand-drawn-feeling rule: two slightly offset strokes, never one clean
    line, which is what makes it read as pen rather than border."""
    d.line([(x, y), (x + w, y + 1)], fill=color, width=width)
    d.line([(x + 3, y + 4), (x + w - 5, y + 4)], fill=color, width=1)


def arrow(d, x: int, y: int, w: int = 44, *, color=INK_SOFT, width: int = 3) -> None:
    """Drawn, never typed. U+2192 is absent from many faces and renders as an
    empty box — it did, on the English card."""
    d.line([(x, y), (x + w, y)], fill=color, width=width)
    d.line([(x + w - 13, y - 8), (x + w, y)], fill=color, width=width)
    d.line([(x + w - 13, y + 8), (x + w, y)], fill=color, width=width)


def sticky(img, box: Tuple[int, int, int, int], *, tilt: float = -1.4, fill=STICKY, tape: bool = True):
    """A tilted sticky note with a tape strip, composited onto `img`.

    Rendered on its own layer and rotated, because a note at exactly 0 degrees
    reads as a yellow div. The tilt is small and fixed — enough to feel placed
    by hand, not enough to look broken.

    `tape=False` suppresses the drawn strip for callers that composite the
    generated one over the same corner — otherwise both land and the note wears
    two pieces of tape.
    """
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pad = 26
    layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((pad + 3, pad + 4, pad + w + 3, pad + h + 4), radius=6, fill=(226, 214, 186, 150))
    ld.rounded_rectangle((pad, pad, pad + w, pad + h), radius=6, fill=fill + (255,))
    # Tape strip over the top-left corner.
    if tape:
        ld.polygon(
            [(pad + 18, pad - 12), (pad + 96, pad - 20), (pad + 100, pad + 8), (pad + 22, pad + 16)],
            fill=(236, 219, 190, 205),
        )
    layer = layer.rotate(tilt, resample=Image.BICUBIC, expand=False)
    img.alpha_composite(layer, (x0 - pad, y0 - pad))
    return (x0 + 22, y0 + 20, x1 - 22, y1 - 18)  # inner text box


def date_chip(d, xy: Tuple[int, int], text: str, font, *, pad_x: int = 16, pad_y: int = 8) -> int:
    """The reference puts the date in a filled chip, not loose text. Returns
    the right edge so the masthead can sit beside it."""
    x, y = xy
    w = d.textlength(text, font=font)
    box = (x, y, x + w + pad_x * 2, y + font.size + pad_y * 2)
    d.rounded_rectangle(box, radius=14, fill=ACCENT)
    d.text((x + pad_x, y + pad_y - 2), text, font=font, fill=(252, 249, 242))
    return int(box[2])


def tone(direction: Optional[str]):
    """`None` means DO NOT COLOUR — VIX is a level, and "VIX down" is not good
    news the way "S&P up" is."""
    if direction == "up":
        return UP
    if direction == "down":
        return DOWN
    return INK
