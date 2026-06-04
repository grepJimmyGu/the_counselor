"""CN company overview service — Phase 3d (2026-06-04).

Returns CompanyOverviewResponse (same shape as US) for CN A-share stocks.
Primary sources: FMP profile + peers (stable). AKShare supplements
financials + news — degrades gracefully on failure.

V1 i18n (2026-06-04): all user-visible content rendered in Chinese.
  - Company name, peer names → local CSV lookup
  - Sector, industry → mapping table (11 US sectors → CN)
  - Exchange → derived from .SS/.SZ suffix
  - Financial summaries → Chinese string builders (no LLM)
  - Scoring labels + warnings → Chinese locale helpers
  - Business Map + Market Position qualitative fields → skipped (US 10-K path)

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
import csv
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
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
)

_log = logging.getLogger("livermore.cn_overview")

_ak_lock = asyncio.Lock()

# ── In-memory cache ────────────────────────────────────────────────────────

_fin_cache: dict[str, tuple[datetime, dict]] = {}
_news_cache: dict[str, tuple[datetime, list[dict]]] = {}
FIN_TTL = timedelta(hours=24)
NEWS_TTL = timedelta(hours=2)

# ── CN name lookup (from local CSVs, loaded once) ──────────────────────────

_cn_name_map: dict[str, str] = {}  # symbol → Chinese name
_cn_exchange_map: dict[str, str] = {}  # symbol → "上海证券交易所" / "深圳证券交易所"


def _load_cn_names() -> None:
    """Populate _cn_name_map and _cn_exchange_map from committed CSVs."""
    global _cn_name_map, _cn_exchange_map
    if _cn_name_map:
        return
    csv_dir = Path(__file__).resolve().parent.parent / "data"
    for fname in ["csi300_constituents.csv", "csi500_constituents.csv",
                  "csi1000_constituents.csv"]:
        path = csv_dir / fname
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig") as fh:
            for rec in csv.DictReader(fh):
                sym = rec.get("yahoo_ticker", "").strip()
                name_cn = rec.get("name_cn", "").strip()
                if sym and name_cn:
                    _cn_name_map[sym] = name_cn
                if sym:
                    _cn_exchange_map[sym] = (
                        "上海证券交易所" if sym.endswith(".SS") else "深圳证券交易所"
                    )


# ── Sector mapping (FMP English → Chinese) ─────────────────────────────────

_SECTOR_CN: dict[str, str] = {
    "Consumer Defensive": "消费品防御",
    "Consumer Cyclical": "周期性消费",
    "Technology": "科技",
    "Financial Services": "金融服务",
    "Healthcare": "医疗健康",
    "Industrials": "工业",
    "Energy": "能源",
    "Basic Materials": "基础材料",
    "Communication Services": "通信服务",
    "Real Estate": "房地产",
    "Utilities": "公用事业",
}


def _sector_cn(en: Optional[str]) -> Optional[str]:
    if not en:
        return None
    return _SECTOR_CN.get(en, en)


# ── Chinese financial summary builders ─────────────────────────────────────


def _pct(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    return f"{v * 100:.1f}%"


def _build_growth_summary_cn(fc) -> Optional[str]:
    parts = []
    if fc.revenue_yoy is not None:
        direction = "增长" if fc.revenue_yoy > 0 else "下降"
        parts.append(f"营收同比{direction}{_pct(abs(fc.revenue_yoy))}")
    if fc.eps_yoy is not None:
        direction = "增长" if fc.eps_yoy > 0 else "下降"
        parts.append(f"每股收益{direction}{_pct(abs(fc.eps_yoy))}")
    if fc.eps_growth_years and fc.eps_growth_years >= 2:
        parts.append(f"连续{fc.eps_growth_years}年每股收益增长")
    return "。".join(parts) + "。" if parts else None


def _build_profitability_summary_cn(fc) -> Optional[str]:
    parts = []
    if fc.gross_margin is not None:
        parts.append(f"毛利率{_pct(fc.gross_margin)}")
    if fc.operating_margin is not None:
        parts.append(f"营业利润率{_pct(fc.operating_margin)}")
    if fc.net_margin is not None:
        parts.append(f"净利率{_pct(fc.net_margin)}")
    if fc.roe is not None:
        parts.append(f"ROE {fc.roe * 100:.0f}%")
    return "。".join(parts) + "。" if parts else None


def _build_cashflow_summary_cn(fc) -> Optional[str]:
    if fc.free_cash_flow is None:
        return None
    amount = (
        f"自由现金流 {fc.free_cash_flow / 1e9:.1f}B" if fc.free_cash_flow >= 1e9
        else f"自由现金流 {fc.free_cash_flow / 1e6:.0f}M"
    )
    if fc.fcf_margin is not None:
        return f"{amount}，自由现金流利润率{_pct(fc.fcf_margin)}。"
    return f"{amount}。"


def _build_balance_sheet_summary_cn(fc) -> Optional[str]:
    if fc.net_debt is None:
        return None
    if fc.net_debt < 0:
        amount = abs(fc.net_debt) / 1e9
        return f"净现金 {amount:.1f}B，资产负债表稳健。"
    amount = fc.net_debt / 1e9
    if fc.debt_to_equity:
        return f"净负债 {amount:.1f}B，负债权益比 {fc.debt_to_equity:.1f}x。"
    return f"净负债 {amount:.1f}B。"


def _build_valuation_summary_cn(fc, risk_score: int) -> Optional[str]:
    parts = []
    if fc.pe_ratio:
        parts.append(f"市盈率 {fc.pe_ratio:.1f}x")
    if fc.ps_ratio:
        parts.append(f"市销率 {fc.ps_ratio:.1f}x")
    if fc.fcf_yield:
        parts.append(f"自由现金流收益率 {_pct(fc.fcf_yield)}")
    if not parts:
        return None
    risk_label = "偏高" if risk_score > 70 else "适中" if risk_score > 40 else "合理"
    return f"{'。'.join(parts)}。估值风险：{risk_label}。"


# ── Chinese scoring labels + warnings ─────────────────────────────────────


def _fin_label_cn(score: int) -> str:
    if score >= 80:
        return "财务验证：强劲"
    if score >= 60:
        return "财务验证：良好"
    if score >= 40:
        return "财务验证：一般"
    return "财务验证：较弱"


_WARNING_CN: dict[str, str] = {
    "Elevated valuation risk": "估值风险偏高",
    "Low PE — potential value trap": "低市盈率 — 警惕价值陷阱",
    "High PE — earnings may not justify price": "高市盈率 — 盈利可能不足以支撑股价",
    "Negative earnings": "负盈利",
    "Low or negative gross margin": "毛利率偏低或为负",
    "High debt levels": "负债水平较高",
    "Low ROIC — poor capital allocation": "资本回报率偏低 — 资本配置效率存疑",
    "Cash-burning — negative FCF": "现金消耗 — 自由现金流为负",
    "Weak FCF conversion": "自由现金流转化率偏弱",
    "Low current ratio — liquidity risk": "流动比率偏低 — 流动性风险",
    "Negative revenue growth": "营收负增长",
    "Inconsistent earnings growth history": "盈利增长历史波动较大",
}


def _warnings_cn(warnings_en: list[str]) -> list[str]:
    result: list[str] = []
    for w in warnings_en:
        if w in _WARNING_CN:
            result.append(_WARNING_CN[w])
        else:
            # Fallback: simple keyword substitution for unknown warnings
            translated = w.replace("Elevated", "偏高").replace("Low", "偏低")
            result.append(translated)
    return result


# ── Helpers ─────────────────────────────────────────────────────────────────


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

    # Ensure CN name map is loaded
    _load_cn_names()

    # Use Chinese name from CSV, fall back to FMP English name
    name = _cn_name_map.get(sym, profile_raw.get("companyName", sym))
    sector = _sector_cn(profile_raw.get("sector"))
    industry = profile_raw.get("industry")
    exchange = _cn_exchange_map.get(sym, profile_raw.get("exchangeFullName",
                                                          profile_raw.get("exchange", "")))
    country = "中国"
    website = profile_raw.get("website")
    description = profile_raw.get("description")
    price = _safe_float(profile_raw.get("price"))
    market_cap = profile_raw.get("mktCap")
    pe_ratio = _safe_float(profile_raw.get("pe"))
    employees = profile_raw.get("fullTimeEmployees")

    # ── 2. FMP peers ──────────────────────────────────────────────────
    peer_tickers: list[str] = []
    try:
        peer_tickers = await client.get_peers(sym)
    except Exception:
        _log.exception("cn_overview: FMP peers failed for %s", sym)

    # Resolve peer tickers to Chinese names
    peer_names: list[str] = []
    for pt in peer_tickers[:8]:
        cn_name = _cn_name_map.get(pt, pt)
        peer_names.append(cn_name)

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
    from app.services.financial_validation_service import FinancialCheckMetrics
    fc = FinancialCheckMetrics()
    fc.pe_ratio = pe_ratio
    fc.roe = roe
    fc.gross_margin = gross_margin
    fc.net_margin = net_margin
    fin_score = compute_financial_validation_score(fc)
    val_risk = compute_valuation_risk_score(fc)
    overall = compute_overall_score(fin_score, val_risk)
    # Import US functions for warnings (convert to CN below)
    from app.services.fundamental_scoring_service import get_warnings
    warnings_en = get_warnings(fc, val_risk)

    # ── 6. Assemble ────────────────────────────────────────────────────
    has_fin = bool(fin)
    source_notes_biz = ["FMP /stable/profile"]
    if has_fin:
        source_notes_biz.append("AKShare stock_financial_abstract")

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
            confidence="partial" if has_fin else "low",
            source_notes=source_notes_biz,
        ),
        market_position=MarketPositionSection(
            key_competitors=peer_names,
            confidence="high" if peer_names else "partial",
            source_notes=["FMP /stable/stock-peers"] if peer_names else [],
        ),
        financial_check=FinancialCheckSection(
            financial_validation_label=_fin_label_cn(fin_score),
            financial_validation_score=fin_score,
            valuation_risk_score=val_risk,
            overall_score=overall,
            # Chinese summaries
            growth_summary=_build_growth_summary_cn(fc),
            profitability_summary=_build_profitability_summary_cn(fc),
            cash_flow_summary=_build_cashflow_summary_cn(fc),
            balance_sheet_summary=_build_balance_sheet_summary_cn(fc),
            valuation_summary=_build_valuation_summary_cn(fc, val_risk),
            pe_ratio=pe_ratio,
            roe=roe,
            gross_margin=gross_margin,
            net_margin=net_margin,
            warnings=_warnings_cn(warnings_en),
            confidence="partial" if has_fin else "low",
            source_notes=(["FMP /stable/profile"] if pe_ratio else [])
            + (["AKShare stock_financial_abstract"] if has_fin else []),
        ),
        cn_news=news_articles,
    )
