"""Option chains: fetched once per symbol, cleaned, and cut to what a screen needs.

A chain is every listed contract for a stock at the last close, about 3 MB
from the provider for a busy name. It is fetched once however many people
ask (apps/api/CLAUDE.md, trap 22: `app.core.concurrency`), kept for half an
hour, and the phone is sent one expiry near the stock's price, a few KB.

Every price in a chain is from the same close: the contracts' bid and ask, and
the stock's own closing price that day. Mixing a live stock price with last
night's option prices would put the wrong contract "at the money" on any day
the stock has moved.

A caller that wants the chain at the stock's price NOW gets every contract
re-estimated for that price (`estimate.py`), so the two still agree.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Dict, List, NamedTuple, Optional, Tuple
from zoneinfo import ZoneInfo

from app.core.concurrency import TTLCache
from app.services.alpha_vantage import AlphaVantageClient, AlphaVantageError, option_root
from app.services.live_quote_service import live_quote_service
from app.services.options.estimate import estimate_chain, estimate_contract, quoted_at

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Last-close prices change once a day, but when the provider publishes them
# is not documented, so look again every half hour. An older chain is served
# while that look happens, for up to a day.
_CHAIN_TTL_SECONDS = 1800.0
_CHAIN_STALE_SECONDS = 24 * 3600.0
# A parsed chain is one to two thousand small tuples. Sixty-four of them is
# tens of megabytes, not hundreds.
_MAX_CHAINS = 64
# A stock with no listed options will not have them an hour from now.
_NO_OPTIONS_TTL_SECONDS = 6 * 3600.0
# After the provider fails, do not ask again for the same symbol for a minute.
_PROVIDER_DOWN_TTL_SECONDS = 60.0

# Strikes kept in memory, and strikes sent to a screen, as a share of the
# stock's price either side of it.
_KEEP_WITHIN = 0.50
_SEND_WITHIN = 0.35

NO_OPTIONS = "no_options"
NOT_AVAILABLE = "not_available"


class OptionsUnavailable(Exception):
    """There is no chain to show. `reason` is NO_OPTIONS or NOT_AVAILABLE."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class OptionContract(NamedTuple):
    contract_id: str
    kind: str  # "call" or "put"
    expiration: date
    strike: float
    bid: float
    ask: float
    # Halfway between bid and ask, in cents: the price a plan is built on.
    mid: float
    last: Optional[float]
    volume: int
    open_interest: int
    # The volatility the price at the close implied, as a fraction (0.45 is
    # 45% a year). None when the provider gave none.
    implied_volatility: Optional[float] = None
    # Set when `mid` is an estimate for the stock's price now: the mid at
    # the close that it was estimated from.
    quoted_mid: Optional[float] = None


@dataclass(frozen=True)
class OptionChain:
    symbol: str
    # The trading day the quoted prices are from.
    as_of: date
    underlying_price: float
    # Per expiry, sorted by strike, the call before the put at each strike.
    by_expiration: Dict[date, List[OptionContract]]
    # Set when the contracts are estimates for a later stock price: when that
    # price traded, and the stock's close the quotes were made against.
    # `underlying_price` is then the later price.
    estimated_at: Optional[datetime] = None
    quoted_underlying_price: Optional[float] = None


@dataclass(frozen=True)
class Expiration:
    date: date
    days: int
    monthly: bool
    implied_move_pct: Optional[float]


@dataclass(frozen=True)
class ChainSlice:
    """One expiry of a chain, with the list of every expiry to choose from."""

    symbol: str
    as_of: date
    underlying_price: float
    expirations: List[Expiration]
    default_expiration: date
    expiration: date
    contracts: List[OptionContract]
    estimated_at: Optional[datetime] = None
    quoted_underlying_price: Optional[float] = None


def today_et() -> date:
    return datetime.now(_ET).date()


# ── Parsing ───────────────────────────────────────────────────────────────────

def _number(value: object) -> Optional[float]:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _cents(value: float) -> float:
    return round(value + 1e-9, 2)


