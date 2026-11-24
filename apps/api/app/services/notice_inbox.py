"""The notice inbox: what each strategy and screen has told the user (2026-11-23).

Notices are rows in `notification_banner_entries`, written by five jobs:

    signal_cron          a strategy's signal changed       strategy     changed
    saved_screen_cron    a new name entered a screen       screen       fyi
    ticker_alert_cron    a followed stock passes / fails   stock_alert  fyi
    daily_position_jobs  a stop or target was hit          position     act
    intraday_jobs        the same, from the intraday feed  position     act

This module groups them by the strategy or screen that sent them, ranks the
groups, and lets the user read or silence a source.

Two rules it keeps:

  - **Exits are never silenced.** A stop or target on a held position is a
    decision about real money; muting a strategy does not touch them.
  - **Muting never deletes.** A muted source's notices are still written, as
    already read, so its history stays visible on its own page.

Rows written before the source columns existed carry only a title, a body and
the source's id; `classify` works out their kind and level on read rather than
rewriting production rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notice_mute import NoticeMute
from app.models.notification_banner import NotificationBannerEntry
from app.models.saved_strategy import SavedStrategy

STRATEGY = "strategy"
SCREEN = "screen"
STOCK_ALERT = "stock_alert"
POSITION = "position"

ACT = "act"
CHANGED = "changed"
FYI = "fyi"

# Higher sorts first.
_LEVEL_RANK = {ACT: 3, CHANGED: 2, FYI: 1}

# Unread notices read per inbox load. Far past any real backlog; a cap so a
# runaway job cannot make the Actions tab load thousands of rows.
_INBOX_ROWS = 500
# Notices shown on one source's page, newest first.
_HISTORY_ROWS = 50


# ── what a notice is ─────────────────────────────────────────────────────────


def source_kind_of(strategy: Optional[SavedStrategy]) -> str:
    """Strategy or screen. Screens are SavedStrategy rows whose
    `strategy_json.kind` is "screen"."""
    body = getattr(strategy, "strategy_json", None) or {}
    return SCREEN if isinstance(body, dict) and body.get("kind") == SCREEN else STRATEGY


def classify(row: NotificationBannerEntry, strategy: Optional[SavedStrategy]) -> Tuple[str, str]:
    """(source_kind, level) for a notice, from its own columns when it has
    them and from what older rows always carried when it does not.

    Older rows came from two writers: `dispatch_in_app_banner`, whose title
    starts with "⚡", and the two exit monitors, whose body says the level
    is "an exit".
    """
    kind = row.source_kind
    level = row.level
    if kind and level:
        return kind, level
    if kind is None:
        if "defines as an exit" in (row.body or "") or not (row.title or "").startswith("⚡"):
            kind = POSITION
        else:
            kind = source_kind_of(strategy)
    if level is None:
        level = default_level(kind)
    return kind, level


def default_level(kind: str) -> str:
    if kind == POSITION:
        return ACT
    if kind == STRATEGY:
        return CHANGED
    return FYI


# ── mutes ────────────────────────────────────────────────────────────────────


def muted_sources(db: Session, user_id: str) -> List[str]:
    rows = db.execute(
        select(NoticeMute.source_id).where(NoticeMute.user_id == user_id)
    ).scalars().all()
    return list(rows)


def is_muted(db: Session, user_id: str, source_id: Optional[str]) -> bool:
    if not source_id:
        return False
    return db.get(NoticeMute, (user_id, source_id)) is not None


def _owned_source(db: Session, user_id: str, source_id: str) -> Optional[SavedStrategy]:
    strategy = db.get(SavedStrategy, source_id)
    if strategy is None or strategy.user_id != user_id:
        return None
    return strategy


class UnknownSource(LookupError):
    """The id is not one of the user's strategies or screens."""


def mute(db: Session, user_id: str, source_id: str) -> int:
    """Silence a strategy or screen. Its unread notices are marked read,
    except exits, which stay. Returns how many were marked read."""
    if _owned_source(db, user_id, source_id) is None:
        raise UnknownSource(source_id)
    if db.get(NoticeMute, (user_id, source_id)) is None:
        db.add(NoticeMute(user_id=user_id, source_id=source_id))
    marked = _mark(db, user_id, source_id=source_id, keep_exits=True)
    db.commit()
    return marked


def unmute(db: Session, user_id: str, source_id: str) -> None:
    row = db.get(NoticeMute, (user_id, source_id))
    if row is not None:
        db.delete(row)
        db.commit()


# ── reading ──────────────────────────────────────────────────────────────────


@dataclass
class Notice:
    id: int
    title: str
    body: str
    symbol: Optional[str]
    source_kind: str
    level: str
    created_at: datetime
    read: bool


@dataclass
class NoticeGroup:
    source_id: Optional[str]
    source_kind: str            # strategy | screen; "other" when no source
    title: str
    level: str                  # the highest unread level
    unread_count: int
    latest_at: datetime
    muted: bool
    notices: List[Notice] = field(default_factory=list)


@dataclass
class MutedSource:
    source_id: str
    source_kind: str
    title: str


def _strategies(db: Session, user_id: str, ids: Iterable[Optional[str]]) -> Dict[str, SavedStrategy]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = db.execute(
        select(SavedStrategy).where(
            SavedStrategy.id.in_(wanted), SavedStrategy.user_id == user_id,
        )
    ).scalars().all()
    return {r.id: r for r in rows}


