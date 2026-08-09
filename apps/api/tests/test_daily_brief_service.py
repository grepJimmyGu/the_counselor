"""Daily brief — the deterministic half of the "Moving today" snapshot.

`build_brief` is pure over plain dicts, so every field is testable here
without a DB, an HTTP client, or a warmed cache.
"""
from __future__ import annotations

from app.services.daily_brief_service import (
    MOVER_COUNT,
    UNUSUAL_MIN_ABS_PCT,
    build_brief,
)


def _quotes(**over):
    q = {
        "^GSPC": {"price": 7757.64, "change_percent": 0.61842},
        "^IXIC": {"price": 26690.615, "change_percent": 1.29899},
        "^DJI": {"price": 54036.93, "change_percent": 0.28177},
        "^VIX": {"price": 14.9, "change_percent": -1.65017},
    }
    q.update(over)
    return q


def _pulse(**over):
    p = {
        "as_of": "2026-08-09T11:29:43",
        "top_assets": [
            {"symbol": "TEAM", "name": "Atlassian", "perf_1d": 0.3531},
            {"symbol": "TWLO", "name": "Twilio", "perf_1d": 0.2489},
            {"symbol": "ABNB", "name": "Airbnb", "perf_1d": 0.1743},
            {"symbol": "NVDA", "name": "NVIDIA", "perf_1d": 0.0227},
            {"symbol": "ZTS", "name": "Zoetis", "perf_1d": -0.0597},
            {"symbol": "PARA", "name": "Paramount", "perf_1d": -0.0604},
            {"symbol": "AKAM", "name": "Akamai", "perf_1d": -0.0676},
        ],
        "sectors": [
            {"name": "Consumer Disc.", "perf_1d": 0.014903, "cmf_20": -0.0773},
            {"name": "Financials", "perf_1d": -0.003633, "cmf_20": 0.1192},
            {"name": "Energy", "perf_1d": -0.011348, "cmf_20": -0.0497},
            {"name": "Utilities", "perf_1d": 0.005302, "cmf_20": -0.1846},
        ],
        "macro_signals": [
            {"category": "Growth", "latestLabel": "CFNAI: -0.02", "trendDirection": "flat",
             "trendLabel": "Stable", "takeaway": "Trend growth"},
            {"category": "Inflation", "latestLabel": "CPI YoY: 3.9%", "trendDirection": "up",
             "trendLabel": "Rising", "takeaway": "Could delay rate cuts"},
            {"category": "Rates", "latestLabel": "10Y Yield: 4.60%", "trendDirection": "up",
             "trendLabel": "Rising", "takeaway": "Pressure on long duration"},
        ],
    }
    p.update(over)
    return p


def _build(**over):
    p = _pulse(**over.pop("pulse", {}))
    return build_brief(quotes=_quotes(**over.pop("quotes", {})), pulse=p,
                       macro_signals=p.get("macro_signals"))


# ── indices ────────────────────────────────────────────────────────────────


def test_indices_are_index_levels_not_etf_prices():
    """The S&P renders ~7,757 (the index), never ~650 (SPY's share price).
    An ETF price printed as an index level is wrong, not merely different —
    and this block exists to be shared."""
    b = _build()
    spx = next(i for i in b.indices if i.symbol == "^GSPC")
    assert spx.price == 7757.64
    assert spx.price > 1000  # a share price could never be here


def test_quote_percents_are_not_re_scaled():
    """Live quotes carry a PERCENT; the pulse carries FRACTIONS. Mixing the
    two conventions renders a +0.62% day as +62%."""
    b = _build()
    assert next(i for i in b.indices if i.symbol == "^GSPC").change_percent == 0.62


def test_vix_comes_from_the_index_not_vxx():
    b = _build()
    assert b.vix is not None and b.vix.symbol == "^VIX"
    assert b.vix.price == 14.9


def test_missing_index_quotes_leave_the_row_empty_not_absent():
    """A quote outage blanks the numbers but must not drop the row — the
    block's layout is fixed, and a vanishing index reads as a broken page."""
    b = build_brief(quotes={}, pulse=_pulse(), macro_signals=None)
    assert len(b.indices) == 3
    assert all(i.price is None for i in b.indices)
    assert b.vix is None
    # And the rest of the block still populates.
    assert b.gainers and b.sector_leading


# ── movers ─────────────────────────────────────────────────────────────────


