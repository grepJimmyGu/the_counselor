from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr


class UserPublic(BaseModel):
    id: str
    handle: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]
    locale: str

    model_config = {"from_attributes": True}


class PlanPublic(BaseModel):
    tier: Literal["scout", "strategist", "quant"]
    status: Literal["active", "trialing", "past_due", "canceled"]
    billing_cycle: Optional[Literal["monthly", "annual"]] = None
    trial_end: Optional[datetime] = None
    current_period_end: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UsageThisMonth(BaseModel):
    period_start: str  # ISO date "YYYY-MM-DD"
    backtest_runs: int
    robustness_runs: int
    saved_strategies_count: int

    model_config = {"from_attributes": True}


class UserMe(UserPublic):
    email: EmailStr
    created_at: datetime
    plan: PlanPublic
    usage: UsageThisMonth


class Entitlements(BaseModel):
    """Single source of truth for capability caps. Returned by GET /api/me/entitlements."""
    tier: Literal["scout", "strategist", "quant"]
    status: Literal["active", "trialing", "past_due", "canceled"]
    backtest_runs_remaining: Optional[int]  # None = unlimited
    universe_size_max: int
    history_window_years: int
    asset_classes: list[str]
    robustness_tests: list[str]
    market_pulse_ticker_scope: Literal["top_250", "all_us", "all_us_plus_alerts"]
    business_model_section: Literal["full", "full_plus_supply_chain"]
    commodity_framework: bool
    saved_strategies_max: int
    api_access: bool
    community_badge: Optional[Literal["verified", "creator"]] = None


class TokenResponse(BaseModel):
    user: UserPublic
    session_token: str


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None
    locale: Literal["en", "zh"] = "en"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OAuthGoogleRequest(BaseModel):
    id_token: str


class PatchMeRequest(BaseModel):
    handle: Optional[str] = None
    display_name: Optional[str] = None
    locale: Optional[Literal["en", "zh"]] = None
    avatar_url: Optional[str] = None
