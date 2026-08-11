# Daily share card — build spec

Jimmy supplied two prompts (English 2026-08-09, Chinese same day) describing a
Xiaohongshu-style knowledge card for the daily US market recap. This file is
the binding contract extracted from them. **The prompts contain example content
from 31 July — every figure and name in them is illustrative.**

## The two rules everything else follows from

**1. The model writes prose. It never emits a figure or a proper noun.**

Numbers come from `daily_card_service.build_card_payload`; sector and index
names come from `card_labels`. A model asked to render `+15.51%` will
eventually render `+15.5%` or `+16.51%`, and a model asked to translate
"Technology" returns 科技 one day and 技术 the next. Each card looks fine
alone; only someone comparing two of them notices. On a card built to be
forwarded as a factual recap, that is the worst failure available.

`card_copy.allowed_numbers` enforces the numeric half mechanically: every
number-shaped token in the generated prose must match a figure we supplied.

**The boundary is provenance, not arithmetic.** Two sources count as supplied —
the card's own figures, *and* anything in the NEWS block we handed the model.
Omitting the second was a real hole: Jimmy's own example copy says "biggest
one-day gain since 2008" and "Azure revenue grew 43%". Both are correct, both
came from articles, neither is a number we computed. A guard that rejected them
would fire on almost every well-written card — and a guard that cries wolf gets
switched off.

