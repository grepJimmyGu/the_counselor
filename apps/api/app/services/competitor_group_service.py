"""
PRD-08e: Competitor Group Service — Per-Segment Revenue Share Rankings
======================================================================
For each business segment, identifies peer companies and computes
revenue-share-based market positioning.

Pipeline:
1. Check competitor_revenue_cache (7-day TTL) → return if fresh
2. Load peer group from competitor_groups table (or seed it first)
3. Fetch 5-year income statements for all peers (parallel, with timeout)
4. Compute annual revenue share = peer_rev / sum(group_revs)
5. Classify: Dominant(>50%) / Market Leader(25-50%) / Major Participant(10-25%) / Niche(<10%)
6. Save to cache + return

Peer seeding (one LLM call per symbol, runs once, stored indefinitely):
- Fetch FMP peers list
- Ask LLM (Haiku) which peers compete in each segment
- Store in competitor_groups table

Disclaimer: "Market share estimate based on public peer group revenue.
Actual total addressable market is larger. This is a relative competitive
position indicator."
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.fmp_client import FMPClient

logger = logging.getLogger(__name__)

_CACHE_TTL_DAYS = 7
_DISCLAIMER = (
    "Market share estimate based on public peer group revenue. "
    "Actual total addressable market is larger. "
    "This is a relative competitive position indicator."
)
_REVENUE_FETCH_TIMEOUT = 10.0  # seconds per peer


def _classify_position(share: float) -> str:
    if share >= 0.50:
        return "Dominant"
    if share >= 0.25:
        return "Market Leader"
    if share >= 0.10:
        return "Major Participant"
    return "Niche"


def _fmt_revenue(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 1e12:
        return f"${v / 1e12:.1f}T"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:.0f}"


@dataclass
class RankingEntry:
    symbol: str
    name: str
    revenue: str           # formatted string, e.g. "$209B"
    revenue_raw: float     # latest year raw value
    share: float           # 0.0 - 1.0
    position: str          # Dominant / Market Leader / Major Participant / Niche
    trend_5yr: list[float] # share per year, oldest→newest, length up to 5


@dataclass
class SegmentRankings:
    segment: str
    rankings: list[RankingEntry] = field(default_factory=list)
    disclaimer: str = _DISCLAIMER
    computed_at: Optional[datetime] = None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_cache(symbol: str, segment: str, db: Session) -> Optional[SegmentRankings]:
    try:
        row = db.execute(
            text(
                "SELECT rankings FROM competitor_revenue_cache"
                " WHERE symbol = :sym AND segment = :seg AND expires_at > :now"
            ),
            {"sym": symbol, "seg": segment, "now": datetime.utcnow()},
        ).fetchone()
        if not row:
            return None
        data = row[0]
        if isinstance(data, str):
            data = json.loads(data)
        entries = [
            RankingEntry(
                symbol=r["symbol"],
                name=r.get("name") or r["symbol"],
                revenue=r.get("revenue") or "N/A",
                revenue_raw=r.get("revenue_raw") or 0,
                share=r.get("share") or 0,
                position=r.get("position") or "Niche",
                trend_5yr=r.get("trend_5yr") or [],
            )
            for r in data
        ]
        return SegmentRankings(segment=segment, rankings=entries)
    except Exception as exc:
        logger.debug("competitor cache load failed for %s/%s: %s", symbol, segment, exc)
        return None


def _save_cache(symbol: str, result: SegmentRankings, db: Session) -> None:
    expires = datetime.utcnow() + timedelta(days=_CACHE_TTL_DAYS)
    data = json.dumps([
        {
            "symbol": r.symbol, "name": r.name,
            "revenue": r.revenue, "revenue_raw": r.revenue_raw,
            "share": r.share, "position": r.position,
            "trend_5yr": r.trend_5yr,
        }
        for r in result.rankings
    ])
    is_sqlite = db.bind.dialect.name == "sqlite" if db.bind else False
    try:
        if is_sqlite:
            db.execute(
                text(
                    "INSERT OR REPLACE INTO competitor_revenue_cache"
                    " (symbol, segment, expires_at, rankings)"
                    " VALUES (:sym, :seg, :exp, :data)"
                ),
                {"sym": symbol, "seg": result.segment, "exp": expires, "data": data},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO competitor_revenue_cache (symbol, segment, expires_at, rankings)"
                    " VALUES (:sym, :seg, :exp, :data::jsonb)"
                    " ON CONFLICT (symbol, segment) DO UPDATE SET"
                    "  expires_at=:exp, rankings=:data::jsonb, computed_at=now()"
                ),
                {"sym": symbol, "seg": result.segment, "exp": expires, "data": data},
            )
        db.commit()
    except Exception as exc:
        logger.warning("competitor cache save failed: %s", exc)
        db.rollback()


def _load_peer_group(symbol: str, segment: str, db: Session) -> list[tuple[str, str]]:
    """Return [(peer_symbol, peer_name), ...] from competitor_groups."""
    try:
        rows = db.execute(
            text(
                "SELECT peer_symbol, peer_name FROM competitor_groups"
                " WHERE symbol = :sym AND segment = :seg"
            ),
            {"sym": symbol, "seg": segment},
        ).fetchall()
        return [(r[0], r[1] or r[0]) for r in rows]
    except Exception:
        return []


def _save_peer_group(
    symbol: str, segment: str, peers: list[tuple[str, str]], db: Session
) -> None:
    try:
        db.execute(
            text("DELETE FROM competitor_groups WHERE symbol = :sym AND segment = :seg"),
            {"sym": symbol, "seg": segment},
        )
        for peer_sym, peer_name in peers:
            db.execute(
                text(
                    "INSERT INTO competitor_groups (symbol, segment, peer_symbol, peer_name)"
                    " VALUES (:sym, :seg, :psym, :pname)"
                ),
                {"sym": symbol, "seg": segment, "psym": peer_sym, "pname": peer_name},
            )
        db.commit()
    except Exception as exc:
        logger.warning("peer group save failed: %s", exc)
        db.rollback()


# ── LLM peer filtering ────────────────────────────────────────────────────────

async def _seed_peer_groups(
    symbol: str,
    segments: list[str],
    raw_peers: list[str],
    db: Session,
) -> dict[str, list[str]]:
    """
    Ask LLM (Haiku) which of the raw FMP peers compete in each segment.
    Returns {segment: [peer_symbols]}.
    Falls back to assigning all peers to every segment if LLM unavailable.
    """
    from app.services.llm_adapter import get_llm_gateway, LLMAdapterError

    gateway = get_llm_gateway()
    if not gateway.is_enabled or not raw_peers or not segments:
        # Fallback: all peers → all segments
        return {seg: raw_peers for seg in segments}

    system_prompt = (
        "You are a financial analyst. Given a company's business segments and a list of peer "
        "companies, determine which peers directly compete in each segment. "
        "Return ONLY valid JSON — no preamble, no markdown. "
        "If unsure, include the peer. Use exact ticker symbols from the input list."
    )
    user_prompt = (
        f"Company: {symbol}\n"
        f"Business segments: {json.dumps(segments)}\n"
        f"Peer companies (symbols): {json.dumps(raw_peers)}\n\n"
        f"For each segment, list which peer symbols compete in that segment.\n"
        f"Return JSON: {{\"segment_name\": [\"PEER1\", \"PEER2\"], ...}}"
    )

    try:
        result = await gateway.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
        )
        # Validate: all returned symbols must be in raw_peers
        valid = set(raw_peers)
        filtered: dict[str, list[str]] = {}
        for seg in segments:
            peers_for_seg = result.get(seg) or result.get(seg.split("·")[0].strip()) or raw_peers
            filtered[seg] = [p for p in peers_for_seg if p in valid]
            if not filtered[seg]:
                filtered[seg] = raw_peers  # fallback
        return filtered
    except (LLMAdapterError, Exception) as exc:
        logger.warning("Peer filtering LLM call failed for %s: %s", symbol, exc)
        return {seg: raw_peers for seg in segments}


# ── Revenue computation ───────────────────────────────────────────────────────

async def _fetch_peer_revenues(
    peers: list[str], fmp: FMPClient, limit: int = 5
) -> dict[str, list[float]]:
    """
    Fetch 5-year revenues for a list of peer symbols in parallel.
    Returns {symbol: [rev_yr1, rev_yr2, ...]} oldest→newest.
    Peers that fail are omitted.
    """
    async def _one(sym: str) -> tuple[str, list[float]]:
        try:
            stmts = await asyncio.wait_for(
                fmp.get_income_statement(sym, limit=limit),
                timeout=_REVENUE_FETCH_TIMEOUT,
            )
            revs = []
            for s in reversed(stmts):  # oldest first
                rev = s.get("revenue") or s.get("totalRevenue")
                if rev is not None:
                    revs.append(float(rev))
            return sym, revs
        except Exception:
            return sym, []

    results = await asyncio.gather(*[_one(p) for p in peers], return_exceptions=True)
    out: dict[str, list[float]] = {}
    for r in results:
        if isinstance(r, tuple):
            sym, revs = r
            if revs:
                out[sym] = revs
    return out


def _compute_rankings(
    symbol: str,
    symbol_name: str,
    segment: str,
    peers: list[tuple[str, str]],
    peer_revenues: dict[str, list[float]],
    symbol_revenues: list[float],
) -> SegmentRankings:
    """
    Compute revenue share rankings for one segment.
    Includes the focal company itself.
    """
    # Build full set: focal + peers
    all_syms: list[tuple[str, str, list[float]]] = [(symbol, symbol_name, symbol_revenues)]
    for peer_sym, peer_name in peers:
        revs = peer_revenues.get(peer_sym)
        if revs:
            all_syms.append((peer_sym, peer_name, revs))

    if len(all_syms) < 2:
        return SegmentRankings(segment=segment)

    # Use latest year's revenue to compute shares (all aligned to same calendar length)
    latest_revs = {sym: revs[-1] for sym, _, revs in all_syms if revs}
    total = sum(latest_revs.values())
    if total == 0:
        return SegmentRankings(segment=segment)

    # Compute 5-year trend: share in each year
    # Find the max years available across all peers
    n_years = max((len(revs) for _, _, revs in all_syms), default=1)
    trend_by_sym: dict[str, list[float]] = {}
    for yr_idx in range(n_years):
        yr_total = sum(
            revs[yr_idx] for _, _, revs in all_syms
            if yr_idx < len(revs)
        )
        for sym, _, revs in all_syms:
            if yr_idx < len(revs) and yr_total > 0:
                trend_by_sym.setdefault(sym, []).append(revs[yr_idx] / yr_total)

    entries: list[RankingEntry] = []
    for sym, name, revs in all_syms:
        rev_latest = revs[-1] if revs else 0
        share = rev_latest / total
        entries.append(RankingEntry(
            symbol=sym,
            name=name,
            revenue=_fmt_revenue(rev_latest),
            revenue_raw=rev_latest,
            share=share,
            position=_classify_position(share),
            trend_5yr=trend_by_sym.get(sym) or [],
        ))

    entries.sort(key=lambda e: e.revenue_raw, reverse=True)
    return SegmentRankings(segment=segment, rankings=entries, computed_at=datetime.utcnow())


# ── Main service ──────────────────────────────────────────────────────────────

class CompetitorGroupService:

    def __init__(self) -> None:
        self._fmp = FMPClient()

    async def get_rankings(
        self,
        symbol: str,
        symbol_name: str,
        segments: list[str],
        raw_peers: list[str],
        db: Session,
    ) -> list[SegmentRankings]:
        """
        Return per-segment competitive rankings.
        Lazy — seeds peer groups and computes rankings on first request per symbol.
        Cached for 7 days thereafter.
        """
        if not segments or not raw_peers:
            return []

        sym = symbol.upper()
        results: list[SegmentRankings] = []

        # Check which segments have fresh cache
        stale_segments: list[str] = []
        for seg in segments:
            cached = _load_cache(sym, seg, db)
            if cached:
                results.append(cached)
            else:
                stale_segments.append(seg)

        if not stale_segments:
            return results

        # Seed peer groups for stale segments (one LLM call covers all)
        peer_map: dict[str, list[tuple[str, str]]] = {}
        for seg in stale_segments:
            existing = _load_peer_group(sym, seg, db)
            if existing:
                peer_map[seg] = existing

        missing_segs = [s for s in stale_segments if s not in peer_map]
        if missing_segs:
            try:
                filtered = await _seed_peer_groups(sym, missing_segs, raw_peers, db)
                for seg, peer_syms in filtered.items():
                    peer_list = [(p, p) for p in peer_syms]
                    _save_peer_group(sym, seg, peer_list, db)
                    peer_map[seg] = peer_list
            except Exception as exc:
                logger.warning("Peer seeding failed for %s: %s", sym, exc)
                for seg in missing_segs:
                    peer_map[seg] = [(p, p) for p in raw_peers]

        # Fetch revenues for all unique peers + focal symbol in parallel
        all_peers = list({p for peers in peer_map.values() for p, _ in peers})
        peer_revenues = await _fetch_peer_revenues(all_peers, self._fmp)

        # Fetch focal symbol revenues
        symbol_revenues: list[float] = []
        try:
            stmts = await self._fmp.get_income_statement(sym, limit=5)
            for s in reversed(stmts):
                rev = s.get("revenue") or s.get("totalRevenue")
                if rev is not None:
                    symbol_revenues.append(float(rev))
        except Exception:
            pass

        # Compute rankings per stale segment
        for seg in stale_segments:
            peers = peer_map.get(seg) or [(p, p) for p in raw_peers]
            ranking = _compute_rankings(
                sym, symbol_name, seg, peers, peer_revenues, symbol_revenues
            )
            _save_cache(sym, ranking, db)
            results.append(ranking)

        # Return in original segment order
        seg_order = {s: i for i, s in enumerate(segments)}
        results.sort(key=lambda r: seg_order.get(r.segment, 999))
        return results
