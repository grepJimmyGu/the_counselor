"""CN company overview service — Phase 3d (2026-06-04).

Returns CompanyOverviewResponse (same shape as US) for CN A-share stocks.
Primary sources: FMP profile + peers (stable). AKShare supplements
financials + news — degrades gracefully on failure.

Reliability:
  1. AKShare imported lazily inside route, never at module level
  2. Every AKShare call in asyncio.to_thread() with 15s timeout
  3. Single asyncio.Lock serialises all AKShare calls (prevent IP bans)
  4. All calls: try/except → logger.exception → safe fallback (None/empty)
  5. In-memory cache: 24h financials, 2h news
  6. Never raises — returns partial response when data is missing
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Optional

from app.schemas.company_overview import (
    BusinessMapSection,
    CompanyOverviewResponse,
    FinancialCheckSection,
    MarketPositionSection,
)
from app.services.fmp_client import FMPClient
from app.services.fundamental_scoring_service import (
    compute_financial_validation_score,
    compute_valuation_risk_score,
    compute_overall_score,
    get_financial_validation_label,
    get_warnings,
)

_log = logging.getLogger("livermore.cn_overview")

_ak_lock = asyncio.Lock()

# ── In-memory cache ────────────────────────────────────────────────────────

_fin_cache: dict[str, tuple[datetime, dict]] = {}
_news_cache: dict[str, tuple[datetime, list[dict]]] = {}
FIN_TTL = timedelta(hours=24)
NEWS_TTL = timedelta(hours=2)


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


# ── AKShare helpers ────────────────────────────────────────────────────────


async def _call_akshare(fn, label: str, timeout_s: float = 15.0):
    try:
        async with _ak_lock:
            return await asyncio.wait_for(
                asyncio.to_thread(fn), timeout=timeout_s,
            )
    except asyncio.TimeoutError:
        _log.warning("cn_overview: %s timed out after %.0fs", label, timeout_s)
        return None
    except Exception:
        _log.exception("cn_overview: %s failed", label)
        return None


# ── Public API ─────────────────────────────────────────────────────────────


async def get_cn_company_overview(symbol: str) -> CompanyOverviewResponse:
    sym = symbol.upper()

    # ── 1. FMP profile (foundation — never depends on AKShare) ──────────
    client = FMPClient()
    profile_raw: dict = {}
    try:
        data = await client._get("/profile", {"symbol": sym})
        if isinstance(data, list) and len(data) > 0:
            profile_raw = dict(data[0])
    except Exception:
        _log.exception("cn_overview: FMP profile failed for %s", sym)

    name = profile_raw.get("companyName", sym)
    sector = profile_raw.get("sector")
    industry = profile_raw.get("industry")
    exchange = profile_raw.get("exchangeFullName", profile_raw.get("exchange", ""))
    country = profile_raw.get("country", "CN")
    website = profile_raw.get("website")
    description = profile_raw.get("description")
    price = _safe_float(profile_raw.get("price"))
    market_cap = profile_raw.get("mktCap")
    pe_ratio = _safe_float(profile_raw.get("pe"))
    employees = profile_raw.get("fullTimeEmployees")

    # ── 2. FMP peers ──────────────────────────────────────────────────
    peers: list[str] = []
    try:
        peers = await client.get_peers(sym)
    except Exception:
        _log.exception("cn_overview: FMP peers failed for %s", sym)

    # ── 3. AKShare financials (best-effort, cached 24h) ────────────────
    code = sym.split(".")[0]
    roe = None
    gross_margin = None
    net_margin = None

    now = datetime.utcnow()
    cached_fin = _fin_cache.get(sym)
    if cached_fin and (now - cached_fin[0]) < FIN_TTL:
        fin = cached_fin[1]
    else:
        try:
            import akshare as ak
        except ImportError:
            fin = {}
        else:
            raw = await _call_akshare(
                lambda: ak.stock_financial_abstract(symbol=code, indicator="盈利能力"),
                label=f"financials({sym})",
            )
            fin = {}
            if raw is not None:
                try:
                    if hasattr(raw, "iloc") and len(raw) > 0:
                        latest = raw.iloc[-1]
                        d = latest.to_dict() if hasattr(latest, "to_dict") else dict(latest)
                        fin = {str(k): _safe_float(v) for k, v in d.items()}
                except Exception:
                    _log.exception("cn_overview: parse financials failed for %s", sym)
            _fin_cache[sym] = (now, fin)

    if fin:
        roe = fin.get("净资产收益率(%)")
        gross_margin = fin.get("销售毛利率(%)")
        net_margin = fin.get("销售净利率(%)")
        if gross_margin is not None:
            gross_margin = gross_margin / 100.0
        if net_margin is not None:
            net_margin = net_margin / 100.0
        if roe is not None:
            roe = roe / 100.0

    # ── 4. AKShare news (best-effort, cached 2h) ───────────────────────
    cached_news = _news_cache.get(sym)
    if cached_news and (now - cached_news[0]) < NEWS_TTL:
        news_articles = cached_news[1]
    else:
        try:
            import akshare as ak  # noqa: F811
        except ImportError:
            news_articles = []
        else:
            raw_news = await _call_akshare(
                lambda: ak.stock_news_em(symbol=code),
                label=f"news({sym})",
            )
            articles: list[dict] = []
            if raw_news is not None:
                try:
                    df = raw_news
                    if hasattr(df, "iloc"):
                        for i in range(min(10, len(df))):
                            row = df.iloc[i]
                            d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                            articles.append({
                                "title": str(d.get("标题", d.get("title", ""))),
                                "time": str(d.get("发布时间", d.get("time", ""))),
                                "source": str(d.get("来源", d.get("source", ""))),
                                "url": str(d.get("新闻链接", d.get("url", ""))),
                            })
                except Exception:
                    _log.exception("cn_overview: parse news failed for %s", sym)
            news_articles = articles
            _news_cache[sym] = (now, news_articles)

    # ── 5. Scoring ────────────────────────────────────────────────────
    # Partial FinancialCheckMetrics — missing FCF, debt ratios, revenue growth
    from app.services.financial_validation_service import FinancialCheckMetrics
    fc = FinancialCheckMetrics(
        pe_ratio=pe_ratio,
        roe=roe,
        gross_margin=gross_margin,
        net_margin=net_margin,
        revenue_yoy=None, eps_yoy=None, eps_growth_years=None,
        operating_margin=None,
        free_cash_flow=None, fcf_conversion=None, fcf_margin=None, fcf_yield=None,
        net_debt=None, debt_to_equity=None, current_ratio=None,
        ps_ratio=None, peg_ratio=None,
    )
    fin_score = compute_financial_validation_score(fc)
    val_risk = compute_valuation_risk_score(fc)
    overall = compute_overall_score(fin_score, val_risk)
    fin_label = get_financial_validation_label(fin_score)

    # ── 6. Assemble ────────────────────────────────────────────────────
    return CompanyOverviewResponse(
        symbol=sym,
        name=name,
        price=price,
        market_cap=int(market_cap) if market_cap else None,
        sector=sector,
        industry=industry,
        exchange=exchange,
        country=country,
        as_of_date=date.today(),
        business_map=BusinessMapSection(
            one_line_summary=description,
            confidence="partial" if fin else "low",
            source_notes=["FMP /stable/profile"]
            + (["AKShare stock_financial_abstract"] if fin else []),
        ),
        market_position=MarketPositionSection(
            key_competitors=peers[:8] if peers else [],
            confidence="high" if peers else "partial",
            source_notes=["FMP /stable/stock-peers"] if peers else [],
        ),
        financial_check=FinancialCheckSection(
            financial_validation_label=fin_label,
            financial_validation_score=fin_score,
            valuation_risk_score=val_risk,
            overall_score=overall,
            pe_ratio=pe_ratio,
            roe=roe,
            gross_margin=gross_margin,
            net_margin=net_margin,
            warnings=get_warnings(fc, val_risk),
            confidence="partial" if fin else "low",
            source_notes=(["FMP /stable/profile"] if pe_ratio else [])
            + (["AKShare stock_financial_abstract"] if fin else []),
        ),
        cn_news=news_articles,
    )