def _title_from_notice(row: NotificationBannerEntry) -> str:
    """The source's name as the notice wrote it: "⚡ Name — signal"."""
    title = (row.title or "").lstrip("⚡").strip()
    return title.split(" — ")[0].strip() or "Your strategy"


def _notice(row: NotificationBannerEntry, strategy: Optional[SavedStrategy]) -> Notice:
    kind, level = classify(row, strategy)
    return Notice(
        id=row.id, title=row.title, body=row.body, symbol=row.symbol,
        source_kind=kind, level=level,
        created_at=row.created_at or datetime.utcnow(),
        read=row.acknowledged_at is not None,
    )


def inbox(db: Session, user_id: str) -> Tuple[List[NoticeGroup], List[MutedSource]]:
    """Unread notices grouped by the strategy or screen that sent them.

    Exits are left out: the Actions tab lists them above, as decisions, and
    they leave that list when the user says what they did. Showing them here
    as well would show every exit twice.

    Groups are ranked by their most important unread notice, then by the
    newest. A source that was muted after these arrived still shows, marked
    muted, until they are read.
    """
    rows = db.execute(
        select(NotificationBannerEntry)
        .where(
            NotificationBannerEntry.user_id == user_id,
            NotificationBannerEntry.acknowledged_at.is_(None),
        )
        .order_by(NotificationBannerEntry.created_at.desc(), NotificationBannerEntry.id.desc())
        .limit(_INBOX_ROWS)
    ).scalars().all()
    mutes = set(muted_sources(db, user_id))
    strategies = _strategies(db, user_id, [r.strategy_slug for r in rows] + list(mutes))

    groups: Dict[Optional[str], NoticeGroup] = {}
    for row in rows:
        strategy = strategies.get(row.strategy_slug or "")
        notice = _notice(row, strategy)
        if notice.source_kind == POSITION:
            continue
        key = row.strategy_slug or None
        group = groups.get(key)
        if group is None:
            group = groups[key] = NoticeGroup(
                source_id=key,
                source_kind=source_kind_of(strategy) if key else "other",
                title=(strategy.title if strategy else None) or _title_from_notice(row),
                level=notice.level,
                unread_count=0,
                latest_at=notice.created_at,
                muted=key in mutes if key else False,
            )
        group.notices.append(notice)
        group.unread_count += 1
        if _LEVEL_RANK.get(notice.level, 0) > _LEVEL_RANK.get(group.level, 0):
            group.level = notice.level

    ranked = sorted(
        groups.values(),
        key=lambda g: (_LEVEL_RANK.get(g.level, 0), g.latest_at),
        reverse=True,
    )
    muted = [
        MutedSource(
            source_id=sid,
            source_kind=source_kind_of(strategies.get(sid)),
            title=strategies[sid].title if sid in strategies else "A deleted strategy",
        )
        for sid in sorted(mutes, key=lambda s: (strategies[s].title.lower() if s in strategies else "~"))
    ]
    return ranked, muted


@dataclass
class SourceHistory:
    source_id: str
    source_kind: str
    title: str
    muted: bool
    notices: List[Notice]


def history(db: Session, user_id: str, source_id: str) -> SourceHistory:
    """Everything one strategy or screen has sent, read or not, newest first."""
    strategy = _owned_source(db, user_id, source_id)
    rows = db.execute(
        select(NotificationBannerEntry)
        .where(
            NotificationBannerEntry.user_id == user_id,
            NotificationBannerEntry.strategy_slug == source_id,
        )
        .order_by(NotificationBannerEntry.created_at.desc(), NotificationBannerEntry.id.desc())
        .limit(_HISTORY_ROWS)
    ).scalars().all()
    if strategy is None and not rows:
        raise UnknownSource(source_id)
    return SourceHistory(
        source_id=source_id,
        source_kind=source_kind_of(strategy),
        title=(strategy.title if strategy else None) or (_title_from_notice(rows[0]) if rows else "Your strategy"),
        muted=is_muted(db, user_id, source_id),
        notices=[_notice(r, strategy) for r in rows],
    )


# ── marking read ─────────────────────────────────────────────────────────────


def _mark(
    db: Session, user_id: str, *,
    ids: Optional[Sequence[int]] = None, source_id: Optional[str] = None,
    keep_exits: bool = False,
) -> int:
    query = select(NotificationBannerEntry).where(
        NotificationBannerEntry.user_id == user_id,
        NotificationBannerEntry.acknowledged_at.is_(None),
    )
    if ids is not None:
        query = query.where(NotificationBannerEntry.id.in_(list(ids)))
    if source_id is not None:
        query = query.where(NotificationBannerEntry.strategy_slug == source_id)
    rows = db.execute(query).scalars().all()
    now = datetime.utcnow()
    marked = 0
    for row in rows:
        if keep_exits and classify(row, None)[0] == POSITION:
            continue
        row.acknowledged_at = now
        marked += 1
    return marked


def mark_read(
    db: Session, user_id: str, *,
    ids: Optional[Sequence[int]] = None, source_id: Optional[str] = None,
) -> int:
    """Mark notices read: the ones named, or every unread one from a source.
    Exits included: reading a notice is not a decision about the position,
    which stays in the Actions list until the user resolves it."""
    if (ids is None) == (source_id is None):
        raise ValueError("Name the notices or the source, not both.")
    marked = _mark(db, user_id, ids=ids, source_id=source_id)
    db.commit()
    return marked
