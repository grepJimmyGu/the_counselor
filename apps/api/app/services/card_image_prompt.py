"""Build the image-generation prompt for the daily share card.

Jimmy's template, with the day's real figures substituted into the ten content
slots. Every styling, structure and prohibition line is his, verbatim.

**Why the whole template, not a summary.** An abridged version was tested on
2026-08-11 and the sector block came back garbled: Technology's -0.88% rendered
as -0,82%, Communication +0.52% vanished entirely, and the money-flow
annotation was mashed into the losers rows as literal gibberish. The
unabridged template with the same data and the same model rendered all
thirteen figures correctly. The compression caused it, not the model — so this
module carries the full text and future edits should add, never trim.

Two things the template does NOT get from Jimmy, both added in response to an
observed failure:

* An accuracy clause naming the decimal point. The first run returned European
  commas throughout (`-0,11%`) on a US market card.
* A prohibition on drawing company logos. The model invented a purple "S" mark
  for SBNY — a fabricated visual claim about a company, the same class of
  problem as a fabricated number and harder to spot.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.card_labels import EN, ZH

# The language must be stated, not inferred. An English prompt produced a
# Chinese card in testing — harmless in a one-off, wrong in a feature where the
# user picks.
_LANGUAGE = {
    EN: "Write every word on the card in ENGLISH. Do not use any other language.",
    ZH: "卡片上的所有文字必须使用简体中文。除下列英文专有名词外，不要使用其他语言："
        "股票代码、Livermore、livermorealpha.com、VIX。",
}

# Added by us, in response to specific observed failures. Kept together and
# labelled so a future editor can see they are not part of Jimmy's template.
_ACCURACY = """
CRITICAL ACCURACY REQUIREMENT
Every number below is real market data.
* Reproduce each figure EXACTLY as written, including the decimal point. Use a period, never a comma.
* Do not add, omit, round, reorder or alter any figure.
* Do not invent any statistic, date, percentage or company fact that is not written below.
* Spell every label exactly as written.
* Do NOT draw company logos, brand marks, app icons or product imagery of any kind. Use the ticker text only.
"""

_STYLE = """Visual References
The overall aesthetic should feel like:

* A highly saveable Xiaohongshu knowledge card
* Notion + Linear + handwritten notebook annotations
* Editorial infographic
* Content-first design
* Strong readability
* Clear visual hierarchy
* Personal research notes from an independent builder

Canvas

* Aspect ratio: 3:4
* Vertical layout
* Designed as a social media knowledge-card cover/post
* High-resolution
* Optimized for mobile reading

Background
Use a noticeably warm, medium-light beige / oatmeal paper background.
Important:

* The beige should be clearly visible, not almost white
* Warm cream / oatmeal / light kraft-paper feeling
* Avoid pure white
* Avoid gray-white
* No gradients
* Subtle paper texture is acceptable, but keep it clean

Overall Layout
Use:

* Generous whitespace
* Modular card-based layout
* Clearly separated information sections
* Rounded borders
* Extremely subtle shadows
* Thin #EAEAEA dividers
* Hand-drawn annotations
* Underlines, circles, arrows, sticky notes and marker highlights
* Important numbers highlighted visually
* Dense enough to feel informative, but never crowded

Give EVERY numbered section the same numbered badge treatment, in sequence.
Do not number some sections and leave others unnumbered.

The page should feel like a well-organized personal market notebook, not a corporate financial report.
Color Palette
Primary text:
#111111
Secondary text:
#666666
Borders:
#EAEAEA
Primary accent:
Dark brown #8B4513
Highlight:
Warm yellow #F4D35E
Supporting colors may include muted green for positive market moves and muted red/orange for negative market moves.
Keep all colors warm and slightly muted.
Do NOT use:

* Neon colors
* Tech blue glow
* Blue-purple AI aesthetics
* Gradients

Typography
Main headline:

* Extra-bold sans serif
* Very large
* Strong editorial presence
* The dominant visual element

Section headings:

* Bold
* Clearly separated from body text
* May use dark-brown labels

Body:

* Medium-weight sans serif
* Highly readable on mobile

Annotations:

* Handwritten or notebook-like style
* Smaller than body copy

Visual Hierarchy
Level 1:
Very large main headline
Level 2:
Section titles
Level 3:
Market data and explanations
Level 4:
Personal annotations, highlights and supporting notes
Important market numbers should receive particularly strong visual emphasis."""

_TAIL = """Illustration Style
Use:

* Simple line drawings
* Hand-drawn notebook doodles
* Small editorial illustrations
* Cute but restrained
* Financial-journal aesthetic
* Small arrows, stars, lightbulbs, sticky notes, magnifying glasses and market-related objects

The illustrations should support the information rather than become the main visual focus.
Do NOT Include

* Company logos, brand marks or app icons of any kind
* AI robots
* Futuristic AI imagery
* Glowing computer chips
* Stock candlestick-chart backgrounds
* Corporate PowerPoint aesthetics
* Advertising-style layouts
* Promotional product graphics
* Gradients
* Cyberpunk
* 3D icons
* Glossy financial-app UI
* Excessive decoration
* Large website banners
* Aggressive CTA buttons

