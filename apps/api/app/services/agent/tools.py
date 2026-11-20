"""What the agent can look up while it talks to its user.

Every tool here reads. None changes anything, and none places an order:
`agent_draft_order` only hands the app a draft for the user to review in the
order ticket they already know.

The tools need to know whose portfolio they are reading. The chat route sets
`current_user_id` before it starts the conversation loop, and a tool that
finds it unset refuses, so a tool can never be run for nobody or for a user
the model named.
"""
from __future__ import annotations

import asyncio
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.agent import AgentInsight
from app.services.agent import monitor

current_user_id: ContextVar[Optional[str]] = ContextVar("agent_user_id", default=None)

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
_MAX_LIST = 15


def _user_id() -> str:
    user_id = current_user_id.get()
    if not user_id:
        raise RuntimeError("This tool is only available inside the agent's conversation.")
    return user_id


def _open_insights(user_id: str) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        rows = db.execute(
            select(AgentInsight)
            .where(AgentInsight.user_id == user_id, AgentInsight.dismissed_at.is_(None))
            .order_by(AgentInsight.created_at.desc())
            .limit(_MAX_LIST)
        ).scalars().all()
        return [{"kind": r.kind, "symbol": r.symbol, "title": r.title, "body": r.body,
                 "found_at": r.created_at.isoformat()} for r in rows]


async def agent_overview() -> Dict[str, Any]:
    """Everything the agent watches for this user, as it stands now."""
    user_id = _user_id()
    inputs = await asyncio.to_thread(monitor._gather, user_id)
    insights = await asyncio.to_thread(_open_insights, user_id)
    held = sorted(inputs.holdings, key=lambda h: h.value, reverse=True)
    symbols = list(dict.fromkeys([h.symbol for h in held] + inputs.watchlist))[:monitor.MAX_SYMBOLS]
    quotes: Dict[str, Dict[str, float]] = {}
    notes = list(inputs.notes)
    if symbols:
        try:
            quotes = await monitor._quotes(symbols)
        except Exception:  # noqa: BLE001
            notes.append("Live prices could not be read just now.")
    total = sum(h.value for h in held)
    return {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": {
            "day_move_alert_pct": inputs.move_alert_pct,
            "max_position_pct": inputs.max_position_pct,
        },
        "brokerage_linked": inputs.brokerage_linked,
        "portfolio_value": round(total, 2) if inputs.brokerage_linked else None,
        "holdings": [
            {"symbol": h.symbol, "units": h.units, "price": h.price, "value": round(h.value, 2),
             "weight_pct": round(100 * h.value / total, 2) if total else None,
             "change_percent_today": (quotes.get(h.symbol) or {}).get("change_percent")}
            for h in held
        ],
        "watchlist": [
            {"symbol": s, "price": (quotes.get(s) or {}).get("price"),
             "change_percent_today": (quotes.get(s) or {}).get("change_percent")}
            for s in inputs.watchlist
        ],
        "exits_waiting": [e.get("symbol") for e in inputs.exits],
        "open_insights": insights,
        "could_not_check": notes,
    }


def _behavior(user_id: str) -> Dict[str, Any]:
    from app.api.routes.snaptrade import snaptrade_behavior
    from app.models.user import User

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            return {"available": False, "reason": "No such user."}
        try:
            view = snaptrade_behavior(start_date=None, end_date=None, current_user=user, db=db)
        except HTTPException as exc:
            return {"available": False, "reason": str(exc.detail)}
        data = view.model_dump()
    # The per-trade lists are for a screen, not for a conversation.
    for key, value in list(data.items()):
        if isinstance(value, list) and len(value) > _MAX_LIST:
            data[key] = value[:_MAX_LIST]
            data[key + "_truncated_from"] = len(value)
    data["available"] = True
    return data


async def agent_trading_behavior() -> Dict[str, Any]:
    """The user's own trading record, measured: the same analysis the
    brokerage page shows on the website."""
    return await asyncio.to_thread(_behavior, _user_id())


async def agent_filing(symbol: str) -> Dict[str, Any]:
    """What a company's latest quarterly filing shows."""
    _user_id()
    from app.services import sec_company_facts

    symbol = str(symbol).strip().upper()
    if not _SYMBOL.match(symbol):
        return {"available": False, "reason": "%r is not a ticker symbol." % symbol}
    try:
        analysis = await sec_company_facts.filing_analysis(symbol)
    except Exception:  # noqa: BLE001
        return {"available": False,
                "reason": "No quarterly filings could be read for %s. It may be a fund or file a different form." % symbol}
    if not analysis.quarters:
        return {"available": False, "reason": "No quarters on file for %s." % symbol}
    latest = analysis.quarters[-1]
    return {
        "available": True,
        "symbol": symbol,
        "company": analysis.company_name,
        "period": latest.label,
        "form": latest.form,
        "filed": latest.filed.isoformat() if latest.filed else None,
        "findings": [{"severity": f.severity, "title": f.title, "detail": f.detail} for f in analysis.findings],
    }


