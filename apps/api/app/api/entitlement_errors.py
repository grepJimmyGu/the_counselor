"""402 Upgrade-Required error envelope (Stage 1a foundation; Stage 3 expands).

Every gate raises HTTPException(402, detail=...) with a structured detail
matching EntitlementErrorDetail. The frontend reads `code` to pick the right
upgrade modal copy and `cta_action` to pick the primary button behavior.

Stage 1a uses the foundation laid out below for:
  - saved_strategies_quota_reached
  - anonymous_runs_exhausted (cta_action="signup") — the ONLY anonymous
    gate; first-run "always passes" policy from 2026-05-22.

(Removed 2026-05-22:
  - `anonymous_chat_locked` — anonymous now allowed ONE custom run
  - `anonymous_universe_too_large` — first-run is unrestricted on universe
  - `anonymous_asset_class_locked` — engine handles missing data cleanly
The runs_exhausted cap covers the post-first-run case.)

Stage 3 will extend with: runs_exhausted, universe_too_large, history_too_long,
robustness_test_locked, market_pulse_ticker_out_of_scope.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel


CodeT = Literal[
    # Stage 1a — saved-strategy gate
    "saved_strategies_quota_reached",
    # Stage 1a — anonymous gates (all resolve to signup)
    "anonymous_runs_exhausted",
    # Stage 3 — extended (declared now so the literal is stable across stages)
    "runs_exhausted",
    "universe_too_large",
    "history_too_long",
    "robustness_test_locked",
    "market_pulse_ticker_out_of_scope",
    # Stage 7 — chat
    "chat_quota_exhausted",
]


class EntitlementErrorDetail(BaseModel):
    code: CodeT
    current_tier: Optional[Literal["scout", "strategist", "quant"]] = None
    required_tier: Optional[Literal["strategist", "quant"]] = None
    current_value: Optional[str] = None
    limit_value: Optional[str] = None
    upgrade_url: str
    cta_text: str
    detail: str
    is_anonymous: bool = False
    cta_action: Literal["signup", "trial", "checkout", "upgrade"] = "upgrade"


class EntitlementErrorResponse(BaseModel):
    error: Literal["upgrade_required"] = "upgrade_required"
    entitlement: EntitlementErrorDetail


# ── Copy maps ─────────────────────────────────────────────────────────────────

_CTA_COPY: dict[str, str] = {
    "saved_strategies_quota_reached": "Upgrade to save more strategies",
    "anonymous_runs_exhausted": "Sign up to keep exploring",
    "runs_exhausted": "Upgrade to Strategist for unlimited runs",
    "universe_too_large": "Upgrade to test larger universes",
    "history_too_long": "Upgrade for longer backtest windows",
    "robustness_test_locked": "Upgrade to Quant for the full robustness suite",
    "market_pulse_ticker_out_of_scope": "Upgrade to research all US stocks",
    "chat_quota_exhausted": "Sign up for unlimited chat",
}

# Which tier unlocks each code.
_REQUIRED_TIER: dict[str, Optional[str]] = {
    "saved_strategies_quota_reached": "strategist",
    "runs_exhausted": "strategist",
    "universe_too_large": "strategist",
    "history_too_long": "strategist",
    "robustness_test_locked": "quant",
    "market_pulse_ticker_out_of_scope": "strategist",
    "chat_quota_exhausted": "strategist",  # Scout cap → upgrade to Strategist
    # Anonymous codes resolve to signup; no required_tier.
}


def upgrade_error(
    code: CodeT,
    *,
    current_tier: Optional[str] = None,
    current_value: Optional[str] = None,
    limit_value: Optional[str] = None,
    is_anonymous: bool = False,
    cta_action_override: Optional[Literal["signup", "trial", "checkout", "upgrade"]] = None,
) -> HTTPException:
    """Build a 402 HTTPException with the standardized envelope.

    `cta_action_override` lets a specific gate pick a non-default action
    without touching the rest of the routing logic. Default is "signup"
    for anonymous, "upgrade" otherwise. The chat quota gate (Stage 7) uses
    "trial" for Scout to send them to the 14-day Strategist trial.
    """
    default_cta: Literal["signup", "upgrade"] = "signup" if is_anonymous else "upgrade"
    cta_action = cta_action_override or default_cta
    required = None if is_anonymous else _REQUIRED_TIER.get(code)
    upgrade_url = (
        f"/signup?gate={code}" if is_anonymous else f"/pricing?gate={code}&from={current_tier or 'scout'}"
    )
    detail = EntitlementErrorDetail(
        code=code,
        current_tier=current_tier,  # type: ignore[arg-type]
        required_tier=required,  # type: ignore[arg-type]
        current_value=current_value,
        limit_value=limit_value,
        upgrade_url=upgrade_url,
        cta_text=_CTA_COPY[code],
        detail=_CTA_COPY[code],
        is_anonymous=is_anonymous,
        cta_action=cta_action,
    )
    envelope = EntitlementErrorResponse(entitlement=detail)
    return HTTPException(status_code=402, detail=envelope.model_dump())
