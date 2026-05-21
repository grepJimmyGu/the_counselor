"""Entitlements resolver (Stage 1a).

Reads tier caps from TIER_CAPS, combines with the user's current-week usage,
and returns an Entitlements snapshot. Two important changes vs Stage 1:

  • The backtest meter is now WEEKLY (5 runs/week for Scout) — not monthly.
    Reads from weekly_usage; monthly_usage is kept populated as a legacy
    reporting source but no longer consulted for gating.

  • Templates are exempt from the universe/history caps. Custom strategies
    (built via chat) are gated. Two separate increment helpers track this
    split: increment_custom_backtest and increment_template_backtest.

Anonymous viewers have a separate cap surface (ANONYMOUS_CAPS) and a separate
resolver (get_anonymous_entitlements) keyed on AnonymousSession instead of User.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.anonymous_session import AnonymousSession
from app.models.user import User, MonthlyUsage
from app.models.weekly_usage import WeeklyUsage
from app.schemas.identity import AnonymousEntitlements, Entitlements

# ── Tier capability caps (Stage 1a matrix) ────────────────────────────────────

TIER_CAPS: dict[str, dict] = {
    "scout": {
        "custom_backtest_runs_per_week": 5,
        "template_runs_unlimited": True,
        "universe_size_max_custom": 5,
        "history_window_years_custom": 5,
        "asset_classes": ["equities"],
        "robustness_tests": [],
        "market_pulse_ticker_scope": "top_250",
        "business_model_section": "full",
        "commodity_framework": False,
        "saved_strategies_max": 10,
        "saved_strategies_always_public": True,
        "community_badge": None,
    },
    "strategist": {
        "custom_backtest_runs_per_week": None,  # unlimited
        "template_runs_unlimited": True,
        "universe_size_max_custom": 25,
        "history_window_years_custom": 10,
        "asset_classes": ["equities", "commodities"],
        # Names must match RobustnessRunRequest.tests_to_run Literal (schemas/robustness.py)
        "robustness_tests": ["parameter_sensitivity", "benchmark_comparison"],
        "market_pulse_ticker_scope": "all_us",
        "business_model_section": "full",
        "commodity_framework": True,
        "saved_strategies_max": 25,
        "saved_strategies_always_public": False,
        "community_badge": None,
    },
    "quant": {
        "custom_backtest_runs_per_week": None,
        "template_runs_unlimited": True,
        "universe_size_max_custom": 100,
        "history_window_years_custom": 20,
        "asset_classes": ["equities", "commodities", "a_shares"],
        # Names must match RobustnessRunRequest.tests_to_run Literal (schemas/robustness.py)
        "robustness_tests": [
            "parameter_sensitivity", "subperiod", "transaction_cost",
            "benchmark_comparison", "peer_ticker",
        ],
        "market_pulse_ticker_scope": "all_us_plus_alerts",
        "business_model_section": "full_plus_supply_chain",
        "commodity_framework": True,
        "saved_strategies_max": 10_000,
        "saved_strategies_always_public": False,
        "community_badge": "verified",
    },
}

ANONYMOUS_CAPS: dict[str, object] = {
    "anonymous_backtest_runs_per_session": 1,
    "asset_classes": ["equities"],
    "market_pulse_ticker_scope": "top_250",
}


# ── Week helpers ──────────────────────────────────────────────────────────────

def get_current_week_start_utc() -> date:
    """Monday 00:00 UTC of the current week."""
    today = datetime.utcnow().date()
    return today - timedelta(days=today.weekday())


def get_or_create_current_weekly_usage(db: Session, user_id: str) -> WeeklyUsage:
    """Return the WeeklyUsage row for *user_id* for the current UTC week.
    Creates one if absent. Handles the race where two concurrent first-requests
    both try to INSERT — the loser sees IntegrityError, rolls back, then re-fetches."""
    week_start = get_current_week_start_utc()
    row = db.get(WeeklyUsage, (user_id, week_start))
    if row is None:
        row = WeeklyUsage(user_id=user_id, week_start=week_start)
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except IntegrityError:
            db.rollback()
            row = db.get(WeeklyUsage, (user_id, week_start))
    return row


def increment_custom_backtest(db: Session, user_id: str) -> int:
    """Increment the weekly custom-strategy counter (gates Scout cap).
    Also bumps the legacy monthly counter so Stage 2 reports keep working.
    Returns the new custom_backtest_runs count for this week."""
    row = get_or_create_current_weekly_usage(db, user_id)
    row.backtest_runs += 1
    row.custom_backtest_runs += 1
    db.commit()
    _bump_monthly_legacy(db, user_id)
    return row.custom_backtest_runs


def increment_template_backtest(db: Session, user_id: str) -> int:
    """Increment the weekly template-run counter. Templates are unlimited for
    all tiers so this is for analytics only. Still bumps monthly legacy."""
    row = get_or_create_current_weekly_usage(db, user_id)
    row.backtest_runs += 1
    row.template_backtest_runs += 1
    db.commit()
    _bump_monthly_legacy(db, user_id)
    return row.template_backtest_runs


def _bump_monthly_legacy(db: Session, user_id: str) -> None:
    """Keep monthly_usage.backtest_runs populated for Stage 2 reports."""
    usage = get_or_create_current_usage(db, user_id)
    usage.backtest_runs += 1
    db.commit()


# ── Entitlements resolvers ────────────────────────────────────────────────────

def get_entitlements(user: User, weekly_usage: Optional[WeeklyUsage]) -> Entitlements:
    """Resolve capability caps for *user* given their current-week *weekly_usage*.

    Stage 6a: for Scout-tier users, reads the PostHog feature flag
    'paywall_variant' (deterministic per user.id) and applies one of three
    H1 paywall variants:
        A (default): runs_meter cap = 5/week (current behavior)
        B: history_window_years_custom = 3 (instead of 5)
        C: universe_size_max_custom = 3 (instead of 5)

    When PostHog isn't configured, get_feature_flag returns 'A' and
    nothing changes. Safe to leave wired indefinitely.
    """
    tier = user.plan.tier
    caps = TIER_CAPS[tier].copy()

    # H1 A/B test — only applies to Scout (other tiers are unlimited/wider)
    if tier == "scout":
        try:
            from app.services.posthog_service import get_feature_flag
            variant = get_feature_flag("paywall_variant", user.id, default="A")
        except Exception:
            variant = "A"
        if variant == "B":
            caps["history_window_years_custom"] = 3
        elif variant == "C":
            caps["universe_size_max_custom"] = 3

    runs_used = weekly_usage.custom_backtest_runs if weekly_usage else 0
    runs_per_week = caps["custom_backtest_runs_per_week"]
    runs_remaining = None if runs_per_week is None else max(0, runs_per_week - runs_used)

    is_creator = getattr(user, "is_creator", False)
    badge = "creator" if tier == "quant" and is_creator else caps["community_badge"]

    return Entitlements(
        tier=tier,
        status=user.plan.status,
        custom_backtest_runs_remaining=runs_remaining,
        week_start=get_current_week_start_utc().isoformat(),
        template_runs_unlimited=caps["template_runs_unlimited"],
        universe_size_max_custom=caps["universe_size_max_custom"],
        history_window_years_custom=caps["history_window_years_custom"],
        asset_classes=caps["asset_classes"],
        robustness_tests=caps["robustness_tests"],
        market_pulse_ticker_scope=caps["market_pulse_ticker_scope"],
        business_model_section=caps["business_model_section"],
        commodity_framework=caps["commodity_framework"],
        saved_strategies_max=caps["saved_strategies_max"],
        saved_strategies_always_public=caps["saved_strategies_always_public"],
        community_badge=badge,
    )


def get_anonymous_entitlements(session: Optional[AnonymousSession]) -> AnonymousEntitlements:
    """Resolve caps for an anonymous viewer, keyed on their AnonymousSession."""
    runs_used = session.runs_used if session else 0
    cap = ANONYMOUS_CAPS["anonymous_backtest_runs_per_session"]
    runs_remaining = max(0, cap - runs_used)
    return AnonymousEntitlements(
        runs_remaining=runs_remaining,
        asset_classes=list(ANONYMOUS_CAPS["asset_classes"]),
        market_pulse_ticker_scope=ANONYMOUS_CAPS["market_pulse_ticker_scope"],
        cta="signup_to_save" if runs_used >= 1 else "signup_to_continue",
    )


# ── Legacy monthly counter — kept for Stage 2 reports ─────────────────────────

def get_or_create_current_usage(db: Session, user_id: str) -> MonthlyUsage:
    """Legacy monthly usage row. Stage 1a's gating reads from weekly_usage;
    this remains so Stage 2 reports that reference monthly counters still work."""
    period_start = date.today().replace(day=1)
    row = db.get(MonthlyUsage, (user_id, period_start))
    if row is None:
        row = MonthlyUsage(user_id=user_id, period_start=period_start)
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except Exception:
            db.rollback()
            row = db.get(MonthlyUsage, (user_id, period_start))
    return row


def increment_backtest_runs(db: Session, user_id: str) -> int:
    """DEPRECATED in Stage 1a — use increment_custom_backtest or
    increment_template_backtest. Kept as a shim that bumps the monthly counter
    only (the weekly counter is the one that gates)."""
    usage = get_or_create_current_usage(db, user_id)
    usage.backtest_runs += 1
    db.commit()
    return usage.backtest_runs
