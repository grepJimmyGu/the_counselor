"""The portfolio agent's endpoints: its settings, what it found, and a scan on request."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models.agent import AgentInsight, AgentProfile
from app.models.user import User
from app.schemas.agent import (
    AgentChatRequest,
    AgentInsightView,
    AgentProfileUpdate,
    AgentProfileView,
    AgentScanView,
)
from app.services.agent import monitor
from app.services.agent import tools as agent_tools
from app.services.llm_adapter import get_llm_gateway

router = APIRouter(prefix="/api/agent", tags=["agent"])

# A scan reads the broker and a batch of quotes; one tap should not start two.
_MIN_SECONDS_BETWEEN_SCANS = 20
_last_scan: Dict[str, float] = {}
_INSIGHT_LIMIT = 60

# Who is in a conversation with the agent right now. One at a time per user:
# a second message while the first is still being answered would run the
# model twice over the same history. The total is capped in settings.
_chatting: Set[str] = set()


def _forget_old_scans(now: float) -> None:
    """Keep the throttle's memory to people who scanned recently."""
    if len(_last_scan) > 5000:
        for user_id in [u for u, at in _last_scan.items() if now - at > _MIN_SECONDS_BETWEEN_SCANS]:
            _last_scan.pop(user_id, None)


def _profile_view(profile: AgentProfile) -> AgentProfileView:
    return AgentProfileView(
        enabled=profile.enabled,
        watchlist=list(profile.watchlist or []),
        move_alert_pct=profile.move_alert_pct,
        max_position_pct=profile.max_position_pct,
        notes=profile.notes or "",
        email_alerts=profile.email_alerts,
        last_scan_at=profile.last_scan_at,
        chat_available=get_llm_gateway().is_enabled,
    )


def _insight_view(row: AgentInsight) -> AgentInsightView:
    return AgentInsightView(
        id=row.id, kind=row.kind, severity=row.severity, symbol=row.symbol,
        title=row.title, body=row.body, facts=row.facts or {}, action=row.action,
        created_at=row.created_at, dismissed=row.dismissed_at is not None,
    )


def _open_insights(db: Session, user_id: str) -> List[AgentInsightView]:
    rows = db.execute(
        select(AgentInsight)
        .where(AgentInsight.user_id == user_id, AgentInsight.dismissed_at.is_(None))
        .order_by(AgentInsight.created_at.desc())
        .limit(_INSIGHT_LIMIT)
    ).scalars().all()
    return [_insight_view(r) for r in rows]


@router.get("/profile", response_model=AgentProfileView)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentProfileView:
    return _profile_view(monitor.get_or_create_profile(db, user.id))


@router.put("/profile", response_model=AgentProfileView)
def update_profile(
    body: AgentProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentProfileView:
    profile = monitor.get_or_create_profile(db, user.id)
    for name in body.model_fields_set:
        value = getattr(body, name)
        if value is not None:
            setattr(profile, name, value)
    db.commit()
    db.refresh(profile)
    return _profile_view(profile)


@router.get("/insights", response_model=List[AgentInsightView])
def list_insights(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> List[AgentInsightView]:
    """What the agent has found and the user has not dismissed, newest first."""
    return _open_insights(db, user.id)


@router.post("/insights/{insight_id}/dismiss", response_model=AgentInsightView)
def dismiss_insight(
    insight_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentInsightView:
    row = db.get(AgentInsight, insight_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such insight.")
    if row.dismissed_at is None:
        row.dismissed_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return _insight_view(row)


@router.post("/scan", response_model=AgentScanView)
async def scan_now(user: User = Depends(get_current_user)) -> AgentScanView:
    """Run the agent's checks now and return what it holds afterwards.

    Works whether or not the agent is turned on: turning it on is what makes
    it run by itself; asking it to look is always allowed.
    """
    user_id: str = user.id
    now = time.monotonic()
    if now - _last_scan.get(user_id, -1e9) < _MIN_SECONDS_BETWEEN_SCANS:
        raise HTTPException(status_code=429, detail="The agent just checked. Try again in a few seconds.")
    _last_scan[user_id] = now
    _forget_old_scans(now)
    try:
        result = await asyncio.wait_for(monitor.scan_user(user_id), monitor.SCAN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="The check took too long. Try again in a moment.",
                            headers={"Retry-After": "30"})

    def _read() -> List[AgentInsightView]:
        with SessionLocal() as db:
            return _open_insights(db, user_id)

    insights = await monitor.run_blocking(_read)
    return AgentScanView(
        checked_at=result.checked_at,
        new_insights=result.new_insights,
        symbols_checked=result.symbols_checked,
        brokerage_linked=result.brokerage_linked,
        notes=result.notes,
        insights=insights,
    )


@router.post("/chat/{conversation_id}/messages")
async def agent_chat(
    conversation_id: str,
    body: AgentChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Talk to the agent. Streams the same events as the general chat
    (`started`, `token`, `tool_call_start`, `tool_result`, `done`, `error`).

    Built on the general chat's engine so that its quota, history, tool loop
    and guardrails apply here unchanged. What differs is what the model is
    told it is, and which tools it is given: the agent's own, which read this
    user's portfolio, plus two general ones.
    """
    from app.api.routes import chat as chat_engine

    if user.plan is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="User plan missing — please retry.")
    # Refused before anything is stored or counted against the user's quota.
    if user.id in _chatting:
        raise HTTPException(status_code=429, detail="Your agent is still answering your last message.",
                            headers={"Retry-After": "5"})
    if len(_chatting) >= get_settings().agent_chat_max_concurrent:
        raise HTTPException(status_code=503, detail="Your agent is busy right now. Try again in a moment.",
                            headers={"Retry-After": "10"})
    chat_engine._check_chat_quota(db, user.id, user.plan.tier)
    conversation = chat_engine._get_or_create_conversation(
        db, conversation_id=conversation_id, user_id=user.id,
        context_type="agent", context_payload=None,
    )
    chat_engine._persist_message(db, conversation.id, role="user", content=body.content)
    profile = monitor.get_or_create_profile(db, user.id)
    today = datetime.now(timezone.utc).date().isoformat()
    messages: List[dict] = (
        [{"role": "system", "content": agent_tools.system_prompt(profile.notes or "", today)}]
        + chat_engine._load_history(db, conversation.id, limit=20)
    )
    # Plain values: the request's session is closed before the stream runs (trap 17).
    conversation_id_value: str = conversation.id
    user_id: str = user.id
    tier: str = user.plan.tier
    content: str = body.content
    whitelist = set(agent_tools.AGENT_TOOLS) | agent_tools.SHARED_TOOLS

    async def event_stream() -> AsyncIterator[str]:
        # Marked here, inside the stream, so that it is always unmarked: the
        # `finally` below runs when the stream ends or the phone goes away,
        # which is not true of anything set before the stream starts.
        _chatting.add(user_id)
        # The agent's tools read this, and only this, to know whose data to load.
        token = agent_tools.current_user_id.set(user_id)
        try:
            yield chat_engine._sse("started", {"conversation_id": conversation_id_value})
            async for frame in chat_engine._run_tool_loop(
                db, conversation_id_value, messages,
                tool_whitelist=whitelist,
                user_id=user_id, tier=tier, user_message=content,
                extra_tools=agent_tools.AGENT_TOOLS,
            ):
                yield frame
        finally:
            _chatting.discard(user_id)
            agent_tools.current_user_id.reset(token)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

