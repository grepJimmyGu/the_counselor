"""Regression tests for the 10-K section parser (PRD-25, Slice 3).

A 10-K names every item TWICE — once in the table of contents (a page-number
line) and once as the real section header. The original `.search()` grabbed the
FIRST hit (the TOC entry), handing the LLM a few hundred chars of page listing
instead of the section body, so extraction returned 0 supply-chain edges. The fix
scans ALL header matches and keeps the one with the LONGEST body.
"""
from __future__ import annotations

from app.services.filing_section_parser import _extract_sections, parse_10k_sections


def _synthetic_10k() -> str:
    # A table of contents whose entries are padded so consecutive item headers sit
    # >200 chars apart — this is what makes the OLD parser capture a TOC fragment
    # (the 200-char end-search skip lands on the *next TOC line*, not the body).
    pad = " ." * 120  # 240 chars of dotted leader, like a real TOC line
    toc = "TABLE OF CONTENTS\n" + "\n".join(
        f"Item {n}. {name}{pad} {page}"
        for n, name, page in [
            ("1", "Business", "4"),
            ("1A", "Risk Factors", "12"),
            ("1B", "Unresolved Staff Comments", "20"),
            ("2", "Properties", "22"),
            ("3", "Legal Proceedings", "23"),
            ("7", "Management's Discussion and Analysis", "30"),
            ("7A", "Quantitative and Qualitative Disclosures", "40"),
            ("8", "Financial Statements", "42"),
        ]
    ) + "\n"
    # The real section bodies (each unambiguously longer than its TOC entry).
    biz = "Item 1. Business\n" + ("We purchase InP substrates from Acme Corporation, a named supplier. " * 60)
    risk = "Item 1A. Risk Factors\n" + ("We depend on a limited number of qualified suppliers. " * 60)
    props = "Item 2. Properties\nWe lease our headquarters.\n"
    mda = "Item 7. Management's Discussion and Analysis\n" + ("Revenue increased year over year. " * 60)
    q = "Item 7A. Quantitative and Qualitative Disclosures\nWe face market risk.\n"
    fin = "Item 8. Financial Statements\nSee the accompanying notes.\n"
    return "\n".join([toc, biz, risk, props, mda, q, fin])


def test_extract_sections_skips_table_of_contents():
    s = _extract_sections(_synthetic_10k())
    # The REAL bodies, not the TOC page-number lines. Under the old `.search()`,
    # item1_business was a ~240-char run of dotted-leader TOC text with no company
    # names, so these all failed.
    assert "Acme Corporation" in s.item1_business
    assert "limited number of qualified suppliers" in s.item1a_risk_factors
    assert "Revenue increased year over year" in s.item7_mda
    assert len(s.item1_business) > 500  # a real body, not a ~240-char TOC fragment
    assert s.has_content


def test_parse_10k_sections_from_html_skips_toc():
    s = parse_10k_sections(f"<html><body>{_synthetic_10k()}</body></html>")
    assert "Acme Corporation" in s.item1_business
    assert s.has_content


def test_parse_empty_html_returns_no_content():
    s = parse_10k_sections("")
    assert not s.has_content
    assert s.item1_business == ""
