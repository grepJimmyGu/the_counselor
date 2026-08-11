"""Font resolution for the share-card renderer.

**A slim container has no fonts.** Not Noto, not DejaVu — Pillow's
`ImageFont.truetype("DejaVuSans.ttf")` raises `OSError` on this machine and
will on Railway too. So the card cannot render at all without bundled font
files, and the Chinese card cannot render without a CJK-capable one.

That's the whole reason this module exists rather than a hard-coded path: the
failure is invisible until someone looks at a card, and by then it has been
forwarded.

**A missing CJK font must REFUSE, not render tofu.** Every glyph would come out
as an empty box — a card that looks broken to the reader and, worse, looks
*fine* to any automated check that only asserts the PNG has bytes. Refusing
means the share button says "not available in Chinese yet", which is true and
actionable. Same rule as the rest of the card: a section with no source
collapses rather than faking.

Bundled fonts live in `app/assets/fonts/`. They are NOT committed yet — see
`docs/DAILY_CARD_SPEC.md`; a GB2312-covering Noto Sans SC subset is ~4-5 MB and
committing binaries of that size to the repo is Jimmy's call, not mine. Until
they land, the dev fallbacks below let the English card render locally.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("livermore.card_fonts")

# Where bundled fonts go. First match wins, so dropping a file in here
# overrides the dev fallback without any code change.
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"

# Preferred bundled filenames, in order.
LATIN_CANDIDATES = ("NotoSans-Bold.ttf", "NotoSans-Regular.ttf", "Inter-Regular.ttf")
LATIN_BOLD_CANDIDATES = ("NotoSans-Bold.ttf", "Inter-Bold.ttf")
CJK_CANDIDATES = ("NotoSansSC-Regular.otf", "NotoSansSC-Regular.ttf", "NotoSansSC.ttf")
CJK_BOLD_CANDIDATES = ("NotoSansSC-Bold.otf", "NotoSansSC-Bold.ttf")

# Development fallbacks. macOS only, and deliberately NOT relied on in
# production — a card that renders locally and 500s on Railway is the failure
# this module is built to make loud.
_DEV_LATIN = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)
_DEV_CJK = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
)


class FontUnavailable(RuntimeError):
    """No font can render this card. Raised rather than emitting tofu."""


def _first_existing(names: tuple, directory: Path) -> Optional[str]:
    for n in names:
        p = directory / n
        if p.exists():
            return str(p)
    return None


def _first_readable(paths: tuple) -> Optional[str]:
    for p in paths:
        if Path(p).exists():
            return p
    return None


# Face index within a .ttc collection. A TrueType Collection holds several
# faces in one file, and `truetype(path, size)` silently takes index 0 —
# Regular. So `bold=True` returned Regular for every headline on every card
# rendered so far, and nothing errored: the text just quietly wasn't bold.
_TTC_BOLD_INDEX = {
    "/System/Library/Fonts/Helvetica.ttc": 1,          # Helvetica Bold
    "/System/Library/Fonts/Hiragino Sans GB.ttc": 2,   # W6, the heavier weight
}


def font_index(path: str, *, bold: bool) -> int:
    """Which face inside the file. Bundled fonts are single-face, so 0."""
    if not bold:
        return 0
    return _TTC_BOLD_INDEX.get(path, 0)


def resolve_font(lang: str, *, bold: bool = False) -> str:
    """Path to a font that can render `lang`, or raise.

    Chinese needs a CJK font specifically: a Latin font asked to draw 科技
    silently produces empty boxes rather than failing, which is exactly the
    kind of "looks fine to the code, broken to the reader" outcome that gets
    shipped.
    """
    if lang == "zh":
        bundled = _first_existing(
            CJK_BOLD_CANDIDATES + CJK_CANDIDATES if bold else CJK_CANDIDATES, FONT_DIR
        )
        if bundled:
            return bundled
        dev = _first_readable(_DEV_CJK)
        if dev:
            logger.warning(
                "card fonts: using the DEV CJK fallback %s — bundle a font in "
                "app/assets/fonts/ before this ships",
                dev,
            )
            return dev
        raise FontUnavailable(
            "No CJK font available. The Chinese card cannot render without one "
            "— every glyph would be an empty box. Bundle NotoSansSC into "
            "apps/api/app/assets/fonts/."
        )

    bundled = _first_existing(
        LATIN_BOLD_CANDIDATES + LATIN_CANDIDATES if bold else LATIN_CANDIDATES, FONT_DIR
    )
    if bundled:
        return bundled
    dev = _first_readable(_DEV_LATIN)
    if dev:
        logger.warning(
            "card fonts: using the DEV Latin fallback %s — bundle a font in "
            "app/assets/fonts/ before this ships",
            dev,
        )
        return dev
    raise FontUnavailable(
        "No font available to render the card. Bundle one into "
        "apps/api/app/assets/fonts/."
    )


def can_render(lang: str) -> bool:
    """Whether a card in this language can be drawn at all.

    The share button asks this before offering a language, so the user never
    clicks through to a 500 — and so the Chinese option is simply absent
    rather than broken while the font is pending.
    """
    try:
        resolve_font(lang)
        return True
    except FontUnavailable:
        return False
