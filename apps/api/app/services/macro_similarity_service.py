"""Macro similarity ("History Rhymes") — Phase 1e.

Powers the History Rhymes section of Market Pulse v2. Compares today's
5-day macro return vector against ~5 years of historical 5-day return
windows via cosine similarity, then surfaces the top-K matches with
their post-window 30-trading-day SPY outcome.

Macro vector dimensions (6):
  TLT  — long bond ETF (rate-direction proxy)
  VXX  — short-term VIX futures (volatility regime)
  UUP  — USD bullish ETF (dollar strength)
  HYG  — high-yield bond ETF (credit conditions)
  GLD  — gold ETF (safe-haven flow)
  USO  — WTI oil ETF (energy / inflation impulse)

We pick ETFs over spot prices because every symbol in this list has
daily OHLCV bars in `price_bars` (the spot symbols are monthly), which
keeps the vector consistent.

Caveat surfaced to the UI: sample sizes are tiny (5y of trading days ≈
1260 candidate windows, with overlap), the signal is noisy, and "the
market sometimes rhymes" doesn't mean "the market will repeat." The
frontend should display this prominently.

Cache: 4h. Macro vectors don't move fast within a single trading day,
and recomputing 1260 cosine similarities is cheap (<50ms), but the DB
roundtrip + score+sort over `price_bars` makes the cache worthwhile.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar

_log = logging.getLogger("livermore.macro_similarity")

# Macro basket — the 6 ETFs whose joint 5-day returns define the vector.
MACRO_BASKET: list[str] = ["SPY", "TLT", "SHY", "UUP", "HYG", "GLD"]

# Hyperparameters
WINDOW_DAYS = 5            # trading-day window for the return vector
POST_WINDOW_DAYS = 30      # trading-day SPY return after each match window
TOP_K = 3                  # number of historical matches to surface
HISTORY_LOOKBACK_DAYS = 365 * 24  # ~24y of calendar history (oldest ETF: SHY, 2002)
MIN_GAP_DAYS = 14          # require matches to be >= 14 trading days apart
                           # (avoid 3 near-identical adjacent windows)


# ── Output shape ────────────────────────────────────────────────────────────


@dataclass
class HistoryRhymeMatch:
    """One historical 5-day window that resembles today's macro vector."""
    label: str                       # "Aug 13–19, 2019" (rendered for UI)
    start_date: str                  # ISO YYYY-MM-DD
    end_date: str                    # ISO YYYY-MM-DD
    context: str                     # short heuristic regime tag
    similarity: float                # cosine similarity, 0..1
    post_window_30d_return: float    # SPY return 30d after window end
    sample_sparkline: list[float]    # 30 normalized SPY values (start=100)


@dataclass
class HistoryRhymesResponse:
    market: str
    as_of: str
    today_vector: dict[str, float]   # symbol → 5d cumulative return
    matches: list[HistoryRhymeMatch] = field(default_factory=list)
    caveat: str = ""


# ── Cache ───────────────────────────────────────────────────────────────────

_CACHE: dict[str, tuple[datetime, HistoryRhymesResponse]] = {}
_CACHE_TTL = timedelta(hours=1)


# ── Math helpers ────────────────────────────────────────────────────────────


