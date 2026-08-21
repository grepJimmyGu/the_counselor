"""SnapTrade — read-only brokerage connection routes (slice 3).

Three routes: what state is this user in, give me a portal to connect a
broker, and what does that broker say I hold. Nothing here places an order.

NOTHING IN THIS MODULE RETURNS `user_secret_encrypted`, and no response
model has a field it could be serialised into. The plaintext exists only
inside `snaptrade_service` for the duration of a call.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import snaptrade_service as st

_log = logging.getLogger("livermore.api.snaptrade")

router = APIRouter(prefix="/api/snaptrade", tags=["snaptrade"])


class SnapTradeStatus(BaseModel):
    """Deliberately says whether the FEATURE is available separately from
    whether this USER has connected. "Not set up yet" and "we can't offer
    this right now" are different problems and the UI should not blur
    them into one dead end."""
    configured: bool
    registered: bool
    connected_accounts: int
    last_synced_at: Optional[str] = None


class ConnectResponse(BaseModel):
    redirect_uri: str


class BrokerPositionView(BaseModel):
    account_id: str
    symbol: str
    units: float
    average_purchase_price: Optional[float] = None
    last_price: Optional[float] = None
    open_pnl: Optional[float] = None


def _require_configured() -> None:
    if not st.is_configured():
        # 503, not 500: the integration is switched off, which is an
        # operator state and not the caller's fault.
        raise HTTPException(
            status_code=503,
            detail="Brokerage connections aren't available right now.",
        )


@router.get("/status", response_model=SnapTradeStatus)
def snaptrade_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SnapTradeStatus:
    """Safe to call whether or not the feature is configured — it reports
    that rather than erroring, so the UI can hide the entry point instead
    of showing a control that 503s when clicked."""
    if not st.is_configured():
        return SnapTradeStatus(
            configured=False, registered=False, connected_accounts=0
        )
    reg = st.get_registration(db, current_user.id)
    accounts = 0
    if reg is not None:
        try:
            accounts = len(st.list_accounts(db, current_user.id))
        except Exception:  # noqa: BLE001
            # An upstream hiccup must not make the page unrenderable; the
            # user is still registered and the count is cosmetic.
            _log.exception("snaptrade: account count failed user=%s", current_user.id)
    return SnapTradeStatus(
        configured=True,
        registered=reg is not None,
        connected_accounts=accounts,
        last_synced_at=(
            reg.last_synced_at.isoformat()
            if reg is not None and reg.last_synced_at
            else None
        ),
    )


@router.post("/connect", response_model=ConnectResponse)
def snaptrade_connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectResponse:
    """A one-time URL where the user authorises their own broker.

    The authorisation happens on SnapTrade's portal against the broker's
    own login. Livermore never sees brokerage credentials — that is the
    whole reason for going through an aggregator rather than asking.
    """
    _require_configured()
    try:
        return ConnectResponse(
            redirect_uri=st.connection_portal_url(db, current_user.id)
        )
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: connect failed user=%s", current_user.id)
        raise HTTPException(
            status_code=502,
            detail="Couldn't reach the brokerage connection service.",
        ) from exc


@router.get("/positions", response_model=List[BrokerPositionView])
def snaptrade_positions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[BrokerPositionView]:
    """What the user's brokers say they hold.

    Read-only, and reported as the BROKER's view — never merged silently
    into a tracked `PositionState`. Livermore's positions carry a strategy
    and an exit ladder; a brokerage holding does not, and quietly
    conflating the two would start a ladder against something the user
    never asked to track.
    """
    _require_configured()
    try:
        rows = st.list_positions(db, current_user.id)
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: positions failed user=%s", current_user.id)
        raise HTTPException(
            status_code=502,
            detail="Couldn't read your brokerage positions.",
        ) from exc
    return [
        BrokerPositionView(
            account_id=r.account_id,
            symbol=r.symbol,
            units=r.units,
            average_purchase_price=r.average_purchase_price,
            last_price=r.last_price,
            open_pnl=r.open_pnl,
        )
        for r in rows
    ]
