from __future__ import annotations

"""
Community Layer API — PRD-12 (watchlists), PRD-13 (votes + signal scores),
PRD-14 (strategy comments + upvotes).

All mutating endpoints require X-Internal-Key (Next.js BFF only).
Read endpoints (signal scores, public community board) are open.
"""

import math
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/api/community", tags=["community"])


# ── Internal key guard (same pattern as auth.py) ─────────────────────────────

def verify_internal_key(x_internal_key: Optional[str] = Header(default=None)) -> None:
    settings = get_settings()
    required = settings.internal_api_key
    if not required:
        raise HTTPException(status_code=503, detail="INTERNAL_API_KEY not configured.")
    if x_internal_key != required:
        raise HTTPException(status_code=401, detail="Invalid internal key.")


# ── PRD-12: Watchlists ────────────────────────────────────────────────────────

class WatchlistItem(BaseModel):
    symbol: str
    added_at: datetime


class WatchlistResponse(BaseModel):
    symbols: list[WatchlistItem]
    count: int


@router.get("/watchlist/{user_id}", response_model=WatchlistResponse,
            dependencies=[Depends(verify_internal_key)])
def get_watchlist(user_id: str, db: Session = Depends(get_db)) -> WatchlistResponse:
    rows = db.execute(
        text("SELECT symbol, added_at FROM user_watchlists WHERE user_id = :uid ORDER BY added_at DESC"),
        {"uid": user_id},
    ).fetchall()
    items = [WatchlistItem(symbol=r._mapping["symbol"], added_at=r._mapping["added_at"]) for r in rows]
    return WatchlistResponse(symbols=items, count=len(items))