def parse_chain(symbol: str, rows: List[dict], underlying_price: float) -> Optional[OptionChain]:
    """Turn the provider's rows into a chain, or None if nothing usable is left.

    Dropped: contracts that are not the standard 100 shares (after a split or
    special dividend the exchange renames them NVDA1, NVDA2…, and their
    payoff is not strike-times-100), contracts nobody is offering (no ask),
    rows with a bid above the ask, and strikes far from the stock's price.
    """
    standard = re.compile(r"^" + re.escape(option_root(symbol)) + r"\d{6}[CP]\d{8}$")
    low, high = underlying_price * (1 - _KEEP_WITHIN), underlying_price * (1 + _KEEP_WITHIN)
    as_of: Optional[date] = None
    by_expiration: Dict[date, List[OptionContract]] = {}
    for row in rows:
        contract_id = str(row.get("contractID", ""))
        kind = str(row.get("type", "")).lower()
        if not standard.match(contract_id) or kind not in ("call", "put"):
            continue
        strike, bid, ask = _number(row.get("strike")), _number(row.get("bid")), _number(row.get("ask"))
        if strike is None or bid is None or ask is None:
            continue
        if strike <= 0 or ask <= 0 or bid < 0 or bid > ask or not (low <= strike <= high):
            continue
        try:
            expiration = date.fromisoformat(str(row.get("expiration", "")))
            priced_on = date.fromisoformat(str(row.get("date", "")))
        except ValueError:
            continue
        as_of = priced_on if as_of is None else max(as_of, priced_on)
        last = _number(row.get("last"))
        sigma = _number(row.get("implied_volatility"))
        by_expiration.setdefault(expiration, []).append(
            OptionContract(
                contract_id=contract_id,
                kind=kind,
                expiration=expiration,
                strike=strike,
                bid=bid,
                ask=ask,
                mid=_cents((bid + ask) / 2),
                last=last if last is not None and last > 0 else None,
                volume=int(_number(row.get("volume")) or 0),
                open_interest=int(_number(row.get("open_interest")) or 0),
                implied_volatility=sigma if sigma is not None and sigma > 0 else None,
            )
        )
    if as_of is None:
        return None
    # A contract that expired on the day the prices are from is settled.
    live = {
        expiration: sorted(contracts, key=lambda c: (c.strike, c.kind))
        for expiration, contracts in by_expiration.items()
        if expiration > as_of
    }
    if not live:
        return None
    return OptionChain(symbol=symbol.upper(), as_of=as_of, underlying_price=underlying_price, by_expiration=live)


# ── Reading a chain ───────────────────────────────────────────────────────────

def _third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def is_monthly(expiration: date, listed: List[date]) -> bool:
    """The standard monthly expiry: the third Friday, or the Thursday before
    it when that Friday is a market holiday and so is not listed."""
    friday = _third_friday(expiration.year, expiration.month)
    if expiration == friday:
        return True
    return expiration == friday - timedelta(days=1) and friday not in listed


def implied_move_pct(contracts: List[OptionContract], underlying_price: float) -> Optional[float]:
    """What the call and the put nearest the stock's price cost together, as a
    percent of that price: the move option prices are charging for by expiry."""
    calls = {c.strike: c for c in contracts if c.kind == "call"}
    puts = {c.strike: c for c in contracts if c.kind == "put"}
    both = sorted(set(calls) & set(puts), key=lambda strike: (abs(strike - underlying_price), strike))
    if not both or underlying_price <= 0:
        return None
    strike = both[0]
    # A "nearest" strike a long way from the price says nothing about a move.
    if abs(strike - underlying_price) > 0.05 * underlying_price:
        return None
    return round((calls[strike].mid + puts[strike].mid) / underlying_price * 100, 1)


def default_expiration(expirations: List[Expiration]) -> date:
    """Where a plan starts: the first monthly expiry at least 30 days out.
    A starting point the user changes, not advice."""
    for wanted in (lambda e: e.monthly and e.days >= 30, lambda e: e.days >= 30):
        for expiration in expirations:
            if wanted(expiration):
                return expiration.date
    return expirations[-1].date


