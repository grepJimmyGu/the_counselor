"""
Market Pulse Service
====================
Computes capital-flow signals for index ETFs, sector ETFs, and macro indicators
entirely from the price_bars table (no external API calls at request time).

Capital flow metric: Chaikin Money Flow (CMF-20)
  CMF = Σ(MFV, 20d) / Σ(Volume, 20d)
  where MFV = ((2C - H - L) / (H - L)) × V   (money flow volume per bar)

  CMF > 0: net buying pressure (accumulation / capital flowing in)
  CMF < 0: net selling pressure (distribution / capital flowing out)
  Range: −1 to +1 (typical real values: −0.3 to +0.3)

Supporting metrics:
  - volume_ratio: 5d avg volume / 20d avg volume (>1.15 = elevated activity)
  - rs_vs_spy_5d: sector 5d return − SPY 5d return (relative strength)
  - perf_1d / perf_5d: price performance from price_bars

Results are cached in-memory for 1 hour to avoid re-querying on every request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.services.live_quote_service import LiveQuote, live_quote_service

logger = logging.getLogger(__name__)

CMF_PERIOD = 20
VOL_SHORT = 5
VOL_LONG = 20
RS_PERIOD = 5
STALE_DAYS = 5  # flag as stale if latest bar is >5 calendar days old

# ── Symbol configs ────────────────────────────────────────────────────────────

US_INDICES = [
    ("SPY",  "S&P 500"),
    ("QQQ",  "NASDAQ 100"),
    ("IWM",  "Russell 2000"),
    ("DIA",  "Dow Jones"),
]

CN_INDICES = [
    ("FXI",  "China Large-Cap"),
    ("KWEB", "China Internet"),
    ("MCHI", "MSCI China"),
]

US_SECTORS = [
    ("XLK",  "Technology"),
    ("XLC",  "Communication"),
    ("XLY",  "Consumer Disc."),
    ("XLP",  "Consumer Staples"),
    ("XLV",  "Healthcare"),
    ("XLF",  "Financials"),
    ("XLI",  "Industrials"),
    ("XLE",  "Energy"),
    ("XLB",  "Materials"),
    ("XLRE", "Real Estate"),
    ("XLU",  "Utilities"),
]

CN_SECTORS = [
    ("KWEB", "Internet / Tech"),
    ("FXI",  "Large Cap"),
    ("MCHI", "Broad Market"),
    ("CQQQ", "China Tech"),
    ("FLCH", "Financials"),
    ("CHIE", "Energy"),
    ("CNYA", "A-Shares"),
]

MACRO_SYMBOLS = [
    ("VXX",        "VIX / Volatility"),
    ("UUP",        "Dollar Index"),
    ("TLT",        "10Y Bond"),
    ("GOLD_SPOT",  "Gold ($/oz)"),     # spot price derived from GLD
    ("WTI_SPOT",   "WTI ($/bbl)"),     # spot price from AV commodity API
    ("HYG",        "High Yield Credit"),
]

# All ETF symbols warmed up by this service — excluded from the stocks top-10
ETF_SYMBOLS: frozenset[str] = frozenset({
    # US broad indices
    "SPY", "QQQ", "IWM", "DIA",
    # CN indices
    "FXI", "KWEB", "MCHI", "CQQQ", "FLCH", "CHIE", "CNYA",
    # US sectors
    "XLK", "XLC", "XLY", "XLP", "XLV", "XLF", "XLI", "XLE", "XLB", "XLRE", "XLU",
    # Macro / bonds / volatility / dollar
    "VXX", "UUP", "TLT", "HYG",
    # Commodity & gold ETFs
    "GLD", "USO", "DBC", "COPX", "WEAT", "GDX", "GDXJ",
})

# Canonical name + category label for ETFs shown in the featured-ETFs tab
ETF_META: dict[str, tuple[str, str]] = {
    "SPY":  ("SPDR S&P 500 ETF",               "ETF — US Broad Market"),
    "QQQ":  ("Invesco QQQ Trust",               "ETF — NASDAQ 100"),
    "IWM":  ("iShares Russell 2000",            "ETF — Small-Cap"),
    "DIA":  ("SPDR Dow Jones ETF",              "ETF — Dow Jones"),
    "GLD":  ("SPDR Gold Shares",                "ETF — Gold"),
    "TLT":  ("iShares 20+ Year Treasury",       "ETF — Long-Term Bonds"),
    "XLK":  ("Technology Select SPDR",          "ETF — Technology"),
    "XLE":  ("Energy Select SPDR",              "ETF — Energy"),
    "XLF":  ("Financials Select SPDR",          "ETF — Financials"),
    "XLV":  ("Health Care Select SPDR",         "ETF — Health Care"),
    "XLI":  ("Industrials Select SPDR",         "ETF — Industrials"),
    "XLY":  ("Consumer Discr. Select SPDR",     "ETF — Consumer Disc."),
    "XLP":  ("Consumer Staples Select SPDR",    "ETF — Consumer Staples"),
    "XLU":  ("Utilities Select SPDR",           "ETF — Utilities"),
    "XLB":  ("Materials Select SPDR",           "ETF — Materials"),
    "XLC":  ("Comm. Svcs. Select SPDR",         "ETF — Communication"),
    "XLRE": ("Real Estate Select SPDR",         "ETF — Real Estate"),
    "FXI":  ("iShares China Large-Cap",         "ETF — China Large-Cap"),
    "KWEB": ("KraneShares China Internet",      "ETF — China Internet"),
    "MCHI": ("iShares MSCI China",              "ETF — MSCI China"),
    "USO":  ("United States Oil Fund",          "ETF — WTI Oil"),
    "HYG":  ("iShares High Yield Corp Bond",    "ETF — High Yield Credit"),
    "UUP":  ("Invesco DB USD Index Bullish",    "ETF — US Dollar"),
    "VXX":  ("iPath VIX Short-Term Futures",    "ETF — Volatility"),
    "DBC":  ("Invesco DB Commodity Index",      "ETF — Commodities"),
    "COPX": ("Global X Copper Miners",          "ETF — Copper Miners"),
    "WEAT": ("Teucrium Wheat Fund",             "ETF — Wheat"),
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class IndexCard:
    symbol: str
    name: str
    price: Optional[float]
    perf_1d: Optional[float]
    perf_5d: Optional[float]
    sparkline_5d: list[float] = field(default_factory=list)
    latest_date: Optional[str] = None   # ISO date of most recent price bar
    is_stale: bool = False              # True if data is >5 calendar days old


@dataclass
class MacroCard:
    symbol: str
    label: str
    price: Optional[float]
    perf_1d: Optional[float]
    latest_date: Optional[str] = None
    is_stale: bool = False


@dataclass
class SectorCard:
    symbol: str
    name: str
    price: Optional[float]
    perf_1d: Optional[float]
    perf_5d: Optional[float]
    rs_vs_spy_5d: Optional[float]   # excess return vs SPY
    cmf_20: Optional[float]         # Chaikin Money Flow, −1 to +1
    volume_ratio: Optional[float]   # 5d avg vol / 20d avg vol
    latest_date: Optional[str] = None
    is_stale: bool = False


@dataclass
class AssetCard:
    symbol: str
    name: str
    sector: Optional[str]
    price: Optional[float]
    perf_1d: Optional[float]
    cmf_20: Optional[float]
    market_cap: Optional[float]
    latest_date: Optional[str] = None
    is_stale: bool = False


@dataclass
class MarketPulseResponse:
    market: str                     # "US" | "CN"
    as_of: str                      # ISO datetime
    indices: list[IndexCard]
    macro: list[MacroCard]
    sectors: list[SectorCard]
    top_assets: list[AssetCard]     # dynamic top 10 by CMF
    featured_etfs: list[AssetCard]


@dataclass
class _LiveBar:
    """PriceBar-shaped current-day bar synthesized from an FMP live quote."""
    trading_date: date
    high: float
    low: float
    close: float
    volume: int


# ── CMF computation ───────────────────────────────────────────────────────────

def _latest_date_str(bars: list) -> Optional[str]:
    """Return ISO date string of the most recent bar, or None."""
    if not bars:
        return None
    td = bars[-1].trading_date
    if hasattr(td, "isoformat"):
        return td.isoformat()
    return str(td)


def _is_stale(bars: list) -> bool:
    """True if the most recent bar is more than STALE_DAYS calendar days old."""
    if not bars:
        return True
    td = bars[-1].trading_date
    bar_date = td if isinstance(td, date) else date.fromisoformat(str(td))
    return (date.today() - bar_date).days > STALE_DAYS


def _compute_cmf(bars: list, period: int = CMF_PERIOD) -> Optional[float]:
    """
    Chaikin Money Flow.
    bars: list of ORM PriceBar objects ordered oldest→newest.
    """
    if len(bars) < period:
        return None
    recent = bars[-period:]
    total_mfv = 0.0
    total_vol = 0.0
    for b in recent:
        h, l, c, v = float(b.high), float(b.low), float(b.close), float(b.volume)
        if h == l:
            mfm = 0.0
        else:
            mfm = (2 * c - h - l) / (h - l)
        total_mfv += mfm * v
        total_vol += v
    return round(total_mfv / total_vol, 4) if total_vol > 0 else None


def _compute_perf(bars: list, lookback: int) -> Optional[float]:
    """Return (close_latest / close_N_ago) - 1."""
    if len(bars) < lookback + 1:
        return None
    latest = float(bars[-1].close)
    past = float(bars[-(lookback + 1)].close)
    return round((latest / past) - 1, 6) if past > 0 else None


def _volume_ratio(bars: list) -> Optional[float]:
    """5d avg volume / 20d avg volume."""
    if len(bars) < VOL_LONG:
        return None
    recent_vols = [float(b.volume) for b in bars[-VOL_SHORT:]]
    long_vols = [float(b.volume) for b in bars[-VOL_LONG:]]
    avg_short = sum(recent_vols) / len(recent_vols)
    avg_long = sum(long_vols) / len(long_vols)
    return round(avg_short / avg_long, 3) if avg_long > 0 else None


def _load_bars(symbol: str, db: Session, limit: int = 25) -> list:
    """Fetch the most recent `limit` price bars for a symbol, oldest first."""
    rows = (
        db.execute(
            select(PriceBar)
            .where(PriceBar.symbol == symbol)
            .order_by(desc(PriceBar.trading_date))
            .limit(limit)
        ).scalars().all()
    )
    return list(reversed(rows))  # oldest → newest


def _build_sector_card(
    symbol: str,
    name: str,
    spy_bars: list,
    db: Session,
) -> SectorCard:
    bars = _load_bars(symbol, db)
    if not bars:
        return SectorCard(symbol=symbol, name=name, price=None, perf_1d=None,
                          perf_5d=None, rs_vs_spy_5d=None, cmf_20=None, volume_ratio=None)

    price = float(bars[-1].close)
    perf_1d = _compute_perf(bars, 1)
    perf_5d = _compute_perf(bars, RS_PERIOD)
    cmf = _compute_cmf(bars)
    vol_r = _volume_ratio(bars)

    spy_5d = _compute_perf(spy_bars, RS_PERIOD) if spy_bars else None
    rs = round(perf_5d - spy_5d, 4) if perf_5d is not None and spy_5d is not None else None

    return SectorCard(
        symbol=symbol, name=name, price=price,
        perf_1d=perf_1d, perf_5d=perf_5d,
        rs_vs_spy_5d=rs, cmf_20=cmf, volume_ratio=vol_r,
        latest_date=_latest_date_str(bars),
        is_stale=_is_stale(bars),
    )


def _build_index_card(symbol: str, name: str, db: Session) -> IndexCard:
    bars = _load_bars(symbol, db, limit=10)
    if not bars:
        return IndexCard(symbol=symbol, name=name, price=None, perf_1d=None, perf_5d=None)
    return IndexCard(
        symbol=symbol, name=name,
        price=float(bars[-1].close),
        perf_1d=_compute_perf(bars, 1),
        perf_5d=_compute_perf(bars, 5),
        sparkline_5d=[float(b.close) for b in bars[-5:]],
        latest_date=_latest_date_str(bars),
        is_stale=_is_stale(bars),
    )


_SPOT_SYMBOLS = frozenset({"WTI_SPOT", "GOLD_SPOT", "COPPER_SPOT", "WHEAT_SPOT"})
_SPOT_STALE_DAYS = 35  # monthly bars → stale if >35 calendar days old


def _is_stale_for_symbol(bars: list, symbol: str) -> bool:
    """Use a longer staleness window for monthly spot price symbols."""
    if not bars:
        return True
    td = bars[-1].trading_date
    bar_date = td if isinstance(td, date) else date.fromisoformat(str(td))
    threshold = _SPOT_STALE_DAYS if symbol in _SPOT_SYMBOLS else STALE_DAYS
    return (date.today() - bar_date).days > threshold


def _build_macro_card(symbol: str, label: str, db: Session) -> MacroCard:
    limit = 3 if symbol not in _SPOT_SYMBOLS else 2
    bars = _load_bars(symbol, db, limit=limit)
    if not bars:
        return MacroCard(symbol=symbol, label=label, price=None, perf_1d=None)
    return MacroCard(
        symbol=symbol, label=label,
        price=round(float(bars[-1].close), 2),
        perf_1d=_compute_perf(bars, 1),  # month-over-month for spot symbols
        latest_date=_latest_date_str(bars),
        is_stale=_is_stale_for_symbol(bars, symbol),
    )


def _build_top_assets(
    market: str,
    db: Session,
    limit: int = 600,
    universe_override: Optional[set] = None,
) -> list[AssetCard]:
    """
    Return the Top Movers candidate pool for the given market.

    **2026-05-23 redesign — full S&P 500 universe.** Per Jimmy's review
    feedback, the US candidate pool is now the entire S&P 500
    constituent list (`app.data.sp500_tickers.SP500_TICKERS` —
    ~531 tickers covering all SPX names + a few class-A/B duals).
    Replaces the previous heuristic (top-50 by `market_cap` filtered
    by region) which sometimes missed mid-cap SPX names like the worst
    losers of the day. The S&P 500 list is the authoritative SPX
    universe and is already the gating boundary for Scout-tier ticker
    scope (`apps/api/app/data/sp500_tickers.py`).

    Implicit benefits of the SP500_TICKERS filter:
      * No CN listings (`.SH`/`.SZ`/`.HK`) — none in the index
      * No ETFs — none in the index (SPY, QQQ etc. are NOT
        constituents of their underlying index)
      * No foreign ADRs, no micro-caps — S&P scoping handles it

    Frontend client-side sort comparators (gainers / losers / CMF)
    operate over this ~500-name pool and slice to the visible 10 per
    `.slice(0, 10)`. With this much variance, each sort mode produces
    meaningfully different rows.

    **Internal universe accessor:** `universe_override` lets tests
    inject a small fake set in place of `SP500_TICKERS`. Production
    callers must NOT pass this — the default is the single source of
    truth.

    US: S&P 500 equities. Symbols without price_bars history are
    dropped (the existing pipeline keeps SPX names warm).

    CN: CN market ETF proxies (individual CN stocks aren't in our
        price_bars DB — ETF proxies are the best available signal).
    """
    if market == "CN":
        return _build_cn_top_assets(db, limit)

    # ── US: S&P 500 constituents ────────────────────────────────────────────
    from app.data.sp500_tickers import SP500_TICKERS
    universe = universe_override if universe_override is not None else SP500_TICKERS
    if not universe:
        return []

    try:
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        sp_list = list(universe)
        # Bind-param placeholders for `WHERE symbol IN (...)` — keeps the
        # query safe across SQLite + Postgres (no string interpolation).
        sp_placeholders = ", ".join(f":s{i}" for i in range(len(sp_list)))
        params: dict = {f"s{i}": sym for i, sym in enumerate(sp_list)}
        params["cutoff"] = cutoff

        rows = db.execute(
            text(
                "SELECT s.symbol, s.name, s.sector, s.market_cap FROM symbols s "
                "WHERE EXISTS ("
                "  SELECT 1 FROM price_bars pb WHERE pb.symbol = s.symbol "
                "  AND pb.trading_date >= :cutoff"
                ") AND s.name IS NOT NULL "
                f"AND s.symbol IN ({sp_placeholders}) "
                "ORDER BY s.market_cap DESC NULLS LAST"
            ),
            params,
        ).fetchall()
    except Exception:
        logger.exception("_build_top_assets query failed")
        return []

    assets: list[AssetCard] = []
    for row in rows:
        sym, name, sector, mcap = row[0], row[1], row[2], row[3]
        bars = _load_bars(sym, db)
        if not bars:
            continue
        cmf = _compute_cmf(bars)
        if cmf is None:
            # CMF needs 20 days; allow shorter-history names through with
            # cmf_20=None so the frontend "Top losers" / "Top gainers"
            # sort still sees them. Old behavior was to skip these
            # entirely, which compounded the CMF-bias of the pool.
            pass
        assets.append(AssetCard(
            symbol=sym, name=name or sym, sector=sector,
            price=float(bars[-1].close),
            perf_1d=_compute_perf(bars, 1),
            cmf_20=cmf,
            market_cap=float(mcap) if mcap else None,
            latest_date=_latest_date_str(bars),
            is_stale=_is_stale(bars),
        ))

    # Order by market_cap descending (not CMF) so the pool is
    # representative — frontend client-side sort handles the per-mode
    # ordering and final slice.
    assets.sort(
        key=lambda a: a.market_cap if a.market_cap is not None else -1.0,
        reverse=True,
    )
    return assets[:limit]


def _build_cn_top_assets(db: Session, limit: int = 10) -> list[AssetCard]:
    """
    CN market capital-flow leaders ranked by CMF.
    Uses US-listed CN ETF proxies (FXI, KWEB, MCHI, CQQQ, CHIE, FLCH, CNYA)
    since individual A-share / HK price bars are not in our DB.
    """
    cn_proxies = ["FXI", "KWEB", "MCHI", "CQQQ", "CHIE", "FLCH", "CNYA"]
    meta_map = {**ETF_META, **CN_ETF_META}
    assets: list[AssetCard] = []
    for sym in cn_proxies:
        bars = _load_bars(sym, db)
        if not bars:
            continue
        cmf = _compute_cmf(bars)
        if cmf is None:
            continue
        meta = meta_map.get(sym, (sym, "CN Market Proxy"))
        name, sector = meta
        assets.append(AssetCard(
            symbol=sym,
            name=name,
            sector=sector,
            price=float(bars[-1].close),
            perf_1d=_compute_perf(bars, 1),
            cmf_20=cmf,
            market_cap=None,
            latest_date=_latest_date_str(bars),
            is_stale=_is_stale(bars),
        ))

    assets.sort(key=lambda a: a.cmf_20 or -99, reverse=True)
    return assets[:limit]


US_FEATURED_ETFS = ["SPY", "QQQ", "GLD", "TLT", "XLK", "XLE", "FXI", "USO", "KWEB", "IWM"]

CN_FEATURED_ETFS = ["FXI", "KWEB", "MCHI", "CQQQ", "CHIE", "FLCH", "CNYA"]

# CN ETF metadata (supplements ETF_META for CN-specific labels)
CN_ETF_META: dict[str, tuple[str, str]] = {
    "FXI":  ("iShares China Large-Cap",        "ETF — CN Large-Cap"),
    "KWEB": ("KraneShares China Internet",      "ETF — CN Internet"),
    "MCHI": ("iShares MSCI China",             "ETF — CN Broad Market"),
    "CQQQ": ("Invesco China Technology",        "ETF — CN Technology"),
    "CHIE": ("Global X China Energy",           "ETF — CN Energy"),
    "FLCH": ("Franklin FTSE China",             "ETF — CN Financials"),
    "CNYA": ("iShares MSCI China A",            "ETF — CN A-Shares"),
}


def _build_featured_etfs(market: str, db: Session) -> list[AssetCard]:
    is_cn = market == "CN"
    etf_list = CN_FEATURED_ETFS if is_cn else US_FEATURED_ETFS
    meta_map = {**ETF_META, **CN_ETF_META}
    cards = []
    for sym in etf_list:
        bars = _load_bars(sym, db)
        if not bars:
            continue
        meta = meta_map.get(sym, (sym, "ETF"))
        name, category = meta
        cards.append(AssetCard(
            symbol=sym,
            name=name,
            sector=category,
            price=float(bars[-1].close),
            perf_1d=_compute_perf(bars, 1),
            cmf_20=_compute_cmf(bars),
            market_cap=None,
            latest_date=_latest_date_str(bars),
            is_stale=_is_stale(bars),
        ))
    return cards


# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE: dict[str, tuple[datetime, MarketPulseResponse]] = {}
_CACHE_TTL_MINUTES = 60

# Live overlays are intentionally cached longer than the generic quote cache.
# A full US Market Pulse refresh touches the whole S&P 500 universe; 5 minutes
# keeps the page current without firing hundreds of quote calls per visitor.
_LIVE_CACHE: dict[str, tuple[datetime, MarketPulseResponse]] = {}
_LIVE_CACHE_TTL_SECONDS = 300

# Phase 1b — narrative cache parallel to the pulse cache. Same TTL.
# Held separately so the route layer can decide whether to lazily fill it
# without forcing every `get_pulse()` caller through the LLM path.
# Value: (timestamp, narrative_or_None). None = "we tried but LLM was off /
# errored"; absent = "never tried this market yet".
from typing import Any as _Any  # local alias for narrative payload
_NARRATIVE_CACHE: dict[str, tuple[datetime, _Any]] = {}


class MarketPulseService:

    def get_pulse(self, market: str, db: Session) -> MarketPulseResponse:
        key = market.upper()
        now = datetime.utcnow()

        cached_at, cached_resp = _CACHE.get(key, (None, None))
        if cached_at and cached_resp and (now - cached_at) < timedelta(minutes=_CACHE_TTL_MINUTES):
            return cached_resp

        result = self._compute(key, db, now)
        _CACHE[key] = (now, result)
        return result

    async def get_live_pulse(self, market: str, db: Session) -> MarketPulseResponse:
        """Return Market Pulse with live quotes applied before ranking/display.

        The base pulse remains the EOD price_bars snapshot. This overlay fetches
        FMP live quotes for the exact response universe, then recalculates the
        fields users read as "today" (price, 1D move, CMF where quote OHLCV is
        available, sector relative strength). If FMP is unavailable or partial,
        missing symbols keep their EOD values.
        """
        key = market.upper()
        now = datetime.utcnow()

        cached_at, cached_resp = _LIVE_CACHE.get(key, (None, None))
        if (
            cached_at
            and cached_resp
            and (now - cached_at) < timedelta(seconds=_LIVE_CACHE_TTL_SECONDS)
        ):
            return cached_resp

        base = self.get_pulse(key, db)
        symbols = _live_quote_symbols(base)
        if not symbols:
            return base

        try:
            quotes = await live_quote_service.get_quotes(symbols)
        except Exception:
            logger.exception("market_pulse live quote overlay failed")
            return base

        live = _apply_live_quotes_to_pulse(base, quotes, db, now)
        _LIVE_CACHE[key] = (now, live)
        return live

    def _compute(self, market: str, db: Session, now: datetime) -> MarketPulseResponse:
        is_cn = market == "CN"

        # Indices
        index_configs = CN_INDICES if is_cn else US_INDICES
        indices = [_build_index_card(sym, name, db) for sym, name in index_configs]

        # Macro (always US)
        # For *_SPOT symbols: fall back to ETF proxy if spot bars not yet loaded
        _SPOT_FALLBACKS = {"GOLD_SPOT": ("GLD", "Gold (GLD)"), "WTI_SPOT": ("USO", "Oil (USO)")}
        macro = []
        for sym, label in MACRO_SYMBOLS:
            card = _build_macro_card(sym, label, db)
            if card.price is None and sym in _SPOT_FALLBACKS:
                fallback_sym, fallback_label = _SPOT_FALLBACKS[sym]
                card = _build_macro_card(fallback_sym, fallback_label, db)
            macro.append(card)

        # Sector cards
        sector_configs = CN_SECTORS if is_cn else US_SECTORS
        spy_bars = _load_bars("SPY", db, limit=10)  # benchmark for RS
        sectors = [
            _build_sector_card(sym, name, spy_bars, db)
            for sym, name in sector_configs
        ]
        # Sort by CMF descending (highest inflow first)
        sectors.sort(
            key=lambda s: s.cmf_20 if s.cmf_20 is not None else -99,
            reverse=True,
        )

        top_assets = _build_top_assets(market, db)
        featured_etfs = _build_featured_etfs(market, db)

        return MarketPulseResponse(
            market=market,
            as_of=now.isoformat(),
            indices=indices,
            macro=macro,
            sectors=sectors,
            top_assets=top_assets,
            featured_etfs=featured_etfs,
        )

    def invalidate_cache(self) -> None:
        _CACHE.clear()
        _LIVE_CACHE.clear()
        _NARRATIVE_CACHE.clear()

    # ── Narrative cache (Phase 1b) ─────────────────────────────────────────
    # Pulse data is sync (`get_pulse` reads price_bars); narrative is async
    # (LLM call). Route layer fetches the pulse first, then checks the
    # narrative cache and lazily generates if empty.

    def get_cached_narrative(self, market: str):
        """Returns narrative if cached and fresh; None if expired/never
        generated. None doesn't distinguish 'absent' from 'LLM disabled' —
        the route just calls generate_narrative() either way (it itself
        handles the disabled case)."""
        key = market.upper()
        entry = _NARRATIVE_CACHE.get(key)
        if entry is None:
            return None
        cached_at, narrative = entry
        if (datetime.utcnow() - cached_at) >= timedelta(minutes=_CACHE_TTL_MINUTES):
            return None
        return narrative

    def set_cached_narrative(self, market: str, narrative) -> None:
        """Store narrative (or None) for this market. Storing None lets us
        skip retrying within the TTL window after a known LLM-disabled or
        failure path."""
        _NARRATIVE_CACHE[market.upper()] = (datetime.utcnow(), narrative)


# ── Live overlay helpers ─────────────────────────────────────────────────────

def _live_quote_symbols(resp: MarketPulseResponse) -> list[str]:
    """Every real market symbol whose displayed value can be live-overlaid."""
    symbols: list[str] = []
    cards = [
        *resp.indices,
        *resp.macro,
        *resp.sectors,
        *resp.top_assets,
        *resp.featured_etfs,
    ]
    for card in cards:
        sym = getattr(card, "symbol", "")
        if not sym or sym in _SPOT_SYMBOLS:
            continue
        symbols.append(sym.upper())
    return sorted(set(symbols))


def _apply_live_quotes_to_pulse(
    resp: MarketPulseResponse,
    quotes: dict[str, LiveQuote],
    db: Session,
    now: datetime,
) -> MarketPulseResponse:
    """Return a new response with live quotes merged into all card surfaces."""
    spy_bars = _load_bars_with_live("SPY", db, quotes.get("SPY"), limit=10)

    sectors = [
        _apply_live_to_sector(card, quotes.get(card.symbol.upper()), spy_bars, db)
        for card in resp.sectors
    ]
    sectors.sort(
        key=lambda s: s.cmf_20 if s.cmf_20 is not None else -99,
        reverse=True,
    )

    return replace(
        resp,
        as_of=now.isoformat(),
        indices=[
            _apply_live_to_index(card, quotes.get(card.symbol.upper()), db)
            for card in resp.indices
        ],
        macro=[
            _apply_live_to_macro(card, quotes.get(card.symbol.upper()))
            for card in resp.macro
        ],
        sectors=sectors,
        top_assets=[
            _apply_live_to_asset(card, quotes.get(card.symbol.upper()), db)
            for card in resp.top_assets
        ],
        featured_etfs=[
            _apply_live_to_asset(card, quotes.get(card.symbol.upper()), db)
            for card in resp.featured_etfs
        ],
    )


def _apply_live_to_index(
    card: IndexCard,
    quote: Optional[LiveQuote],
    db: Session,
) -> IndexCard:
    if quote is None:
        return card
    bars = _load_bars_with_live(card.symbol, db, quote, limit=10)
    return replace(
        card,
        price=round(quote.price, 2),
        perf_1d=_quote_perf_1d(quote),
        perf_5d=_compute_perf(bars, 5) if bars else card.perf_5d,
        sparkline_5d=(
            [float(b.close) for b in bars[-5:]]
            if bars
            else card.sparkline_5d
        ),
        latest_date=date.today().isoformat(),
        is_stale=False,
    )


def _apply_live_to_macro(
    card: MacroCard,
    quote: Optional[LiveQuote],
) -> MacroCard:
    if quote is None:
        return card
    return replace(
        card,
        price=round(quote.price, 2),
        perf_1d=_quote_perf_1d(quote),
        latest_date=date.today().isoformat(),
        is_stale=False,
    )


def _apply_live_to_sector(
    card: SectorCard,
    quote: Optional[LiveQuote],
    spy_bars: list,
    db: Session,
) -> SectorCard:
    if quote is None:
        return card
    bars = _load_bars_with_live(card.symbol, db, quote)
    perf_5d = _compute_perf(bars, RS_PERIOD) if bars else card.perf_5d
    spy_5d = _compute_perf(spy_bars, RS_PERIOD) if spy_bars else None
    rs = (
        round(perf_5d - spy_5d, 4)
        if perf_5d is not None and spy_5d is not None
        else card.rs_vs_spy_5d
    )
    return replace(
        card,
        price=round(quote.price, 2),
        perf_1d=_quote_perf_1d(quote),
        perf_5d=perf_5d,
        rs_vs_spy_5d=rs,
        cmf_20=_compute_cmf(bars) if bars else card.cmf_20,
        volume_ratio=_volume_ratio(bars) if bars else card.volume_ratio,
        latest_date=date.today().isoformat(),
        is_stale=False,
    )


def _apply_live_to_asset(
    card: AssetCard,
    quote: Optional[LiveQuote],
    db: Session,
) -> AssetCard:
    if quote is None:
        return card
    bars = _load_bars_with_live(card.symbol, db, quote)
    return replace(
        card,
        price=round(quote.price, 2),
        perf_1d=_quote_perf_1d(quote),
        cmf_20=_compute_cmf(bars) if bars else card.cmf_20,
        market_cap=quote.market_cap if quote.market_cap is not None else card.market_cap,
        latest_date=date.today().isoformat(),
        is_stale=False,
    )


def _load_bars_with_live(
    symbol: str,
    db: Session,
    quote: Optional[LiveQuote],
    limit: int = 25,
) -> list:
    bars = _load_bars(symbol, db, limit=limit)
    if quote is None:
        return bars

    live_bar = _live_bar_from_quote(quote)
    if live_bar is None:
        return bars

    if bars:
        latest = bars[-1].trading_date
        latest_date = (
            latest if isinstance(latest, date) else date.fromisoformat(str(latest))
        )
        if latest_date == live_bar.trading_date:
            return [*bars[:-1], live_bar]
    return [*bars, live_bar]


def _live_bar_from_quote(quote: LiveQuote) -> Optional[_LiveBar]:
    if quote.day_high is None or quote.day_low is None or quote.volume is None:
        return None
    high = max(float(quote.day_high), quote.price)
    low = min(float(quote.day_low), quote.price)
    return _LiveBar(
        trading_date=date.today(),
        high=high,
        low=low,
        close=float(quote.price),
        volume=int(quote.volume),
    )


def _quote_perf_1d(quote: LiveQuote) -> float:
    return round(float(quote.change_percent) / 100.0, 6)