Magnitudes only, sign and separators stripped, trailing full stops removed
("since 2008." must match the article's `2008`).

**Two things the guard deliberately does not do**, both because they are
parsing rather than validation: it does not check direction words ("VIX rose
6.83%" passes), and it does not check that a news figure was attributed to the
right subject. It catches invented magnitudes. That is all it claims.

Violations drop **per field**, not per card. One bad sentence shouldn't cost
the whole thing, and a dropped section is already the behaviour below.

**2. A section with no source collapses. It never fakes.**

No news that day → fewer than three drivers, or the module drops. No unusual
mover → no "Stock of the Day". Better a shorter card than three confident
explanations for a rally that didn't happen for those reasons.

## Slot → source

| § | Slot | Source |
|---|---|---|
| 1 | Date `26.7.31 · 周五` | `card_labels.date_label` from the brief's close date |
| 1 | Masthead | `chrome("masthead")` |
| 2 | Headline | **generated** |
| 3 | Subtitle | **generated** |
| 4 | Dow / S&P / Nasdaq / VIX | `^DJI` `^GSPC` `^IXIC` `^VIX` — index levels, never the SPY/QQQ/DIA/VXX proxies |
| 4 | Supporting note | **generated** |
| 5 | WINNERS / LOSERS | `brief.sectors`, split by sign, worst-first in the losers column |
| 5 | Money-flow annotation | **generated**, grounded in the Chaikin values |
| 6 | Ticker + % | `brief.unusual` |
| 6 | Key points | **generated from fetched news only** |
| 6 | Fundamentals / Valuation / Trend | `evaluation_scoring.score_stock` |
| 6 | Takeaway + handwritten note | **generated** |
| 7 | Three drivers | **generated from fetched news only** |
| 8 | Today's Takeaway | **generated** |
| 9–10 | Attribution, URL, disclaimer | `chrome(...)` |

## Rendering

**Pillow, not an SVG rasteriser and not an image model.** The doodles — arrows,
lightbulbs, sticky notes — are generated **once** as static assets and embedded;
they don't change daily and they're what a diffusion model is actually good at.
Everything carrying meaning is drawn by us.

### The split: generated pixels, rendered words

Five image-model generations produced the right *look* and damaged the *data*
every time, differently each time. The decisive case was a Chinese card where
every figure was correct but the labels had detached — `医疗 −1.10%` when
Healthcare was **+1.67%**. A number-only OCR gate passes that card. No single
mechanical check catches the whole failure set.

The cause is what the model is doing: it draws glyph *shapes it has seen*, not
text it looks up. Latin has ~52 letterforms and it manages; Chinese has
thousands of dense multi-stroke characters, so at 20px it emits stroke-shaped
plausible non-characters (标→桁, 琼→珉) with no concept of a wrong character.

So the boundary is drawn at **anything a reader reads**:

| Layer | Owner | Where |
|---|---|---|
| Ornament — corner mark, doodles, tape | image model, **once** | `card_plate.PLATE_PROMPT` → `app/assets/plates/plate.png` |
| Ornament placement | renderer | `card_ornaments.place()` |
| Structure, figures, labels, prose | renderer | `card_render.py` + `card_paper.py` |

The prompt asks for a **background plate with empty zones**, not a finished
card — a finished card leaves nowhere to composite, and any mark resembling
writing ruins the plate. `scripts/build_card_ornaments.py` then cuts the plate
into individual transparent PNGs, because a whole plate would also decide
*where* things sit and that is layout: the takeaway note has to land under the
takeaway text, not wherever the model put a rectangle.

Every ornament slot is one the layout already reserves — the corner mark sits
in the header band beside the date chip, the research mark in the 250px the
subtitle wrap deliberately leaves clear. Nothing is placed over a figure, and
`place()` returns nothing the layout reads, so no ornament can move one.

**A missing ornament set is a normal state.** `place()` is a silent no-op when
the asset isn't on disk. Decoration is the one part of this card whose absence
costs nothing a reader can misread — unlike a missing figure, or tofu.

**Regenerating returns a different drawing**, so the generated plate is
committed alongside the cuts; it's the only way to re-cut the ones we have.

cairosvg needs system Cairo libraries on the Railway image — deployment risk
for little gain, since the layout is fixed and every coordinate is ours.
Playwright would give perfect fidelity by reusing the design's HTML/CSS, but it
ships a ~400MB browser and Railway memory is the binding constraint.

**Two things were NOT dependencies and had to be made ones.** `Pillow` was
importable locally only via unrelated packages (matplotlib, plotly), so the
card would have worked in dev and `ImportError`d on Railway. And **no font is
findable at all** — not even DejaVu — so fonts must be bundled for the ENGLISH
card too, not just Chinese.

**Layout is priority-ordered, not first-come-first-served.** The conclusion
block's band is reserved before the optional middle content flows. Flowing in
document order dropped it three renders running while the bullets above kept
their room — the layout was deciding importance by accident.

**Glyphs are not guaranteed either.** `→` (U+2192) is absent from Helvetica and
rendered as an empty box on the *English* card. Arrows are drawn with lines;
no arrow appears in any label string.

**Chinese needs a bundled CJK font**, and a missing one must REFUSE rather than
draw tofu — empty boxes pass every check that only asserts the PNG has bytes,
and are obviously broken to the reader it was forwarded to. `card_fonts.can_render`
lets the share button ask before offering a language.

Fonts go in `apps/api/app/assets/fonts/`. **Not committed yet:** a
GB2312-covering Noto Sans SC subset is ~4-5 MB, and committing binaries of that
size to the repo is a call for Jimmy, not a default. Until they land, macOS dev
fallbacks let both cards render locally and every use logs a warning. A bold
**Latin** face is only ~200-400 KB — drop any `.ttf` in as `NotoSans-Bold.ttf`
or `Inter-Bold.ttf` and it takes precedence with no code change.

**`bold=True` returned Regular on every card ever rendered.** A `.ttc` is a
TrueType *Collection* holding several faces in one file, and
`ImageFont.truetype(path, size)` silently takes index 0. Nothing errored — the
headlines just quietly weren't bold. `card_fonts.font_index()` selects the
face; `test_bold_actually_draws_bold` pins it on rendered ink rather than on a
face name, so it holds whether the weight comes from a second face inside a
collection or from a separately bundled bold file.

**PNG output shows `livermorealpha.com` as plain readable text** — no simulated
button (Chinese prompt §9). The real link travels in the share sheet.

## Lifecycle

The first share of a trading day generates from the **prior close** and writes
one row per `(trading_date, lang)`. Every later viewer gets that same row —
immutable, so a forwarded link shows what the sharer saw. No cron: nothing
generates on a day nobody shares.

Rows are kept indefinitely. Storing the **data** rather than the rendered PNG
is ~1.5 MB/year (≈3 KB × 2 languages × 252 days); storing PNGs would be ~50
MB/year on the Postgres disk, and trap #10 exists because a disk-full event
during a backfill took Market Pulse down.

A past date's card can never change, so `Cache-Control: immutable` is literally
true — after the first view, browsers and any CDN serve it without touching us.

**The card and the home block will differ during market hours.** The block
shows today's live pulse; the card shows the prior close. That's intended — a
shared card should be a settled number — so the button reads "Share yesterday's
close" rather than "Share".

## Aesthetic constraints (from both prompts)

Warm oatmeal/beige ground, clearly not white and not grey-white. Text `#111111`
/ `#666666`, borders `#EAEAEA`, accent brown `#8B4513`, highlight yellow
`#F4D35E`. Muted green up / muted red-orange down. 3:4 vertical, mobile-first.

Explicitly forbidden: gradients, neon, tech-blue or blue-purple "AI" styling,
glow, 3D icons, cyberpunk, candlestick-chart backgrounds, corporate-deck
styling, large CTAs, large logos, promotional phrasing ("Sign Up Now", "Try It
Free"), AI robots, glowing chips.

The register both prompts insist on: an independent builder's daily research
notebook — *"here is what happened, here is why I think it happened, here is
what the data showed"* — with Livermore appearing as the **source of the
research**, not an advertised product. Not a brokerage report, not financial
media, not stock-picking advice.
