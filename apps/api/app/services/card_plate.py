"""The generated layer: ornament with no words in it.

Jimmy's rule, and it's the right one — **separate image generation from word
generation**. Five image-model runs damaged the data every time, differently:
Chinese characters rendered as plausible non-characters (标普500 -> 桁普500,
道琼斯 -> 道珉斯), the Nasdaq shown at VIX's figure, eight sector percentages
dropped, the URL emitted as `llvermoralpha.com`, the weekday wrong.

The cause is what the model is doing: it draws glyph *shapes it has seen*, not
text it looks up. Fifty-two Latin letterforms it can manage; thousands of dense
CJK characters at 20px it cannot, and it has no concept of a wrong character,
so nothing errors.

So we stop asking it for a card and ask it for a **plate**: ground texture,
one corner illustration, sticky-note and tape shapes, and empty space where
every word will go. The renderer composites the words on top.

**Generated once, not daily.** The ornament shouldn't drift between days, and
regenerating it per card would reintroduce the variance we just removed.
"""
from __future__ import annotations

from typing import Dict

# Zones the renderer owns. The plate must leave these clear — the prompt states
# them in words because the model can't be handed coordinates.
PLATE_W, PLATE_H = 1080, 1440

PLATE_PROMPT = """Design a BACKGROUND PLATE for a Xiaohongshu-style financial knowledge card.

THIS IS NOT A FINISHED CARD. It is the decorative layer only. Text will be
printed on top of it afterwards by a separate program.

ABSOLUTE REQUIREMENT: **Do not draw any text, letters, numbers, words,
characters, labels, captions or symbols that resemble writing.** No English, no
Chinese, no numerals, no lorem ipsum, no fake handwriting, no squiggles that
imitate a line of text. Any mark that looks like writing ruins the plate. If
you are tempted to label something, leave it blank.

CANVAS: 3:4 vertical, 1080 x 1440, high resolution.

BACKGROUND: a light warm cream paper, around #FAF6EC. Clearly warm, clearly
not pure white, but light and airy rather than tan or kraft. Very subtle paper
grain. No gradients.

WHAT TO DRAW:

1. A hand-drawn line illustration in the TOP RIGHT corner only, occupying
   roughly a 300x300 area: circular arrows suggesting money rotating between
   places, drawn in simple black ink line-art, notebook-doodle style. Cute but
   restrained. No text anywhere in or near it.

2. Two warm-yellow sticky-note rectangles (around #F4D35E), slightly rotated by
   1-2 degrees, with a small strip of translucent washi tape across one corner
   of each. One in the middle-right area, one in the lower area. LEAVE THEM
   COMPLETELY BLANK inside - no writing of any kind.

3. Four or five tiny scattered ink doodles in the margins: a small star, a
   lightbulb, a magnifying glass, a coffee cup, a paper aeroplane. Each no
   larger than 60px. Placed in the outer margins only, never in the middle
   third of the page.

WHAT TO LEAVE EMPTY:

* The top-left quarter: a headline goes there.
* The entire central band: two large data tables go there. Keep it clean paper,
  no ornament, no lines, no boxes.
* The bottom 120px: a footer goes there.

STYLE: simple black line drawings, hand-drawn notebook doodles, financial
research-journal aesthetic. Warm, muted, restrained.

DO NOT INCLUDE: any text or characters; company logos; AI robots; glowing
chips; candlestick charts; gradients; 3D icons; neon; tech blue; photographic
elements; borders around the whole page.
"""


def plate_request(model: str = "gpt-image-1") -> Dict:
    """The image-API body for the plate. One call, reused forever."""
    return {
        "model": model,
        "prompt": PLATE_PROMPT,
        "size": "1024x1536",
        "quality": "high",
        "n": 1,
    }


# The plate is never composited whole — `scripts/build_card_ornaments.py` cuts
# it into `app/assets/ornaments/`, and `card_ornaments.place()` positions each
# piece. A whole plate would decide where things sit, and that is layout: the
# takeaway note has to land under the takeaway text, not wherever the model put
# a rectangle.
#
# The generated source is committed alongside the cuts. Re-running this prompt
# returns a *different* drawing, so the source is the only way to re-cut the
# ones we have.
PLATE_PATH = "app/assets/plates/plate.png"

__all__ = ["PLATE_PROMPT", "plate_request", "PLATE_PATH", "PLATE_W", "PLATE_H"]
