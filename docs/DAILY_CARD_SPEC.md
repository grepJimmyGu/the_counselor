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

`numeric_tokens` + `injected_numbers` enforce the numeric half mechanically:
every number-shaped token in the generated prose must match a figure we
supplied. Magnitudes only — prose carries the sign in words ("VIX fell 6.83%"
is correct for −6.83%), so comparing raw strings would reject good copy and
train whoever hit it to switch the guard off. **The guard does not check
direction words**; that is parsing, not validation.

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

**Deterministic SVG → PNG, not an image model.** The doodles — arrows,
lightbulbs, sticky notes — are generated **once** as static assets and embedded;
they don't change daily and they're what a diffusion model is actually good at.
Everything carrying meaning is drawn by us.

Playwright would give perfect fidelity by reusing the design's HTML/CSS, but it
ships a ~400MB browser and Railway memory is the binding constraint (see the
backlog). SVG + a rasteriser is ~20MB.

**Chinese needs a bundled CJK font.** A slim Railway container has no CJK
glyphs; the 中文 card would render as tofu boxes. This looks fine locally and
breaks only in production.

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
