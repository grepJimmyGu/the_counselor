"""Stage 6a — H1 paywall A/B test variant assignment.

Variants:
  A (default): Scout = 5 runs/wk, 5yr history, 5-ticker custom universe
  B: 3yr history (tighter history paywall)
  C: 3-ticker universe (tighter universe paywall)

Variant assignment comes from PostHog feature flag 'paywall_variant'.
Without a PostHog key, get_feature_flag returns the default ("A") and
nothing changes — entitlements identical to pre-Stage-6a behavior.
"""
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy.orm import Session

from app.services.entitlements import (
    get_entitlements,
    get_or_create_current_weekly_usage,
)


def test_no_posthog_defaults_to_variant_a(make_user, db: Session):
    """With no key set, get_feature_flag returns default='A' → no cap changes."""
    user = make_user(email="ab-a-default@test.com", tier="scout")
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ent = get_entitlements(user, weekly)
    # Variant A == current Scout defaults
    assert ent.universe_size_max_custom == 5
    assert ent.history_window_years_custom == 5


def test_variant_a_unchanged(make_user, db: Session):
    user = make_user(email="ab-a@test.com", tier="scout")
    with patch("app.services.posthog_service.get_feature_flag", return_value="A"):
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
    assert ent.universe_size_max_custom == 5
    assert ent.history_window_years_custom == 5


def test_variant_b_tightens_history(make_user, db: Session):
    user = make_user(email="ab-b@test.com", tier="scout")
    with patch("app.services.posthog_service.get_feature_flag", return_value="B"):
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
    assert ent.history_window_years_custom == 3  # tightened
    assert ent.universe_size_max_custom == 5     # untouched


def test_variant_c_tightens_universe(make_user, db: Session):
    user = make_user(email="ab-c@test.com", tier="scout")
    with patch("app.services.posthog_service.get_feature_flag", return_value="C"):
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
    assert ent.universe_size_max_custom == 3  # tightened
    assert ent.history_window_years_custom == 5  # untouched


def test_strategist_unaffected_by_variant(make_user, db: Session):
    """A/B test only applies to Scout. Strategist sees their normal caps."""
    user = make_user(email="ab-strat@test.com", tier="strategist")
    with patch("app.services.posthog_service.get_feature_flag", return_value="B"):
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
    assert ent.universe_size_max_custom == 25  # Strategist default
    assert ent.history_window_years_custom == 10


def test_quant_unaffected_by_variant(make_user, db: Session):
    user = make_user(email="ab-quant@test.com", tier="quant")
    with patch("app.services.posthog_service.get_feature_flag", return_value="C"):
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
    assert ent.universe_size_max_custom == 100  # Quant default
    assert ent.history_window_years_custom == 20


def test_posthog_error_falls_back_to_a(make_user, db: Session):
    """If PostHog itself errors, fall back to variant A — never crash."""
    user = make_user(email="ab-err@test.com", tier="scout")
    with patch("app.services.posthog_service.get_feature_flag",
               side_effect=Exception("posthog down")):
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
    assert ent.universe_size_max_custom == 5
    assert ent.history_window_years_custom == 5
