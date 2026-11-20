"""The agent's conversation: what it is given, what it can do, and what reaches the app."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, List
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.api.routes.agent import agent_chat
from app.api.routes.chat import ChatMessageRequest, post_message
from app.schemas.agent import AgentChatRequest
from app.services.agent import monitor, tools
from app.services.agent.checks import Holding
from app.services.llm_adapter import ChatDone, ChatToken, ChatToolCall


def _fake_gateway(events_per_iteration: List[List], seen: List[dict]) -> MagicMock:
    calls = {"n": 0}

    def _stream(**kwargs) -> AsyncIterator:
        seen.append(kwargs)
        events = events_per_iteration[calls["n"]]
        calls["n"] += 1

        async def _it():
            for event in events:
                yield event

        return _it()

    gateway = MagicMock()
    gateway.chat_completion_with_tools = _stream
    return gateway


async def _frames(response) -> List[dict]:
    frames: List[dict] = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for line in text.split("\n\n"):
            line = line.strip()
            if line.startswith("data: "):
                frames.append(json.loads(line[len("data: "):]))
    return frames


def _tool_names(kwargs: dict) -> set:
    return {t["function"]["name"] for t in kwargs["tools"]}


@pytest.mark.asyncio
async def test_a_draft_order_reaches_the_app_and_nothing_is_placed(db: Session, make_user) -> None:
    user = make_user(email="agentchat@example.com", password="pw")
    seen: List[dict] = []
    fake = _fake_gateway([
        [ChatToolCall(call_id="c1", name="agent_draft_order",
                      arguments={"symbol": "aapl", "side": "sell", "units": 66, "reason": "Back to the 25% limit."}),
         ChatDone(finish_reason="tool_calls")],
        [ChatToken(text="I have put a draft in front of you."), ChatDone(finish_reason="stop")],
    ], seen)

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake), \
         patch("app.services.snaptrade_service.place_previewed_order") as place, \
         patch("app.services.snaptrade_service.preview_order") as preview:
        response = await agent_chat("conv-agent-1", AgentChatRequest(content="Trim AAPL to my limit"), user=user, db=db)
        frames = await _frames(response)

    types = [f["type"] for f in frames]
    assert types[0] == "started" and "done" in types
    (result,) = [f for f in frames if f["type"] == "tool_result"]
    assert result["client"] == {
        "type": "review_order", "symbol": "AAPL", "side": "sell", "units": 66.0,
        "reason": "Back to the 25% limit.",
    }
    # The agent has no way to reach the broker's order endpoints.
    place.assert_not_called()
    preview.assert_not_called()
    # What the model was told the draft was: shown, not sent.
    tool_message = [m for m in seen[1]["messages"] if m.get("role") == "tool"][0]
    assert "Nothing has been sent to their broker" in tool_message["content"]


@pytest.mark.asyncio
async def test_the_agent_gets_its_own_tools_and_the_general_chat_does_not(db: Session, make_user) -> None:
    user = make_user(email="tools@example.com", password="pw")
    agent_seen: List[dict] = []
    general_seen: List[dict] = []
    done = [[ChatToken(text="ok"), ChatDone(finish_reason="stop")]]

    with patch("app.api.routes.chat.get_llm_gateway", return_value=_fake_gateway(done, agent_seen)):
        await _frames(await agent_chat("conv-agent-2", AgentChatRequest(content="hi"), user=user, db=db))
    with patch("app.api.routes.chat.get_llm_gateway", return_value=_fake_gateway(done, general_seen)):
        await _frames(await post_message("conv-general-2", ChatMessageRequest(content="hi"), user=user, db=db))

    agent_tools = _tool_names(agent_seen[0])
    assert set(tools.AGENT_TOOLS) <= agent_tools
    assert agent_tools == set(tools.AGENT_TOOLS) | tools.SHARED_TOOLS
    # Nothing that builds or runs a strategy for the user behind the conversation.
    assert "backtest_execute" not in agent_tools
    assert not (set(tools.AGENT_TOOLS) & _tool_names(general_seen[0]))


@pytest.mark.asyncio
async def test_the_agent_is_told_the_rules_and_what_the_user_said_about_themselves(db: Session, make_user) -> None:
    user = make_user(email="notes@example.com", password="pw")
    profile = monitor.get_or_create_profile(db, user.id)
    profile.notes = "I hold for years and never use margin."
    db.commit()
    seen: List[dict] = []
    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]], seen)
    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        await _frames(await agent_chat("conv-agent-3", AgentChatRequest(content="hi"), user=user, db=db))

    system = seen[0]["messages"][0]
    assert system["role"] == "system"
    assert "I hold for years and never use margin." in system["content"]
    assert "never place, send or execute an order" in system["content"]
    assert "comes from a tool result" in system["content"]
    # The user's message follows it.
    assert seen[0]["messages"][-1] == {"role": "user", "content": "hi"}


def test_a_tool_refuses_to_run_outside_a_users_conversation() -> None:
    assert tools.current_user_id.get() is None
    for call in (tools.agent_overview(), tools.agent_trading_behavior(),
                 tools.agent_filing("NVDA"), tools.agent_draft_order("NVDA", "buy", units=1)):
        with pytest.raises(RuntimeError, match="only available inside the agent"):
            asyncio.run(call)


def _as(user_id: str, coroutine_factory):
    async def run():
        token = tools.current_user_id.set(user_id)
        try:
            return await coroutine_factory()
        finally:
            tools.current_user_id.reset(token)
    return asyncio.run(run())


def test_a_draft_must_be_a_real_order_shape() -> None:
    def draft(**kwargs):
        return _as("u-1", lambda: tools.agent_draft_order(**kwargs))

    assert "client" in draft(symbol="nvda", side="BUY", amount_usd=500)
    assert draft(symbol="nvda", side="BUY", amount_usd=500)["client"]["amount_usd"] == 500.0
    assert "error" in draft(symbol="NVDA", side="short", units=1)
    assert "error" in draft(symbol="not a ticker", side="buy", units=1)
    assert "error" in draft(symbol="NVDA", side="buy")
    assert "error" in draft(symbol="NVDA", side="buy", units=1, amount_usd=100)
    assert "error" in draft(symbol="NVDA", side="sell", units=-3)


def test_the_overview_reports_weights_from_holdings_and_moves_from_quotes() -> None:
    inputs = monitor._Inputs(
        watchlist=["NVDA"], move_alert_pct=4.0, max_position_pct=25.0,
        holdings=[Holding("AAPL", 100, 300.0), Holding("MSFT", 20, 500.0)],
        brokerage_linked=True, exits=[{"symbol": "AMD"}], notes=[],
    )

    async def fake_quotes(symbols):
        assert symbols == ["AAPL", "MSFT", "NVDA"]
        return {"AAPL": {"price": 300.0, "change_percent": -1.5}, "NVDA": {"price": 146.0, "change_percent": -3.3}}

    with patch.object(monitor, "_gather", return_value=inputs), \
         patch.object(tools, "_open_insights", return_value=[{"title": "AAPL is 75% of your holdings"}]), \
         patch.object(monitor, "_quotes", fake_quotes):
        overview = _as("u-1", tools.agent_overview)

    assert overview["portfolio_value"] == 40000.0
    assert [(h["symbol"], h["weight_pct"]) for h in overview["holdings"]] == [("AAPL", 75.0), ("MSFT", 25.0)]
    assert overview["holdings"][0]["change_percent_today"] == -1.5
    # A symbol with no quote is reported as unknown, never as zero.
    assert overview["holdings"][1]["change_percent_today"] is None
    assert overview["watchlist"] == [{"symbol": "NVDA", "price": 146.0, "change_percent_today": -3.3}]
    assert overview["exits_waiting"] == ["AMD"]
    assert overview["settings"] == {"day_move_alert_pct": 4.0, "max_position_pct": 25.0}


def test_an_unlinked_brokerage_has_no_portfolio_value_rather_than_zero() -> None:
    inputs = monitor._Inputs(
        watchlist=[], move_alert_pct=4.0, max_position_pct=25.0, holdings=[],
        brokerage_linked=False, exits=[], notes=["No brokerage is linked, so holdings were not checked."],
    )
    with patch.object(monitor, "_gather", return_value=inputs), patch.object(tools, "_open_insights", return_value=[]):
        overview = _as("u-1", tools.agent_overview)
    assert overview["brokerage_linked"] is False
    assert overview["portfolio_value"] is None
    assert overview["could_not_check"] == ["No brokerage is linked, so holdings were not checked."]
