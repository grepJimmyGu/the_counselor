from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")

Strategy = Literal["long_call", "long_put", "covered_call", "protective_put"]


class OptionContractView(BaseModel):
    contract_id: str
    kind: Literal["call", "put"]
    strike: float
    bid: float
    ask: float
    # The price a plan is built on: halfway between bid and ask at the
    # close, or, in an estimated chain, the estimate for the stock's price now.
    mid: float
    # Only in an estimated chain: halfway between bid and ask at the close,
    # which `mid` was estimated from. `bid` and `ask` are always the close's.
    quoted_mid: Optional[float] = None
    last: Optional[float] = None
    volume: int
    open_interest: int


class OptionExpirationView(BaseModel):
    date: date
    days: int
    # The standard monthly expiry (third Friday), as against a weekly one.
    monthly: bool
    # What the call and put nearest the stock's price cost together, as a
    # percent of that price. Null when there is no such pair.
    implied_move_pct: Optional[float] = None


class OptionChainView(BaseModel):
    """One expiry of a stock's option chain, near the stock's price."""

    symbol: str
    # The trading day the quoted prices are from.
    as_of: date
    # The stock's close that day, or, in an estimated chain, its price now.
    underlying_price: float
    # Set when the chain was asked for at the stock's price now and that
    # price is from a later session than `as_of`: when the stock traded at
    # `underlying_price`, and its close on `as_of` that the quotes were made
    # against. Every contract's `mid` is then an estimate.
    estimated_at: Optional[datetime] = None
    quoted_underlying_price: Optional[float] = None
    expirations: List[OptionExpirationView]
    default_expiration: date
    expiration: date
    contracts: List[OptionContractView]


class OptionLeg(BaseModel):
    """One line of a plan: shares, or contracts of one option."""

    kind: Literal["stock", "call", "put"]
    side: Literal["buy", "sell"]
    # Shares for a stock leg, contracts (of 100 shares) for an option leg.
    quantity: int = Field(ge=1, le=100_000)
    # Per share: as quoted at the close, or an estimate for the stock's
    # price when the plan was built (`quoted_price` is then set).
    price: float = Field(ge=0, le=1_000_000)
    # Only when `price` is an estimate: the quote at the close it came from.
    # It lives in the saved legs, so a plan read back still says which of its
    # prices were estimates.
    quoted_price: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    strike: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    expiration: Optional[date] = None
    contract_id: Optional[str] = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _an_option_names_its_contract(self) -> "OptionLeg":
        is_option = self.kind != "stock"
        named = self.strike is not None and self.expiration is not None and bool(self.contract_id)
        if is_option and not named:
            raise ValueError("An option leg needs its strike, expiration and contract_id.")
        if not is_option and (self.strike is not None or self.expiration is not None or self.contract_id):
            raise ValueError("A stock leg has no strike, expiration or contract_id.")
        return self


class OptionPlanCreate(BaseModel):
    symbol: str
    strategy: Strategy
    legs: List[OptionLeg] = Field(min_length=1, max_length=4)
    # The stock's price and the day the plan's prices are from.
    underlying_price: float = Field(gt=0, le=1_000_000)
    as_of: date

    @field_validator("symbol")
    @classmethod
    def _a_ticker(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not SYMBOL.match(symbol):
            raise ValueError("Not a ticker symbol.")
        return symbol


class OptionPlanView(BaseModel):
    id: str
    symbol: str
    # Plain text on the way out, so an app older than a strategy added later
    # can still read the list.
    strategy: str
    legs: List[OptionLeg]
    underlying_price: float
    as_of: date
    created_at: datetime
