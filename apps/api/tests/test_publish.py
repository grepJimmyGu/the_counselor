"""Stage 4a — publish + feed + snapshot integrity + Scout auto-publish."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.published_strategy import PublishedStrategy
from app.models.saved_strategy import SavedStrategy
from app.services import community_publish_service as svc
from app.services.community_publish_service import PublishStrategyRequest
from app.services.saved_strategy_service import SaveStrategyRequest, save_strategy


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_publish_payload(title: str = "My Test Strategy") -> PublishStrategyRequest:
    return PublishStrategyRequest(
        title=title,
        description="A description that says useful things.",
        strategy_json={
            "strategy_name": "test-strategy",
            "strategy_type": "moving_average_filter",
            "universe": ["AAPL", "MSFT"],
            "benchmark": "SPY",
        },
    )


# ── Publish basics ───────────────────────────────────────────────────────────


def test_publish_creates_snapshot(make_user, db: Session):
    user = make_user(email="pub@test.com", tier="strategist")
    row = svc.publish_strategy(db, user, _make_publish_payload())
    assert row.id and row.slug
    assert row.user_id == user.id
    assert row.title == "My Test Strategy"
    assert row.universe_snapshot == ["AAPL", "MSFT"]
    assert row.benchmark_snapshot == "SPY"
    assert row.strategy_type == "moving_average_filter"
    assert row.is_hidden is False
    assert row.is_deleted is False
    assert row.like_count == 0


def test_publish_generates_unique_slug(make_user, db: Session):
    user = make_user(email="slug@test.com", tier="strategist")
    r1 = svc.publish_strategy(db, user, _make_publish_payload(title="Same Title"))
    r2 = svc.publish_strategy(db, user, _make_publish_payload(title="Same Title"))
    assert r1.slug != r2.slug
    # Both should have the same base slug
    assert r1.slug.startswith("same-title-")
    assert r2.slug.startswith("same-title-")


def test_publish_slug_handles_special_chars(make_user, db: Session):
    user = make_user(email="special@test.com", tier="strategist")
    row = svc.publish_strategy(
        db, user, _make_publish_payload(title="100-day MA + RSI < 30!"),
    )
    # Should be safely sluggified
    assert row.slug.startswith("100-day-ma-rsi-30-")
    assert " " not in row.slug
    assert "!" not in row.slug


def test_edit_saved_strategy_does_not_affect_published(make_user, db: Session):
    """Snapshot integrity: editing the saved version doesn't change the published row."""
    user = make_user(email="snapshot@test.com", tier="strategist")
    saved_strategy_json = {
        "strategy_name": "v1",
        "strategy_type": "moving_average_filter",
        "universe": ["AAPL"],
        "benchmark": "SPY",
    }
    # Publish a snapshot
    published = svc.publish_strategy(
        db, user,
        PublishStrategyRequest(
            title="My Strat",
            strategy_json=saved_strategy_json,
        ),
    )
    original_universe = list(published.universe_snapshot)

    # Pretend the user edits their saved version (mutate the local dict — published
    # row already has a snapshot deep-copied via SQLAlchemy JSON serialization).
    saved_strategy_json["universe"].append("NVDA")
    saved_strategy_json["strategy_name"] = "v2"

    # Reload published row and verify it's unchanged.
    db.refresh(published)
    assert published.universe_snapshot == original_universe


# ── Scout auto-publish ───────────────────────────────────────────────────────


def test_scout_save_auto_publishes(make_user, db: Session):
    """Stage 1a + 4a: Scout saves automatically also publish to community."""
    user = make_user(email="scout-pub@test.com", tier="scout")
    saved = save_strategy(
        db, user,
        SaveStrategyRequest(
            title="Scout's Strategy",
            strategy_json={
                "strategy_name": "scout-test",
                "strategy_type": "momentum_rotation",
                "universe": ["AAPL", "MSFT", "GOOGL"],
                "benchmark": "SPY",
            },
        ),
    )
    assert saved.is_public is True  # Stage 1a force-public

    # Also created a published_strategies row
    published = db.scalar(
        select(PublishedStrategy).where(PublishedStrategy.user_id == user.id)
    )
    assert published is not None, "Scout save should auto-publish"
    assert published.title == "Scout's Strategy"
    assert published.strategy_type == "momentum_rotation"


def test_strategist_save_does_not_auto_publish(make_user, db: Session):
    """Strategist+ saves do NOT auto-publish — explicit publish only."""
    user = make_user(email="strat-priv@test.com", tier="strategist")
    save_strategy(
        db, user,
        SaveStrategyRequest(
            title="Strategist Private",
            strategy_json={
                "strategy_name": "priv",
                "strategy_type": "moving_average_filter",
                "universe": ["AAPL"],
                "benchmark": "SPY",
            },
            is_public=False,
        ),
    )
    saved_count = db.query(SavedStrategy).filter(SavedStrategy.user_id == user.id).count()
    published_count = db.query(PublishedStrategy).filter(
        PublishedStrategy.user_id == user.id
    ).count()
    assert saved_count == 1
    assert published_count == 0