def _near(contracts: List[OptionContract], underlying_price: float) -> List[OptionContract]:
    """The contracts a screen is sent: strikes within reach of the stock's price."""
    low, high = underlying_price * (1 - _SEND_WITHIN), underlying_price * (1 + _SEND_WITHIN)
    return [c for c in contracts if low <= c.strike <= high]


def _two_sided(contracts: List[OptionContract]) -> bool:
    return {c.kind for c in contracts} == {"call", "put"}


def slice_chain(chain: OptionChain, expiration: Optional[date], today: date) -> ChainSlice:
    """One expiry's contracts near the stock's price, plus every expiry still ahead."""
    listed = sorted(e for e in chain.by_expiration if e > today)
    if not listed:
        raise OptionsUnavailable(NOT_AVAILABLE, f"Option prices for {chain.symbol} are out of date.")
    expirations = [
        Expiration(
            date=e,
            days=(e - today).days,
            monthly=is_monthly(e, listed),
            implied_move_pct=implied_move_pct(chain.by_expiration[e], chain.underlying_price),
        )
        for e in listed
    ]
    chosen = expiration or default_expiration(expirations)
    if chosen not in chain.by_expiration or chosen <= today:
        raise OptionsUnavailable(NO_OPTIONS, f"{chain.symbol} has no options expiring on {chosen.isoformat()}.")
    return ChainSlice(
        symbol=chain.symbol,
        as_of=chain.as_of,
        underlying_price=chain.underlying_price,
        expirations=expirations,
        default_expiration=default_expiration(expirations),
        expiration=chosen,
        contracts=_near(chain.by_expiration[chosen], chain.underlying_price),
        estimated_at=chain.estimated_at,
        quoted_underlying_price=chain.quoted_underlying_price,
    )


# ── Fetching ──────────────────────────────────────────────────────────────────

