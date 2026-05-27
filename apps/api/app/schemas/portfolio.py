"""Portfolio Mode schemas (PRD-13b).

Two layers:
  * Inputs  — Holding, DiagnoseRequest
  * Outputs — StyleMix, FactorExposure, BehaviorAggregate, SectorBreakdown,
              OverlayRecommendation, PortfolioDiagnosis, DiagnoseResponse

The Holding model is the canonical shape for "one position in a user's
book" — reused wherever a future mode ingests user-supplied holdings.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Inputs ───────────────────────────────────────────────────────────────────


class Holding(BaseModel):
    """One position in the user's portfolio.

    The user MUST provide either `weight` or `shares`. If both are present,
    `weight` wins (it expresses target allocation intent directly).
    `cost_basis_per_share` is optional and used only for P&L display —
    it does NOT affect the backtest.
    """

    ticker: str = Field(..., min_length=1, max_length=10)
    weight: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Target portfolio weight 0..1. Wins over `shares` if both present.",
    )
    shares: Optional[float] = Field(
        None, gt=0.0,
        description="Number of shares held. Used only if `weight` is None.",
    )
    cost_basis_per_share: Optional[float] = Field(
        None, gt=0.0,
        description="USD per share. Optional. Display only — does not affect backtest.",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return (v or "").upper().strip()

    @model_validator(mode="after")
    def at_least_one_size_field(self) -> "Holding":
        if self.weight is None and self.shares is None:
            raise ValueError(
                f"Holding {self.ticker}: must provide either `weight` or `shares`"
            )
        return self


class DiagnoseRequest(BaseModel):
    holdings: list[Holding] = Field(
        ..., min_length=1, max_length=100,
        description=(
            "Portfolio holdings. Endpoint enforces tier-specific caps "
            "(Scout: 5, Strategist: 25, Quant: 100) on top of this hard cap."
        ),
    )


# ── Diagnosis output ─────────────────────────────────────────────────────────

StyleBucket = Literal["growth", "value", "defensive", "commodity", "macro_sensitive"]
BehaviorBucket = Literal["trending", "mean_reverting", "mixed"]
OverlayKind = Literal["defensive", "rotation", "rebalance"]


class StyleMix(BaseModel):
    """Fraction of portfolio (weight-adjusted) in each style bucket.

    All five buckets sum to ~1.0. A holding without enough data to classify
    falls into `macro_sensitive` as the catch-all (which the
    `unclassified_weight` field separately reports for transparency).
    """

    growth: float = Field(0.0, ge=0.0, le=1.0)
    value: float = Field(0.0, ge=0.0, le=1.0)
    defensive: float = Field(0.0, ge=0.0, le=1.0)
    commodity: float = Field(0.0, ge=0.0, le=1.0)
    macro_sensitive: float = Field(0.0, ge=0.0, le=1.0)
    unclassified_weight: float = Field(0.0, ge=0.0, le=1.0)


class FactorExposure(BaseModel):
    """Weight-averaged factor exposure across holdings.

    Each field is an absolute exposure on a normalized scale; positive
    means tilted *toward* the factor, negative *away*. Values that
    couldn't be computed (e.g. missing fundamentals) are `None`.
    """

    size: Optional[float] = None          # log(market_cap) z-score
    value: Optional[float] = None         # -P/E z-score (cheap → higher)
    momentum: Optional[float] = None      # 12-1m return z-score
    quality: Optional[float] = None       # ROE z-score
    low_vol: Optional[float] = None       # -realized_vol_1y z-score
    beta_to_spy: Optional[float] = None   # CompanyProfile.beta (weighted mean)


class BehaviorAggregate(BaseModel):
    """% of book (weight-adjusted) in each behavior bucket.

    Rolled up from per-holding fingerprints computed by
    `compute_asset_behavior_fingerprint`. Sums to ~1.0.
    """

    trending_pct: float = Field(0.0, ge=0.0, le=1.0)
    mean_reverting_pct: float = Field(0.0, ge=0.0, le=1.0)
    mixed_pct: float = Field(0.0, ge=0.0, le=1.0)


class SectorBreakdown(BaseModel):
    """Weight share by GICS sector. Sums to ~1.0 across known sectors;
    missing-sector weight is reported separately."""

    sectors: dict[str, float] = Field(default_factory=dict)
    unknown_sector_weight: float = Field(0.0, ge=0.0, le=1.0)


class OverlayRecommendation(BaseModel):
    overlay: OverlayKind
    rank: int = Field(..., ge=1, le=3, description="1 = top pick, 3 = least-fit")
    reason: str = Field(..., description="One-line rationale shown on the OverlayPicker card.")


class PortfolioDiagnosis(BaseModel):
    """Summary view of a portfolio's character — the dashboard payload."""

    n_holdings: int
    style_mix: StyleMix
    factor_exposure: FactorExposure
    behavior: BehaviorAggregate
    sectors: SectorBreakdown
    # Realized portfolio vol at current weights (annualized stdev of daily
    # portfolio returns, 1-year window). None when too few holdings have
    # price history to compute.
    realized_vol_1y: Optional[float] = None
    # Trailing-5y max drawdown of the portfolio at its current weights.
    # Computed by simulating a buy-and-hold of the weights against
    # daily-rebalanced returns. None when too few holdings have history.
    max_drawdown_5y: Optional[float] = None
    # Soft caveats the dashboard surfaces to the user (e.g. "3 of 5
    # holdings have <1y of price data; vol and drawdown estimates may
    # be noisy").
    caveats: list[str] = Field(default_factory=list)


class DiagnoseResponse(BaseModel):
    diagnosis: PortfolioDiagnosis
    recommended_overlays: list[OverlayRecommendation]
    cache_hit: bool = False  # surfaced for debugging / metrics
