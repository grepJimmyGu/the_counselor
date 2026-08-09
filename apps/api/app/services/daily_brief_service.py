"""Daily market brief — the deterministic half of the "Moving today" block.

Assembles exactly the fields the snapshot renders, from sources that already
ship. No LLM here on purpose: every number below is checkable against the
market, and keeping the arithmetic separate from the generated prose is what
lets the block show the tape even when the model call fails.

Two source swaps matter, and both fix a number that would have been WRONG
rather than merely different:

  * **Indices come from the index, not its ETF.** `market_pulse` tracks
    SPY / QQQ / DIA. SPY is ~$650; the S&P 500 is ~7,750. A snapshot that
    prints an ETF share price as an index level is visibly wrong to anyone
    who knows the market — and this block exists to be shared.
  * **VIX is `^VIX`, not VXX.** VXX is a VIX-*futures* ETF; its price is not
    the volatility level and doesn't track it closely.

Both symbols already resolve through the existing FMP quote path — no new
provider, no new key.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("livermore.daily_brief")

# The real indices, in the order the block reads them.
INDEX_SYMBOLS: Sequence[tuple] = (
    ("^GSPC", "S&P 500"),
    ("^IXIC", "Nasdaq Composite"),
    ("^DJI", "Dow Jones"),
)
VIX_SYMBOL = "^VIX"

# Movers shown per side. Three, per Jimmy's template.
MOVER_COUNT = 3

# A move has to clear this to be called out as unusual. Below it, the "biggest
# move of the day" is just the top of a quiet leaderboard, and labelling it
# UNUSUAL would cry wolf on an ordinary session.
UNUSUAL_MIN_ABS_PCT = 8.0

# Macro rows carried into the block, in display order. `Growth` is computed
# but not shown — the snapshot is a market read, and CFNAI is a slow monthly
# series that never changes between two closes.
MACRO_CATEGORIES: Sequence[str] = ("Inflation", "Rates", "Stress")


@dataclass
class BriefQuote:
    symbol: str
    name: str
    price: Optional[float] = None
    change_percent: Optional[float] = None


@dataclass
class BriefMover:
    symbol: str
    name: Optional[str]
    change_percent: float


@dataclass
class BriefSector:
    name: str
    change_percent: Optional[float] = None
    money_flow: Optional[float] = None


@dataclass
class BriefMacro:
    category: str
    label: str          # "CPI YoY: 3.9%"
    direction: str      # "up" | "down" | "flat"
    trend: str          # "Rising" | "Cooling" | "Stable"
    takeaway: str


@dataclass
class DailyBrief:
    as_of: Optional[str]
    indices: List[BriefQuote] = field(default_factory=list)
    vix: Optional[BriefQuote] = None
    macro: List[BriefMacro] = field(default_factory=list)
    gainers: List[BriefMover] = field(default_factory=list)
    losers: List[BriefMover] = field(default_factory=list)
    sector_leading: Optional[BriefSector] = None
    sector_lagging: Optional[BriefSector] = None
    flow_into: Optional[BriefSector] = None
    flow_out_of: Optional[BriefSector] = None
    unusual: Optional[BriefMover] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pct(v: Optional[float]) -> Optional[float]:
    """Pulse perf fields are FRACTIONS (0.0062); the block shows percents."""
    if v is None:
        return None
    try:
        return round(float(v) * 100, 2)
    except (TypeError, ValueError):
        return None


def build_brief(
    *,
    quotes: Dict[str, Dict[str, Any]],
    pulse: Dict[str, Any],
    macro_signals: Optional[Sequence[Dict[str, Any]]] = None,
) -> DailyBrief:
    """Assemble the brief from already-fetched inputs.

    Pure: takes plain dicts rather than doing its own I/O, so the whole shape
    is testable without a DB, an HTTP client or a warmed cache.
    """
    brief = DailyBrief(as_of=pulse.get("as_of"))

    # ── indices + VIX ──────────────────────────────────────────────────────
    for sym, name in INDEX_SYMBOLS:
        q = quotes.get(sym) or {}
        brief.indices.append(
            BriefQuote(
                symbol=sym,
                name=name,
                price=q.get("price"),
                # Live quotes already carry a PERCENT here, unlike the pulse's
                # fractions. Mixing the two conventions is how a +0.62% day
                # renders as +62%.
                change_percent=(
                    round(float(q["change_percent"]), 2)
                    if q.get("change_percent") is not None
                    else None
                ),
            )
        )

    vq = quotes.get(VIX_SYMBOL)
    if vq:
        brief.vix = BriefQuote(
            symbol=VIX_SYMBOL,
            name="VIX",
            price=vq.get("price"),
            change_percent=(
                round(float(vq["change_percent"]), 2)
                if vq.get("change_percent") is not None
                else None
            ),
        )

    # ── macro ──────────────────────────────────────────────────────────────
    by_cat = {s.get("category"): s for s in (macro_signals or []) if s.get("category")}
    for cat in MACRO_CATEGORIES:
        s = by_cat.get(cat)
        if not s:
            continue
        brief.macro.append(
            BriefMacro(
                category=cat,
                label=s.get("latestLabel") or "",
                direction=s.get("trendDirection") or "flat",
                trend=s.get("trendLabel") or "",
                takeaway=s.get("takeaway") or "",
            )
        )

    # ── movers ─────────────────────────────────────────────────────────────
    # Ranked by 1-day RETURN. `top_assets` arrives sorted by Chaikin Money
    # Flow, which is a different question — the CMF leader can be flat on the
    # day, so reusing that order would put the wrong names under "biggest
    # gainers".
    assets = [
        a for a in (pulse.get("top_assets") or []) if a.get("perf_1d") is not None
    ]
    ranked = sorted(assets, key=lambda a: a["perf_1d"], reverse=True)

    def _mover(a: Dict[str, Any]) -> BriefMover:
        return BriefMover(
            symbol=a.get("symbol", ""),
            name=a.get("name"),
            change_percent=_pct(a.get("perf_1d")) or 0.0,
        )

    brief.gainers = [_mover(a) for a in ranked[:MOVER_COUNT]]
    # Reversed so the worst loser reads first, mirroring the gainers column.
    brief.losers = [_mover(a) for a in list(reversed(ranked))[:MOVER_COUNT]]

    # ── sectors ────────────────────────────────────────────────────────────
    sectors = [s for s in (pulse.get("sectors") or []) if s.get("name")]

    by_perf = sorted(
        [s for s in sectors if s.get("perf_1d") is not None],
        key=lambda s: s["perf_1d"],
        reverse=True,
    )
    if by_perf:
        brief.sector_leading = BriefSector(
            name=by_perf[0]["name"], change_percent=_pct(by_perf[0].get("perf_1d"))
        )
        brief.sector_lagging = BriefSector(
            name=by_perf[-1]["name"], change_percent=_pct(by_perf[-1].get("perf_1d"))
        )

    by_flow = sorted(
        [s for s in sectors if s.get("cmf_20") is not None],
        key=lambda s: s["cmf_20"],
        reverse=True,
    )
    # Needs at least TWO sectors: "money moved from X to Y" is a comparison,
    # and with one data point the strongest and weakest are the same name.
    if len(by_flow) >= 2:
        brief.flow_into = BriefSector(
            name=by_flow[0]["name"],
            change_percent=_pct(by_flow[0].get("perf_1d")),
            money_flow=round(float(by_flow[0]["cmf_20"]), 4),
        )
        brief.flow_out_of = BriefSector(
            name=by_flow[-1]["name"],
            change_percent=_pct(by_flow[-1].get("perf_1d")),
            money_flow=round(float(by_flow[-1]["cmf_20"]), 4),
        )

    # ── unusual ────────────────────────────────────────────────────────────
    # The largest ABSOLUTE move, so a -12% crash is as callable as a +12% pop,
    # and only when it clears the threshold. On a quiet day there is no
    # unusual mover, and saying so is more useful than promoting a +2% name.
    if ranked:
        extreme = max(ranked, key=lambda a: abs(a["perf_1d"]))
        pct = _pct(extreme.get("perf_1d")) or 0.0
        if abs(pct) >= UNUSUAL_MIN_ABS_PCT:
            brief.unusual = _mover(extreme)

    return brief
