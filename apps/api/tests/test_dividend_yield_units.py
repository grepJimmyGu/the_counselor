"""Pin the dividend-yield SCALE end to end.

The regression this guards: `fmp_adapter` stored FMP's `lastDividend` — annual
dollars per share — directly into `symbols.dividend_yield`. Nothing errored.
MSFT's $3.56 annual payout simply became "3.56", which the screener compared
against a 0.04 threshold and the stocks table rendered as "356.00%".

Three consumers have to agree on one scale, and only a test can hold them
together because each looks correct in isolation:

  * `fmp_adapter._dividend_yield` WRITES a fraction
  * `screen_filter_parser` turns "4%" into 0.04 — a fraction
  * `_page-inner.tsx` renders `dividend_yield * 100` — expects a fraction

If someone "fixes" one side to percent, one of these fails.
"""
from __future__ import annotations

from app.services.adapters.fmp_adapter import _dividend_yield
from app.services.screen_filter_parser import extract_filters


def test_yield_is_a_fraction_not_dollars() -> None:
    # MSFT: $3.56/yr on a ~$510 share is ~0.7%, i.e. 0.007 as a fraction.
    y = _dividend_yield(3.56, 510.0)
    assert y is not None
    assert 0.006 < y < 0.008, f"expected a ~0.007 fraction, got {y}"
    # The specific bug: storing the raw dollar figure.
    assert y != 3.56


def test_high_payout_stays_a_fraction() -> None:
    # LLY: $6.92/yr on a ~$1,010 share. A dollars-per-share leak shows up here
    # as a value greater than 1, which no real yield ever is.
    y = _dividend_yield(6.92, 1010.0)
    assert y is not None and y < 1.0


def test_missing_or_junk_inputs_are_none_not_zero() -> None:
    # None (not 0.0) — a non-payer must be absent from a min-yield screen, and
    # 0.0 would still satisfy `>= 0`.
    assert _dividend_yield(None, 100.0) is None
    assert _dividend_yield(1.0, None) is None
    assert _dividend_yield(0, 100.0) is None
    assert _dividend_yield(1.0, 0) is None
    assert _dividend_yield("n/a", "n/a") is None


def test_parser_threshold_is_on_the_same_scale_as_storage() -> None:
    """The cross-component contract: "4%" must mean 4% of the stored value."""
    filters, applied = extract_filters("dividend yield above 4%")
    assert filters is not None
    threshold = filters.min_dividend_yield
    assert threshold == 0.04, f"parser emits {threshold}; storage is a fraction"

    # A 5% payer clears a 4% bar; a 0.7% payer does not. Under the old
    # dollars-per-share storage, MSFT's "3.56" cleared 0.04 and every dividend
    # payer matched.
    five_pct = _dividend_yield(5.0, 100.0)
    msft = _dividend_yield(3.56, 510.0)
    assert five_pct >= threshold
    assert msft < threshold
    assert "4%" in applied[0]


# ── the second half of the same bug, found in production 2026-08-13 ─────────
#
# The fraction guard above lives inside `fmp_adapter`, so it only covers rows
# written through that one function. Production still held 25 rows whose yield
# was not a fraction:
#
#     ALT  566.89   SPY  7.525   DIA  8.411   TLT  3.914   QQQ  3.034
#
# SPY's is its ~$7.50 annual payout — `lastDividend` dollars, written before
# the fraction fix and never rewritten, because the backfill that repaired the
# rest targets the Russell 3000 and these are ETFs. A `min_dividend_yield`
# screen ranked every one of them above every real payer.


def test_dollars_per_share_are_refused_not_rescaled() -> None:
    """The values actually found in production, by symbol.

    Refusing matters more than it looks: 7.525 / 100 would present SPY as a
    confident 7.5% yielder when the real figure is ~1.16%. A wrong number that
    looks right is the failure this column already shipped once — None simply
    drops the name out of a min-yield screen.
    """
    from app.services.fundamental_service import sane_dividend_yield

    for symbol, stored in [("SPY", 7.525), ("DIA", 8.41103), ("TLT", 3.91428),
                           ("QQQ", 3.03434), ("IWM", 2.65641), ("ALT", 566.8863636)]:
        assert sane_dividend_yield(stored) is None, f"{symbol}: {stored} passed as a yield"


def test_a_real_yield_survives_untouched() -> None:
    from app.services.fundamental_service import sane_dividend_yield

    for good in (0.0116, 0.0421, 0.0007, 0.0, 0.9999):
        assert sane_dividend_yield(good) == good


def test_junk_and_negatives_are_none() -> None:
    from app.services.fundamental_service import sane_dividend_yield

    assert sane_dividend_yield(None) is None
    assert sane_dividend_yield(-0.01) is None
    assert sane_dividend_yield("nonsense") is None


def test_yfinance_reads_the_unambiguous_key() -> None:
    """yfinance's `dividendYield` means a fraction in some releases and a
    percent in others, so the stored scale depended on the installed version.
    `dividendRate` is dollars per share in every release."""
    from app.services.adapters.yfinance_adapter import _yield_from_rate

    # SPY: ~$7.50/yr on a ~$645 share.
    y = _yield_from_rate(7.50, 645.0)
    assert y is not None and 0.010 < y < 0.013, f"expected ~0.0116, got {y}"
    assert _yield_from_rate(None, 645.0) is None
    assert _yield_from_rate(7.50, 0) is None


def test_the_screener_refuses_to_read_a_row_it_would_misreport(tmp_path) -> None:
    """The write guard stops new bad rows; production already holds 25. Until
    they are rewritten the READ side has to refuse them, or a dividend screen
    keeps returning ETFs at the top on the strength of a dollar figure."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.session import Base
    from app.models.symbol import SymbolCache
    from app.schemas.screener import ScreenerFilters
    from app.services.screener_service import ScreenerService

    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(SymbolCache(symbol="SPY", name="SPDR S&P 500", dividend_yield=7.525, is_active=True))
        db.add(SymbolCache(symbol="KO", name="Coca-Cola", dividend_yield=0.031, is_active=True))
        db.commit()

        got = ScreenerService().screen(db, ScreenerFilters(min_dividend_yield=0.02, limit=10))
        symbols = [r.symbol for r in got.results]
        assert "KO" in symbols, "a real 3.1% payer must still match a 2% floor"
        assert "SPY" not in symbols, "a dollars-per-share row was reported as a yield"
