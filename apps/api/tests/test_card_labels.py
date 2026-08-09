"""Bilingual card labels — the map the model is never allowed to produce.

A model asked to translate "Technology" returns 科技 one day and 技术 the
next. Each card looks fine alone; only someone comparing two days sees it. So
sectors, index names and section headings are a fixed lookup, and these tests
pin the lookup to the data that feeds it.
"""
from __future__ import annotations

import pytest

from app.services.card_labels import (
    CHROME,
    EN,
    INDEX_LABELS,
    LANGUAGES,
    SECTOR_ZH,
    ZH,
    chrome,
    date_label,
    index_label,
    sector_label,
)
from app.services.daily_brief_service import INDEX_SYMBOLS, VIX_SYMBOL
from app.services.market_pulse_service import US_SECTORS


def test_every_live_sector_has_a_chinese_name():
    """The card's data comes from `US_SECTORS`. A sector added or renamed
    upstream must fail HERE, not silently print an English name onto the
    Chinese card."""
    missing = [name for _, name in US_SECTORS if name not in SECTOR_ZH]
    assert not missing, f"US_SECTORS has {missing} with no Chinese label"


def test_no_orphan_translations():
    """The reverse: a key we translate that no longer exists upstream is dead
    weight that outlives the rename it was written for."""
    live = {name for _, name in US_SECTORS}
    orphans = [k for k in SECTOR_ZH if k not in live]
    assert not orphans, f"SECTOR_ZH translates {orphans}, absent from US_SECTORS"


def test_every_card_index_has_both_languages():
    for sym, _ in INDEX_SYMBOLS:
        assert sym in INDEX_LABELS, f"{sym} renders on the card with no label"
    assert VIX_SYMBOL in INDEX_LABELS
    for sym, entry in INDEX_LABELS.items():
        assert set(entry) == set(LANGUAGES), f"{sym} is missing a language"


def test_every_chrome_string_has_both_languages():
    for key, entry in CHROME.items():
        assert set(entry) == set(LANGUAGES), f"chrome '{key}' is missing a language"
        assert all(v.strip() for v in entry.values()), f"chrome '{key}' has an empty string"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_lookup_never_returns_empty(lang):
    """An empty label renders as a blank slot on a card that gets forwarded —
    worse than an untranslated one."""
    for _, name in US_SECTORS:
        assert sector_label(name, lang).strip()
    for sym in INDEX_LABELS:
        assert index_label(sym, lang).strip()


def test_untranslated_sector_falls_back_to_english_not_blank():
    assert sector_label("Newly Added Sector", ZH) == "Newly Added Sector"


def test_chinese_labels_are_actually_chinese():
    """Guards a copy-paste that leaves an English string in the ZH column —
    invisible in review, obvious to a reader."""
    for name, zh in SECTOR_ZH.items():
        assert any("一" <= ch <= "鿿" for ch in zh), f"{name} -> {zh!r} has no CJK"


def test_date_label_matches_the_prompt_format():
    # Both prompts specify `26.7.31 · 周五` — two-digit year, no zero padding.
    assert date_label("2026-07-31", ZH) == "26.7.31 · 周五"
    assert date_label("2026-07-31", EN) == "26.7.31 · Friday"


def test_date_label_weekday_is_computed_not_assumed():
    assert date_label("2026-08-10", EN).endswith("Monday")
    assert date_label("2026-08-10", ZH).endswith("周一")


def test_disclaimer_is_carried_verbatim():
    """A compliance line, not copy to be improved by the next editor."""
    assert chrome("disclaimer", ZH) == "仅个人复盘记录，不构成任何投资建议。"
    assert "Not investment advice" in chrome("disclaimer", EN)
