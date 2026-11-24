"""The notice inbox (2026-11-23): notices grouped by the strategy or screen
that sent them, read in bulk, and silenced per source.

Jimmy's brief: "a simple, clear notice system that users can identify
important information quickly and take actions" — silence, read or avoid
messages, and trace each one back to the strategy or screen behind it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.notice_mute import NoticeMute
from app.models.notification_banner import NotificationBannerEntry
from app.models.saved_strategy import SavedStrategy
from app.services import notice_inbox as ni
from app.services.channel_dispatcher import (
    SignalChangeEvent,
    dispatch_in_app_banner,
    dispatch_signal_change_email,
)

T0 = datetime(2026, 11, 23, 14, 0, 0)


def _source(db: Session, user, title: str, *, screen: bool = False) -> SavedStrategy:
    s = SavedStrategy(
        id=str(uuid4()), user_id=user.id, title=title,
        strategy_json={"kind": "screen"} if screen else {"strategy_type": "trend_following"},
    )
    db.add(s)
    db.commit()
    return s


def _notice(db: Session, user, source, *, minutes: int = 0, read: bool = False, **cols) -> NotificationBannerEntry:
    row = NotificationBannerEntry(
        user_id=user.id,
        title=cols.pop("title", f"⚡ {source.title if source else 'X'} — LONG NVDA"),
        body=cols.pop("body", "Top-3 by trailing 6-month return."),
        strategy_slug=source.id if source else None,
        created_at=T0 + timedelta(minutes=minutes),
        acknowledged_at=T0 if read else None,
        **cols,
    )
    db.add(row)
    db.commit()
    return row


def _exit(db: Session, user, source, *, minutes: int = 0, legacy: bool = False) -> NotificationBannerEntry:
    cols = {} if legacy else {"source_kind": "position", "level": "act", "symbol": "AMD"}
    return _notice(
        db, user, source, minutes=minutes,
        title="AMD hit your stop",
        body=f"AMD reached a level your strategy '{source.title}' defines as an exit. "
             "Nothing has been sold — no order goes out unless you send it.",
        **cols,
    )


# ── grouping and ranking ─────────────────────────────────────────────────────


def test_notices_are_grouped_by_their_source_and_the_important_ones_come_first(
    db: Session, make_user,
) -> None:
    user = make_user(email="inbox-group@test.com")
    trend = _source(db, user, "Trend NVDA")
    momo = _source(db, user, "Momentum leaders", screen=True)
    _notice(db, user, momo, minutes=30, source_kind="screen", level="fyi", symbol="PLTR")
    _notice(db, user, momo, minutes=20, source_kind="screen", level="fyi", symbol="CRWD")
    _notice(db, user, trend, minutes=10, source_kind="strategy", level="changed")
    _notice(db, user, trend, minutes=5, read=True, source_kind="strategy", level="changed")

    groups, muted = ni.inbox(db, user.id)

    # The strategy's buy/sell change outranks two newer screen entrants.
    assert [g.title for g in groups] == ["Trend NVDA", "Momentum leaders"]
    assert [(g.source_kind, g.level, g.unread_count) for g in groups] == [
        ("strategy", "changed", 1), ("screen", "fyi", 2),
    ]
    assert [n.symbol for n in groups[1].notices] == ["PLTR", "CRWD"]
    assert muted == []


def test_exits_are_not_repeated_in_the_inbox_because_they_are_listed_as_decisions(
    db: Session, make_user,
) -> None:
    user = make_user(email="inbox-exits@test.com")
    trend = _source(db, user, "Trend AMD")
    _exit(db, user, trend)
    _exit(db, user, trend, minutes=1, legacy=True)

    groups, _ = ni.inbox(db, user.id)

    assert groups == []
    # …but the source's own page still shows them.
    assert [n.level for n in ni.history(db, user.id, trend.id).notices] == ["act", "act"]


def test_REGRESSION_rows_written_before_the_source_columns_are_classified_on_read(
    db: Session, make_user,
) -> None:
    """Production has months of notices with only a title, a body and the
    source's id. They are classified on read, not rewritten."""
    user = make_user(email="inbox-legacy@test.com")
    trend = _source(db, user, "Trend NVDA")
    screen = _source(db, user, "Breakouts", screen=True)
    _notice(db, user, trend)
    _notice(db, user, screen, title="⚡ Breakouts — PLTR entered 'Breakouts'")
    _notice(db, user, None, title="⚡ Old strategy — LONG SPY")

    groups, _ = ni.inbox(db, user.id)

    kinds = {(g.title, g.source_kind, g.level) for g in groups}
    assert kinds == {
        ("Trend NVDA", "strategy", "changed"),
        ("Breakouts", "screen", "fyi"),
        ("Old strategy", "other", "changed"),
    }


