"""SnapTrade — READ-ONLY brokerage connection (slice 3).

Registers a Livermore user with SnapTrade, hands them a connection portal,
and reads back the holdings their broker reports. Nothing here places,
previews, cancels or modifies an order.

WHY READ-ONLY IS ENFORCED RATHER THAN PROMISED. The SDK also exposes
order-placement, order-impact and per-account transacting endpoints, plus
a whole transacting group on the client. Placing an order is a different
regulatory question from publishing — it is the piece that needs counsel
and probably a registered partner (spec §6.6, build_specs/daily_path_v1.md)
— so it must not become reachable because somebody reached for the nearest
SDK method while doing something else. This module exposes read methods
only, and `tests/test_snaptrade_readonly_guard.py` fails the build if any
of those names appears anywhere under `app/`. (That test names them; this
docstring deliberately does not, so the guard can stay blunt rather than
learning to parse docstrings.)

WHY THE OFFICIAL SDK. Every request is signed with a timestamp + HMAC
scheme. Hand-rolling that is precisely the class of thing that fails
subtly and silently, which is what trap #14 in apps/api/CLAUDE.md is about.
The SDK is the vendor's own description of their surface.

CONFIGURATION IS ALL-OR-NOTHING. Without all three env vars the feature
reports itself unconfigured and its routes 503. It never degrades to
storing a brokerage credential in the clear, and it never crashes the app
at boot — a missing key must not take production down (trap #11).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.snaptrade_user import SnapTradeUser

_log = logging.getLogger("livermore.snaptrade")


class SnapTradeNotConfigured(RuntimeError):
    """Raised when the env vars are absent. Callers turn this into a 503 —
    it is an operator state, not a user error."""


@dataclass(frozen=True)
class BrokerPosition:
    """One holding, in the only terms this product needs.

    `average_purchase_price` is the broker's cost basis, and it is the
    reason this integration is worth building: `declare_position` needs
    symbol + shares + entry price, and the broker supplies all three. The
    manual entry that gated the whole execution loop disappears rather than
    merely getting easier.
    """

    account_id: str
    symbol: str
    units: float
    average_purchase_price: Optional[float]
    last_price: Optional[float]
    open_pnl: Optional[float]


def is_configured() -> bool:
    s = get_settings()
    return bool(
        s.snaptrade_client_id
        and s.snaptrade_consumer_key
        and s.snaptrade_encryption_key
    )


# ── secret handling ─────────────────────────────────────────────────────────


def _fernet():
    from cryptography.fernet import Fernet

    s = get_settings()
    if not s.snaptrade_encryption_key:
        raise SnapTradeNotConfigured("snaptrade_encryption_key is not set")
    return Fernet(s.snaptrade_encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ── client ──────────────────────────────────────────────────────────────────


def _client():
    """The SDK client. Imported lazily so the app boots without the package
    present and without the env vars set — the feature simply reports itself
    unconfigured."""
    if not is_configured():
        raise SnapTradeNotConfigured("SnapTrade env vars are not set")
    from snaptrade_client import SnapTrade, SnapTradeAuth

    s = get_settings()
    # Credentials go through `auth`, NOT as top-level kwargs. The
    # constructor still ACCEPTS `client_id=` / `consumer_key=` — and raises
    # TypeError("... must be passed through 'auth'") if either is non-None.
    # So the natural-looking call compiles, passes any test that injects a
    # client, and blows up the first time a real user clicks Connect.
    # Verified against the SDK's own constructor, not recalled.
    factory = (
        SnapTradeAuth.personal_api_key
        if s.snaptrade_auth_mode.strip().lower() == "personal"
        else SnapTradeAuth.commercial_api_key
    )
    return SnapTrade(auth=factory(
        consumer_key=s.snaptrade_consumer_key,
        client_id=s.snaptrade_client_id,
    ))


# ── registration + connection ───────────────────────────────────────────────


def get_registration(db: Session, user_id: str) -> Optional[SnapTradeUser]:
    return db.execute(
        select(SnapTradeUser).where(SnapTradeUser.user_id == user_id)
    ).scalar_one_or_none()


def register_user(db: Session, user_id: str, *, client: Any = None) -> SnapTradeUser:
    """Register this Livermore user with SnapTrade, or return the existing
    registration. Idempotent — re-registering would issue a NEW userSecret
    and orphan every connection the user already authorised.
    """
    existing = get_registration(db, user_id)
    if existing is not None:
        return existing

    api = client or _client()
    resp = api.authentication.register_snap_trade_user(user_id=user_id)
    body = _body(resp)
    secret = body.get("userSecret")
    st_user_id = body.get("userId") or user_id
    if not secret:
        raise RuntimeError("SnapTrade registration returned no userSecret")

    row = SnapTradeUser(
        id=str(uuid4()),
        user_id=user_id,
        snaptrade_user_id=str(st_user_id),
        user_secret_encrypted=encrypt_secret(str(secret)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def connection_portal_url(
    db: Session, user_id: str, *, client: Any = None
) -> str:
    """A one-time URL where the user authorises their own broker.

    The authorisation happens on SnapTrade's portal against the broker's own
    login — Livermore never sees the user's brokerage credentials, which is
    the entire point of doing this through an aggregator.
    """
    reg = get_registration(db, user_id) or register_user(db, user_id, client=client)
    api = client or _client()
    resp = api.authentication.login_snap_trade_user(
        user_id=reg.user_id,
        user_secret=decrypt_secret(reg.user_secret_encrypted),
    )
    body = _body(resp)
    url = body.get("redirectURI") or body.get("redirect_uri")
    if not url:
        raise RuntimeError("SnapTrade login returned no redirect URI")
    return str(url)


# ── reading ─────────────────────────────────────────────────────────────────


def list_accounts(
    db: Session, user_id: str, *, client: Any = None
) -> List[Dict[str, Any]]:
    reg = get_registration(db, user_id)
    if reg is None:
        return []
    api = client or _client()
    resp = api.account_information.list_user_accounts(
        user_id=reg.user_id,
        user_secret=decrypt_secret(reg.user_secret_encrypted),
    )
    return list(_body(resp) or [])


def list_positions(
    db: Session, user_id: str, *, client: Any = None
) -> List[BrokerPosition]:
    """Every holding across every connected account.

    A failure on ONE account is logged and skipped rather than failing the
    whole read: a user with three brokers connected should not lose sight of
    all of them because one is having a bad morning.
    """
    reg = get_registration(db, user_id)
    if reg is None:
        return []
    api = client or _client()
    secret = decrypt_secret(reg.user_secret_encrypted)

    out: List[BrokerPosition] = []
    for account in list_accounts(db, user_id, client=api):
        account_id = str(account.get("id") or "")
        if not account_id:
            continue
        try:
            # `get_all_account_positions` -> GET /accounts/{accountId}/positions/all.
            # Verified against the SDK's own path module, not recalled:
            # `get_user_account_positions` is the plausible-sounding name
            # and it does not exist. Trap #14 in apps/api/CLAUDE.md.
            resp = api.account_information.get_all_account_positions(
                user_id=reg.user_id, user_secret=secret, account_id=account_id,
            )
            for pos in _body(resp) or []:
                symbol = _symbol_of(pos)
                if not symbol:
                    continue
                out.append(BrokerPosition(
                    account_id=account_id,
                    symbol=symbol,
                    units=float(pos.get("units") or 0.0),
                    average_purchase_price=_maybe_float(
                        pos.get("average_purchase_price")
                    ),
                    last_price=_maybe_float(pos.get("price")),
                    open_pnl=_maybe_float(pos.get("open_pnl")),
                ))
        except Exception:  # noqa: BLE001
            _log.exception(
                "snaptrade: positions read failed for account %s", account_id
            )

    reg.last_synced_at = datetime.utcnow()
    db.commit()
    return out


# ── helpers ─────────────────────────────────────────────────────────────────


def _body(resp: Any) -> Any:
    """The SDK returns a response object with `.body`; tests pass plain
    dicts and lists. Accept both rather than forcing fixtures to imitate the
    SDK's wrapper."""
    return getattr(resp, "body", resp)


def _symbol_of(pos: Dict[str, Any]) -> Optional[str]:
    """SnapTrade nests the ticker under `symbol.symbol.symbol` — the outer
    is the position's symbol record, the middle its universal symbol, the
    inner the actual ticker string. Walk it defensively; a shape change
    should drop one position, not raise."""
    node: Any = pos.get("symbol")
    for _ in range(3):
        if isinstance(node, str):
            return node.strip().upper() or None
        if isinstance(node, dict):
            node = node.get("symbol")
            continue
        return None
    return None


def _maybe_float(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None
