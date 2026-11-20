from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
MAX_WATCHLIST = 50


class AgentProfileView(BaseModel):
    enabled: bool
    watchlist: List[str]
    move_alert_pct: float
    max_position_pct: float
    notes: str
    last_scan_at: Optional[datetime] = None
    # False when no language model is configured on this server. The monitor
    # and its insights work without one; the conversation does not.
    chat_available: bool = False


class AgentProfileUpdate(BaseModel):
    """Only the fields sent are changed."""

    enabled: Optional[bool] = None
    watchlist: Optional[List[str]] = None
    move_alert_pct: Optional[float] = Field(default=None, ge=1, le=50)
    max_position_pct: Optional[float] = Field(default=None, ge=5, le=100)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("watchlist")
    @classmethod
    def _clean_watchlist(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        cleaned = list(dict.fromkeys(str(s).strip().upper() for s in value if str(s).strip()))
        if len(cleaned) > MAX_WATCHLIST:
            raise ValueError("A watchlist holds at most %d symbols." % MAX_WATCHLIST)
        for symbol in cleaned:
            if not _SYMBOL.match(symbol):
                raise ValueError("%r is not a ticker symbol." % symbol)
        return cleaned


class AgentInsightView(BaseModel):
    id: str
    kind: str
    severity: str
    symbol: Optional[str] = None
    title: str
    body: str
    facts: Dict[str, Any] = {}
    # What the app can open for the user to act: {"type": "open_company", ...},
    # {"type": "review_order", "symbol", "side", "units"} or {"type": "open_actions"}.
    action: Optional[Dict[str, Any]] = None
    created_at: datetime
    dismissed: bool = False


class AgentChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class AgentScanView(BaseModel):
    checked_at: datetime
    new_insights: int
    symbols_checked: int
    brokerage_linked: bool
    notes: List[str] = []
    insights: List[AgentInsightView] = []