# ── Feed ─────────────────────────────────────────────────────────────────────


def test_feed_excludes_hidden_and_deleted(make_user, db: Session):
    user = make_user(email="hide@test.com", tier="strategist")
    r1 = svc.publish_strategy(db, user, _make_publish_payload(title="Visible"))
    r2 = svc.publish_strategy(db, user, _make_publish_payload(title="Hidden"))
    r3 = svc.publish_strategy(db, user, _make_publish_payload(title="Deleted"))
    r2.is_hidden = True
    r3.is_deleted = True
    db.commit()

    rows = svc.list_feed(db, sort="newest")
    slugs = {r.slug for r in rows}
    assert r1.slug in slugs
    assert r2.slug not in slugs
    assert r3.slug not in slugs


def test_feed_newest_sort(make_user, db: Session):
    user = make_user(email="newest@test.com", tier="strategist")
    r_old = svc.publish_strategy(db, user, _make_publish_payload(title="Old"))
    r_new = svc.publish_strategy(db, user, _make_publish_payload(title="New"))
    rows = svc.list_feed(db, sort="newest")
    assert rows[0].slug == r_new.slug  # newest first
    assert rows[1].slug == r_old.slug


def test_feed_filter_by_strategy_type(make_user, db: Session):
    user = make_user(email="filter-type@test.com", tier="strategist")
    r_momentum = svc.publish_strategy(
        db, user,
        PublishStrategyRequest(
            title="Momentum",
            strategy_json={
                "strategy_name": "m",
                "strategy_type": "momentum_rotation",
                "universe": ["AAPL"],
                "benchmark": "SPY",
            },
        ),
    )
    r_meanrev = svc.publish_strategy(
        db, user,
        PublishStrategyRequest(
            title="MeanRev",
            strategy_json={
                "strategy_name": "mr",
                "strategy_type": "rsi_mean_reversion",
                "universe": ["AAPL"],
                "benchmark": "SPY",
            },
        ),
    )
    rows = svc.list_feed(db, strategy_type="momentum_rotation")
    assert all(r.strategy_type == "momentum_rotation" for r in rows)
    assert r_momentum.slug in {r.slug for r in rows}
    assert r_meanrev.slug not in {r.slug for r in rows}


def test_feed_filter_by_ticker_in_universe(make_user, db: Session):
    user = make_user(email="filter-tick@test.com", tier="strategist")
    r_aapl = svc.publish_strategy(
        db, user,
        PublishStrategyRequest(
            title="AAPL Strat",
            strategy_json={
                "strategy_name": "a",
                "strategy_type": "moving_average_filter",
                "universe": ["AAPL"],
                "benchmark": "SPY",
            },
        ),
    )
    r_nvda = svc.publish_strategy(
        db, user,
        PublishStrategyRequest(
            title="NVDA Strat",
            strategy_json={
                "strategy_name": "n",
                "strategy_type": "moving_average_filter",
                "universe": ["NVDA"],
                "benchmark": "SPY",
            },
        ),
    )
    rows = svc.list_feed(db, ticker="AAPL")
    slugs = {r.slug for r in rows}
    assert r_aapl.slug in slugs
    assert r_nvda.slug not in slugs


# ── State changes ────────────────────────────────────────────────────────────


def test_get_by_slug_hides_deleted(make_user, db: Session):
    user = make_user(email="get-del@test.com", tier="strategist")
    row = svc.publish_strategy(db, user, _make_publish_payload())
    assert svc.get_by_slug(db, row.slug) is not None
    svc.soft_delete(db, user.id, row.id)
    assert svc.get_by_slug(db, row.slug) is None


def test_soft_delete_only_works_for_owner(make_user, db: Session):
    alice = make_user(email="alice-del@test.com", tier="strategist")
    bob = make_user(email="bob-del@test.com", tier="strategist")
    row = svc.publish_strategy(db, alice, _make_publish_payload())
    assert svc.soft_delete(db, bob.id, row.id) is False
    db.refresh(row)
    assert row.is_deleted is False
    assert svc.soft_delete(db, alice.id, row.id) is True


def test_update_only_works_for_owner(make_user, db: Session):
    alice = make_user(email="alice-up@test.com", tier="strategist")
    bob = make_user(email="bob-up@test.com", tier="strategist")
    row = svc.publish_strategy(db, alice, _make_publish_payload())
    bob_attempt = svc.update_strategy(db, bob.id, row.id, title="Hacked")
    assert bob_attempt is None
    db.refresh(row)
    assert row.title == "My Test Strategy"
