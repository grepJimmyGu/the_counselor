"""Rebuild the bundled Latin subset for the share card.

**The card cannot render without a bundled font.** A slim Linux container has
none — not Noto, not DejaVu — and the macOS fallbacks in `card_fonts` exist
only so the thing draws on a laptop. CI proved the point the day the renderer
landed: `FontUnavailable` on Ubuntu, and Railway is Ubuntu, so the share
endpoint would have 500'd in production for every English card.

The full DejaVu pair is 1.4 MB and most of it is glyphs this card will never
draw. Subset to what the labels and the number formatting actually produce and
it's 49 KB.

Re-run this when a new label introduces a character outside the ranges below —
`test_the_bundled_latin_subset_covers_every_character_the_card_draws` is what
tells you that happened.

    python3 scripts/build_card_fonts.py

**Dev-only: needs `fonttools`, which is NOT a backend dependency**, and reads
DejaVu out of matplotlib's data directory (also not a dependency). Both are
present on a normal dev machine; neither belongs on the Railway image to
support a one-off asset build.

DejaVu is redistributable under the Bitstream Vera licence — `LICENSE_DEJAVU`
ships beside the fonts and must stay there.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "assets" / "fonts"

# What the card can actually draw: ASCII, Latin-1 (accented company names), the
# punctuation the labels use, and the currency/maths signs formatted figures
# produce. U+2212 is the real minus sign; U+2190-2193 are the arrows, kept so a
# future label can use one — Helvetica's lack of U+2192 drew an empty box on
# the English card once already.
UNICODES = (
    "U+0020-007E,U+00A0-00FF,U+2010-2015,U+2018-201F,U+2020-2022,U+2026,"
    "U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2190-2193,U+2212,U+25CF,U+2713"
)

FACES = ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")


def _source_dir() -> Path:
    import matplotlib

    return Path(matplotlib.get_data_path()) / "fonts" / "ttf"


def main() -> int:
    try:
        from fontTools import subset
    except ImportError:
        print("needs fonttools: pip install fonttools")
        return 1

    src = _source_dir()
    OUT.mkdir(parents=True, exist_ok=True)
    for face in FACES:
        a, b = src / face, OUT / face
        if not a.exists():
            print(f"missing source {a}")
            return 1
        subset.main([
            str(a),
            f"--unicodes={UNICODES}",
            f"--output-file={b}",
            "--layout-features=*",
            "--no-hinting",
            # Keep the visible .notdef box. Without it a character outside the
            # subset draws NOTHING — the silent disappearance this codebase
            # refuses everywhere else.
            "--notdef-outline",
        ])
        print(f"  {face}: {a.stat().st_size // 1024}K -> {b.stat().st_size // 1024}K")

    licence = src / "LICENSE_DEJAVU"
    if licence.exists():
        (OUT / "LICENSE_DEJAVU").write_bytes(licence.read_bytes())
        print("  LICENSE_DEJAVU copied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
