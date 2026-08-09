"""Bilingual labels for the daily share card.

**Every proper noun on the card comes from here, never from the model.**

The card is generated in English and Chinese. The prose is written natively in
each language by the LLM — a translated Chinese card reads translated, and
資金流向 / 領漲 are the words a Chinese reader expects. But the *names* must be
a fixed lookup, because a model asked to translate "Technology" will return
科技 one day and 技术 or 科技板块 the next. Nothing catches that: each card
looks fine alone, and only someone comparing two days sees the brand wobble.
Worse, a mistranslated sector is a factual error on a card built to be
forwarded.

So the rule from the numbers extends to names: **the model emits no figures
and no proper nouns.** It writes sentences around slots we fill.

Keys are the exact display strings our data produces — `US_SECTORS` in
`market_pulse_service` for sectors, `INDEX_SYMBOLS` in `daily_brief_service`
for indices. `tests/test_card_labels.py` pins that correspondence, so renaming
a sector upstream fails the build instead of silently emitting an English name
onto the Chinese card.
"""
from __future__ import annotations

from typing import Dict

EN = "en"
ZH = "zh"
LANGUAGES = (EN, ZH)

# Sector display name -> Chinese. Keys mirror `US_SECTORS` exactly.
SECTOR_ZH: Dict[str, str] = {
    "Technology": "科技",
    "Communication": "通信服务",
    "Consumer Disc.": "可选消费",
    "Consumer Staples": "必需消费",
    "Healthcare": "医疗",
    "Financials": "金融",
    "Industrials": "工业",
    "Energy": "能源",
    "Materials": "材料",
    "Real Estate": "房地产",
    "Utilities": "公用事业",
}

# Index symbol -> display name per language. The English side is deliberately
# NOT the raw `name` off the quote ("NASDAQ Composite" vs "Nasdaq Composite")
# so the card's typography stays consistent whatever FMP returns.
INDEX_LABELS: Dict[str, Dict[str, str]] = {
    "^DJI": {EN: "Dow Jones", ZH: "道琼斯"},
    "^GSPC": {EN: "S&P 500", ZH: "标普500"},
    "^IXIC": {EN: "Nasdaq", ZH: "纳斯达克"},
    "^VIX": {EN: "VIX", ZH: "VIX 恐慌指数"},
}

# Fixed card chrome. Section headings, standing copy, the disclaimer.
CHROME: Dict[str, Dict[str, str]] = {
    "masthead": {EN: "Daily U.S. Market Recap · Livermore", ZH: "每日美股复盘 · Livermore"},
    "market_performance": {EN: "Market Performance", ZH: "大盘表现"},
    "sectors": {EN: "Sector Performance", ZH: "盘面板块"},
    "winners": {EN: "WINNERS", ZH: "上涨板块"},
    "losers": {EN: "LOSERS", ZH: "下跌板块"},
    "money_flow": {EN: "Money Flow", ZH: "资金逻辑"},
    "stock_of_day": {EN: "Stock of the Day", ZH: "今日代表个股"},
    "score": {EN: "Livermore 3-Dimensional Score", ZH: "Livermore 三维评分"},
    "score_health": {EN: "Fundamentals / Health", ZH: "健康度 / 基本面"},
    "score_valuation": {EN: "Valuation", ZH: "估值"},
    "score_trend": {EN: "Trend", ZH: "趋势"},
    "drivers": {EN: "Three Drivers Behind Today's Move", ZH: "驱动行情的3个关键因素"},
    "takeaway": {EN: "Today's Takeaway", ZH: "今日结论"},
    "source": {EN: "Market data & analysis: Livermore", ZH: "数据 & 分析：Livermore"},
    "explore": {EN: "Explore the full analysis →", ZH: "查看完整分析 →"},
    # Kept verbatim from Jimmy's two prompts — this is a compliance line, not
    # copy to be improved by whoever next edits the card.
    "disclaimer": {
        EN: "Personal market review only. Not investment advice.",
        ZH: "仅个人复盘记录，不构成任何投资建议。",
    },
}

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEKDAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def sector_label(name: str, lang: str) -> str:
    """Chinese where we have it, the English name otherwise.

    A missing key falls through to English rather than raising: a sector we
    haven't translated should still render its data on the card. The contract
    test is what stops that fallback becoming permanent — it fails the moment
    `US_SECTORS` gains a name this map lacks.
    """
    if lang == ZH:
        return SECTOR_ZH.get(name, name)
    return name


def index_label(symbol: str, lang: str, fallback: str = "") -> str:
    entry = INDEX_LABELS.get(symbol)
    if entry:
        return entry.get(lang, entry[EN])
    return fallback or symbol


def chrome(key: str, lang: str) -> str:
    entry = CHROME.get(key)
    if not entry:
        return key
    return entry.get(lang, entry[EN])


def date_label(iso_date: str, lang: str) -> str:
    """`26.7.31 · 周五` / `26.7.31 · Friday` — the header stamp from both
    prompts. Deliberately the two-digit year and no zero padding, matching the
    notebook-header feel rather than an ISO stamp."""
    from datetime import date as _date

    d = _date.fromisoformat(iso_date)
    stem = f"{d.year % 100}.{d.month}.{d.day}"
    day = (WEEKDAY_ZH if lang == ZH else WEEKDAY_EN)[d.weekday()]
    return f"{stem} · {day}"