def test_gainers_and_losers_rank_by_return_not_money_flow():
    """`top_assets` arrives sorted by Chaikin Money Flow — a different
    question. The CMF leader can be flat on the day, so reusing that order
    puts the wrong names under "biggest gainers"."""
    b = _build()
    assert [m.symbol for m in b.gainers] == ["TEAM", "TWLO", "ABNB"]
    assert [m.symbol for m in b.losers] == ["AKAM", "PARA", "ZTS"]


def test_percent_conversion_from_pulse_fractions():
    b = _build()
    assert b.gainers[0].change_percent == 35.31
    assert b.losers[0].change_percent == -6.76


def test_mover_counts_are_capped():
    b = _build()
    assert len(b.gainers) == MOVER_COUNT and len(b.losers) == MOVER_COUNT


def test_assets_without_a_return_are_dropped_not_sorted_as_zero():
    b = _build(pulse={"top_assets": [
        {"symbol": "AAA", "name": "A", "perf_1d": 0.05},
        {"symbol": "BBB", "name": "B", "perf_1d": None},
    ]})
    assert [m.symbol for m in b.gainers] == ["AAA"]
    assert "BBB" not in [m.symbol for m in b.losers]


# ── sectors + flow ─────────────────────────────────────────────────────────


def test_sector_leader_and_laggard_use_return():
    b = _build()
    assert b.sector_leading.name == "Consumer Disc."
    assert b.sector_leading.change_percent == 1.49
    assert b.sector_lagging.name == "Energy"


def test_money_flow_uses_chaikin_not_return():
    """Deliberately a different ranking from leader/laggard: Consumer Disc.
    led on price while money was LEAVING it (cmf -0.077). Collapsing the two
    would make the flow line a restatement of the sector line."""
    b = _build()
    assert b.flow_into.name == "Financials"
    assert b.flow_out_of.name == "Utilities"
    assert b.flow_into.name != b.sector_leading.name


def test_flow_needs_two_sectors_to_be_a_direction():
    """"Money moved from X to Y" is a comparison. With one data point the
    strongest and weakest are the same name, which would render as
    "Energy → Energy"."""
    b = _build(pulse={"sectors": [{"name": "Energy", "perf_1d": 0.01, "cmf_20": 0.2}]})
    assert b.flow_into is None and b.flow_out_of is None
    # The leader/laggard line doesn't need two, so it still renders.
    assert b.sector_leading is not None


# ── unusual ────────────────────────────────────────────────────────────────


def test_unusual_picks_the_largest_absolute_move():
    b = _build()
    assert b.unusual is not None and b.unusual.symbol == "TEAM"


def test_a_big_drop_is_as_unusual_as_a_big_pop():
    b = _build(pulse={"top_assets": [
        {"symbol": "UP", "name": "U", "perf_1d": 0.02},
        {"symbol": "CRASH", "name": "C", "perf_1d": -0.31},
    ]})
    assert b.unusual.symbol == "CRASH"


def test_quiet_day_has_no_unusual_mover():
    """Below the threshold, "biggest move of the day" is just the top of a
    quiet leaderboard. Labelling it UNUSUAL every session cries wolf."""
    small = (UNUSUAL_MIN_ABS_PCT - 2) / 100
    b = _build(pulse={"top_assets": [
        {"symbol": "AAA", "name": "A", "perf_1d": small},
        {"symbol": "BBB", "name": "B", "perf_1d": -small / 2},
    ]})
    assert b.unusual is None
    assert b.gainers  # the leaderboard itself still renders


# ── macro ──────────────────────────────────────────────────────────────────


def test_macro_carries_direction_and_takeaway():
    b = _build()
    infl = next(m for m in b.macro if m.category == "Inflation")
    assert infl.direction == "up" and infl.trend == "Rising"
    assert infl.label == "CPI YoY: 3.9%"
    assert infl.takeaway


def test_growth_is_computed_but_not_shown():
    """CFNAI is a slow monthly series — it cannot change between two closes,
    so it would be a permanently static chip in a daily snapshot."""
    b = _build()
    assert "Growth" not in [m.category for m in b.macro]
    assert [m.category for m in b.macro] == ["Inflation", "Rates", "Stress"][: len(b.macro)]


def test_absent_macro_signals_are_skipped_not_faked():
    b = build_brief(quotes=_quotes(), pulse=_pulse(), macro_signals=None)
    assert b.macro == []
    assert b.indices  # everything else still renders


def test_serializes_to_plain_json_types():
    d = _build().to_dict()
    import json

    json.loads(json.dumps(d))  # raises if a dataclass leaked through
    assert d["indices"][0]["symbol"] == "^GSPC"
