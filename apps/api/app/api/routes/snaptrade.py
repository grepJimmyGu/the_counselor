"""SnapTrade — brokerage connection and order placement.

Status, connect-a-broker, read holdings (slice 3), and place an order
(slice 4c).

ORDER PLACEMENT IS TWO ROUTES, and the split is the safety property.
`/orders/preview` prices an order and returns a trade id; `/orders/place`
takes ONLY that id. No route accepts a symbol and a quantity and sends it,
so nothing can place an order the user has not seen priced.

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
    # Separate from `configured`: reading holdings can be on while order
    # placement is off, and the UI must not offer a Place button that 503s.
    trading_enabled: bool = False


class ConnectRequest(BaseModel):
    """`return_path` is a SITE-RELATIVE PATH, never a URL. The server builds
    the origin from its own config — see `return_url_for`. Accepting a full
    URL here would be an open redirect on the step where we have just asked
    someone to trust us with a brokerage login."""
    return_path: Optional[str] = None


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
            configured=False, registered=False, connected_accounts=0,
            trading_enabled=False,
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
        trading_enabled=st.is_trading_enabled(),
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
    payload: Optional[ConnectRequest] = None,
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
            redirect_uri=st.connection_portal_url(
                db, current_user.id,
                return_path=payload.return_path if payload else None,
            )
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


# ── order placement (slice 4c) ──────────────────────────────────────────────
#
# Two endpoints, and the split is the safety property rather than a style
# choice. `/orders/preview` prices an order and returns a trade id;
# `/orders/place` takes ONLY that id. There is no route that accepts a
# symbol and a quantity and sends it, so no client — ours or anyone's —
# can place an order the user has not seen priced.


class PreviewOrderRequest(BaseModel):
    account_id: str
    symbol: str
    action: str                    # "BUY" | "SELL"
    units: float
    order_type: str = "Market"
    time_in_force: str = "Day"
    price: Optional[float] = None  # limit price; ignored for Market


class PreviewOrderResponse(BaseModel):
    trade_id: str
    symbol: str
    action: str
    units: float
    estimated_commission: Optional[float] = None
    remaining_cash: Optional[float] = None


class PlaceOrderRequest(BaseModel):
    """Only an id. Deliberately carries no symbol, quantity or side — those
    were fixed when the user previewed, and accepting them here would let a
    caller preview one order and place a different one."""
    trade_id: str


class PlaceOrderResponse(BaseModel):
    status: Optional[str] = None
    brokerage_order_id: Optional[str] = None


def _require_trading() -> None:
    _require_configured()
    if not st.is_trading_enabled():
        raise HTTPException(
            status_code=503,
            detail="Order placement isn't enabled.",
        )


@router.post("/orders/preview", response_model=PreviewOrderResponse)
def preview_order(
    payload: PreviewOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PreviewOrderResponse:
    """Price an order without sending it. Nothing is transmitted here."""
    _require_trading()
    try:
        out = st.preview_order(
            db, current_user.id,
            account_id=payload.account_id,
            ticker=payload.symbol,
            action=payload.action,
            units=payload.units,
            order_type=payload.order_type,
            time_in_force=payload.time_in_force,
            price=payload.price,
        )
    except st.TradingDisabled:
        raise HTTPException(status_code=503, detail="Order placement isn't enabled.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: preview failed user=%s", current_user.id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PreviewOrderResponse(**{
        k: out[k] for k in PreviewOrderResponse.model_fields if k in out
    })


@router.post("/orders/place", response_model=PlaceOrderResponse)
def place_order(
    payload: PlaceOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlaceOrderResponse:
    """Send an order the user has already previewed.

    This is the one route in the product that moves real money. It takes a
    trade id and nothing else, so it can only ever execute an order that
    was priced first and shown to the person placing it.
    """
    _require_trading()
    try:
        body = st.place_previewed_order(db, current_user.id, payload.trade_id)
    except st.TradingDisabled:
        raise HTTPException(status_code=503, detail="Order placement isn't enabled.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: place failed user=%s", current_user.id)
        raise HTTPException(status_code=502, detail="Couldn't place the order.") from exc
    return PlaceOrderResponse(
        status=body.get("status"),
        brokerage_order_id=body.get("brokerage_order_id") or body.get("id"),
    )
