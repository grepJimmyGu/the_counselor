from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.fmp_client import FMPClient, FMPError, FMPNotConfiguredError, FMPRateLimitError
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway
from app.services.sec_edgar_client import fetch_filing_html
from app.services.filing_section_parser import parse_10k_sections

logger = logging.getLogger(__name__)

_CACHE_TTL_DAYS = 90  # 10-K is annual; re-fetch after 90 days

_SYSTEM_PROMPT = """You are a financial analyst extracting structured business intelligence from SEC 10-K filings.

Extract the following fields from the provided filing sections. Return ONLY a valid JSON object — no preamble, no markdown.

Rules:
- Use only information explicitly stated in the filing. Do not infer or fabricate.
- Keep text fields to 1-2 sentences maximum.
- Lists: 3-6 items maximum.
- Use null for any field not clearly stated in the text.
- For market_growth_label choose exactly one: "fast-growing" | "growing" | "stable" | "declining" | "cyclical" | "unclear"
- For competitive_position_label choose exactly one: "market leader" | "top 3 player" | "significant player" | "niche player" | "unclear"
- For upstream_suppliers: list named suppliers/manufacturers mentioned (e.g. "TSMC", "Foxconn"). Use short proper names. Max 6.
- For downstream_customers: list named customers or customer segments (e.g. "Apple", "Enterprise", "US Carriers"). Max 6.

Return JSON with exactly this shape:
{
  "one_line_summary": "One sentence: what the company does and how it makes money.",
  "revenue_model": "How the company generates revenue (subscription, transaction fees, product sales, licensing, etc.).",
  "customer_types": ["type1", "type2"],
  "pricing_power_implication": "1-2 sentences on pricing power evidence from the filing.",
  "market_category": "The primary industry/market segment this company competes in.",
  "market_size_estimate": "Market size if explicitly stated (e.g. '$50B TAM'), otherwise null.",
  "market_growth_label": "fast-growing|growing|stable|declining|cyclical|unclear",
  "competitive_position_label": "market leader|top 3 player|significant player|niche player|unclear",
  "market_share_notes": "Any market share data or competitive position statements, or null.",
  "key_growth_drivers": ["driver1", "driver2", "driver3"],
  "key_risks": ["risk1", "risk2", "risk3"],
  "upstream_suppliers": ["Supplier A", "Supplier B"],
  "downstream_customers": ["Customer A", "Customer B"]
}"""


@dataclass
class BusinessIntelligence:
    symbol: str
    filing_type: str = "10-K"
    filing_date: Optional[str] = None
    filing_url: Optional[str] = None
    one_line_summary: Optional[str] = None
    revenue_model: Optional[str] = None
    customer_types: list[str] = field(default_factory=list)
    pricing_power_implication: Optional[str] = None
    market_category: Optional[str] = None
    market_size_estimate: Optional[str] = None
    market_growth_label: Optional[str] = None
    competitive_position_label: Optional[str] = None
    market_share_notes: Optional[str] = None
    key_growth_drivers: list[str] = field(default_factory=list)
    key_risks: list[str] = field(default_factory=list)
    upstream_suppliers: list[str] = field(default_factory=list)
    downstream_customers: list[str] = field(default_factory=list)
    confidence: str = "partial"
    source_notes: list[str] = field(default_factory=list)


