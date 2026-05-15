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
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar

logger = logging.getLogger(__name__)

CMF_PERIOD = 20
VOL_SHORT = 5
VOL_LONG = 20
RS_PERIOD = 5

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
    ("VXX",  "VIX / Volatility"),
    ("UUP",  "Dollar Index"),
    ("TLT",  "10Y Bond"),
    ("GLD",  "Gold"),
    ("USO",  "Oil"),
    ("HYG",  "High Yield Credit"),
]


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class IndexCard:
    symbol: str
    name: str
    price: Optional[float]
    perf_1d: Optional[float]
    perf_5d: Optional[float]
    sparkline_5d: list[float] = field(default_factory=list)


@dataclass
class MacroCard:
    symbol: str
    label: str
    price: Optional[float]
    perf_1d: Optional[float]


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


@dataclass
class AssetCard:
    symbol: str
    name: str
    sector: Optional[str]
    price: Optional[float]
    perf_1d: Optional[float]
    cmf_20: Optional[float]
    market_cap: Optional[float]


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
    )


def _build_macro_card(symbol: str, label: str, db: Session) -> MacroCard:
    bars = _load_bars(symbol, db, limit=3)
    if not bars:
        return MacroCard(symbol=symbol, label=label, price=None, perf_1d=None)
    return MacroCard(
        symbol=symbol, label=label,
        price=float(bars[-1].close),
        perf_1d=_compute_perf(bars, 1),
    )


def _build_top_assets(market: str, db: Session, limit: int = 10) -> list[AssetCard]:
    """
    Compute CMF for all symbols in symbol_health_scores (our pre-warmed universe)
    that have price_bars data. Return top `limit` by CMF (highest = most accumulation).
    """
    try:
        # Get symbols from our universe that also have recent price bars
        from sqlalchemy import text
        rows = db.execute(text(
            "SELECT s.symbol, s.name, s.sector, s.market_cap FROM symbols s "
            "WHERE EXISTS ("
            "  SELECT 1 FROM price_bars pb WHERE pb.symbol = s.symbol "
            "  AND pb.trading_date >= CURRENT_DATE - INTERVAL '30 days'"
            ") AND s.name IS NOT NULL "
            "ORDER BY s.market_cap DESC NULLS LAST LIMIT 200"
        )).fetchall()
    except Exception:
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
        cards.append(AssetCard(
            symbol=sym, name=sym, sector=None,
            price=float(bars[-1].close),
            perf_1d=_compute_perf(bars, 1),
            cmf_20=_compute_cmf(bars),
            market_cap=None,
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
        macro = [_build_macro_card(sym, label, db) for sym, label in MACRO_SYMBOLS]

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