class OptionChainService:
    def __init__(self, client: Optional[AlphaVantageClient] = None) -> None:
        self._client = client or AlphaVantageClient()
        self._chains: TTLCache[OptionChain] = TTLCache(
            ttl=_CHAIN_TTL_SECONDS, stale_for=_CHAIN_STALE_SECONDS, max_entries=_MAX_CHAINS
        )
        # Single expiries fetched to repair a one-sided chain (see `slice`).
        self._expiries: TTLCache[List[OptionContract]] = TTLCache(
            ttl=_CHAIN_TTL_SECONDS, max_entries=256, keep=_two_sided
        )
        self._no_options: TTLCache[str] = TTLCache(ttl=_NO_OPTIONS_TTL_SECONDS, max_entries=4096)
        self._provider_down: TTLCache[str] = TTLCache(ttl=_PROVIDER_DOWN_TTL_SECONDS, max_entries=4096)

    async def get(self, symbol: str) -> OptionChain:
        """The chain for `symbol`. Raises OptionsUnavailable when there is none."""
        sym = symbol.upper()
        message = self._no_options.peek(sym)
        if message is not None:
            raise OptionsUnavailable(NO_OPTIONS, message)
        return await self._chains.get(sym, lambda: self._load(sym))

    async def slice(
        self, symbol: str, expiration: Optional[date], today: date,
        stock_now: Optional[float] = None, traded_at: Optional[datetime] = None,
    ) -> ChainSlice:
        """One expiry near the stock's price, with every expiry to choose from.

        With `stock_now` (and when it traded), every contract is estimated
        for that price and the slice is cut around it. Without, or when that
        price is from the chain's own day, the prices are the close's.

        The provider's full chain sometimes arrives with one side missing:
        on 2026-11-20 AAPL and SPY came back with every call and no puts,
        while NVDA and MSFT were whole. Asking for the one expiry returns
        both sides, so a one-sided expiry is fetched again on its own. If
        that does not help, what there is gets sent.
        """
        quoted = await self.get(symbol)
        chain = estimate_chain(quoted, stock_now, traded_at) if stock_now is not None else quoted
        part = slice_chain(chain, expiration, today)
        if _two_sided(chain.by_expiration[part.expiration]):
            return part
        key: Tuple[str, date] = (chain.symbol, part.expiration)
        try:
            contracts = await self._expiries.get(key, lambda: self._load_expiry(quoted, part.expiration))
        except Exception as exc:  # noqa: BLE001 — the one-sided expiry is still worth sending
            logger.warning("refetch of %s %s failed: %s", chain.symbol, part.expiration, type(exc).__name__)
            return part
        if not _two_sided(contracts):
            return part
        if chain.estimated_at is not None:
            contracts = [
                estimate_contract(c, quoted.underlying_price, chain.underlying_price, quoted_at(quoted.as_of), chain.estimated_at)
                for c in contracts
            ]
        move = implied_move_pct(contracts, chain.underlying_price)
        return replace(
            part,
            contracts=_near(contracts, chain.underlying_price),
            expirations=[
                replace(e, implied_move_pct=move) if e.date == part.expiration else e
                for e in part.expirations
            ],
        )

    async def _load_expiry(self, chain: OptionChain, expiration: date) -> List[OptionContract]:
        rows = await self._client.fetch_option_chain(chain.symbol, expiration)
        parsed = parse_chain(chain.symbol, rows, chain.underlying_price)
        return parsed.by_expiration.get(expiration, []) if parsed is not None else []

    async def _load(self, sym: str) -> OptionChain:
        down = self._provider_down.peek(sym)
        if down is not None:
            raise OptionsUnavailable(NOT_AVAILABLE, down)
        try:
            rows = await self._client.fetch_option_chain(sym)
        except Exception as exc:  # noqa: BLE001 — any provider failure is "not available"
            # An httpx error's text includes the request URL, which holds the
            # API key. Log the kind of failure; a provider message is safe.
            detail = str(exc) if isinstance(exc, AlphaVantageError) else type(exc).__name__
            logger.warning("option chain for %s failed: %s", sym, detail)
            raise self._down(sym) from None
        if not rows:
            raise self._none(sym)
        as_of = _latest_date(rows)
        price = await self._close_on(sym, as_of)
        if price is None:
            raise self._down(sym)
        chain = parse_chain(sym, rows, price)
        if chain is None:
            raise self._none(sym)
        return chain

    async def _close_on(self, sym: str, as_of: Optional[date]) -> Optional[float]:
        """The stock's closing price on the day the option prices are from.

        The live quote is the fallback: right after the close it is that same
        price, and during the next session it is the best there is.
        """
        try:
            bars = await self._client.fetch_daily_adjusted(sym, outputsize="compact")
            on_or_before = [b for b in bars if as_of is None or b["trading_date"] <= as_of]
            if on_or_before:
                close = float(on_or_before[-1]["close"])
                if close > 0:
                    return close
        except Exception as exc:  # noqa: BLE001 — fall through to the live quote
            logger.info("daily close for %s failed (%s); using the live quote", sym, type(exc).__name__)
        quote = await live_quote_service.get_quote(sym)
        return quote.price if quote is not None and quote.price > 0 else None

    def _none(self, sym: str) -> OptionsUnavailable:
        message = f"There are no listed options for {sym}."
        self._no_options.put(sym, message)
        return OptionsUnavailable(NO_OPTIONS, message)

    def _down(self, sym: str) -> OptionsUnavailable:
        message = "Option prices are not available right now. Try again in a minute."
        self._provider_down.put(sym, message)
        return OptionsUnavailable(NOT_AVAILABLE, message)


def _latest_date(rows: List[dict]) -> Optional[date]:
    latest: Optional[date] = None
    for row in rows:
        try:
            priced_on = date.fromisoformat(str(row.get("date", "")))
        except ValueError:
            continue
        latest = priced_on if latest is None else max(latest, priced_on)
    return latest


option_chain_service = OptionChainService()