async def agent_draft_order(
    symbol: str,
    side: str,
    units: Optional[float] = None,
    amount_usd: Optional[float] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """Show the user a draft order to review. Places nothing."""
    _user_id()
    symbol = str(symbol).strip().upper()
    side = str(side).strip().lower()
    if not _SYMBOL.match(symbol):
        return {"error": "%r is not a ticker symbol." % symbol}
    if side not in ("buy", "sell"):
        return {"error": "side is 'buy' or 'sell'."}
    if (units is None) == (amount_usd is None):
        return {"error": "Give either units or amount_usd, not both and not neither."}
    size = units if units is not None else amount_usd
    if not isinstance(size, (int, float)) or size <= 0:
        return {"error": "The size is a positive number."}
    draft = {"type": "review_order", "symbol": symbol, "side": side, "reason": str(reason)[:300]}
    if units is not None:
        draft["units"] = float(units)
    else:
        draft["amount_usd"] = float(amount_usd)
    return {
        "client": draft,
        "status": "A draft was shown to the user. Nothing has been sent to their broker. "
                  "They review it in the order ticket, see the broker's price, and confirm it themselves.",
    }


def _tool(name: str, description: str, handler, properties: Optional[dict] = None, required: Optional[list] = None) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        "handler": handler,
    }


AGENT_TOOLS: Dict[str, dict] = {t["name"]: t for t in (
    _tool(
        "agent_overview",
        "The user's portfolio and watchlist right now: holdings with their weight and today's move, "
        "watched symbols with price and today's move, the user's own limits, exits waiting on a decision, "
        "and what the agent has already flagged. Call this before answering anything about the user's "
        "portfolio, watchlist or what needs attention.",
        agent_overview,
    ),
    _tool(
        "agent_trading_behavior",
        "The user's own buying and selling, measured from their brokerage record: realized results, "
        "how winners and losers were held, what exits gave up. Call this for questions about how the "
        "user trades.",
        agent_trading_behavior,
    ),
    _tool(
        "agent_filing",
        "What a company's latest 10-Q or 10-K shows: the period and findings computed from the filed figures.",
        agent_filing,
        {"symbol": {"type": "string", "description": "Ticker, e.g. NVDA"}},
        ["symbol"],
    ),
    _tool(
        "agent_draft_order",
        "Show the user a draft order to review in their order ticket. This places nothing; only the user "
        "can confirm an order. Use it only when the user has asked to buy or sell, or asked what order "
        "would meet a rule they set. Give units or amount_usd.",
        agent_draft_order,
        {
            "symbol": {"type": "string"},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "units": {"type": "number", "description": "Number of shares"},
            "amount_usd": {"type": "number", "description": "Dollar amount, instead of units"},
            "reason": {"type": "string", "description": "One sentence: the rule or request this draft answers"},
        },
        ["symbol", "side"],
    ),
)}

# General tools from the main chat that are useful here too.
SHARED_TOOLS = {"stock_lookup", "concept_explainer"}


def system_prompt(user_notes: str, today: str) -> str:
    notes = user_notes.strip()
    return (
        "You are the user's portfolio agent inside Livermore. You watch their watchlist and their "
        "holdings and help them act on their own strategy and judgement.\n"
        "Rules you never break:\n"
        "1. Every number you state comes from a tool result in this conversation. You do no arithmetic "
        "beyond restating those numbers, and you never recall a price or a figure from memory. If a "
        "tool did not give it to you, say you do not have it.\n"
        "2. You never place, send or execute an order, and you never say you did. The most you do is "
        "show a draft with agent_draft_order, which the user reviews and confirms themselves.\n"
        "3. You do not predict prices and you do not tell the user what they should do. You say what "
        "happened, what their own rules and limits say about it, and what the options are.\n"
        "4. You are not a financial adviser. If asked for a recommendation, say what the facts and "
        "the user's own rules show and leave the decision with them.\n"
        "Style: lead with the answer. Be brief and specific. Name the symbol and the figure. "
        "No preamble, no disclaimers beyond rule 4 when it applies.\n"
        "Today is %s (UTC).%s"
    ) % (today, ("\nWhat the user told you about how they invest: " + notes) if notes else "")
