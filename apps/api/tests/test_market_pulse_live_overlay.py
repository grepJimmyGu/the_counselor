"""Regression tests for Market Pulse live quote overlay.

The page must rank/render after collecting the latest data for the defined
universe. These tests pin the backend side of that contract so the frontend
does not have to patch visible card prices after stale EOD ranking.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models.price_bar import PriceBar
from app.services.live_quote_service import LiveQuote
from app.services.market_pulse_service import (
    AssetCard,
    MarketPulseResponse,
    SectorCard,
    _apply_live_quotes_to_pulse,
)


def _quote(
    symbol: str,
    price: float,
    change_percent: float,
    day_high: float = 101.0,
    day_low: float = 99.0,
    volume: int = 1_000_000,
) -> LiveQuote:
    return LiveQuote(
        symbol=symbol,
        price=price,
        change=price * change_percent / 100.0,
        change_percent=change_percent,
        day_high=day_high,
        day_low=day_low,
        volume=volume,
        market_cap=None,
        name=symbol,
        exchange="NYSE",
        fetched_at=1.0,
    )


def _asset(symbol: str) -> AssetCard:
    return AssetCard(
        symbol=symbol,
        name=symbol,
        sector="Technology",
        price=100.0,
        perf_1d=0.0,
        cmf_20=None,
        market_cap=None,
        latest_date="2026-05-22",
        is_stale=False,
    )


def _sector(symbol: str, cmf: float) -> SectorCard:
    return SectorCard(
        symbol=symbol,
        name=symbol,
        price=100.0,
        perf_1d=0.0,
        perf_5d=0.0,
        rs_vs_spy_5d=0.0,
        cmf_20=cmf,
        volume_ratio=1.0,
        latest_date="2026-05-22",
        is_stale=False,
    )


def _response(
    top_assets: list[AssetCard],
    sectors: list[SectorCard],
) -> MarketPulseResponse:
    return MarketPulseResponse(
        market="US",
        as_of="2026-05-22T12:00:00",
        indices=[],
        macro=[],
        sectors=sectors,
        top_assets=top_assets,
        featured_etfs=[],
    )


def _insert_flat_bars(db, symbol: str, count: int = 19) -> None:
    today = date.today()
    for i in range(count):
        db.add(PriceBar(
            symbol=symbol,
            trading_date=today - timedelta(days=count - i),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            adjusted_close=100.0,
            volume=1_000_000,
            dividend_amount=0.0,
            split_coefficient=1.0,
            source="test",
            fetched_at=datetime.utcnow(),
        ))
    db.commit()


def test_live_overlay_updates_beyond_public_quote_route_cap(db):
    """A full S&P-sized mover pool must not silently stop at 100 symbols."""
    top_assets = [_asset(f"S{i:03d}") for i in range(150)]
    quotes = {
        f"S{i:03d}": _quote(
            f"S{i:03d}",
            price=100.0 + i,
            change_percent=i / 10.0,
        )
        for i in range(150)
    }

    live = _apply_live_quotes_to_pulse(
        _response(top_assets, sectors=[]),
        quotes,
        db,
        datetime(2026, 5, 26, 18, 0, 0),
    )

    last = live.top_assets[-1]
    assert last.symbol == "S149"
    assert last.price == 249.0
    assert last.perf_1d == 0.149
    assert last.latest_date == date.today().isoformat()


def test_live_overlay_recomputes_sector_cmf_and_resorts(db):
    """Sector rotation should reflect the live quote's current-day OHLCV."""
    for symbol in ("SPY", "XLK", "XLE"):
        _insert_flat_bars(db, symbol)

    resp = _response(
        top_assets=[],
        sectors=[
            _sector("XLE", cmf=0.30),
            _sector("XLK", cmf=-0.30),
        ],
    )
    quotes = {
        "SPY": _quote(
            "SPY",
            price=101.0,
            change_percent=1.0,
            day_high=101.0,
            day_low=99.0,
        ),
        "XLK": _quote(
            "XLK",
            price=110.0,
            change_percent=5.0,
            day_high=110.0,
            day_low=100.0,
        ),
        "XLE": _quote(
            "XLE",
            price=100.0,
            change_percent=-5.0,
            day_high=110.0,
            day_low=100.0,
        ),
    }

    live = _apply_live_quotes_to_pulse(
        resp,
        quotes,
        db,
        datetime(2026, 5, 26, 18, 0, 0),
    )

    assert [s.symbol for s in live.sectors] == ["XLK", "XLE"]
    assert live.sectors[0].price == 110.0
    assert live.sectors[0].perf_1d == 0.05
    assert live.sectors[0].cmf_20 is not None
    assert live.sectors[0].cmf_20 > live.sectors[1].cmf_20
