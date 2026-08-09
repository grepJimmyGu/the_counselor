"""Daily share card — the injected half of the payload.

Turns a `DailyBrief` (plus the stock-of-the-day's 3-dimensional score) into
every slot on the card that is NOT written by the model: labels, figures,
rankings, the date stamp, the disclaimer.

**Formatting happens here, once.** The formatted strings ("+1.19%", "7,757.64")
are both what the renderer draws AND what the model is shown, so it can
reference a figure verbatim instead of restating it from a raw float and
rounding it differently. Two format paths would let the card's headline and its
data card disagree about the same number.

The generated prose is a separate concern (step 3). This module is pure and
synchronous: given a brief, it always produces the same payload.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.services.card_labels import EN, chrome, date_label, index_label, sector_label
from app.services.daily_brief_service import DailyBrief
from app.services.evaluation_scoring import ThreeDimensionalScore

LIVERMORE_URL = "livermorealpha.com"

# Sectors shown per column. Jimmy's example runs 4 losers / 3 winners; the card
# has room for about four a side before the module stops being scannable.
SECTOR_COLUMN_CAP = 4


def fmt_pct(v: Optional[float]) -> str:
    """`+1.19%` / `-6.83%`. Two decimals, explicit sign — the card's numbers are
    its whole credibility, so they never render bare."""
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else ''}{v:.2f}%"


def fmt_level(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}"


@dataclass
class CardStat:
    label: str
    value: str
    """Signed percent as text. `None` where the row has no % (rare)."""
    change: Optional[str] = None
    """Sign of the move, for the renderer's colour choice. `None` means the row
    must NOT be coloured — VIX is a level, and "VIX down" is not good news the
    way "S&P up" is."""
    direction: Optional[str] = None  # "up" | "down" | None


@dataclass
class CardStock:
    symbol: str
    change: str
    direction: str
    score_health: Optional[int] = None
    score_valuation: Optional[int] = None
    score_trend: Optional[int] = None
    score_final: Optional[int] = None


@dataclass
class CardPayload:
    lang: str
    trading_date: str
    date_label: str
    masthead: str
    indices: List[CardStat] = field(default_factory=list)
    winners: List[CardStat] = field(default_factory=list)
    losers: List[CardStat] = field(default_factory=list)
    flow_from: Optional[str] = None
    flow_to: Optional[str] = None
    flow_from_value: Optional[str] = None
    flow_to_value: Optional[str] = None
    stock: Optional[CardStock] = None
    labels: Dict[str, str] = field(default_factory=dict)
    source_url: str = LIVERMORE_URL
    disclaimer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _direction(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    return "up" if v >= 0 else "down"


def build_card_payload(
    brief: DailyBrief,
    *,
    lang: str = EN,
    score: Optional[ThreeDimensionalScore] = None,
) -> CardPayload:
    trading_date = (brief.as_of or "")[:10]

    payload = CardPayload(
        lang=lang,
        trading_date=trading_date,
        date_label=date_label(trading_date, lang) if trading_date else "",
        masthead=chrome("masthead", lang),
        disclaimer=chrome("disclaimer", lang),
        labels={
            k: chrome(k, lang)
            for k in (
                "market_performance", "sectors", "winners", "losers", "money_flow",
                "stock_of_day", "score", "score_health", "score_valuation",
                "score_trend", "drivers", "takeaway", "source", "explore",
            )
        },
    )

    # ── the four index cards ────────────────────────────────────────────────
    for q in brief.indices:
        payload.indices.append(
            CardStat(
                label=index_label(q.symbol, lang, fallback=q.name),
                value=fmt_level(q.price),
                change=fmt_pct(q.change_percent),
                direction=_direction(q.change_percent),
            )
        )
    if brief.vix:
        payload.indices.append(
            CardStat(
                label=index_label(brief.vix.symbol, lang, fallback=brief.vix.name),
                value=fmt_level(brief.vix.price),
                change=fmt_pct(brief.vix.change_percent),
                # direction stays None ON PURPOSE: VIX is a level, so the
                # renderer must not paint it green when it falls.
                direction=None,
            )
        )

    # ── sectors, split by sign ──────────────────────────────────────────────
    # `brief.sectors` arrives ranked by return descending, so winners read from
    # the top and losers from the bottom. Losers are reversed so the WORST
    # reads first — a "losers" column ordered best-to-worst buries its own
    # headline.
    ups = [s for s in brief.sectors if (s.change_percent or 0) > 0]
    downs = [s for s in brief.sectors if (s.change_percent or 0) <= 0]
    payload.winners = [
        CardStat(
            label=sector_label(s.name, lang),
            value=fmt_pct(s.change_percent),
            direction="up",
        )
        for s in ups[:SECTOR_COLUMN_CAP]
    ]
    payload.losers = [
        CardStat(
            label=sector_label(s.name, lang),
            value=fmt_pct(s.change_percent),
            direction="down",
        )
        for s in list(reversed(downs))[:SECTOR_COLUMN_CAP]
    ]

    # ── money flow ──────────────────────────────────────────────────────────
    if brief.flow_into and brief.flow_out_of:
        payload.flow_from = sector_label(brief.flow_out_of.name, lang)
        payload.flow_to = sector_label(brief.flow_into.name, lang)
        payload.flow_from_value = (
            f"{brief.flow_out_of.money_flow:.2f}"
            if brief.flow_out_of.money_flow is not None
            else None
        )
        payload.flow_to_value = (
            f"{brief.flow_into.money_flow:.2f}"
            if brief.flow_into.money_flow is not None
            else None
        )

    # ── stock of the day ────────────────────────────────────────────────────
    # The unusual mover, so the feature card is tied to the rest of the
    # snapshot rather than picking a second, unrelated name. Absent on a quiet
    # day — the module drops instead of promoting a +2% name to "stock of the
    # day".
    if brief.unusual:
        payload.stock = CardStock(
            symbol=brief.unusual.symbol,
            change=fmt_pct(brief.unusual.change_percent),
            direction=_direction(brief.unusual.change_percent) or "up",
            score_health=score.health if score else None,
            score_valuation=score.valuation if score else None,
            score_trend=score.trend if score else None,
            score_final=score.final if score else None,
        )

    return payload


def numeric_tokens(text: str) -> List[str]:
    """Every number-shaped token in a string, NORMALISED to a magnitude.

    The generation step feeds this the model's prose and checks each token
    against the injected figures. A number the model produced that isn't one we
    gave it is a hallucination — and a hallucinated figure on a card built to
    be forwarded is the worst failure this feature has.

    Sign and thousands separators are stripped, because prose carries the sign
    in words: "VIX fell 6.83%" is correct English for a -6.83% move, and
    "26690.62" is the same figure as "26,690.62". Comparing raw strings would
    reject well-written copy as a hallucination — which is worse than useless,
    because it would train whoever hits it to disable the guard.

    **What this therefore does NOT catch:** a wrong direction word ("VIX rose
    6.83%"). Deciding which figure a sentence refers to is parsing, not
    validation; the prompt supplies the direction and the reviewer sees the
    card. The guard's job is narrower and mechanical — no invented magnitudes.

    Kept here rather than in the generator so the injected side and the checked
    side share one definition of "a number".
    """
    import re

    return [
        t.lstrip("+-").replace(",", "")
        for t in re.findall(r"[-+]?\d[\d,]*\.?\d*", text)
    ]


def injected_numbers(payload: CardPayload) -> set:
    """Every figure the card legitimately carries, as it renders."""
    out = set()

    def add(s: Optional[str]) -> None:
        if s:
            out.update(numeric_tokens(s))

    for stat in list(payload.indices) + list(payload.winners) + list(payload.losers):
        add(stat.value)
        add(stat.change)
    add(payload.flow_from_value)
    add(payload.flow_to_value)
    if payload.stock:
        add(payload.stock.change)
        for v in (
            payload.stock.score_health,
            payload.stock.score_valuation,
            payload.stock.score_trend,
            payload.stock.score_final,
        ):
            if v is not None:
                out.add(str(v))
    return out
