from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

# Max characters to keep per section before sending to LLM (~3,000 tokens)
_MAX_SECTION_CHARS = 12_000


@dataclass
class FilingSections:
    item1_business: str = ""
    item1a_risk_factors: str = ""
    item7_mda: str = ""

    @property
    def has_content(self) -> bool:
        return bool(self.item1_business or self.item1a_risk_factors or self.item7_mda)

    def combined_for_llm(self) -> str:
        parts = []
        if self.item1_business:
            parts.append(f"=== ITEM 1: BUSINESS ===\n{self.item1_business}")
        if self.item1a_risk_factors:
            parts.append(f"=== ITEM 1A: RISK FACTORS ===\n{self.item1a_risk_factors}")
        if self.item7_mda:
            parts.append(f"=== ITEM 7: MD&A ===\n{self.item7_mda}")
        return "\n\n".join(parts)


def parse_10k_sections(html: str) -> FilingSections:
    """
    Extract Item 1, Item 1A, and Item 7 text from a 10-K HTML filing.
    Uses plain-text splitting on item headings — works across old and iXBRL formats.
    """
    if not html:
        return FilingSections()

    text = _html_to_text(html)
    return _extract_sections(text)


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style noise
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# Patterns that mark the START of each target section
_ITEM_1_START = re.compile(
    r"(?:^|\n)\s*ITEM\s+1\.?\s*(?:BUSINESS|THE BUSINESS)\b",
    re.IGNORECASE,
)
_ITEM_1A_START = re.compile(
    r"(?:^|\n)\s*ITEM\s+1A\.?\s*(?:RISK FACTORS?)\b",
    re.IGNORECASE,
)
_ITEM_2_START = re.compile(
    r"(?:^|\n)\s*ITEM\s+2\.?\s*(?:PROPERTIES|UNREGISTERED|PURCHASES)\b",
    re.IGNORECASE,
)
_ITEM_7_START = re.compile(
    r"(?:^|\n)\s*ITEM\s+7\.?\s*(?:MANAGEMENT|MD&A)\b",
    re.IGNORECASE,
)
_ITEM_7A_START = re.compile(
    r"(?:^|\n)\s*ITEM\s+7A\.?\s*",
    re.IGNORECASE,
)
_ITEM_8_START = re.compile(
    r"(?:^|\n)\s*ITEM\s+8\.?\s*",
    re.IGNORECASE,
)


def _extract_between(text: str, start_pat: re.Pattern, end_pats: list[re.Pattern]) -> str:
    # A 10-K names each item TWICE: once in the table of contents (a short
    # page-number entry) and once as the real section header. `.search()` returns
    # the FIRST hit — the TOC entry — yielding a few hundred chars of page listing
    # instead of the section body, which then starves the LLM (0 edges extracted).
    # Scan ALL start matches and keep the one with the LONGEST body: the TOC entry
    # is tiny, the real section runs to thousands of chars.
    best = ""
    for m_start in start_pat.finditer(text):
        content_start = m_start.end()
        end_pos = len(text)
        for pat in end_pats:
            m_end = pat.search(text, content_start + 200)  # skip 200 chars to avoid false hits
            if m_end and m_end.start() < end_pos:
                end_pos = m_end.start()
        section = text[content_start:end_pos].strip()
        if len(section) > len(best):
            best = section
    return best[:_MAX_SECTION_CHARS]


def _extract_sections(text: str) -> FilingSections:
    item1 = _extract_between(
        text, _ITEM_1_START,
        [_ITEM_1A_START, _ITEM_2_START, _ITEM_7_START],
    )
    item1a = _extract_between(
        text, _ITEM_1A_START,
        [_ITEM_2_START, _ITEM_7_START],
    )
    item7 = _extract_between(
        text, _ITEM_7_START,
        [_ITEM_7A_START, _ITEM_8_START],
    )
    return FilingSections(
        item1_business=item1,
        item1a_risk_factors=item1a,
        item7_mda=item7,
    )
