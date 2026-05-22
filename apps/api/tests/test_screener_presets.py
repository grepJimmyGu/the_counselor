"""Phase 1f — screener_presets service + preset route tests.

Covers:
  * PRESETS registry contains all 9 expected slugs in display order
  * Each scout preset returns reasonable results when symbol data is
    seeded
  * get_preset() lookup

Route-level tier-gating tests are skipped here — the existing test
fixtures don't spin up an HTTP client with overridable auth deps, and
the gating logic is exercised by `_TIER_ORDER` comparison + the
existing `upgrade_error` envelope (which has its own tests).
"""
from __future__ import annotations

from app.models.symbol import SymbolCache
from app.services import screener_presets as svc


# ── Service-layer unit tests ────────────────────────────────────────────────


def test_all_presets_returns_nine_in_display_order():
    presets = svc.all_presets()
    assert len(presets) == 9
    slugs = [p.slug for p in presets]
    assert slugs == [
        "trending-ai",
        "top-growth",
        "top-small-cap",
        "top-rated",
        "top-dividend",
        "top-value",
        "positive-catalyst",
        "community-confirmed",
        "rising-attention",
    ]


def test_preset_tiers_match_design():
    assert svc.PRESETS["trending-ai"].tier == "scout"
    assert svc.PRESETS["top-growth"].tier == "scout"
    assert svc.PRESETS["top-dividend"].tier == "scout"
    assert svc.PRESETS["positive-catalyst"].tier == "strategist"
    assert svc.PRESETS["community-confirmed"].tier == "strategist"
    assert svc.PRESETS["rising-attention"].tier == "quant"


def test_get_preset_lookup():
    assert svc.get_preset("trending-ai") is svc.PRESETS["trending-ai"]
    assert svc.get_preset("bogus") is None


def test_preset_query_returns_filtered_rows(db):
    """Seed a small symbol cache and verify the trending-ai query picks
    up the AI basket members."""
    # Insert one ticker from the AI basket + one not in it.
    # Use ORM instances so the default last_seen_at is applied.
    db.add_all([
        SymbolCache(
            symbol="NVDA", name="NVIDIA", sector="Information Technology",
            market_cap=3_000_000_000_000, market_cap_category="mega",
            is_active=True,
        ),
        SymbolCache(
            symbol="XYZUNKNOWN", name="Unknown",
            sector="Information Technology",
            market_cap=1_000_000_000, market_cap_category="small",
            is_active=True,
        ),
    ])
    db.commit()

    q = svc.PRESETS["trending-ai"].build_query(db)
    rows = db.execute(q).scalars().all()
    syms = {r.symbol for r in rows}
    assert "NVDA" in syms
    assert "XYZUNKNOWN" not in syms


def test_top_dividend_query_filters_yield(db):
    """top-dividend preset only includes symbols with dividend_yield >= 4%."""
    db.add_all([
        SymbolCache(symbol="HIGH", name="HIGH", dividend_yield=0.05, is_active=True),
        SymbolCache(symbol="MID", name="MID", dividend_yield=0.03, is_active=True),
        SymbolCache(symbol="LOW", name="LOW", dividend_yield=0.01, is_active=True),
    ])
    db.commit()

    q = svc.PRESETS["top-dividend"].build_query(db)
    rows = db.execute(q).scalars().all()
    syms = {r.symbol for r in rows}
    assert "HIGH" in syms
    assert "MID" not in syms
    assert "LOW" not in syms


def test_top_value_query_caps_pe_and_market_cap(db):
    """top-value: P/E < 15 AND market_cap >= $2B."""
    db.add_all([
        SymbolCache(symbol="GOOD", name="GOOD", pe_ratio=10.0, market_cap=3_000_000_000, is_active=True),
        SymbolCache(symbol="EXPENSIVE", name="EXPENSIVE", pe_ratio=20.0, market_cap=5_000_000_000, is_active=True),  # P/E too high
        SymbolCache(symbol="TINY", name="TINY", pe_ratio=8.0, market_cap=500_000_000, is_active=True),                # cap too small
        SymbolCache(symbol="OK2", name="OK2", pe_ratio=12.0, market_cap=10_000_000_000, is_active=True),
    ])
    db.commit()

    q = svc.PRESETS["top-value"].build_query(db)
    rows = db.execute(q).scalars().all()
    syms = {r.symbol for r in rows}
    assert syms == {"GOOD", "OK2"}


def test_top_small_cap_query_filters_category(db):
    """top-small-cap: market_cap_category == 'small'."""
    db.add_all([
        SymbolCache(symbol="SMALL1", name="SMALL1", market_cap_category="small", is_active=True),
        SymbolCache(symbol="MEGA", name="MEGA", market_cap_category="mega", is_active=True),
        SymbolCache(symbol="MID", name="MID", market_cap_category="mid", is_active=True),
    ])
    db.commit()
    q = svc.PRESETS["top-small-cap"].build_query(db)
    syms = {r.symbol for r in db.execute(q).scalars().all()}
    assert syms == {"SMALL1"}


def test_inactive_symbols_excluded(db):
    """is_active=False rows must not appear in any preset."""
    db.add_all([
        SymbolCache(symbol="ACTIVE", name="ACTIVE", dividend_yield=0.06, is_active=True),
        SymbolCache(symbol="INACTIVE", name="INACTIVE", dividend_yield=0.07, is_active=False),
    ])
    db.commit()
    q = svc.PRESETS["top-dividend"].build_query(db)
    syms = {r.symbol for r in db.execute(q).scalars().all()}
    assert "ACTIVE" in syms
    assert "INACTIVE" not in syms


def test_all_preset_query_builders_return_select():
    """Smoke: every preset's build_query is callable + produces a
    SQLAlchemy Select (not None / not an error)."""
    # Use a None for the session arg — none of the builders dereference
    # `db` (they only use it as a future hook for sub-queries that might
    # need it). If a future preset DOES touch db, this smoke test will
    # need a real db fixture.
    from sqlalchemy.sql.expression import Select
    for slug, p in svc.PRESETS.items():
        # Some implementations might touch the session in the future
        # (e.g. for cross-table joins); call them with None to confirm
        # they don't today.
        q = p.build_query(None)  # type: ignore[arg-type]
        assert isinstance(q, Select), f"{slug} did not return a Select"


# ── Tier gating logic (route helper) ───────────────────────────────────────


def test_tier_ordering_matches_design():
    """`_TIER_ORDER` in the route correctly orders scout < strategist < quant
    so the `<` comparison in the gate fires the right way."""
    from app.api.routes.screener import _TIER_ORDER
    assert _TIER_ORDER["scout"] < _TIER_ORDER["strategist"]
    assert _TIER_ORDER["strategist"] < _TIER_ORDER["quant"]


def test_required_tier_override_threads_through_envelope():
    """`upgrade_error(required_tier_override="quant")` produces an
    envelope whose `required_tier` is 'quant' even though the
    static map for `screener_preset_locked` has no entry."""
    from app.api.entitlement_errors import upgrade_error
    err = upgrade_error(
        "screener_preset_locked",
        current_tier="scout",
        is_anonymous=False,
        required_tier_override="quant",
    )
    # FastAPI HTTPException carries detail as a dict
    detail = err.detail  # type: ignore[union-attr]
    assert detail["entitlement"]["required_tier"] == "quant"
    assert detail["entitlement"]["code"] == "screener_preset_locked"
