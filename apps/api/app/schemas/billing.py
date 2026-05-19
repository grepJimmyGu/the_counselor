from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class TierOption(BaseModel):
    tier: Literal["strategist", "quant"]
    billing_cycle: Literal["monthly", "annual"]
    price_id: str
    amount_cents: int
    display_price: str


class PricingPage(BaseModel):
    options: list[TierOption]
    trial_days: int = 14


class CheckoutSessionRequest(BaseModel):
    tier: Literal["strategist", "quant"]
    billing_cycle: Literal["monthly", "annual"]
    return_url: str


class CheckoutSessionResponse(BaseModel):
    url: str


class TrialStartRequest(BaseModel):
    tier: Literal["strategist", "quant"]


class TrialStartResponse(BaseModel):
    trial_end: datetime
    tier: str


class CustomerPortalResponse(BaseModel):
    url: str
