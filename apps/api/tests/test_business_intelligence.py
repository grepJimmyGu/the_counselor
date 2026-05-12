from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.filing_section_parser import FilingSections, parse_10k_sections


# ── Section parser ────────────────────────────────────────────────────────────

SAMPLE_10K = """
<html><body>
<p>Table of Contents</p>

<p>ITEM 1. BUSINESS</p>
<p>Acme Corp designs and sells widgets worldwide. We generate revenue primarily through
direct product sales to enterprise customers. Our customers include large manufacturers
and government agencies. We have pricing power due to our proprietary technology.</p>

<p>ITEM 1A. RISK FACTORS</p>
<p>Our business faces risks including supply chain disruption, competition from low-cost
manufacturers, and regulatory changes in key markets. Currency fluctuations may impact
our international revenue.</p>

<p>ITEM 2. PROPERTIES</p>
<p>We lease 500,000 sq ft of office space globally.</p>

<p>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</p>
<p>Revenue grew 15% year over year driven by strong enterprise demand. We expect
continued growth in the widget market which we estimate at $50B globally. We hold
a top-3 position in our primary markets.</p>

<p>ITEM 7A. QUANTITATIVE DISCLOSURES</p>
<p>Interest rate risk...</p>

<p>ITEM 8. FINANCIAL STATEMENTS</p>
</body></html>
"""


def test_parser_extracts_all_three_sections():
    sections = parse_10k_sections(SAMPLE_10K)
    assert sections.has_content
    assert "widgets" in sections.item1_business.lower()
    assert "supply chain" in sections.item1a_risk_factors.lower()
    assert "revenue grew" in sections.item7_mda.lower()


def test_parser_stops_at_section_boundaries():
    sections = parse_10k_sections(SAMPLE_10K)
    # Item 1 should NOT contain Item 2 content
    assert "500,000 sq ft" not in sections.item1_business
    # Item 7 should NOT contain Item 8 content
    assert "FINANCIAL STATEMENTS" not in sections.item7_mda


def test_parser_returns_empty_on_blank_html():
    sections = parse_10k_sections("")
    assert not sections.has_content
    assert sections.item1_business == ""


def test_parser_handles_malformed_html():
    sections = parse_10k_sections("<html><body>No items here</body></html>")
    assert not sections.has_content


def test_combined_for_llm_includes_labels():
    sections = FilingSections(
        item1_business="Business content here",
        item1a_risk_factors="Risk content here",
        item7_mda="",
    )
    combined = sections.combined_for_llm()
    assert "ITEM 1: BUSINESS" in combined
    assert "ITEM 1A: RISK FACTORS" in combined
    assert "ITEM 7" not in combined  # empty section omitted


def test_section_truncation():
    long_text = "A" * 20_000
    html = f"<html><body><p>ITEM 1. BUSINESS</p><p>{long_text}</p><p>ITEM 1A. RISK FACTORS</p></body></html>"
    sections = parse_10k_sections(html)
    assert len(sections.item1_business) <= 12_000


# ── BusinessIntelligenceService ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bi_service_returns_none_when_fmp_not_configured():
    from app.services.business_intelligence_service import BusinessIntelligenceService
    from app.services.fmp_client import FMPNotConfiguredError
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None  # no cache

    with patch("app.services.business_intelligence_service.FMPClient") as MockFMP:
        mock_fmp = AsyncMock()
        mock_fmp.get_sec_filings.side_effect = FMPNotConfiguredError("no key")
        MockFMP.return_value = mock_fmp
        svc = BusinessIntelligenceService()
        result = await svc.get("AAPL", db)
        assert result is None


@pytest.mark.asyncio
async def test_bi_service_returns_low_confidence_when_filing_download_fails():
    from app.services.business_intelligence_service import BusinessIntelligenceService
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None

    with patch("app.services.business_intelligence_service.FMPClient") as MockFMP, \
         patch("app.services.business_intelligence_service.fetch_filing_html", return_value=""), \
         patch("app.services.business_intelligence_service.get_llm_gateway"):
        mock_fmp = AsyncMock()
        mock_fmp.get_sec_filings.return_value = [{"finalLink": "https://sec.gov/test.htm", "dateFiled": "2024-01-01"}]
        MockFMP.return_value = mock_fmp
        svc = BusinessIntelligenceService()
        result = await svc.get("AAPL", db)
        assert result is not None
        assert result.confidence == "low"


@pytest.mark.asyncio
async def test_bi_service_returns_high_confidence_on_success():
    from app.services.business_intelligence_service import BusinessIntelligenceService
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None
    db.execute.return_value  # for the INSERT

    llm_payload = {
        "one_line_summary": "Acme sells widgets to enterprises.",
        "revenue_model": "Direct product sales",
        "customer_types": ["Enterprise", "Government"],
        "pricing_power_implication": "Strong pricing power from proprietary tech.",
        "market_category": "Industrial widgets",
        "market_size_estimate": "$50B",
        "market_growth_label": "growing",
        "competitive_position_label": "top 3 player",
        "market_share_notes": "Top-3 in primary markets",
        "key_growth_drivers": ["Enterprise demand", "International expansion"],
        "key_risks": ["Supply chain", "Competition"],
    }

    with patch("app.services.business_intelligence_service.FMPClient") as MockFMP, \
         patch("app.services.business_intelligence_service.fetch_filing_html", return_value=SAMPLE_10K), \
         patch("app.services.business_intelligence_service.get_llm_gateway") as mock_gw:
        mock_fmp = AsyncMock()
        mock_fmp.get_sec_filings.return_value = [{"finalLink": "https://sec.gov/test.htm", "dateFiled": "2024-01-01"}]
        MockFMP.return_value = mock_fmp

        mock_gateway = AsyncMock()
        mock_gateway.is_enabled = True
        mock_gateway.generate_json = AsyncMock(return_value=llm_payload)
        mock_gw.return_value = mock_gateway

        svc = BusinessIntelligenceService()
        result = await svc.get("AAPL", db)

        assert result is not None
        assert result.confidence == "high"
        assert result.one_line_summary == "Acme sells widgets to enterprises."
        assert result.market_size_estimate == "$50B"
        assert result.competitive_position_label == "top 3 player"
        assert "Enterprise" in result.customer_types
