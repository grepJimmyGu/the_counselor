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
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar

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
        perf_5d=_compute_perf(bars, min(5, len(bars) - 1)),
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


def _build_top_assets(market: str, db: Session, limit: int = 10) -> list[AssetCard]:
    """
    Return top `limit` stocks by CMF from our warmed universe.
    ETFs are explicitly excluded so the Stocks tab only shows equities.
    """
    try:
        # Build exclusion placeholders for known ETF symbols
        etf_list = list(ETF_SYMBOLS)
        placeholders = ", ".join(f":e{i}" for i in range(len(etf_list)))
        etf_params = {f"e{i}": sym for i, sym in enumerate(etf_list)}

        # Use a bound date parameter for cross-dialect compatibility (SQLite + PG)
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        etf_params["cutoff"] = cutoff

        rows = db.execute(
            text(
                "SELECT s.symbol, s.name, s.sector, s.market_cap FROM symbols s "
                "WHERE EXISTS ("
                "  SELECT 1 FROM price_bars pb WHERE pb.symbol = s.symbol "
                "  AND pb.trading_date >= :cutoff"
                ") AND s.name IS NOT NULL "
                f"AND s.symbol NOT IN ({placeholders}) "
                "AND (s.instrument_type IS NULL OR s.instrument_type != 'ETF') "
                "ORDER BY s.market_cap DESC NULLS LAST LIMIT 200"
            ),
            etf_params,
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
            continue
        assets.append(AssetCard(
            symbol=sym, name=name or sym, sector=sector,
            price=float(bars[-1].close),
            perf_1d=_compute_perf(bars, 1),
            cmf_20=cmf,
            market_cap=float(mcap) if mcap else None,
            latest_date=_latest_date_str(bars),
            is_stale=_is_stale(bars),
        ))

    # Sort by CMF descending (strongest accumulation first)
    assets.sort(key=lambda a: a.cmf_20 or -99, reverse=True)
    return assets[:limit]


def _build_featured_etfs(db: Session) -> list[AssetCard]:
    etf_list = ["SPY", "QQQ", "GLD", "TLT", "XLK", "XLE", "FXI", "USO", "KWEB", "IWM"]
    cards = []
    for sym in etf_list:
        bars = _load_bars(sym, db)
        if not bars:
            continue
        meta = ETF_META.get(sym, (sym, "ETF"))
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
        featured_etfs = _build_featured_etfs(db)

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
