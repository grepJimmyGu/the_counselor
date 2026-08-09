"""The prose half of the daily share card — prompts and validation.

The model writes sentences. It never writes a figure and never names a sector
or an index; those are injected by `daily_card_service` and `card_labels`. This
module builds the prompt that says so, and enforces it afterwards rather than
trusting it.

**Native, not translated.** English and Chinese are generated independently
from the same figures. A Chinese card translated from English reads translated
— 資金流向, 領漲, 大盤 are the words a Chinese reader expects, and English-first
prose doesn't land on them. Two generations a day is the whole cost.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.services.card_labels import EN, ZH
from app.services.daily_card_service import (
    CardPayload,
    injected_numbers,
    numeric_tokens,
)

logger = logging.getLogger("livermore.card_copy")

# Fields the model returns. Every one is prose; none may contain a figure we
# didn't supply.
TEXT_FIELDS = (
    "headline",
    "subtitle",
    "market_note",
    "money_flow_note",
    "stock_takeaway",
    "stock_annotation",
    "takeaway_body",
    "takeaway_highlight",
)
LIST_FIELDS = ("stock_points",)


@dataclass
class CardCopy:
    headline: str = ""
    subtitle: str = ""
    market_note: str = ""
    money_flow_note: str = ""
    stock_points: List[str] = field(default_factory=list)
    stock_takeaway: str = ""
    stock_annotation: str = ""
    drivers: List[Dict[str, str]] = field(default_factory=list)
    takeaway_body: str = ""
    takeaway_highlight: str = ""
    """Fields dropped by the numeric guard. Surfaced rather than silent — a
    card missing its headline should be visible in the log, not a mystery."""
    rejected: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_SYSTEM = {
    EN: (
        "You write the prose for a daily US market recap card — an independent "
        "builder's research notebook, not financial media, not a brokerage note, "
        "and never stock-picking advice. Plain English a beginner can follow.\n\n"
        "HARD RULES:\n"
        "1. NEVER write a number that was not given to you. Reference the "
        "figures in the DATA block verbatim, or describe the move in words.\n"
        "2. NEVER name a sector or an index. The card renders those itself.\n"
        "3. Say what happened and why you think it happened. If the data does "
        "not support a reason, say less rather than inventing one.\n"
        "4. Return ONLY a JSON object. No markdown, no commentary."
    ),
    ZH: (
        "你在为一张「每日美股复盘」知识卡片撰写文案——独立开发者的研究笔记，"
        "不是财经媒体，不是券商研报，更不是荐股。用大白话解释，"
        "让没有投资背景的人也能看懂。\n\n"
        "硬性规则：\n"
        "1. 绝对不要写出没有提供给你的数字。引用 DATA 中给出的数值原文，"
        "或者用文字描述涨跌。\n"
        "2. 绝对不要写出板块名或指数名，卡片会自己渲染这些名称。\n"
        "3. 说清楚今天发生了什么、你认为为什么会发生。"
        "如果数据不足以支撑某个原因，就少写，不要编。\n"
        "4. 只返回一个 JSON 对象，不要 markdown，不要额外说明。"
    ),
}

_SHAPE = {
    "headline": "the day's biggest story, one punchy line",
    "subtitle": "one sentence of context, clearly secondary to the headline",
    "market_note": "one plain-language sentence on the tape and the mood",
    "money_flow_note": "one or two sentences on where money moved and why",
    "stock_points": "3-5 short bullet strings about the featured stock",
    "stock_takeaway": "one sentence — what this move actually means",
    "stock_annotation": "a short handwritten-style aside, the author thinking aloud",
    "drivers": "list of {title, body} — ONLY reasons supported by the NEWS block; omit entirely if absent",
    "takeaway_body": "two sentences closing the day",
    "takeaway_highlight": "the single phrase worth remembering, under 8 words",
}


def build_prompt(
    payload: CardPayload,
    *,
    news: Optional[List[Dict[str, str]]] = None,
) -> tuple:
    """(system, user). The DATA block carries figures as the strings the card
    renders, so the model can quote one rather than reformatting a float and
    disagreeing with the card beside it."""
    lang = payload.lang
    data: Dict[str, Any] = {
        "date": payload.date_label,
        "indices": [
            {"name": s.label, "level": s.value, "change": s.change} for s in payload.indices
        ],
        "sectors_up": [{"name": s.label, "change": s.value} for s in payload.winners],
        "sectors_down": [{"name": s.label, "change": s.value} for s in payload.losers],
    }
    if payload.flow_from and payload.flow_to:
        data["money_flow"] = {
            "out_of": payload.flow_from,
            "into": payload.flow_to,
            "chaikin_out": payload.flow_from_value,
            "chaikin_into": payload.flow_to_value,
        }
    if payload.stock:
        data["featured_stock"] = {
            "symbol": payload.stock.symbol,
            "change": payload.stock.change,
            "score_fundamentals": payload.stock.score_health,
            "score_valuation": payload.stock.score_valuation,
            "score_trend": payload.stock.score_trend,
        }

    parts = [
        "DATA (every figure you may use; quote them exactly):",
        json.dumps(data, ensure_ascii=False, indent=1),
    ]
    if news:
        parts += [
            "",
            "NEWS (the only basis for `drivers` and `stock_points`):",
            json.dumps(news, ensure_ascii=False, indent=1),
        ]
    else:
        # Rule 2 of the spec: a section with no source collapses.
        parts += [
            "",
            "NEWS: none available. Return `drivers` as an empty list and keep "
            "`stock_points` to what the DATA itself supports. Do not invent "
            "reasons, earnings figures, or company events.",
        ]
    parts += ["", "Return JSON with exactly these keys:", json.dumps(_SHAPE, indent=1)]

    return _SYSTEM.get(lang, _SYSTEM[EN]), "\n".join(parts)


def _violations(text: str, allowed: set) -> List[str]:
    return [t for t in numeric_tokens(text) if t not in allowed]


def allowed_numbers(
    payload: CardPayload, news: Optional[List[Dict[str, str]]] = None
) -> set:
    """Every figure the model may legitimately write.

    Two sources, not one. The card's own figures are obvious. The NEWS block is
    the second — and omitting it was a real hole: Jimmy's own example copy says
    "biggest one-day gain since 2008" and "Azure revenue grew 43%". Both are
    correct, both come from articles we handed the model, and neither is a
    number we computed. A guard that rejected them would fire on almost every
    well-written card, and a guard that cries wolf gets switched off.

    So the boundary is *provenance*, not arithmetic: the model may quote any
    figure we gave it, from either source, and may invent none. It can still
    misattribute a news figure — catching that would mean parsing the article,
    which is the same line we drew on direction words.
    """
    allowed = injected_numbers(payload)
    for item in news or []:
        for value in item.values():
            if isinstance(value, str):
                allowed.update(numeric_tokens(value))
    return allowed


def validate_copy(
    raw: Dict[str, Any],
    payload: CardPayload,
    news: Optional[List[Dict[str, str]]] = None,
) -> CardCopy:
    """Drop any field carrying a figure we didn't supply.

    Per-field rather than all-or-nothing: one bad sentence shouldn't cost the
    whole card, and a dropped section is already the spec's behaviour for a
    section with no source. What must never happen is an invented figure
    reaching a card built to be forwarded.
    """
    allowed = allowed_numbers(payload, news)
    copy = CardCopy()

    for key in TEXT_FIELDS:
        val = raw.get(key)
        if not isinstance(val, str) or not val.strip():
            continue
        bad = _violations(val, allowed)
        if bad:
            copy.rejected.append(key)
            logger.warning("card copy: dropped %s — invented figures %s", key, bad)
            continue
        setattr(copy, key, val.strip())

    for key in LIST_FIELDS:
        items = raw.get(key)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            if not isinstance(item, str) or not item.strip():
                continue
            bad = _violations(item, allowed)
            if bad:
                copy.rejected.append(f"{key}[]")
                logger.warning("card copy: dropped a %s item — invented %s", key, bad)
                continue
            kept.append(item.strip())
        setattr(copy, key, kept)

    for item in raw.get("drivers") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title and not body:
            continue
        bad = _violations(f"{title} {body}", allowed)
        if bad:
            copy.rejected.append("drivers[]")
            logger.warning("card copy: dropped a driver — invented %s", bad)
            continue
        copy.drivers.append({"title": title, "body": body})

    return copy
