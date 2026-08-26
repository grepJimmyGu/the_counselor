"""SnapTrade — brokerage connection (slice 3) and order placement (4c).

Registers a Livermore user with SnapTrade, hands them a portal to connect a
broker, reads back the holdings their broker reports, and — when trading is
enabled for the environment — prices and places an order the user has
confirmed.

WHAT IS STILL ENFORCED. Order placement is a deliberate product decision,
but two things about it are not negotiable and the guard test fails the
build on either: no order may be sent without a preview the user saw
(SnapTrade's force-order path is banned outright), and no order may
originate anywhere but a request a person made (nothing in `jobs/`, ever).
See `tests/test_snaptrade_readonly_guard.py`.

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


def return_url_for(path: Optional[str]) -> str:
    """Build the post-authorisation return URL from a caller-supplied PATH.

    OPEN-REDIRECT GUARD. `custom_redirect` tells SnapTrade where to send the
    user after they finish at their broker — so whatever reaches it is a
    destination we hand a real person mid-flow, having just asked them to
    trust us with a brokerage login. If a client could pass a full URL, that
    is an open redirect on the most sensitive step in the product.

    So the client sends a path and NEVER a URL. The origin comes from our own
    configuration, and anything that is not a simple site-relative path is
    discarded rather than sanitised — "//evil.com" and "https://evil.com" are
    both just not paths, and half-cleaning a hostile input is how these bugs
    survive review.
    """
    import os

    site = os.environ.get(
        "NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com"
    ).rstrip("/")
    if not path or not path.startswith("/") or path.startswith("//"):
        return site
    if "\\" in path or "\n" in path or "\r" in path:
        return site
    return site + path


def connection_portal_url(
    db: Session,
    user_id: str,
    *,
    return_path: Optional[str] = None,
    client: Any = None,
) -> str:
    """A one-time URL where the user authorises their own broker.

    The authorisation happens on SnapTrade's portal against the broker's own
    login — Livermore never sees the user's brokerage credentials, which is
    the entire point of doing this through an aggregator.

    `return_path` is where SnapTrade sends them afterwards. Without it they
    land wherever SnapTrade defaults to, which for someone halfway through
    the portfolio flow means losing their place immediately after doing the
    most trust-demanding thing we ask of them.
    """
    reg = get_registration(db, user_id) or register_user(db, user_id, client=client)
    api = client or _client()
    resp = api.authentication.login_snap_trade_user(
        user_id=reg.user_id,
        user_secret=decrypt_secret(reg.user_secret_encrypted),
        custom_redirect=return_url_for(return_path),
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


# ── the account, as the broker sees it ──────────────────────────────────────
#
# Everything below is a READ. None of it maps a trade onto a Livermore
# strategy — the user's brokerage history is worth seeing on its own terms,
# and forcing it through a strategy lens would hide the trades that don't fit
# one, which is most of them.


@dataclass(frozen=True)
class BrokerActivity:
    """One thing that happened in the account: a buy, a sell, a dividend.

    `trade_date` is when it happened; `settlement_date` is when it cleared.
    They differ by days and only the first is what a person means by "when
    I bought it."
    """

    account_id: str
    activity_id: Optional[str]
    type: Optional[str]          # BUY | SELL | DIVIDEND | FEE | …
    symbol: Optional[str]
    units: Optional[float]
    price: Optional[float]
    amount: Optional[float]
    fee: Optional[float]
    currency: Optional[str]
    trade_date: Optional[str]
    settlement_date: Optional[str]
    description: Optional[str]


def _each_account(db: Session, user_id: str, client: Any):
    """Yield (api, secret, account_id) for every connected account.

    Shared by every read below so a failure on one broker skips that broker
    rather than the whole page — a user with three connected should not lose
    all three because one is having a bad morning.
    """
    reg = get_registration(db, user_id)
    if reg is None:
        return
    api = client or _client()
    secret = decrypt_secret(reg.user_secret_encrypted)
    for account in list_accounts(db, user_id, client=api):
        account_id = str(account.get("id") or "")
        if account_id:
            yield api, reg.user_id, secret, account_id


def list_activities(
    db: Session, user_id: str, *, start_date: Optional[str] = None,
    end_date: Optional[str] = None, limit: int = 250, client: Any = None,
) -> List[BrokerActivity]:
    """Transactions across every connected account, newest first.

    `start_date`/`end_date` are ISO dates. SnapTrade paginates; `limit` is
    per account, and the default is deliberately generous — a year of a
    normal retail account is well under it, and asking twice for the same
    window is worse than asking once for slightly too much.
    """
    out: List[BrokerActivity] = []
    for api, st_user, secret, account_id in _each_account(db, user_id, client):
        try:
            kwargs: Dict[str, Any] = {
                "user_id": st_user, "user_secret": secret,
                "account_id": account_id, "limit": limit,
            }
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date
            resp = api.account_information.get_account_activities(**kwargs)
            body = _body(resp) or {}
            # Paginated shape is {"data": [...]}; some builds return a bare list.
            rows = body.get("data") if isinstance(body, dict) else body
            for a in rows or []:
                out.append(BrokerActivity(
                    account_id=account_id,
                    activity_id=str(a.get("id")) if a.get("id") else None,
                    type=a.get("type"),
                    symbol=_symbol_of(a),
                    units=_maybe_float(a.get("units")),
                    price=_maybe_float(a.get("price")),
                    amount=_maybe_float(a.get("amount")),
                    fee=_maybe_float(a.get("fee")),
                    currency=(a.get("currency") or {}).get("code")
                    if isinstance(a.get("currency"), dict) else a.get("currency"),
                    trade_date=a.get("trade_date"),
                    settlement_date=a.get("settlement_date"),
                    description=a.get("description"),
                ))
        except Exception:  # noqa: BLE001
            _log.exception("snaptrade: activities read failed for %s", account_id)

    out.sort(key=lambda a: a.trade_date or "", reverse=True)
    return out


def list_recent_orders(
    db: Session, user_id: str, *, days: int = 30, client: Any = None,
) -> List[Dict[str, Any]]:
    """Orders the broker has on file — including ones placed elsewhere.

    This is how a placed order learns whether it filled: the broker is the
    only party that knows.
    """
    out: List[Dict[str, Any]] = []
    for api, st_user, secret, account_id in _each_account(db, user_id, client):
        try:
            resp = api.account_information.get_user_account_orders(
                user_id=st_user, user_secret=secret,
                account_id=account_id, days=days,
            )
            for o in _body(resp) or []:
                row = dict(o)
                row["account_id"] = account_id
                out.append(row)
        except Exception:  # noqa: BLE001
            _log.exception("snaptrade: orders read failed for %s", account_id)
    return out


def get_return_rates(
    db: Session, user_id: str, *, client: Any = None,
) -> List[Dict[str, Any]]:
    """The broker's own performance numbers, per account.

    Deliberately the BROKER's calculation rather than ours. We do not know
    the deposits and withdrawals that make a return figure meaningful, and a
    number we computed from an incomplete picture would be worse than one we
    simply passed through.
    """
    out: List[Dict[str, Any]] = []
    for api, st_user, secret, account_id in _each_account(db, user_id, client):
        try:
            resp = api.account_information.get_user_account_return_rates(
                user_id=st_user, user_secret=secret, account_id=account_id,
            )
            body = _body(resp) or {}
            rows = body.get("data") if isinstance(body, dict) else body
            for r in rows or []:
                row = dict(r)
                row["account_id"] = account_id
                out.append(row)
        except Exception:  # noqa: BLE001
            _log.exception("snaptrade: return rates failed for %s", account_id)
    return out


def get_balance_history(
    db: Session, user_id: str, *, client: Any = None,
) -> List[Dict[str, Any]]:
    """Account value over time — the equity curve the broker keeps."""
    out: List[Dict[str, Any]] = []
    for api, st_user, secret, account_id in _each_account(db, user_id, client):
        try:
            resp = api.account_information.get_account_balance_history(
                user_id=st_user, user_secret=secret, account_id=account_id,
            )
            body = _body(resp) or {}
            rows = body.get("data") if isinstance(body, dict) else body
            for r in rows or []:
                row = dict(r)
                row["account_id"] = account_id
                out.append(row)
        except Exception:  # noqa: BLE001
            _log.exception("snaptrade: balance history failed for %s", account_id)
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


# ── order placement (slice 4c) ──────────────────────────────────────────────
#
# TWO-STEP ONLY. SnapTrade offers `place_force_order` (POST /trade/place),
# which sends an order with no preview. This module never calls it, and
# `tests/test_snaptrade_readonly_guard.py` fails the build if anything does.
#
# The difference is the entire product argument. `get_order_impact` returns
# what the order would actually do — real cost, commission, resulting cash
# — and a trade id. `place_order` can then only execute THAT id. So a user
# cannot have an order placed they did not see priced: the confirmation is
# structural, not a checkbox we remember to render.
#
# Nothing here is automatic. Every call originates in a request the user
# made, one order at a time. There is no scheduled path into these
# functions and no bulk form.


class TradingDisabled(RuntimeError):
    """Order placement is off for this environment. Separate from
    `SnapTradeNotConfigured` because reading holdings and sending orders are
    different decisions — one being on says nothing about the other."""


def is_trading_enabled() -> bool:
    return bool(is_configured() and get_settings().snaptrade_trading_enabled)


def _require_trading() -> None:
    if not is_trading_enabled():
        raise TradingDisabled("SnapTrade order placement is not enabled")


def resolve_symbol_id(
    db: Session, user_id: str, account_id: str, ticker: str, *, client: Any = None
) -> Optional[str]:
    """Ticker -> SnapTrade `universal_symbol_id`.

    The trading endpoints take an opaque symbol id, not "NVDA", and the id
    is scoped to the account's brokerage — the same ticker can differ
    between brokers. Resolving per account rather than globally is why this
    takes `account_id`.

    ON `reference_data`, NOT `trading`. It reads as a trading call and it is
    the first step of placing an order, so it was written as
    `api.trading.symbol_search_user_account` — which does not exist. That is
    an AttributeError on the first preview a user ever runs, i.e. the first
    time anyone presses Place.

    Invisible to the whole suite, because every test here injects a
    `MagicMock` client and a mock answers to any attribute you ask it for.
    Third instance of trap #14 in this integration, after
    `get_user_account_positions` and the `SnapTrade(client_id=...)`
    constructor. `tests/test_snaptrade_sdk_contract.py` now checks every
    call against the installed SDK instead of against memory.
    """
    reg = get_registration(db, user_id)
    if reg is None:
        return None
    api = client or _client()
    resp = api.reference_data.symbol_search_user_account(
        user_id=reg.user_id,
        user_secret=decrypt_secret(reg.user_secret_encrypted),
        account_id=account_id,
        substring=ticker,
    )
    wanted = ticker.strip().upper()
    for row in _body(resp) or []:
        # Exact ticker only. A substring search for "NV" happily returns
        # NVDA, NVR and NVAX; placing an order against "closest match"
        # is not a mistake worth risking to save the user a tap.
        if str(row.get("symbol", "")).strip().upper() == wanted:
            sid = row.get("id")
            return str(sid) if sid else None
    return None


def preview_order(
    db: Session,
    user_id: str,
    *,
    account_id: str,
    ticker: str,
    action: str,
    units: Optional[float] = None,
    notional: Optional[float] = None,
    order_type: str = "Market",
    time_in_force: str = "Day",
    price: Optional[float] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """Price the order without sending it. Returns the impact plus the
    `trade_id` that `place_order` will need.

    This is the ONLY way to obtain a trade id, which is what makes the
    preview impossible to skip.
    """
    _require_trading()
    reg = get_registration(db, user_id)
    if reg is None:
        raise RuntimeError("No brokerage connection for this user.")
    if (units is None) == (notional is None):
        raise ValueError("Send exactly one of `units` or `notional`.")
    if units is not None and units <= 0:
        raise ValueError("units must be positive")
    if notional is not None and notional <= 0:
        raise ValueError("notional must be positive")
    if action.upper() not in {"BUY", "SELL"}:
        raise ValueError("action must be BUY or SELL")

    api = client or _client()
    symbol_id = resolve_symbol_id(
        db, user_id, account_id, ticker, client=api
    )
    if not symbol_id:
        raise RuntimeError(f"{ticker} is not tradable in this account.")

    resp = api.trading.get_order_impact(
        user_id=reg.user_id,
        user_secret=decrypt_secret(reg.user_secret_encrypted),
        account_id=account_id,
        action=action.upper(),
        universal_symbol_id=symbol_id,
        order_type=order_type,
        time_in_force=time_in_force,
        # SnapTrade takes one or the other. Passing `units=None` explicitly
        # would send a null; omit the key that is not in play.
        **({"units": units} if units is not None else {"notional_value": notional}),
        price=price,
    )
    body = _body(resp) or {}
    trade = body.get("trade") or {}
    trade_id = trade.get("id") or body.get("id")
    if not trade_id:
        raise RuntimeError("SnapTrade returned no trade id for this preview.")
    return {
        "trade_id": str(trade_id),
        "symbol": ticker.strip().upper(),
        "action": action.upper(),
        "units": units,
        "estimated_commission": _maybe_float(body.get("estimated_commission")),
        "remaining_cash": _maybe_float(body.get("remaining_cash")),
        "raw": body,
    }


def place_previewed_order(
    db: Session, user_id: str, trade_id: str, *, client: Any = None
) -> Dict[str, Any]:
    """Send an order the user has already seen priced.

    Takes ONLY a trade id — deliberately. There is no path here that
    accepts a symbol and a quantity, so no caller can assemble an order and
    send it in one motion. To place anything you must first have previewed
    it, which means the user saw the cost.
    """
    _require_trading()
    reg = get_registration(db, user_id)
    if reg is None:
        raise RuntimeError("No brokerage connection for this user.")
    if not trade_id:
        raise ValueError("trade_id is required")

    api = client or _client()
    resp = api.trading.place_order(
        user_id=reg.user_id,
        user_secret=decrypt_secret(reg.user_secret_encrypted),
        trade_id=trade_id,
    )
    body = _body(resp) or {}
    _log.info(
        "snaptrade order placed user=%s trade_id=%s status=%s",
        user_id, trade_id, body.get("status"),
    )
    return dict(body)
