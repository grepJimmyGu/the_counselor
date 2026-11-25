"""Today's option prices, estimated from the stock's price now.

The provider's option prices are from the last close (real-time option
prices are not on the plan). On a day the stock moves 12% they describe a
different stock: on 2026-11-25 NVDA traded at $145.72 against a chain priced
at $155.38.

Jimmy's choice, 2026-11-25: estimate, and say that it is an estimate.

How. Each contract's own price at the close is the starting point, and a
pricing model supplies only the CHANGE since then:

    estimate = price at the close
               + model(stock now, time left now) - model(stock at the close, time left then)

with the contract's own implied volatility from the close in both terms. The
model is Black-Scholes. Using it for the change and not for the level means
whatever it gets wrong about this contract (early exercise, dividends, the
rate) is in both terms and mostly cancels; a contract whose stock has not
moved keeps its quoted price, less a day's time value.

What it does not know: implied volatility moves when the stock does, usually
up when the stock falls. So after a sharp fall a real price is likely above
the estimate for puts and calls alike, and the reverse after a sharp rise.
It is an estimate of where the last close's prices would be, not a quote.
"""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.services.options.chain_service import OptionChain, OptionContract

_ET = ZoneInfo("America/New_York")

# The yearly interest rate the model discounts at. It sits in both terms of
# the difference, so the estimate depends on it little. Measured on a $150
# stock at 60% volatility, a point either way moves the estimate by up to 3
# cents for a 5% move in the stock on options out to four months (5 cents at
# a year), and up to 15 cents (26 at a year) for a 31% move.
RATE = 0.04
_SECONDS_IN_YEAR = 365 * 86_400.0
# Implied volatilities outside this are the provider's placeholders for a
# contract it could not solve (0, or thousands of percent).
_SIGMA_RANGE = (0.01, 5.0)


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes(kind: str, stock: float, strike: float, years: float, sigma: float, rate: float = RATE) -> float:
    """The Black-Scholes price of a European call or put on a stock that pays
    no dividend. At expiry, or with no volatility, it is what the option is
    worth exercised."""
    if stock <= 0 or strike <= 0:
        return 0.0
    if years <= 0 or sigma <= 0:
        return max(stock - strike, 0.0) if kind == "call" else max(strike - stock, 0.0)
    spread = sigma * math.sqrt(years)
    d1 = (math.log(stock / strike) + (rate + sigma * sigma / 2.0) * years) / spread
    d2 = d1 - spread
    discounted = strike * math.exp(-rate * years)
    if kind == "call":
        return stock * _normal_cdf(d1) - discounted * _normal_cdf(d2)
    return discounted * _normal_cdf(-d2) - stock * _normal_cdf(-d1)


def years_to_expiry(expiration: date, at: datetime) -> float:
    """Calendar time from `at` to the 4 pm New York close on `expiration`."""
    closes = datetime.combine(expiration, time(16, 0), tzinfo=_ET)
    return max((closes - at).total_seconds(), 0.0) / _SECONDS_IN_YEAR


def estimate_mid(
    contract: "OptionContract", quoted_stock: float, stock_now: float, quoted_at: datetime, now: datetime
) -> float:
    """`contract`'s price with the stock at `stock_now`, from its price at the close."""
    strike = contract.strike
    is_call = contract.kind == "call"
    intrinsic = max(stock_now - strike, 0.0) if is_call else max(strike - stock_now, 0.0)
    estimate = contract.mid
    sigma = contract.implied_volatility
    if sigma is not None and _SIGMA_RANGE[0] <= sigma <= _SIGMA_RANGE[1]:
        then = black_scholes(contract.kind, quoted_stock, strike, years_to_expiry(contract.expiration, quoted_at), sigma)
        after = black_scholes(contract.kind, stock_now, strike, years_to_expiry(contract.expiration, now), sigma)
        estimate = contract.mid + (after - then)
    # An option is never worth less than exercising it, never nothing while
    # it can still be traded, and never more than what it gives a right to.
    ceiling = stock_now if is_call else strike
    return round(min(max(estimate, intrinsic, 0.01), ceiling) + 1e-9, 2)


def estimate_contract(
    contract: "OptionContract", quoted_stock: float, stock_now: float, quoted_at: datetime, now: datetime
) -> "OptionContract":
    return contract._replace(
        mid=estimate_mid(contract, quoted_stock, stock_now, quoted_at, now), quoted_mid=contract.mid
    )


def quoted_at(as_of: date) -> datetime:
    """The moment a chain's prices are from: the close on its trading day."""
    return datetime.combine(as_of, time(16, 0), tzinfo=_ET)


def is_newer(as_of: date, traded_at: Optional[datetime]) -> bool:
    """Whether a stock price traded at `traded_at` is from a later session
    than a chain priced on `as_of`. A price from that same day (the evening
    after the close, or before the next open) is the price the chain already has."""
    return traded_at is not None and traded_at.astimezone(_ET).date() > as_of


def estimate_chain(chain: "OptionChain", stock_now: float, traded_at: Optional[datetime]) -> "OptionChain":
    """`chain` repriced for the stock at `stock_now`, or `chain` itself when
    that price is not from a later session than the chain's."""
    if stock_now <= 0 or traded_at is None or not is_newer(chain.as_of, traded_at):
        return chain
    then = quoted_at(chain.as_of)
    return replace(
        chain,
        underlying_price=stock_now,
        quoted_underlying_price=chain.underlying_price,
        estimated_at=traded_at,
        by_expiration={
            expiration: [estimate_contract(c, chain.underlying_price, stock_now, then, traded_at) for c in contracts]
            for expiration, contracts in chain.by_expiration.items()
        },
    )