def test_someone_elses_notices_and_sources_never_show(db: Session, make_user) -> None:
    me = make_user(email="inbox-me@test.com")
    other = make_user(email="inbox-other@test.com")
    theirs = _source(db, other, "Their strategy")
    _notice(db, other, theirs)

    assert ni.inbox(db, me.id)[0] == []
    with pytest.raises(ni.UnknownSource):
        ni.history(db, me.id, theirs.id)
    with pytest.raises(ni.UnknownSource):
        ni.mute(db, me.id, theirs.id)


# ── reading ──────────────────────────────────────────────────────────────────


def test_a_whole_source_or_named_notices_can_be_marked_read(db: Session, make_user) -> None:
    user = make_user(email="inbox-read@test.com")
    trend = _source(db, user, "Trend")
    screen = _source(db, user, "Screen", screen=True)
    a = _notice(db, user, trend, source_kind="strategy", level="changed")
    _notice(db, user, screen, source_kind="screen", level="fyi")
    _notice(db, user, screen, minutes=1, source_kind="screen", level="fyi")

    assert ni.mark_read(db, user.id, source_id=screen.id) == 2
    assert [g.title for g in ni.inbox(db, user.id)[0]] == ["Trend"]

    assert ni.mark_read(db, user.id, ids=[a.id]) == 1
    assert ni.inbox(db, user.id)[0] == []

    with pytest.raises(ValueError):
        ni.mark_read(db, user.id)
    with pytest.raises(ValueError):
        ni.mark_read(db, user.id, ids=[a.id], source_id=trend.id)


# ── muting ───────────────────────────────────────────────────────────────────


def test_muting_clears_a_source_but_never_an_exit(db: Session, make_user) -> None:
    user = make_user(email="inbox-mute@test.com")
    trend = _source(db, user, "Trend AMD")
    _notice(db, user, trend, source_kind="strategy", level="changed")
    exit_row = _exit(db, user, trend, minutes=1)
    legacy_exit = _exit(db, user, trend, minutes=2, legacy=True)

    assert ni.mute(db, user.id, trend.id) == 1

    groups, muted = ni.inbox(db, user.id)
    assert groups == []
    assert [(m.title, m.source_kind) for m in muted] == [("Trend AMD", "strategy")]
    db.refresh(exit_row)
    db.refresh(legacy_exit)
    assert exit_row.acknowledged_at is None and legacy_exit.acknowledged_at is None
    assert ni.history(db, user.id, trend.id).muted is True

    ni.unmute(db, user.id, trend.id)
    assert ni.inbox(db, user.id)[1] == []
    ni.unmute(db, user.id, trend.id)  # twice is harmless


def _event(user, source) -> SignalChangeEvent:
    return SignalChangeEvent(
        user_email=user.email, user_id=user.id, strategy_name=source.title,
        strategy_slug=source.id, change_type="flip_to_long",
        new_signal_display="LONG NVDA", as_of_date=date(2026, 11, 23),
        reference_prices={}, rule_context="Close crossed above the 50-day average.",
        risk_context="", executed_url=f"/strategies/{source.id}",
    )


@pytest.fixture
def writer_uses_test_db(db: Session, monkeypatch):
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    return db