def _five_day_return_vector(prices_asc: list[float], end_idx: int) -> Optional[np.ndarray]:
    """5-day cumulative return ending at bar index `end_idx` for a single
    symbol. Returns None when the window goes off the start of the
    series."""
    start_idx = end_idx - WINDOW_DAYS
    if start_idx < 0 or end_idx >= len(prices_asc):
        return None
    base = prices_asc[start_idx]
    end = prices_asc[end_idx]
    if base <= 0:
        return None
    return np.array([end / base - 1.0])


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity in [-1, 1]; clip to [0, 1] for the UI badge."""
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


# ── Context labeling ────────────────────────────────────────────────────────


def _context_label(vec: np.ndarray) -> str:
    """Heuristic plain-English regime tag from the 6-dim macro vector.

    Order: SPY, TLT, SHY, UUP, HYG, GLD.
    """
    if len(vec) != len(MACRO_BASKET):
        return "Mixed signals"

    spy, tlt, shy, uup, hyg, gld = vec.tolist()
    pieces: list[str] = []
    if spy > 0.03:
        pieces.append("equities ripping")
    elif spy < -0.03:
        pieces.append("equities selling off")
    elif spy > 0.01:
        pieces.append("stocks up")
    elif spy < -0.01:
        pieces.append("stocks down")
    if tlt > 0.02 and shy < tlt * 0.5:
        pieces.append("curve steepening")
    elif tlt > 0.02:
        pieces.append("bonds rallying")
    elif tlt < -0.02 and shy > tlt * 0.5:
        pieces.append("curve flattening")
    elif tlt < -0.02:
        pieces.append("bonds selling off")
    if uup > 0.02:
        pieces.append("dollar bid")
    elif uup < -0.02:
        pieces.append("dollar soft")
    if hyg < -0.015:
        pieces.append("credit widening")
    elif hyg > 0.015:
        pieces.append("credit tight")
    if gld > 0.03:
        pieces.append("gold bid")

    if not pieces:
        return "Quiet macro tape"
    return pieces[0].capitalize() + " · " + " · ".join(pieces[1:]) if len(pieces) > 1 else pieces[0].capitalize()


# ── Data load ───────────────────────────────────────────────────────────────


def _load_aligned_prices(
    db: Session,
    symbols: list[str],
    cutoff: date,
) -> tuple[list[date], dict[str, list[float]]]:
    """Load all symbols, intersect their date sets, return:
      - sorted list of trading dates common to every symbol
      - dict symbol → list of adj_close aligned to those dates

    Empty `dates` or empty per-symbol list means the caller should bail out.
    """
    by_symbol: dict[str, dict[date, float]] = {}
    for sym in symbols:
        rows = (
            db.execute(
                select(PriceBar.trading_date, PriceBar.adjusted_close)
                .where(PriceBar.symbol == sym)
                .where(PriceBar.trading_date >= cutoff)
                .order_by(PriceBar.trading_date.asc())
            ).fetchall()
        )
        m = {r[0]: float(r[1]) for r in rows if r[1] is not None and float(r[1]) > 0}
        by_symbol[sym] = m

    if not by_symbol or any(not v for v in by_symbol.values()):
        return [], {s: [] for s in symbols}

    # Intersect on date
    shared: Optional[set[date]] = None
    for sym in symbols:
        d_set = set(by_symbol[sym].keys())
        shared = d_set if shared is None else (shared & d_set)
    dates_asc = sorted(shared or [])
    if not dates_asc:
        return [], {s: [] for s in symbols}

    aligned = {sym: [by_symbol[sym][d] for d in dates_asc] for sym in symbols}
    return dates_asc, aligned


# ── Match construction ─────────────────────────────────────────────────────


def _format_label(start: date, end: date) -> str:
    """Format two dates as 'Aug 13–19, 2019' or 'Dec 28, 2018 – Jan 3, 2019'."""
    if start.year != end.year:
        return f"{start.strftime('%b %-d, %Y')} – {end.strftime('%b %-d, %Y')}"
    if start.month != end.month:
        return f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"
    return f"{start.strftime('%b %-d')}–{end.day}, {start.year}"


def _vector_at_index(
    end_idx: int, aligned: dict[str, list[float]]
) -> Optional[np.ndarray]:
    """Build the 6-dim 5-day return vector ending at the bar with index
    `end_idx`. Returns None when any symbol's window goes off the
    series start."""
    comps: list[float] = []
    for sym in MACRO_BASKET:
        v = _five_day_return_vector(aligned[sym], end_idx)
        if v is None:
            return None
        comps.append(float(v[0]))
    return np.array(comps)


def _post_window_spy_outcome(
    end_idx: int, spy_prices: list[float], spy_dates: list[date], macro_dates: list[date]
) -> tuple[Optional[float], list[float]]:
    """Return (30d_return, 30-bar sparkline starting at 100) for SPY,
    starting on the bar AFTER `end_idx` (using macro-aligned dates →
    map to SPY's own bar index). Returns (None, []) if not enough
    SPY bars exist after the window."""
    if end_idx + 1 >= len(macro_dates):
        return None, []
    start_date = macro_dates[end_idx + 1]
    # Find first SPY bar at or after start_date
    spy_start_idx = None
    for i, d in enumerate(spy_dates):
        if d >= start_date:
            spy_start_idx = i
            break
    if spy_start_idx is None:
        return None, []
    spy_end_idx = spy_start_idx + POST_WINDOW_DAYS - 1
    if spy_end_idx >= len(spy_prices):
        return None, []

    base = spy_prices[spy_start_idx]
    if base <= 0:
        return None, []
    end = spy_prices[spy_end_idx]
    ret = end / base - 1.0
    sparkline = [round(spy_prices[i] / base * 100.0, 3) for i in range(spy_start_idx, spy_end_idx + 1)]
    return ret, sparkline


# ── Price refresh ─────────────────────────────────────────────────────────────


async def _refresh_macro_prices(db: Session, required_from: date) -> None:
    """Ensure the macro basket + SPY have current price data before
    computing today's vector. force=False lets ensure_history skip
    symbols that already have today's bar."""
    from app.services.alpha_vantage import AlphaVantageClient
    from app.services.price_cache_service import PriceCacheService

    symbols = set(MACRO_BASKET + ["SPY"])
    try:
        client = AlphaVantageClient()
        svc = PriceCacheService(client)
        for sym in symbols:
            try:
                await svc.ensure_history(db, sym, required_from, force=False)
            except Exception:
                pass
    except Exception:
        pass


# ── Public API ─────────────────────────────────────────────────────────────


async def get_history_rhymes(
    market: str, db: Session, force_refresh: bool = False
) -> HistoryRhymesResponse:
    """Build the History Rhymes payload. Cached 1h. Calls ensure_history
    before computing so ETF prices reflect today's close."""
    key = market.upper()
    if key != "US":
        return _empty_response(market, caveat="History Rhymes is US-only in v1.")

    now = datetime.utcnow()
    if not force_refresh:
        cached = _CACHE.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

    # Refresh ETF price data so vectors reflect today's close.
    cutoff = date.today() - timedelta(days=HISTORY_LOOKBACK_DAYS)
    await _refresh_macro_prices(db, cutoff)
    dates_asc, aligned = _load_aligned_prices(db, MACRO_BASKET, cutoff)

    if not dates_asc or len(dates_asc) < WINDOW_DAYS + 1:
        return _empty_response(
            market,
            caveat=(
                "Insufficient macro price history. Run "
                "/api/data/warmup for TLT, VXX, UUP, HYG, GLD, USO first."
            ),
        )

    # Today's vector — most recent fully-formed 5-day window
    today_end_idx = len(dates_asc) - 1
    today_vec = _vector_at_index(today_end_idx, aligned)
    if today_vec is None:
        return _empty_response(market, caveat="Insufficient bars to compute today's window.")

    today_vector_dict = {
        sym: round(float(today_vec[i]), 5) for i, sym in enumerate(MACRO_BASKET)
    }

    # SPY series for post-window outcome — load separately so we can
    # walk past the macro window's end.
    spy_rows = (
        db.execute(
            select(PriceBar.trading_date, PriceBar.adjusted_close)
            .where(PriceBar.symbol == "SPY")
            .where(PriceBar.trading_date >= cutoff)
            .order_by(PriceBar.trading_date.asc())
        ).fetchall()
    )
    spy_dates = [r[0] for r in spy_rows]
    spy_prices = [float(r[1]) for r in spy_rows]
    if not spy_prices:
        return _empty_response(
            market,
            caveat="SPY price history missing. Run /api/data/warmup first.",
        )

    # Compute cosine similarity for every historical 5-day window. We
    # exclude the last 31 windows (today's window + the 30 post-window
    # days where the post-outcome would be incomplete) so every match
    # has a fully-formed post outcome.
    similarities: list[tuple[int, float]] = []  # (end_idx, sim)
    last_searchable_idx = today_end_idx - POST_WINDOW_DAYS - 1
    for end_idx in range(WINDOW_DAYS, last_searchable_idx + 1):
        # Skip the most recent ~5 days to avoid trivially "matching"
        # today's window with yesterday's.
        if today_end_idx - end_idx < WINDOW_DAYS:
            continue
        vec = _vector_at_index(end_idx, aligned)
        if vec is None:
            continue
        sim = _cosine(today_vec, vec)
        similarities.append((end_idx, sim))

    if not similarities:
        return _empty_response(
            market, caveat="No historical windows found in the lookback range."
        )

    # Sort descending by similarity, then dedupe by MIN_GAP_DAYS
    # (so the top 3 aren't three near-identical adjacent windows).
    similarities.sort(key=lambda t: t[1], reverse=True)

    chosen: list[tuple[int, float]] = []
    for end_idx, sim in similarities:
        if any(abs(end_idx - c_idx) < MIN_GAP_DAYS for c_idx, _ in chosen):
            continue
        chosen.append((end_idx, sim))
        if len(chosen) >= TOP_K:
            break

    matches: list[HistoryRhymeMatch] = []
    for end_idx, sim in chosen:
        start_idx = end_idx - WINDOW_DAYS + 1
        if start_idx < 0:
            continue
        start = dates_asc[start_idx]
        end = dates_asc[end_idx]
        vec = _vector_at_index(end_idx, aligned)
        context = _context_label(vec) if vec is not None else "Mixed signals"
        post_ret, sparkline = _post_window_spy_outcome(
            end_idx, spy_prices, spy_dates, dates_asc
        )
        if post_ret is None:
            continue
        matches.append(HistoryRhymeMatch(
            label=_format_label(start, end),
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            context=context,
            similarity=round(max(0.0, sim), 4),  # clip negatives for UI badge
            post_window_30d_return=round(post_ret, 5),
            sample_sparkline=sparkline,
        ))

    response = HistoryRhymesResponse(
        market=market.upper(),
        as_of=now.isoformat(),
        today_vector=today_vector_dict,
        matches=matches,
        caveat=(
            "Sample sizes are small and markets often don't rhyme. "
            "Use as a context cue, not a prediction."
        ),
    )
    _CACHE[key] = (now, response)
    return response


def invalidate_cache() -> None:
    _CACHE.clear()


def _empty_response(market: str, caveat: str) -> HistoryRhymesResponse:
    return HistoryRhymesResponse(
        market=market.upper(),
        as_of=datetime.utcnow().isoformat(),
        today_vector={},
        matches=[],
        caveat=caveat,
    )