class BusinessIntelligenceService:
    def __init__(self) -> None:
        self._fmp = FMPClient()
        self._gateway = get_llm_gateway()

    async def get(self, symbol: str, db: Session) -> BusinessIntelligence | None:
        sym = symbol.upper()

        cached = _load_cache(sym, db)
        if cached:
            return cached

        bi = await self._fetch_and_analyze(sym)
        if bi:
            _save_cache(bi, db)
        return bi

    async def _fetch_and_analyze(self, symbol: str) -> BusinessIntelligence | None:
        # 1. Get latest 10-K filing URL from FMP
        filing_url: str | None = None
        filing_date: str | None = None
        try:
            filings = await self._fmp.get_sec_filings(symbol, filing_type="10-K", limit=1)
            if filings:
                filing_url = filings[0].get("finalLink") or filings[0].get("link")
                filing_date = filings[0].get("dateFiled")
        except (FMPNotConfiguredError, FMPRateLimitError, FMPError) as exc:
            logger.warning("FMP sec-filings failed for %s: %s", symbol, exc)
            return None

        if not filing_url:
            logger.info("No 10-K filing URL found for %s", symbol)
            return None

        # 2. Fetch filing HTML from EDGAR
        html = await fetch_filing_html(filing_url)
        if not html:
            return BusinessIntelligence(
                symbol=symbol,
                filing_url=filing_url,
                filing_date=filing_date,
                confidence="low",
                source_notes=["Filing download failed — EDGAR unreachable or filing too large"],
            )

        # 3. Parse relevant sections
        sections = parse_10k_sections(html)
        if not sections.has_content:
            logger.info("Section parser found no content for %s", symbol)
            return BusinessIntelligence(
                symbol=symbol,
                filing_url=filing_url,
                filing_date=filing_date,
                confidence="low",
                source_notes=["Section extraction failed — filing format not recognized"],
            )

        # 4. LLM extraction
        if not self._gateway.is_enabled:
            return BusinessIntelligence(
                symbol=symbol,
                filing_url=filing_url,
                filing_date=filing_date,
                confidence="low",
                source_notes=["LLM not configured — raw filing retrieved but not analyzed"],
            )

        combined_text = sections.combined_for_llm()
        user_prompt = (
            f"Extract business intelligence for {symbol} from this 10-K filing:\n\n"
            + combined_text
        )

        try:
            payload = await self._gateway.generate_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.1,
            )
        except LLMAdapterError as exc:
            logger.warning("LLM extraction failed for %s: %s", symbol, exc)
            return BusinessIntelligence(
                symbol=symbol,
                filing_url=filing_url,
                filing_date=filing_date,
                confidence="low",
                source_notes=[f"LLM extraction failed: {type(exc).__name__}"],
            )

        return BusinessIntelligence(
            symbol=symbol,
            filing_type="10-K",
            filing_date=filing_date,
            filing_url=filing_url,
            one_line_summary=payload.get("one_line_summary"),
            revenue_model=payload.get("revenue_model"),
            customer_types=payload.get("customer_types") or [],
            pricing_power_implication=payload.get("pricing_power_implication"),
            market_category=payload.get("market_category"),
            market_size_estimate=payload.get("market_size_estimate"),
            market_growth_label=payload.get("market_growth_label"),
            competitive_position_label=payload.get("competitive_position_label"),
            market_share_notes=payload.get("market_share_notes"),
            key_growth_drivers=payload.get("key_growth_drivers") or [],
            key_risks=payload.get("key_risks") or [],
            upstream_suppliers=payload.get("upstream_suppliers") or [],
            downstream_customers=payload.get("downstream_customers") or [],
            confidence="high",
            source_notes=[
                f"SEC 10-K filed {filing_date or 'date unknown'}",
                "Extracted: Item 1 (Business), Item 1A (Risk Factors), Item 7 (MD&A)",
                "Analysis by LLM — verify material facts with primary source",
            ],
        )


# ── DB cache helpers ──────────────────────────────────────────────────────────

def _load_cache(symbol: str, db: Session) -> BusinessIntelligence | None:
    now = datetime.utcnow()
    row = db.execute(
        text(
            "SELECT symbol, filing_type, filing_date, filing_url,"
            " one_line_summary, revenue_model, customer_types,"
            " pricing_power_implication, market_category, market_size_estimate,"
            " market_growth_label, competitive_position_label, market_share_notes,"
            " key_growth_drivers, key_risks,"
            " upstream_suppliers, downstream_customers,"
            " confidence, source_notes"
            " FROM company_business_intelligence"
            " WHERE symbol = :sym AND expires_at > :now"
            " ORDER BY created_at DESC LIMIT 1"
        ),
        {"sym": symbol, "now": now},
    ).fetchone()

    if not row:
        return None

    r = row._mapping  # type: ignore[attr-defined]

    def _jl(v):
        if v is None:
            return []
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []

    return BusinessIntelligence(
        symbol=r["symbol"],
        filing_type=r["filing_type"] or "10-K",
        filing_date=r.get("filing_date"),
        filing_url=r.get("filing_url"),
        one_line_summary=r.get("one_line_summary"),
        revenue_model=r.get("revenue_model"),
        customer_types=_jl(r.get("customer_types")),
        pricing_power_implication=r.get("pricing_power_implication"),
        market_category=r.get("market_category"),
        market_size_estimate=r.get("market_size_estimate"),
        market_growth_label=r.get("market_growth_label"),
        competitive_position_label=r.get("competitive_position_label"),
        market_share_notes=r.get("market_share_notes"),
        key_growth_drivers=_jl(r.get("key_growth_drivers")),
        key_risks=_jl(r.get("key_risks")),
        upstream_suppliers=_jl(r.get("upstream_suppliers")),
        downstream_customers=_jl(r.get("downstream_customers")),
        confidence=r.get("confidence") or "partial",
        source_notes=_jl(r.get("source_notes")),
    )