def test_a_muted_source_still_records_its_notice_but_already_read(
    db: Session, make_user, writer_uses_test_db,
) -> None:
    user = make_user(email="inbox-write@test.com")
    trend = _source(db, user, "Trend NVDA")

    assert dispatch_in_app_banner(_event(user, trend), source_kind="strategy", level="changed", symbol="NVDA")
    ni.mute(db, user.id, trend.id)
    assert dispatch_in_app_banner(_event(user, trend), source_kind="strategy", level="changed", symbol="NVDA")

    rows = db.query(NotificationBannerEntry).filter_by(user_id=user.id).order_by(NotificationBannerEntry.id).all()
    assert [(r.source_kind, r.level, r.symbol) for r in rows] == [("strategy", "changed", "NVDA")] * 2
    # The first was read by the mute; the second arrived read.
    assert all(r.acknowledged_at is not None for r in rows)
    assert len(ni.history(db, user.id, trend.id).notices) == 2


def test_REGRESSION_mute_covers_email_too(db: Session, make_user, monkeypatch) -> None:
    """Jimmy's decision (2026-11-23): "mute covers email too". Checked in the
    one function every signal-change email passes through."""
    user = make_user(email="inbox-email@test.com")
    trend = _source(db, user, "Trend NVDA")
    sent = []
    monkeypatch.setattr(
        "app.services.channel_dispatcher.send_email",
        lambda *a, **kw: sent.append(kw.get("template")) or True,
    )

    assert dispatch_signal_change_email(_event(user, trend), db, user) is True
    ni.mute(db, user.id, trend.id)
    assert dispatch_signal_change_email(_event(user, trend), db, user) is False
    assert sent == ["signal_change"]


# ── routes ───────────────────────────────────────────────────────────────────


def test_the_routes_group_read_and_mute_for_the_signed_in_user_only(db: Session, make_user) -> None:
    from app.api.routes.notifications import (
        MarkReadRequest,
        mark_notices_read,
        mute_notice_source,
        notice_inbox_view,
        notice_source_view,
        unmute_notice_source,
    )

    user = make_user(email="inbox-routes@test.com")
    other = make_user(email="inbox-routes-other@test.com")
    screen = _source(db, user, "Breakouts", screen=True)
    theirs = _source(db, other, "Theirs")
    _notice(db, user, screen, source_kind="screen", level="fyi", symbol="PLTR")

    view = notice_inbox_view(current_user=user, db=db)
    assert [(g.title, g.source_kind, g.unread_count) for g in view.groups] == [("Breakouts", "screen", 1)]
    assert view.groups[0].notices[0].symbol == "PLTR"

    assert mute_notice_source(source_id=screen.id, current_user=user, db=db).status_code == 204
    assert notice_inbox_view(current_user=user, db=db).muted[0].title == "Breakouts"
    assert notice_source_view(source_id=screen.id, current_user=user, db=db).muted is True
    assert unmute_notice_source(source_id=screen.id, current_user=user, db=db).status_code == 204

    with pytest.raises(HTTPException) as foreign:
        mute_notice_source(source_id=theirs.id, current_user=user, db=db)
    assert foreign.value.status_code == 404
    with pytest.raises(HTTPException) as blank:
        mark_notices_read(payload=MarkReadRequest(), current_user=user, db=db)
    assert blank.value.status_code == 400
    assert mark_notices_read(
        payload=MarkReadRequest(source_id=screen.id), current_user=user, db=db,
    ).marked == 0  # the mute already read it


def test_the_websites_banner_endpoint_is_unchanged(db: Session, make_user) -> None:
    from app.api.routes.notifications import list_pending_banners

    user = make_user(email="inbox-web@test.com")
    trend = _source(db, user, "Trend AMD")
    _exit(db, user, trend)
    _notice(db, user, trend, minutes=1, source_kind="strategy", level="changed")

    rows = list_pending_banners(current_user=user, db=db)
    assert len(rows) == 2 and rows[0].strategy_slug == trend.id