@router.post("/watchlist/{user_id}/{symbol}", dependencies=[Depends(verify_internal_key)])
def add_to_watchlist(user_id: str, symbol: str, db: Session = Depends(get_db)) -> dict:
    sym = symbol.upper()
    try:
        db.execute(
            text("INSERT INTO user_watchlists (user_id, symbol) VALUES (:uid, :sym)"
                 " ON CONFLICT (user_id, symbol) DO NOTHING"),
            {"uid": user_id, "sym": sym},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to add to watchlist.")
    _refresh_signal_score(sym, db)
    return {"symbol": sym, "action": "added"}


@router.delete("/watchlist/{user_id}/{symbol}", dependencies=[Depends(verify_internal_key)])
def remove_from_watchlist(user_id: str, symbol: str, db: Session = Depends(get_db)) -> dict:
    sym = symbol.upper()
    db.execute(
        text("DELETE FROM user_watchlists WHERE user_id = :uid AND symbol = :sym"),
        {"uid": user_id, "sym": sym},
    )
    db.commit()
    _refresh_signal_score(sym, db)
    return {"symbol": sym, "action": "removed"}


@router.get("/watchlist/{user_id}/{symbol}/status",
            dependencies=[Depends(verify_internal_key)])
def watchlist_status(user_id: str, symbol: str, db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        text("SELECT 1 FROM user_watchlists WHERE user_id = :uid AND symbol = :sym"),
        {"uid": user_id, "sym": symbol.upper()},
    ).fetchone()
    return {"symbol": symbol.upper(), "in_watchlist": row is not None}


# ── PRD-13: Votes ─────────────────────────────────────────────────────────────

VoteType = Literal["bull", "bear", "hold"]


class VoteRequest(BaseModel):
    vote: VoteType


class VoteSummary(BaseModel):
    symbol: str
    bull: int
    bear: int
    hold: int
    total: int
    user_vote: Optional[str] = None


@router.post("/vote/{user_id}/{symbol}", dependencies=[Depends(verify_internal_key)])
def cast_vote(user_id: str, symbol: str, body: VoteRequest,
              db: Session = Depends(get_db)) -> VoteSummary:
    sym = symbol.upper()
    now = datetime.utcnow()
    try:
        db.execute(
            text(
                "INSERT INTO user_votes (user_id, symbol, vote, voted_at, updated_at)"
                " VALUES (:uid, :sym, :vote, :now, :now)"
                " ON CONFLICT (user_id, symbol) DO UPDATE SET vote = :vote, updated_at = :now"
            ),
            {"uid": user_id, "sym": sym, "vote": body.vote, "now": now},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to record vote.")
    _refresh_signal_score(sym, db)
    return _get_vote_summary(sym, user_id, db)


@router.delete("/vote/{user_id}/{symbol}", dependencies=[Depends(verify_internal_key)])
def remove_vote(user_id: str, symbol: str, db: Session = Depends(get_db)) -> dict:
    sym = symbol.upper()
    db.execute(
        text("DELETE FROM user_votes WHERE user_id = :uid AND symbol = :sym"),
        {"uid": user_id, "sym": sym},
    )
    db.commit()
    _refresh_signal_score(sym, db)
    return {"symbol": sym, "action": "removed"}


@router.get("/votes/{symbol}", response_model=VoteSummary)
def get_vote_summary(symbol: str, user_id: Optional[str] = Query(default=None),
                     db: Session = Depends(get_db)) -> VoteSummary:
    return _get_vote_summary(symbol.upper(), user_id, db)


def _get_vote_summary(symbol: str, user_id: Optional[str],
                      db: Session) -> VoteSummary:
    rows = db.execute(
        text("SELECT vote, COUNT(*) as cnt FROM user_votes WHERE symbol = :sym GROUP BY vote"),
        {"sym": symbol},
    ).fetchall()
    counts = {r._mapping["vote"]: r._mapping["cnt"] for r in rows}
    user_vote = None
    if user_id:
        row = db.execute(
            text("SELECT vote FROM user_votes WHERE user_id = :uid AND symbol = :sym"),
            {"uid": user_id, "sym": symbol},
        ).fetchone()
        if row:
            user_vote = row._mapping["vote"]
    bull = counts.get("bull", 0)
    bear = counts.get("bear", 0)
    hold = counts.get("hold", 0)
    return VoteSummary(symbol=symbol, bull=bull, bear=bear, hold=hold,
                       total=bull + bear + hold, user_vote=user_vote)


# ── PRD-13: Community Signal Score ───────────────────────────────────────────

class SignalScore(BaseModel):
    symbol: str
    watchlist_count: int
    bull_votes: int
    bear_votes: int
    hold_votes: int
    total_votes: int
    strategy_run_count: int
    signal_score: float
    signal_label: str
    computed_at: Optional[datetime]
    disclaimer: str = (
        "Community sentiment reflects aggregated user activity on this platform. "
        "It is not financial advice and does not represent any recommendation to buy or sell."
    )


class CommunityBoardResponse(BaseModel):
    items: list[SignalScore]
    total: int
    disclaimer: str = (
        "Community sentiment reflects aggregated user activity on this platform. "
        "It is not financial advice."
    )


@router.get("/signal/{symbol}", response_model=SignalScore)
def get_signal_score(symbol: str, db: Session = Depends(get_db)) -> SignalScore:
    row = db.execute(
        text("SELECT * FROM community_signal_scores WHERE symbol = :sym"),
        {"sym": symbol.upper()},
    ).fetchone()
    if not row:
        return _empty_signal(symbol.upper())
    return _row_to_signal(row)


@router.get("/board", response_model=CommunityBoardResponse)
def get_community_board(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> CommunityBoardResponse:
    """Most active stocks ranked by community signal score."""
    rows = db.execute(
        text(
            "SELECT * FROM community_signal_scores"
            " WHERE signal_score > 0"
            " ORDER BY signal_score DESC"
            " LIMIT :limit OFFSET :offset"
        ),
        {"limit": limit, "offset": offset},
    ).fetchall()
    total_row = db.execute(
        text("SELECT COUNT(*) FROM community_signal_scores WHERE signal_score > 0")
    ).fetchone()
    total = total_row[0] if total_row else 0
    return CommunityBoardResponse(
        items=[_row_to_signal(r) for r in rows],
        total=total,
    )


def _row_to_signal(row: object) -> SignalScore:
    r = row._mapping  # type: ignore[attr-defined]
    return SignalScore(
        symbol=r["symbol"],
        watchlist_count=r["watchlist_count"] or 0,
        bull_votes=r["bull_votes"] or 0,
        bear_votes=r["bear_votes"] or 0,
        hold_votes=r["hold_votes"] or 0,
        total_votes=r["total_votes"] or 0,
        strategy_run_count=r["strategy_run_count"] or 0,
        signal_score=float(r["signal_score"] or 0),
        signal_label=r["signal_label"] or "Neutral",
        computed_at=r.get("computed_at"),
    )


def _empty_signal(symbol: str) -> SignalScore:
    return SignalScore(
        symbol=symbol, watchlist_count=0, bull_votes=0, bear_votes=0,
        hold_votes=0, total_votes=0, strategy_run_count=0,
        signal_score=0.0, signal_label="No Activity", computed_at=None,
    )


def _refresh_signal_score(symbol: str, db: Session) -> None:
    """
    Recompute and upsert the community signal score for a symbol.
    Formula: (watchlist_adds × 1.5) + (bull_votes - bear_votes × 0.8)
             + (strategy_runs × 2.0), normalised to 0–100.
    """
    wl = db.execute(
        text("SELECT COUNT(*) FROM user_watchlists WHERE symbol = :sym"),
        {"sym": symbol},
    ).fetchone()[0] or 0

    vote_rows = db.execute(
        text("SELECT vote, COUNT(*) as cnt FROM user_votes WHERE symbol = :sym GROUP BY vote"),
        {"sym": symbol},
    ).fetchall()
    votes = {r._mapping["vote"]: r._mapping["cnt"] for r in vote_rows}
    bull = votes.get("bull", 0)
    bear = votes.get("bear", 0)
    hold = votes.get("hold", 0)
    total_votes = bull + bear + hold

    runs = db.execute(
        text("SELECT COUNT(*) FROM backtests WHERE symbols LIKE :pat"),
        {"pat": f"%{symbol}%"},
    ).fetchone()[0] or 0

    raw = (wl * 1.5) + ((bull - bear * 0.8)) + (runs * 2.0)
    # Soft normalise with sigmoid-like scaling: score in [0, 100]
    score = round(min(100.0, max(0.0, 50.0 + 10.0 * math.tanh(raw / 10.0))), 2)

    if score >= 70:
        label = "Strong Community Interest"
    elif score >= 60:
        label = "Rising Attention"
    elif score >= 50:
        label = "Moderate Interest"
    elif score >= 40:
        label = "Low Activity"
    else:
        label = "No Activity"

    db.execute(
        text(
            "INSERT INTO community_signal_scores"
            " (symbol, watchlist_count, bull_votes, bear_votes, hold_votes,"
            "  total_votes, strategy_run_count, signal_score, signal_label, computed_at)"
            " VALUES (:sym, :wl, :bull, :bear, :hold, :total, :runs, :score, :label, :now)"
            " ON CONFLICT (symbol) DO UPDATE SET"
            "  watchlist_count=:wl, bull_votes=:bull, bear_votes=:bear,"
            "  hold_votes=:hold, total_votes=:total, strategy_run_count=:runs,"
            "  signal_score=:score, signal_label=:label, computed_at=:now"
        ),
        {
            "sym": symbol, "wl": wl, "bull": bull, "bear": bear,
            "hold": hold, "total": total_votes, "runs": runs,
            "score": score, "label": label, "now": datetime.utcnow(),
        },
    )
    db.commit()


# ── PRD-14: Strategy Comments + Upvotes ──────────────────────────────────────

class CommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(BaseModel):
    id: int
    user_id: str
    strategy_slug: str
    content: str
    created_at: datetime
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class CommentsListResponse(BaseModel):
    comments: list[CommentResponse]
    total: int


@router.get("/comments/{slug}", response_model=CommentsListResponse)
def get_comments(slug: str, db: Session = Depends(get_db)) -> CommentsListResponse:
    # SQLite uses CAST, PostgreSQL uses :: cast syntax for UUID join
    join_expr = (
        "LEFT JOIN users u ON CAST(u.id AS TEXT) = c.user_id"
        if _is_sqlite(db)
        else "LEFT JOIN users u ON u.id::text = c.user_id"
    )
    rows = db.execute(
        text(
            f"SELECT c.id, c.user_id, c.strategy_slug, c.content, c.created_at,"  # noqa: S608
            f" u.display_name, u.avatar_url"
            f" FROM strategy_comments c {join_expr}"
            f" WHERE c.strategy_slug = :slug ORDER BY c.created_at DESC"
        ),
        {"slug": slug},
    ).fetchall()
    total = len(rows)
    return CommentsListResponse(
        comments=[_row_to_comment(r) for r in rows],
        total=total,
    )


@router.post("/comments/{slug}", response_model=CommentResponse,
             dependencies=[Depends(verify_internal_key)])
def add_comment(slug: str, user_id: str, body: CommentRequest,
                db: Session = Depends(get_db)) -> CommentResponse:
    db.execute(
        text(
            "INSERT INTO strategy_comments (user_id, strategy_slug, content)"
            " VALUES (:uid, :slug, :content)"
        ),
        {"uid": user_id, "slug": slug, "content": body.content.strip()},
    )
    db.commit()
    row = db.execute(
        text(
            "SELECT c.id, c.user_id, c.strategy_slug, c.content, c.created_at,"
            " u.display_name, u.avatar_url"
            " FROM strategy_comments c LEFT JOIN users u ON CAST(u.id AS TEXT) = c.user_id"
            " WHERE c.user_id = :uid AND c.strategy_slug = :slug"
            " ORDER BY c.created_at DESC LIMIT 1"
        ),
        {"uid": user_id, "slug": slug},
    ).fetchone()
    return _row_to_comment(row)


@router.delete("/comments/{comment_id}", dependencies=[Depends(verify_internal_key)])
def delete_comment(comment_id: int, user_id: str,
                   db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        text("SELECT user_id FROM strategy_comments WHERE id = :id"),
        {"id": comment_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found.")
    if row._mapping["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment.")
    db.execute(text("DELETE FROM strategy_comments WHERE id = :id"), {"id": comment_id})
    db.commit()
    return {"id": comment_id, "action": "deleted"}


class UpvoteResponse(BaseModel):
    slug: str
    upvote_count: int
    user_upvoted: bool


@router.get("/upvotes/{slug}", response_model=UpvoteResponse)
def get_upvotes(slug: str, user_id: Optional[str] = Query(default=None),
                db: Session = Depends(get_db)) -> UpvoteResponse:
    count = db.execute(
        text("SELECT COUNT(*) FROM strategy_upvotes WHERE strategy_slug = :slug"),
        {"slug": slug},
    ).fetchone()[0] or 0
    user_upvoted = False
    if user_id:
        row = db.execute(
            text("SELECT 1 FROM strategy_upvotes WHERE user_id = :uid AND strategy_slug = :slug"),
            {"uid": user_id, "slug": slug},
        ).fetchone()
        user_upvoted = row is not None
    return UpvoteResponse(slug=slug, upvote_count=count, user_upvoted=user_upvoted)


@router.post("/upvotes/{slug}", response_model=UpvoteResponse,
             dependencies=[Depends(verify_internal_key)])
def toggle_upvote(slug: str, user_id: str, db: Session = Depends(get_db)) -> UpvoteResponse:
    existing = db.execute(
        text("SELECT 1 FROM strategy_upvotes WHERE user_id = :uid AND strategy_slug = :slug"),
        {"uid": user_id, "slug": slug},
    ).fetchone()
    if existing:
        db.execute(
            text("DELETE FROM strategy_upvotes WHERE user_id = :uid AND strategy_slug = :slug"),
            {"uid": user_id, "slug": slug},
        )
    else:
        db.execute(
            text("INSERT INTO strategy_upvotes (user_id, strategy_slug) VALUES (:uid, :slug)"),
            {"uid": user_id, "slug": slug},
        )
    db.commit()
    return get_upvotes(slug, user_id, db)


@router.get("/leaderboard", response_model=list[dict])
def get_leaderboard(
    limit: int = Query(default=10, le=20),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Top strategies by upvote count — sorted by community activity, not returns."""
    rows = db.execute(
        text(
            "SELECT b.slug, b.name, COUNT(u.id) as upvotes"
            " FROM strategy_upvotes u"
            " JOIN backtests b ON b.slug = u.strategy_slug"
            " WHERE b.slug IS NOT NULL AND b.is_public = TRUE"
            " GROUP BY b.slug, b.name"
            " ORDER BY upvotes DESC LIMIT :limit"
        ),
        {"limit": limit},
    ).fetchall()
    return [
        {"slug": r._mapping["slug"], "name": r._mapping["name"],
         "upvotes": r._mapping["upvotes"]}
        for r in rows
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_comment(row: object) -> CommentResponse:
    r = row._mapping  # type: ignore[attr-defined]
    return CommentResponse(
        id=r["id"],
        user_id=str(r["user_id"]),
        strategy_slug=r["strategy_slug"],
        content=r["content"],
        created_at=r["created_at"],
        display_name=r.get("display_name"),
        avatar_url=r.get("avatar_url"),
    )


def _is_sqlite(db: Session) -> bool:
    return db.bind.dialect.name == "sqlite"  # type: ignore[union-attr]
