from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User, MonthlyUsage
from app.schemas.identity import Entitlements

# ── Tier capability caps ──────────────────────────────────────────────────────

TIER_CAPS: dict[str, dict] = {
    "scout": {
        "backtest_runs_per_month": 5,
        "universe_size_max": 5,
        "history_window_years": 5,
        "asset_classes": ["equities"],
        "robustness_tests": [],
        "market_pulse_ticker_scope": "top_250",
        "business_model_section": "full",
        "commodity_framework": False,
        "saved_strategies_max": 3,
        "api_access": False,
    },
    "strategist": {
        "backtest_runs_per_month": None,  # unlimited
        "universe_size_max": 25,
        "history_window_years": 10,
        "asset_classes": ["equities", "commodities"],
        "robustness_tests": ["param_sensitivity", "benchmark"],
        "market_pulse_ticker_scope": "all_us",
        "business_model_section": "full",
        "commodity_framework": True,
        "saved_strategies_max": 25,
        "api_access": False,
    },
    "quant": {
        "backtest_runs_per_month": None,
        "universe_size_max": 100,
        "history_window_years": 20,
        "asset_classes": ["equities", "commodities", "a_shares"],
        "robustness_tests": [
            "param_sensitivity", "sub_period", "transaction_cost", "benchmark", "peer_ticker",
        ],
        "market_pulse_ticker_scope": "all_us_plus_alerts",
        "business_model_section": "full_plus_supply_chain",
        "commodity_framework": True,
        "saved_strategies_max": 10_000,
        "api_access": True,
    },
}


def get_entitlements(user: User, usage: Optional[MonthlyUsage]) -> Entitlements:
    """Resolve capability caps for *user* given their current-month *usage*."""
    tier = user.plan.tier
    caps = TIER_CAPS[tier]
    runs_used = usage.backtest_runs if usage else 0
    runs_per_month = caps["backtest_runs_per_month"]
    runs_remaining = None if runs_per_month is None else max(0, runs_per_month - runs_used)

    is_creator = getattr(user, "is_creator", False)
    badge = (
        "creator" if tier == "quant" and is_creator
        else "verified" if tier == "quant"
        else None
    )

    return Entitlements(
        tier=tier,
        status=user.plan.status,
        backtest_runs_remaining=runs_remaining,
        universe_size_max=caps["universe_size_max"],
        history_window_years=caps["history_window_years"],
        asset_classes=caps["asset_classes"],
        robustness_tests=caps["robustness_tests"],
        market_pulse_ticker_scope=caps["market_pulse_ticker_scope"],
        business_model_section=caps["business_model_section"],
        commodity_framework=caps["commodity_framework"],
        saved_strategies_max=caps["saved_strategies_max"],
        api_access=caps["api_access"],
        community_badge=badge,
    )


def get_or_create_current_usage(db: Session, user_id: str) -> MonthlyUsage:
    """Return the MonthlyUsage row for *user_id* in the current UTC month.
    Creates one if it doesn't exist yet, using INSERT … ON CONFLICT DO NOTHING semantics
    so parallel first requests don't produce duplicate rows."""
    period_start = date.today().replace(day=1)
    row = db.get(MonthlyUsage, (user_id, period_start))
    if row is None:
        row = MonthlyUsage(user_id=user_id, period_start=period_start)
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except Exception:
            # Another request beat us to it — race on first-of-month
            db.rollback()
            row = db.get(MonthlyUsage, (user_id, period_start))
    return row


def increment_backtest_runs(db: Session, user_id: str) -> int:
    usage = get_or_create_current_usage(db, user_id)
    usage.backtest_runs += 1
    db.commit()
    return usage.backtest_runs
