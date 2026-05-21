"""Publish service (Stage 4a).

Operates on the new published_strategies table. Snapshot semantics: a published
strategy is a frozen copy of the strategy_json + metrics + universe at publish
time, decoupled from the user's saved version.

The Scout auto-publish path (called from saved_strategy_service when
ent.saved_strategies_always_public=True) creates BOTH a saved row and a
published row. Strategist+ saves create only the saved row unless the user
explicitly publishes.
"""
from __future__ import annotations

import random
import re
import string
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.backtest import BacktestRecord
from app.models.published_strategy import PublishedStrategy
from app.models.user import User

# ── Schemas ───────────────────────────────────────────────────────────────────


class PublishStrategyRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    strategy_json: dict
    backtest_record_id: Optional[str] = None
    # Optional snapshot of equity curve points for /s/[slug] chart rendering.
    equity_curve_snapshot: Optional[list[dict]] = None


# ── Slug ──────────────────────────────────────────────────────────────────────

_NANOID_ALPHABET = string.ascii_lowercase + string.digits


def _nanoid(n: int = 6) -> str:
    return "".join(random.choices(_NANOID_ALPHABET, k=n))


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    return s or "strategy"


def _unique_slug(db: Session, title: str) -> str:
    """Build slug + nanoid suffix; retry on the rare collision."""
    base = _slugify(title)
    for _ in range(5):
        candidate = f"{base}-{_nanoid()}"
        existing = db.scalar(select(PublishedStrategy).where(PublishedStrategy.slug == candidate))
        if not existing:
            return candidate
    # 5 collisions → fall back to a longer nanoid; 8 chars makes the next collision
    # extremely unlikely
    return f"{base}-{_nanoid(8)}"


# ── Metrics snapshot helpers ──────────────────────────────────────────────────


def _extract_metrics(backtest_record_id: Optional[str], db: Session) -> dict[str, Any]:
    """Best-effort extraction of the top-line metrics from a BacktestRecord.
    Returns {} if the record isn't found — caller can supply metrics directly."""
    if not backtest_record_id:
        return {}
    bt = db.get(BacktestRecord, backtest_record_id)
    if bt is None or not bt.result_payload:
        return {}
    payload = bt.result_payload or {}
    metrics = payload.get("metrics", {}) if isinstance(payload, dict) else {}
    return {
        "total_return": metrics.get("total_return"),
        "annualized_return": metrics.get("annualized_return"),
        "sharpe_ratio": metrics.get("sharpe_ratio"),
        "max_drawdown": metrics.get("max_drawdown"),
        "win_rate": metrics.get("win_rate"),
        "number_of_trades": metrics.get("number_of_trades"),
        "buy_and_hold_return": metrics.get("buy_and_hold_return"),
    }


def _extract_equity_curve(backtest_record_id: Optional[str], db: Session) -> list[dict]:
    """Pull the equity_curve points from the backtest result, downsample to
    keep the snapshot reasonable (~150 points max)."""
    if not backtest_record_id:
        return []
    bt = db.get(BacktestRecord, backtest_record_id)
    if bt is None or not bt.result_payload:
        return []
    payload = bt.result_payload if isinstance(bt.result_payload, dict) else {}
    curve = payload.get("equity_curve") or []
    benchmark = payload.get("benchmark_curve") or []

    # Zip by date when possible; otherwise just take equity points.
    pts = []
    if curve and benchmark and len(curve) == len(benchmark):
        for e, b in zip(curve, benchmark):
            pts.append({
                "date": e.get("date") if isinstance(e, dict) else None,
                "equity": e.get("value") if isinstance(e, dict) else None,
                "benchmark": b.get("value") if isinstance(b, dict) else None,
            })
    elif curve:
        for e in curve:
            pts.append({
                "date": e.get("date") if isinstance(e, dict) else None,
                "equity": e.get("value") if isinstance(e, dict) else None,
                "benchmark": None,
            })

    # Downsample to ~150 points
    if len(pts) > 150:
        stride = len(pts) // 150
        pts = pts[::stride][:150]
    return pts


# ── Publish ───────────────────────────────────────────────────────────────────