def _save_cache(bi: BusinessIntelligence, db: Session) -> None:
    expires_at = datetime.utcnow() + timedelta(days=_CACHE_TTL_DAYS)
    try:
        db.execute(
            text(
                "INSERT INTO company_business_intelligence"
                " (symbol, filing_type, filing_date, filing_url,"
                "  one_line_summary, revenue_model, customer_types,"
                "  pricing_power_implication, market_category, market_size_estimate,"
                "  market_growth_label, competitive_position_label, market_share_notes,"
                "  key_growth_drivers, key_risks,"
                "  upstream_suppliers, downstream_customers,"
                "  confidence, source_notes, expires_at)"
                " VALUES"
                " (:symbol, :filing_type, :filing_date, :filing_url,"
                "  :one_line_summary, :revenue_model, :customer_types,"
                "  :pricing_power_implication, :market_category, :market_size_estimate,"
                "  :market_growth_label, :competitive_position_label, :market_share_notes,"
                "  :key_growth_drivers, :key_risks,"
                "  :upstream_suppliers, :downstream_customers,"
                "  :confidence, :source_notes, :expires_at)"
                " ON CONFLICT (symbol) DO UPDATE SET"
                "  filing_type = EXCLUDED.filing_type,"
                "  filing_date = EXCLUDED.filing_date,"
                "  filing_url = EXCLUDED.filing_url,"
                "  one_line_summary = EXCLUDED.one_line_summary,"
                "  revenue_model = EXCLUDED.revenue_model,"
                "  customer_types = EXCLUDED.customer_types,"
                "  pricing_power_implication = EXCLUDED.pricing_power_implication,"
                "  market_category = EXCLUDED.market_category,"
                "  market_size_estimate = EXCLUDED.market_size_estimate,"
                "  market_growth_label = EXCLUDED.market_growth_label,"
                "  competitive_position_label = EXCLUDED.competitive_position_label,"
                "  market_share_notes = EXCLUDED.market_share_notes,"
                "  key_growth_drivers = EXCLUDED.key_growth_drivers,"
                "  key_risks = EXCLUDED.key_risks,"
                "  upstream_suppliers = EXCLUDED.upstream_suppliers,"
                "  downstream_customers = EXCLUDED.downstream_customers,"
                "  confidence = EXCLUDED.confidence,"
                "  source_notes = EXCLUDED.source_notes,"
                "  expires_at = EXCLUDED.expires_at,"
                "  created_at = CURRENT_TIMESTAMP"
            ),
            {
                "symbol": bi.symbol,
                "filing_type": bi.filing_type,
                "filing_date": bi.filing_date,
                "filing_url": bi.filing_url,
                "one_line_summary": bi.one_line_summary,
                "revenue_model": bi.revenue_model,
                "customer_types": json.dumps(bi.customer_types),
                "pricing_power_implication": bi.pricing_power_implication,
                "market_category": bi.market_category,
                "market_size_estimate": bi.market_size_estimate,
                "market_growth_label": bi.market_growth_label,
                "competitive_position_label": bi.competitive_position_label,
                "market_share_notes": bi.market_share_notes,
                "key_growth_drivers": json.dumps(bi.key_growth_drivers),
                "key_risks": json.dumps(bi.key_risks),
                "upstream_suppliers": json.dumps(bi.upstream_suppliers),
                "downstream_customers": json.dumps(bi.downstream_customers),
                "confidence": bi.confidence,
                "source_notes": json.dumps(bi.source_notes),
                "expires_at": expires_at,
            },
        )
        db.commit()
    except Exception as exc:
        logger.warning("Failed to cache business intelligence for %s: %s", bi.symbol, exc)
        db.rollback()
