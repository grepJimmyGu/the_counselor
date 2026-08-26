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
from pydantic import BaseModel, model_validator
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


# ── the account, as the broker sees it ──────────────────────────────────────
#
# Four reads that mirror what the brokerage already knows. None of them maps
# a trade onto a Livermore strategy: a user's history is worth seeing on its
# own terms, and a strategy lens would hide every trade that doesn't fit one.


class BrokerActivityView(BaseModel):
    account_id: str
    activity_id: Optional[str] = None
    type: Optional[str] = None          # BUY | SELL | DIVIDEND | FEE | …
    symbol: Optional[str] = None
    units: Optional[float] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    fee: Optional[float] = None
    currency: Optional[str] = None
    # When it HAPPENED. `settlement_date` is when it cleared, days later —
    # only the first is what a person means by "when I bought it".
    trade_date: Optional[str] = None
    settlement_date: Optional[str] = None
    description: Optional[str] = None


@router.get("/activities", response_model=List[BrokerActivityView])
def snaptrade_activities(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 250,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[BrokerActivityView]:
    """Buys, sells and dividends across every connected account, newest first.

    `start_date` / `end_date` are ISO dates and are passed straight through —
    "the last year" is a caller decision, not a server default, because the
    right window differs between a page load and a one-off backfill.
    """
    _require_configured()
    try:
        rows = st.list_activities(
            db, current_user.id,
            start_date=start_date, end_date=end_date, limit=limit,
        )
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: activities failed user=%s", current_user.id)
        raise HTTPException(status_code=502, detail="Couldn't read your transaction history.") from exc
    return [BrokerActivityView(**vars(r)) for r in rows]


@router.get("/orders", response_model=List[dict])
def snaptrade_orders(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """Orders the broker has on file — including ones placed elsewhere.

    Passed through rather than reshaped: order payloads differ by brokerage
    and inventing a common shape would drop the fields that differ, which are
    usually the ones a user is looking for.
    """
    _require_configured()
    try:
        return st.list_recent_orders(db, current_user.id, days=days)
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: orders failed user=%s", current_user.id)
        raise HTTPException(status_code=502, detail="Couldn't read your recent orders.") from exc


@router.get("/performance", response_model=List[dict])
def snaptrade_performance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """The BROKER's own return rates, per account and timeframe.

    Deliberately theirs and not ours. A return figure is only meaningful
    against the deposits and withdrawals that produced it, and we do not see
    those — a number computed here from an incomplete picture would be worse
    than one passed through.
    """
    _require_configured()
    try:
        return st.get_return_rates(db, current_user.id)
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: performance failed user=%s", current_user.id)
        raise HTTPException(status_code=502, detail="Couldn't read your performance.") from exc


@router.get("/balance-history", response_model=List[dict])
def snaptrade_balance_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """Account value over time — the equity curve the broker keeps."""
    _require_configured()
    try:
        return st.get_balance_history(db, current_user.id)
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: balance history failed user=%s", current_user.id)
        raise HTTPException(status_code=502, detail="Couldn't read your balance history.") from exc


class SymbolSummaryView(BaseModel):
    symbol: str
    trades: int
    buys: int
    sells: int
    realised_pnl: float
    win_rate: Optional[float] = None
    avg_holding_days: Optional[float] = None
    gross_bought: float = 0.0


class ExitGapView(BaseModel):
    """M1. Positive = holding would have been worth more. Negative = the
    exits added value, which is reported just as plainly."""
    dollars: float
    is_material: bool
    sells_measured: int
    sells_total: int
    symbols_measured: int
    largest_symbol: Optional[str] = None
    largest_dollars: Optional[float] = None
    # The bar we priced the counterfactual against. `price_bars` is a cache;
    # "worth $N today" over a stale bar is a different claim, so the date is
    # rendered (the date-stamp product invariant).
    as_of: Optional[str] = None
    excluded: List[List[str]] = []


class ExecutionQualityView(BaseModel):
    """M4. Where each fill landed in its own day's range, priced against that
    day's midpoint — a fill you could plausibly have got, unlike the low."""
    dollars: float
    buy_dollars: float
    sell_dollars: float
    fills_measured: int
    fills_total: int
    buy_percentile: Optional[float] = None
    sell_percentile: Optional[float] = None
    in_worst_tercile: bool = False


class RollUpView(BaseModel):
    """The one sentence. A CEILING — every part is a counterfactual, and the
    rendered copy has to say so rather than hiding it in a tooltip."""
    dollars: float
    exit_gap: float
    fees: float
    execution: float
    components: List[str] = []


class TradingBehaviorView(BaseModel):
    """What the user's own record says about how they trade.

    Every field is a count of something they did. Nothing here predicts, and
    nothing scores them.
    """
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    total_buys: int
    total_sells: int
    symbols_traded: int

    round_trips: int
    realised_pnl: float
    fees_paid: float
    wins: int
    losses: int
    win_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    # What you make when right over what you lose when wrong. The number that
    # decides whether a method survives, and the one nobody knows.
    win_loss_ratio: Optional[float] = None
    largest_win: Optional[float] = None
    largest_loss: Optional[float] = None

    avg_holding_days: Optional[float] = None
    median_holding_days: Optional[float] = None
    avg_holding_days_winners: Optional[float] = None
    avg_holding_days_losers: Optional[float] = None
    # The disposition effect, as a yes or no. NULL when either side has no
    # completed trades — a two-trade history cannot support the claim.
    holds_losers_longer: Optional[bool] = None

    top_symbols_by_trades: List[SymbolSummaryView] = []
    top_symbols_by_pnl: List[SymbolSummaryView] = []
    worst_symbols_by_pnl: List[SymbolSummaryView] = []

    # Why the numbers are what they are.
    unmatched_sells: int = 0
    unmatched_sell_symbols: List[str] = []
    open_lots: int = 0

    # What the figures above are computed ON. A number over 9 of 10 symbols
    # is a different claim from one over all 10, and the difference belongs
    # on screen rather than in a docstring.
    symbols_total: int = 0
    symbols_included: int = 0
    excluded: List[List[str]] = []      # [symbol, reason] pairs
    splits_seen: int = 0
    splits_adjusted: int = 0

    # What changing it would have been worth (PRD-43a M1/M4 + the roll-up).
    exit_gap: Optional[ExitGapView] = None
    execution: Optional[ExecutionQualityView] = None
    recoverable: Optional[RollUpView] = None
    # Remedy keys, in the order the surface should offer them. A finding that
    # names no remedy is a verdict, and we do not ship verdicts.
    remedies: List[str] = []


@router.get("/behavior", response_model=TradingBehaviorView)
def snaptrade_behavior(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TradingBehaviorView:
    """Read the user's own trading record back to them.

    Computed here rather than in the browser: FIFO lot matching is real logic
    that deserves tests, and the same summary will feed strategy
    recommendations later. Two consumers, one implementation.
    """
    _require_configured()
    from app.services.mirror.portfolio_ledger_service import build_ledger, load_splits
    from app.services.trading_behavior import summarize

    # Trap #17: snapshot before anything can commit and expire the instance.
    user_id: str = current_user.id

    try:
        activities = st.list_activities(
            db, user_id,
            start_date=start_date, end_date=end_date, limit=250,
        )
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: behavior read failed user=%s", user_id)
        raise HTTPException(status_code=502, detail="Couldn't read your trading history.") from exc

    rows = [vars(a) for a in activities]

    # The broker round-trip above is the slow part of this request, and it is
    # a BLOCKING SDK call — this handler is `def` on purpose so FastAPI runs
    # it in a worker thread rather than on the event loop. `close()` hands the
    # pool connection back now instead of at the end of the request; the
    # session is still usable and checks out a fresh one for the price read
    # below. That is the #126 lesson in its synchronous form: never hold a
    # pool slot across a third party.
    db.close()

    symbols = {str(r.get("symbol") or "").upper() for r in rows}
    symbols.discard("")
    ledger = build_ledger(rows, {})
    if symbols:
        try:
            # NOT bounded on the start side, deliberately. A user's window
            # routinely begins after a position was opened, and the split
            # that makes their sell unmatchable happened before the first row
            # we can see. Bounding by `window_start` hides exactly the split
            # that explains the problem. Loading earlier ones is free —
            # `_apply_splits` only applies splits AFTER a trade date, so a
            # split nobody traded across changes nothing.
            splits = load_splits(db, symbols, end=ledger.coverage.window_end)
            ledger = build_ledger(rows, splits)
        except Exception:  # noqa: BLE001
            # Losing the split data degrades honesty, not availability: we
            # fall back to raw matching, which is what shipped before this.
            # Logged loudly (trap #20) rather than warned, because a silent
            # fallback here means a split position reports a loss that never
            # happened — and that reads exactly like a real finding.
            _log.exception("snaptrade: split lookup failed user=%s", user_id)

    b = summarize(ledger.transactions)

    # M1 and M4. Two more bounded reads on the same session — the symbols the
    # user traded, never the universe.
    from app.services.mirror.measurements import (
        exit_gap, execution_quality, load_bars_on, load_latest_closes, recoverable,
    )
    from app.services.trading_behavior import _parse_date, _side

    skip = {sym for sym, _ in ledger.coverage.excluded}
    gap = exit_gap(ledger.transactions, {}, skip_symbols=skip)
    xq = execution_quality(ledger.transactions, {})
    try:
        if symbols:
            gap = exit_gap(
                ledger.transactions,
                load_latest_closes(db, symbols),
                skip_symbols=skip,
            )
        pairs = [
            (str(t.get("symbol") or "").upper(), _parse_date(t.get("trade_date")))
            for t in ledger.transactions
            if _side(t) in ("BUY", "SELL")
        ]
        pairs = [(sym, when) for sym, when in pairs if sym and when]
        if pairs:
            xq = execution_quality(ledger.transactions, load_bars_on(db, pairs))
    except Exception:  # noqa: BLE001
        # Same posture as the split lookup: the description of what they did
        # still stands without the pricing of it. Logged with a traceback
        # (trap #20) — a silently missing headline looks identical to a user
        # who simply has nothing to recover.
        _log.exception("snaptrade: measurement read failed user=%s", user_id)

    roll = recoverable(gap, b.fees_paid, xq)
    remedies = [r for r in (gap.remedy, xq.remedy) if r]

    def _sym(s) -> SymbolSummaryView:
        return SymbolSummaryView(
            symbol=s.symbol, trades=s.trades, buys=s.buys, sells=s.sells,
            realised_pnl=round(s.realised_pnl, 2), win_rate=s.win_rate,
            avg_holding_days=s.avg_holding_days,
            gross_bought=round(s.gross_bought, 2),
        )

    return TradingBehaviorView(
        window_start=b.window_start.isoformat() if b.window_start else None,
        window_end=b.window_end.isoformat() if b.window_end else None,
        total_buys=b.total_buys, total_sells=b.total_sells,
        symbols_traded=b.symbols_traded,
        round_trips=b.round_trips,
        realised_pnl=round(b.realised_pnl, 2),
        fees_paid=round(b.fees_paid, 2),
        wins=b.wins, losses=b.losses, win_rate=b.win_rate,
        avg_win=round(b.avg_win, 2) if b.avg_win is not None else None,
        avg_loss=round(b.avg_loss, 2) if b.avg_loss is not None else None,
        win_loss_ratio=b.win_loss_ratio,
        largest_win=round(b.largest_win, 2) if b.largest_win is not None else None,
        largest_loss=round(b.largest_loss, 2) if b.largest_loss is not None else None,
        avg_holding_days=b.avg_holding_days,
        median_holding_days=b.median_holding_days,
        avg_holding_days_winners=b.avg_holding_days_winners,
        avg_holding_days_losers=b.avg_holding_days_losers,
        holds_losers_longer=b.holds_losers_longer,
        top_symbols_by_trades=[_sym(s) for s in b.top_symbols_by_trades],
        top_symbols_by_pnl=[_sym(s) for s in b.top_symbols_by_pnl],
        worst_symbols_by_pnl=[_sym(s) for s in b.worst_symbols_by_pnl],
        unmatched_sells=b.unmatched_sells,
        unmatched_sell_symbols=b.unmatched_sell_symbols,
        open_lots=b.open_lots,
        symbols_total=ledger.coverage.symbols_total,
        symbols_included=ledger.coverage.symbols_included,
        excluded=[[sym, reason] for sym, reason in ledger.coverage.excluded],
        splits_seen=ledger.coverage.splits_seen,
        splits_adjusted=ledger.coverage.splits_adjusted,
        exit_gap=ExitGapView(
            dollars=round(gap.dollars, 2),
            is_material=gap.is_material,
            sells_measured=gap.sells_measured,
            sells_total=gap.sells_total,
            symbols_measured=gap.symbols_measured,
            largest_symbol=gap.largest_symbol,
            largest_dollars=(
                round(gap.largest_dollars, 2)
                if gap.largest_dollars is not None else None
            ),
            as_of=gap.as_of.isoformat() if gap.as_of else None,
            excluded=[[sym, reason] for sym, reason in gap.excluded],
        ),
        execution=ExecutionQualityView(
            dollars=round(xq.dollars, 2),
            buy_dollars=round(xq.buy_dollars, 2),
            sell_dollars=round(xq.sell_dollars, 2),
            fills_measured=xq.fills_measured,
            fills_total=xq.fills_total,
            buy_percentile=xq.buy_percentile,
            sell_percentile=xq.sell_percentile,
            in_worst_tercile=xq.in_worst_tercile,
        ),
        recoverable=RollUpView(
            dollars=round(roll.dollars, 2),
            exit_gap=round(roll.exit_gap, 2),
            fees=round(roll.fees, 2),
            execution=round(roll.execution, 2),
            components=roll.components,
        ),
        remedies=remedies,
    )


# ── order placement (slice 4c) ──────────────────────────────────────────────
#
# Two endpoints, and the split is the safety property rather than a style
# choice. `/orders/preview` prices an order and returns a trade id;
# `/orders/place` takes ONLY that id. There is no route that accepts a
# symbol and a quantity and sends it, so no client — ours or anyone's —
# can place an order the user has not seen priced.


class BrokerAccountView(BaseModel):
    """Enough to choose an account and know which one you chose.

    A SELL knows its account from the position being sold. A BUY does not —
    you do not own the thing yet — so the buyer has to pick, and picking
    requires seeing the institution and the last digits.
    """
    id: str
    name: Optional[str] = None
    number: Optional[str] = None
    institution_name: Optional[str] = None


@router.get("/accounts", response_model=List[BrokerAccountView])
def snaptrade_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[BrokerAccountView]:
    """The user's connected brokerage accounts.

    Exists because BUY orders need an account id and cannot get one from a
    position. `/positions` carries `account_id` per holding, which is enough
    to sell — and useless to someone whose account is empty and who wants to
    make their first purchase.
    """
    _require_configured()
    try:
        rows = st.list_accounts(db, current_user.id)
    except st.SnapTradeNotConfigured:
        raise HTTPException(status_code=503, detail="Brokerage connections aren't available right now.")
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: accounts failed user=%s", current_user.id)
        raise HTTPException(
            status_code=502, detail="Couldn't read your brokerage accounts.",
        ) from exc

    out: List[BrokerAccountView] = []
    for r in rows:
        rid = r.get("id")
        if not rid:
            continue          # an account we cannot address is not an option
        inst = r.get("institution_name")
        if isinstance(inst, dict):
            inst = inst.get("name")
        out.append(BrokerAccountView(
            id=str(rid),
            name=r.get("name") or r.get("nickname"),
            number=r.get("number"),
            institution_name=inst,
        ))
    return out


class PreviewOrderRequest(BaseModel):
    account_id: str
    symbol: str
    action: str                    # "BUY" | "SELL"
    # EXACTLY ONE of these. A sell is sized in shares — you sell what you
    # hold. A buy is sized in dollars, because "how much of my money" is the
    # question a person actually answers, and SnapTrade takes a notional
    # amount natively rather than making us round a share count.
    units: Optional[float] = None
    notional: Optional[float] = None
    order_type: str = "Market"
    time_in_force: str = "Day"
    price: Optional[float] = None  # limit price; ignored for Market

    @model_validator(mode="after")
    def exactly_one_size(self) -> "PreviewOrderRequest":
        if (self.units is None) == (self.notional is None):
            raise ValueError(
                "Send exactly one of `units` or `notional`. Sending both "
                "would let the ticket display one number and transmit "
                "another."
            )
        return self


class PreviewOrderResponse(BaseModel):
    trade_id: str
    symbol: str
    action: str
    # OPTIONAL, and it has to be. A buy is sized in dollars, so there is no
    # share count to send — the broker computes one, and SnapTrade's own
    # `ManualTrade` types it `UnitsNullable`. Requiring it here 500'd every
    # dollar-sized buy for as long as trading was enabled.
    units: Optional[float] = None
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
            notional=payload.notional,
            order_type=payload.order_type,
            time_in_force=payload.time_in_force,
            price=payload.price,
        )
        # Serialised INSIDE the try on purpose. When this raised outside it,
        # a response the model rejected surfaced as a bare 500 with no log
        # line — which is how the dollar-sized buy stayed invisible.
        return PreviewOrderResponse(**{
            k: out[k] for k in PreviewOrderResponse.model_fields if k in out
        })
    except st.TradingDisabled:
        raise HTTPException(status_code=503, detail="Order placement isn't enabled.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _log.exception("snaptrade: preview failed user=%s", current_user.id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
