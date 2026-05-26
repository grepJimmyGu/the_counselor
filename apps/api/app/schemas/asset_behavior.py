"""Pydantic schema for the Asset Behavior Fingerprint endpoint (Module 2).

Mirrors `AssetBehaviorFingerprint` from
`app/services/asset_behavior_service.py` 1-to-1; kept in its own schema
module so the route can declare a `response_model` without circular imports.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AssetBehaviorFingerprintResponse(BaseModel):
    symbol: str = Field(..., description="Ticker symbol, uppercased.")
    asset_type: str = Field(..., description="One of: single_stock, commodity_etf, broad_etf, sector_etf, pair, basket, unknown")
    trending_pct: Optional[float] = Field(None, description="Percentage (0-100) of valid rolling windows that count as trending. Null when insufficient data.")
    mean_reverting_pct: Optional[float] = Field(None, description="Percentage (0-100) of |z|>1.5 extreme events that reverted within 10 days. Null when too few events.")
    realized_vol_1y: Optional[float] = Field(None, description="Annualised stdev of daily returns over the last 252 trading days. Null when insufficient data.")
    realized_vol_5y: Optional[float] = Field(None, description="Annualised stdev of daily returns over the last 5 years (or available history). Null when insufficient data.")
    max_drawdown_5y: Optional[float] = Field(None, description="Max drawdown over the last 5 years as a negative decimal (-0.32 == -32%). Null when insufficient data.")
    current_regime: str = Field(..., description="One of: trending, range_bound, volatile, mixed")
    data_quality: str = Field(..., description="One of: good, limited, insufficient")
    strategy_implication: str = Field(..., description="Short plain-English implication for strategy family selection.")