def publish_strategy(
    db: Session,
    user: User,
    payload: PublishStrategyRequest,
) -> PublishedStrategy:
    """Create a new PublishedStrategy. Snapshots strategy_json, metrics,
    universe, benchmark, equity curve. Slug is unique. Returns the row."""
    strategy = payload.strategy_json
    universe = strategy.get("universe", []) if isinstance(strategy, dict) else []
    benchmark = strategy.get("benchmark", "SPY") if isinstance(strategy, dict) else "SPY"
    strategy_type = strategy.get("strategy_type", "unknown") if isinstance(strategy, dict) else "unknown"

    # Metrics: prefer caller-supplied snapshot if equity_curve was passed;
    # otherwise pull from the backtest record.
    metrics_snapshot = _extract_metrics(payload.backtest_record_id, db)
    equity_curve = payload.equity_curve_snapshot or _extract_equity_curve(payload.backtest_record_id, db)

    ps = PublishedStrategy(
        id=str(uuid4()),
        slug=_unique_slug(db, payload.title),
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        strategy_json=strategy,
        backtest_record_id=payload.backtest_record_id,
        metrics_snapshot=metrics_snapshot,
        universe_snapshot=list(universe),
        benchmark_snapshot=str(benchmark),
        strategy_type=str(strategy_type),
        equity_curve_snapshot=equity_curve,
        locale=getattr(user, "locale", "en") or "en",
    )
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps


# ── Feed / detail / state ─────────────────────────────────────────────────────


def list_feed(
    db: Session,
    *,
    sort: str = "trending",
    strategy_type: Optional[str] = None,
    ticker: Optional[str] = None,
    handle: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> list[PublishedStrategy]:
    """Return a page of published strategies. Hidden and deleted excluded."""
    q = select(PublishedStrategy).where(
        PublishedStrategy.is_hidden == False,  # noqa: E712
        PublishedStrategy.is_deleted == False,  # noqa: E712
    )
    if strategy_type:
        q = q.where(PublishedStrategy.strategy_type == strategy_type)
    if ticker:
        # Cross-dialect "ticker in universe_snapshot JSON array" check via LIKE
        ticker_upper = ticker.upper()
        # Match `"AAPL"` in the serialized array. Works because we use double-quoted JSON strings.
        from sqlalchemy import cast, String as _S
        q = q.where(cast(PublishedStrategy.universe_snapshot, _S).ilike(f'%"{ticker_upper}"%'))
    if handle:
        # Resolve handle → user_id once.
        user_id = db.scalar(select(User.id).where(User.handle == handle.lower()))
        if user_id is None:
            return []
        q = q.where(PublishedStrategy.user_id == user_id)

    # Sort options
    if sort == "newest":
        q = q.order_by(PublishedStrategy.created_at.desc())
    elif sort == "top_returns":
        # JSON metrics_snapshot.total_return — cross-dialect comparison is finicky.
        # For v1, fetch and sort in Python. Acceptable for small feed sizes.
        q = q.order_by(PublishedStrategy.created_at.desc())
        rows = list(db.scalars(q))
        rows.sort(key=lambda r: (r.metrics_snapshot or {}).get("total_return") or 0, reverse=True)
        start = (page - 1) * page_size
        return rows[start:start + page_size]
    elif sort == "top_sharpe":
        q = q.order_by(PublishedStrategy.created_at.desc())
        rows = list(db.scalars(q))
        rows.sort(key=lambda r: (r.metrics_snapshot or {}).get("sharpe_ratio") or 0, reverse=True)
        start = (page - 1) * page_size
        return rows[start:start + page_size]
    else:
        # "trending": (likes*3 + comments*2 + follows) / (hours_since+2)^1.5
        q = q.order_by(PublishedStrategy.created_at.desc())
        rows = list(db.scalars(q))
        now = datetime.utcnow()

        def score(r: PublishedStrategy) -> float:
            hours = max((now - r.created_at.replace(tzinfo=None)).total_seconds() / 3600.0, 0.0)
            return (r.like_count * 3 + r.comment_count * 2 + r.follow_count) / ((hours + 2) ** 1.5)

        rows.sort(key=score, reverse=True)
        start = (page - 1) * page_size
        return rows[start:start + page_size]

    start = (page - 1) * page_size
    return list(db.scalars(q.offset(start).limit(page_size)))


def get_by_slug(db: Session, slug: str) -> Optional[PublishedStrategy]:
    row = db.scalar(select(PublishedStrategy).where(PublishedStrategy.slug == slug))
    if row is None:
        return None
    if row.is_hidden or row.is_deleted:
        return None
    return row


def increment_view(db: Session, slug: str) -> None:
    row = db.scalar(select(PublishedStrategy).where(PublishedStrategy.slug == slug))
    if row is None or row.is_hidden or row.is_deleted:
        return
    row.view_count = (row.view_count or 0) + 1
    db.commit()


def update_strategy(
    db: Session,
    user_id: str,
    strategy_id: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[PublishedStrategy]:
    row = db.get(PublishedStrategy, strategy_id)
    if row is None or row.user_id != user_id or row.is_deleted:
        return None
    if title is not None:
        row.title = title
    if description is not None:
        row.description = description
    db.commit()
    db.refresh(row)
    return row


def soft_delete(db: Session, user_id: str, strategy_id: str) -> bool:
    row = db.get(PublishedStrategy, strategy_id)
    if row is None or row.user_id != user_id:
        return False
    row.is_deleted = True
    db.commit()
    return True
