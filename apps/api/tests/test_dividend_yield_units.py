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
