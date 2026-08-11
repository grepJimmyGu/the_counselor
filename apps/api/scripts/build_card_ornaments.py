"""Cut the generated plate into individual ornament PNGs.

The image model draws ornament well and text badly, so it gets to draw
ornament and nothing else (see `app/services/card_plate.py`). But a whole
generated plate would also decide *where* things sit, and layout is the
renderer's job — the takeaway note has to land under the takeaway text, not
wherever the model felt like putting a rectangle.

So this splits the plate into separate transparent assets. The renderer then
places each one deterministically. Run once, commit the output, done: the
ornament shouldn't drift between days, and regenerating per card would put
back the variance we just removed.

    python3 scripts/build_card_ornaments.py [plate.png]

Names are assigned by hand after looking at the output — the script emits
numbered crops and can't know which blob is the coffee cup.

**Dev-only, and it needs `scipy`, which is NOT a backend dependency.** That's
deliberate: nothing under `app/` imports this, it runs once per generated
plate, and adding scipy to the Railway image to support a one-off asset cut
would be a poor trade. Install it locally if you need to re-cut.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
PLATE = ROOT / "app" / "assets" / "plates" / "plate.png"
OUT = ROOT / "app" / "assets" / "ornaments"

# Strokes of one doodle are separate blobs — the $ sits inside the circle, the
# arrowheads float off the arcs. Dilate before labelling so a drawing comes out
# as one asset instead of nine.
MERGE_RADIUS = 16
MIN_AREA = 1_500  # below this it's speckle, not a drawing
ALPHA_FLOOR = 40


def _disc(r: int) -> np.ndarray:
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    return x * x + y * y <= r * r


def _boxes(alpha: np.ndarray):
    solid = alpha > ALPHA_FLOOR
    merged = ndimage.binary_dilation(solid, structure=_disc(MERGE_RADIUS))
    labels, n = ndimage.label(merged)
    out = []
    for i in range(1, n + 1):
        # Bounds from the REAL ink, not the dilated blob — otherwise every crop
        # carries MERGE_RADIUS of empty margin and the placement is off.
        ys, xs = np.where(solid & (labels == i))
        if ys.size < MIN_AREA:
            continue
        out.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1, int(ys.size)))
    return out


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else PLATE
    if not src.exists():
        print(f"no plate at {src}")
        return 1

    img = Image.open(src).convert("RGBA")
    arr = np.array(img)
    boxes = _boxes(arr[:, :, 3])
    boxes.sort(key=lambda b: -b[4])

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{len(boxes)} ornaments in {src.name} ({img.width}x{img.height})\n")
    for idx, (x0, y0, x1, y1, area) in enumerate(boxes):
        crop = img.crop((x0, y0, x1, y1))
        # Fully-transparent pixels carry junk RGB from the generator; it never
        # composites, but it leaks into any later resize that averages
        # neighbours. Neutralise it against the ink colour.
        c = np.array(crop)
        c[:, :, :3][c[:, :, 3] < 8] = 40
        crop = Image.fromarray(c)
        name = f"{idx:02d}.png"
        crop.save(OUT / name)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        print(
            f"  {name}  {crop.width:4d}x{crop.height:<4d} at ({x0:4d},{y0:4d})"
            f"  centre {cx/img.width:.2f},{cy/img.height:.2f}  ink {area}"
        )
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