Overall Feeling
The creator is an independent builder using his own AI investing product, Livermore, to conduct a daily U.S. stock-market review.
Every evening after the market closes, he opens the tool, looks through the data, takes notes, interprets what happened, and turns the findings into a visual research journal.
Livermore should appear naturally as the source of the research and analysis, not as an advertised product.
It should NOT feel like an advertisement.
It should NOT feel like stock-picking advice.
It should feel like:
"Here is what happened today."
"Here is why I think it happened."
"Here is what I learned from the data."
"If you want to explore the underlying research, it's available at livermorealpha.com."
Translate professional financial concepts into plain English that a beginner investor can understand.
The final visual should feel like a combination of:
Notion research notes x handwritten investment journal x high-quality social-media infographic x independent builder's daily log."""


def _stat_lines(stats: List[Dict[str, Any]]) -> str:
    return "\n".join(f"{s['label']}\n{s.get('change') or s.get('value')}" for s in stats)


def build_image_prompt(
    payload: Dict[str, Any],
    copy: Dict[str, Any],
    *,
    drivers: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Jimmy's template with today's slots filled.

    A section with no source is instructed to be OMITTED rather than left to
    the model's imagination — the same collapse-don't-fake rule the rest of the
    card follows. On the 2026-08-11 test the model honoured it: no news, no
    invented drivers.
    """
    lang = payload.get("lang", EN)
    labels = payload.get("labels") or {}
    stock = payload.get("stock") or {}

    indices = _stat_lines(payload.get("indices") or [])
    losers = _stat_lines(payload.get("losers") or [])
    winners = _stat_lines(payload.get("winners") or [])

    if drivers:
        drivers_block = "7. Three Drivers Behind Today's Move\nCreate three numbered mini-cards.\n" + "\n".join(
            f"{i:02d} - {d.get('title', '')}\n{d.get('body', '')}" for i, d in enumerate(drivers, 1)
        ) + "\nUse tiny hand-drawn illustrations for each factor."
    else:
        drivers_block = (
            "7. OMIT this section entirely. There is no verified news today, so do not "
            "create a drivers module and do not invent any reasons for the day's moves. "
            "Close the layout up so no empty space is left where it would have been."
        )

    flow = ""
    if payload.get("flow_from") and payload.get("flow_to"):
        flow = (
            f"Add a highlighted annotation:\n{labels.get('money_flow', 'Money Flow')}\n"
            f"{copy.get('money_flow_note') or ''}"
        )

    points = "\n".join(f"* {p}" for p in (copy.get("stock_points") or [])) or "* Largest single-day move in the index today"

    return f"""Design a high-quality Xiaohongshu-style financial knowledge card for a Daily U.S. Market Recap.

{_LANGUAGE.get(lang, _LANGUAGE[EN])}

{_STYLE}
{_ACCURACY}
Required Structure
1. Top Header
Include a compact date label:
{payload.get('date_label', '')}
Beside it:
{payload.get('masthead', '')}
Keep this area small and editorial, like the header of a personal research notebook.
2. Main Headline
{copy.get('headline') or ''}
Use an oversized extra-bold black font.
Highlight or underline one important phrase using warm yellow.
3. Subtitle
{copy.get('subtitle') or ''}
Keep this concise and clearly secondary to the headline.
Add a restrained hand-drawn illustration related to the day's story.
Do NOT use a stock-chart background.
4. {labels.get('market_performance', 'Market Performance')}
Create four compact data cards:
{indices}
Supporting note:
{copy.get('market_note') or ''}
Use simple hand-drawn icons and small arrows.
5. {labels.get('sectors', 'Sector Performance')}
Divide this section into two clear groups. List each sector on its own line.
{labels.get('losers', 'LOSERS')}
{losers}
{labels.get('winners', 'WINNERS')}
{winners}
{flow}
6. {labels.get('stock_of_day', 'Stock of the Day')}
Create one larger feature card:
{stock.get('symbol', '')} {stock.get('change', '')}
Key points:

{points}

Do not add any other statistic about this company. Do not draw its logo.
Highlighted takeaway:
{copy.get('stock_takeaway') or ''}
{drivers_block}
8. Highlighted Conclusion Module
Use a warm-yellow sticky-note style card.
Title:
{labels.get('takeaway', "Today's Takeaway")}
Body:
{copy.get('takeaway_body') or ''}
Highlight the key phrase:
{copy.get('takeaway_highlight') or ''}
9. Livermore Attribution + Website
Add a small, tasteful product attribution near the bottom of the card.
Use wording such as:
{labels.get('source', 'Market data & analysis: Livermore')}
Below it, include:
{labels.get('explore', 'Explore the full analysis')} -> {payload.get('source_url', 'livermorealpha.com')}
The website should be clearly readable but visually understated.
Important:

* Do NOT make the URL look like a large advertisement
* Do NOT use a large CTA button
* Do NOT use promotional phrases like "Sign Up Now" or "Try It Free"
* Treat the website as a source/reference link, similar to the URL printed at the bottom of a research notebook
* Optionally add a tiny hand-drawn arrow or underline around the URL
* Keep it secondary to the market content

10. Footer
Small and understated:
{payload.get('disclaimer', '')}
The disclaimer should remain visible but should not dominate the design.
{_TAIL}"""
