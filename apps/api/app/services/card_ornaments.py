"""Generated ornament, placed by us.

The split Jimmy called: **the model draws pixels, the renderer draws words.**
The model is good at a hand-drawn dollar mark and hopeless at a sector label,
so it gets the doodles and nothing else — see `card_plate.py` for the prompt
and the five failed card generations that motivated it.

But a whole generated plate would still decide *where* things sit, and that is
layout. The takeaway note has to land under the takeaway text. So the plate is
cut into separate assets (`scripts/build_card_ornaments.py`) and placed here,
at coordinates this module owns.

**Every slot is one the layout already reserves.** The corner mark sits in the
header band beside the date chip; the research mark sits in the 250px the
subtitle wrap deliberately leaves clear. Nothing is placed over a figure, and
nothing here can move a figure — `place()` composites onto the base image and
returns nothing the layout reads.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("livermore.card_ornaments")

ORNAMENT_DIR = Path(__file__).resolve().parents[1] / "assets" / "ornaments"

_cache: dict = {}


def load(name: str):
    """An ornament as RGBA, or None if it isn't on disk.

    None rather than raising: ornament is the one part of this card that is
    purely decoration. A missing doodle costs nothing a reader can misread; a
    missing figure would. The card must still render on a machine that has
    never run the asset build.
    """
    if name in _cache:
        return _cache[name]
    path = ORNAMENT_DIR / f"{name}.png"
    img = None
    if path.exists():
        try:
            from PIL import Image

            img = Image.open(path).convert("RGBA")
        except Exception:
            logger.exception("ornament %s failed to load", name)
            img = None
    _cache[name] = img
    return img


def _fit(img, box: Tuple[int, int, int, int]):
    """Scale to fit inside `box` without distorting the drawing."""
    from PIL import Image

    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    scale = min(bw / img.width, bh / img.height)
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    return img.resize((w, h), Image.LANCZOS)


def place(
    base,
    name: str,
    box: Tuple[int, int, int, int],
    *,
    anchor: str = "center",
    opacity: float = 1.0,
    rotate: float = 0.0,
) -> Optional[Tuple[int, int, int, int]]:
    """Composite an ornament inside `box`. Returns where it landed, or None.

    Silently does nothing when the asset is absent — see `load()`.
    """
    img = load(name)
    if img is None:
        return None

    if rotate:
        from PIL import Image

        # BICUBIC, not LANCZOS: `rotate` rejects LANCZOS outright.
        img = img.rotate(rotate, expand=True, resample=Image.BICUBIC)
    img = _fit(img, box)

    if opacity < 1.0:
        alpha = img.getchannel("A").point(lambda v: int(v * opacity))
        img.putalpha(alpha)

    x0, y0, x1, y1 = box
    if anchor == "right":
        px = x1 - img.width
    elif anchor == "left":
        px = x0
    else:
        px = x0 + (x1 - x0 - img.width) // 2
    py = y0 + (y1 - y0 - img.height) // 2

    base.alpha_composite(img, (int(px), int(py)))
    return (int(px), int(py), int(px) + img.width, int(py) + img.height)


def has_ornaments() -> bool:
    """Whether the asset build has been run in this checkout."""
    return any(load(n) is not None for n in ("rotation", "tape", "magnifier"))


__all__ = ["load", "place", "has_ornaments", "ORNAMENT_DIR"]
