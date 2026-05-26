"""
PRD-08d: Revenue Segment Service
=================================
Fetches and caches product + geographic revenue segmentation from FMP.
Data source: /stable/revenue-product-segmentation and /revenue-geographic-segmentation
Cache: revenue_segments table, 24h TTL.

FMP response format:
  [{date: "2024-09-28", "iPhone": 201183000000, "Services": 96169000000, ...}]
  (segment names are dynamic keys — everything except "date" is a segment)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.fmp_client import FMPClient

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 24
_SEGMENT_COLORS = [
    "#6366f1", "#f59e0b", "#10b981", "#ef4444",
    "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6",
]
_GEO_COLORS = [
    "#3b82f6", "#f59e0b", "#10b981", "#ef4444",
    "#8b5cf6", "#ec4899", "#06b6d4", "#f97316",
]


@dataclass
class SegmentYear:
    year: int
    segments: dict[str, float] = field(default_factory=dict)  # {name: revenue}


@dataclass
class RevenueSegmentData:
    product_years: list[SegmentYear] = field(default_factory=list)  # newest first
    geo_years: list[SegmentYear] = field(default_factory=list)
    segment_names: list[str] = field(default_factory=list)  # ordered by latest revenue
    geo_names: list[str] = field(default_factory=list)
    segment_colors: list[str] = field(default_factory=list)
    geo_colors: list[str] = field(default_factory=list)
    fallback_note: Optional[str] = None  # shown when no segment breakdown


_META_KEYS = {"date", "symbol", "fiscalYear", "period", "reportedCurrency", "calendarYear"}


def _parse_fmp_segment_rows(rows: list[dict]) -> list[SegmentYear]:
    """
    Convert FMP segment data into [{year, segments: {name: value}}].

    FMP stable returns one of two formats:
      Flat:   [{date, iPhone: 201B, Services: 96B, fiscalYear: 2024, ...}]
      Nested: [{date, "Apple": {iPhone: 201B, Services: 96B}, fiscalYear: 2024}]

    We handle both. In the nested case the company-name wrapper key is skipped
    and its child keys become segment names.
    """
    result = []
    for row in rows:
        date_str = row.get("date") or ""
        try:
            year = int(date_str[:4])
        except (ValueError, TypeError):
            # Try fiscalYear field as fallback
            fy = row.get("fiscalYear")
            if fy:
                try:
                    year = int(float(fy))
                except (ValueError, TypeError):
                    continue
            else:
                continue

        segments: dict[str, float] = {}

        for k, v in row.items():
            if k in _META_KEYS:
                continue

            if isinstance(v, dict):
                # Nested format — the key is the company name, value is {segment: amount}
                for seg_name, seg_val in v.items():
                    if seg_name in _META_KEYS:
                        continue
                    try:
                        fv = float(seg_val)
                        if fv > 0:
                            segments[seg_name] = fv
                    except (TypeError, ValueError):
                        pass
            else:
                try:
                    fv = float(v)
                    if fv > 0:
                        segments[k] = fv
                except (TypeError, ValueError):
                    pass

        if segments:
            result.append(SegmentYear(year=year, segments=segments))

    return sorted(result, key=lambda x: x.year, reverse=True)


def _ordered_names(years: list[SegmentYear]) -> list[str]:
    """Return segment names ordered by their revenue in the most recent year."""
    if not years:
        return []
    latest = years[0].segments
    return sorted(latest.keys(), key=lambda k: latest.get(k, 0), reverse=True)


# ── DB cache helpers ──────────────────────────────────────────────────────────

def _is_bad_cache(years: list[SegmentYear]) -> bool:
    """Return True if cached data only has fiscalYear as a segment — broken old format."""
    if not years:
        return False
    for y in years:
        if set(y.segments.keys()) - {"fiscalYear"}:
            return False  # has at least one real segment
    return True  # all years only have fiscalYear


def _is_stale(symbol: str, segment_type: str, db: Session) -> bool:
    """Return True if cache is absent or older than 24h."""
    try:
        row = db.execute(
            text(
                "SELECT MAX(fetched_at) FROM revenue_segments"
                " WHERE symbol = :sym AND segment_type = :stype"
            ),
            {"sym": symbol, "stype": segment_type},
        ).scalar()
        if not row:
            return True
        cutoff = datetime.utcnow() - timedelta(hours=_CACHE_TTL_HOURS)
        if isinstance(row, str):
            row = datetime.fromisoformat(row)
        return row < cutoff
    except Exception:
        return True


def _load_cache(symbol: str, segment_type: str, db: Session) -> list[SegmentYear]:
    """Load cached rows from DB and deserialise."""
    try:
        rows = db.execute(
            text(
                "SELECT fiscal_year, data FROM revenue_segments"
                " WHERE symbol = :sym AND segment_type = :stype"
                " ORDER BY fiscal_year DESC"
            ),
            {"sym": symbol, "stype": segment_type},
        ).fetchall()
        result = []
        for r in rows:
            data = r[1]
            if isinstance(data, str):
                data = json.loads(data)
            result.append(SegmentYear(year=r[0], segments=data))
        return result
    except Exception:
        return []


def _save_cache(symbol: str, segment_type: str, years: list[SegmentYear], db: Session) -> None:
    is_sqlite = "sqlite" in __import__("app.core.config", fromlist=["get_settings"]).get_settings().database_url
    try:
        # Delete existing rows for this symbol + type
        db.execute(
            text("DELETE FROM revenue_segments WHERE symbol = :sym AND segment_type = :stype"),
            {"sym": symbol, "stype": segment_type},
        )
        for sy in years:
            data_json = json.dumps(sy.segments)
            db.execute(
                text(
                    "INSERT INTO revenue_segments (symbol, fiscal_year, segment_type, data)"
                    " VALUES (:sym, :yr, :stype, :data)"
                    if is_sqlite else
                    # CAST(:data AS jsonb) — NOT `:data::jsonb`. SQLAlchemy's
                    # `text()` bind-parameter regex uses a negative-lookahead
                    # `(?!:)` that refuses to match `:data` when followed by
                    # `:`, so `:data::jsonb` is sent to Postgres literally,
                    # which then raises `SyntaxError at or near ":"`. Use the
                    # explicit CAST form (or wrap as `(:data)::jsonb`) in any
                    # SQLAlchemy text() statement that needs a postgres cast.
                    "INSERT INTO revenue_segments (symbol, fiscal_year, segment_type, data)"
                    " VALUES (:sym, :yr, :stype, CAST(:data AS jsonb))"
                ),
                {"sym": symbol, "yr": sy.year, "stype": segment_type, "data": data_json},
            )
        db.commit()
    except Exception as exc:
        logger.warning("Failed to cache revenue segments for %s/%s: %s", symbol, segment_type, exc)
        db.rollback()


# ── Main service ──────────────────────────────────────────────────────────────

class RevenueSegmentService:

    def __init__(self) -> None:
        self._fmp = FMPClient()

    async def get(self, symbol: str, db: Session) -> RevenueSegmentData:
        sym = symbol.upper()

        # ── Product segments ───────────────────────────────────────────────────
        product_years: list[SegmentYear] = []
        cached_product = _load_cache(sym, "product", db)
        if _is_stale(sym, "product", db) or _is_bad_cache(cached_product):
            try:
                raw = await self._fmp.get_revenue_segments(sym, limit=5)
                if raw:
                    product_years = _parse_fmp_segment_rows(raw)
                    _save_cache(sym, "product", product_years, db)
                else:
                    product_years = []
            except Exception as exc:
                logger.warning("Revenue segment fetch failed for %s: %s", sym, exc)
                product_years = cached_product
        else:
            product_years = cached_product

        # ── Geographic segments ───────────────────────────────────────────────
        geo_years: list[SegmentYear] = []
        cached_geo = _load_cache(sym, "geo", db)
        if _is_stale(sym, "geo", db) or _is_bad_cache(cached_geo):
            try:
                raw = await self._fmp.get_geo_segments(sym, limit=5)
                if raw:
                    geo_years = _parse_fmp_segment_rows(raw)
                    _save_cache(sym, "geo", geo_years, db)
                else:
                    geo_years = []
            except Exception as exc:
                logger.warning("Geo segment fetch failed for %s: %s", sym, exc)
                geo_years = cached_geo
        else:
            geo_years = cached_geo

        segment_names = _ordered_names(product_years)
        geo_names = _ordered_names(geo_years)

        fallback_note = None
        if not product_years:
            fallback_note = "Segment breakdown not disclosed by this company."

        return RevenueSegmentData(
            product_years=product_years[:5],
            geo_years=geo_years[:5],
            segment_names=segment_names,
            geo_names=geo_names,
            segment_colors=_SEGMENT_COLORS[: len(segment_names)],
            geo_colors=_GEO_COLORS[: len(geo_names)],
            fallback_note=fallback_note,
        )
