"""Our SnapTrade calls must match the SDK that is actually installed.

TRAP #14, and this integration has already been bitten by it THREE times:

  - `get_user_account_positions` was written from memory. The real name is
    `get_all_account_positions`. Caught by reading the wheel.
  - `SnapTrade(client_id=..., consumer_key=...)` — the constructor ACCEPTS
    both kwargs and then raises `TypeError`. It needs
    `auth=SnapTradeAuth.commercial_api_key(...)`. That one would have failed
    on the first real Connect click and was invisible to every test, because
    every test injects a `MagicMock` client.
  - `api.trading.symbol_search_user_account` — the method is real, the
    SECTION was wrong. It lives on `reference_data`. Caught by this file
    on the day trading was about to be switched on; it is the first call
    `preview_order` makes, so every Place click would have AttributeError'd.

That is the whole problem: mocking the client means a wrong method name or a
renamed kwarg passes the entire suite and fails on the first real call. The
order path in particular — `symbol_search_user_account` → `get_order_impact`
→ `place_order` — has never executed against the live API, so nothing but
this file stands between a typo and a user's first Place click.

SKIPS when the SDK is not importable, so local runs are unaffected; CI
installs `snaptrade-python-sdk` from requirements.txt and runs it for real.
Same pattern as `test_postgres_migrations.py` skipping without `PG_TEST_URL`.
"""

from __future__ import annotations

import inspect

import pytest

snaptrade_client = pytest.importorskip(
    "snaptrade_client",
    reason="snaptrade-python-sdk not installed locally; runs in CI",
)


def _params(method) -> set:
    """Keyword names a bound SDK method accepts."""
    try:
        sig = inspect.signature(method)
    except (TypeError, ValueError):  # pragma: no cover - C-level callables
        pytest.skip("signature not introspectable for this SDK build")
    names = set(sig.parameters)
    # Generated clients often take **kwargs; that would make any assertion
    # here vacuous, so say so rather than passing silently.
    if any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    ):
        pytest.skip("SDK method accepts **kwargs — signature check is vacuous")
    return names


@pytest.fixture(scope="module")
def api():
    """A client built exactly the way `snaptrade_service._client` builds one.

    Constructed with throwaway credentials and never called — this is a
    signature check, not a network test. Building it the same way is the
    point: the constructor shape is one of the two things that has already
    been wrong.
    """
    from snaptrade_client import SnapTrade
    from snaptrade_client.auth import SnapTradeAuth

    return SnapTrade(
        auth=SnapTradeAuth.commercial_api_key(
            consumer_key="test-consumer-key", client_id="test-client-id",
        )
    )


# Every SDK call `snaptrade_service` makes, with the kwargs it passes.
CALLS = [
    ("authentication", "register_snap_trade_user", {"user_id"}),
    ("authentication", "login_snap_trade_user", {"user_id", "user_secret"}),
    ("account_information", "list_user_accounts", {"user_id", "user_secret"}),
    ("account_information", "get_all_account_positions",
     {"user_id", "user_secret", "account_id"}),
    # `reference_data`, NOT `trading` — see `resolve_symbol_id`. Written as
    # a trading call because it reads like one; it is an AttributeError on
    # the first preview any user runs.
    ("reference_data", "symbol_search_user_account",
     {"user_id", "user_secret", "account_id", "substring"}),
    # `units` for a sell, `notional_value` for a buy — the service sends
    # exactly one. Both are pinned: a buy that reached production with a
    # renamed notional kwarg would fail on the first purchase anyone makes.
    ("trading", "get_order_impact",
     {"user_id", "user_secret", "account_id", "action", "universal_symbol_id",
      "order_type", "time_in_force", "units", "notional_value", "price"}),
    ("trading", "place_order", {"user_id", "user_secret", "trade_id"}),
    # The account reads. Same discipline: these were written from the SDK's
    # own surface, and this asserts they still match it.
    # `offset` added PRD-43a slice 1. It is the whole pagination fix, so it
    # is pinned here against the real SDK rather than only against a mock —
    # a MagicMock would have agreed with any name I invented.
    ("account_information", "get_account_activities",
     {"user_id", "user_secret", "account_id", "start_date", "end_date",
      "limit", "offset"}),
    ("account_information", "get_user_account_orders",
     {"user_id", "user_secret", "account_id", "days"}),
    ("account_information", "get_user_account_return_rates",
     {"user_id", "user_secret", "account_id"}),
    ("account_information", "get_account_balance_history",
     {"user_id", "user_secret", "account_id"}),
]


@pytest.mark.parametrize("group,method,kwargs", CALLS)
def test_the_method_exists_and_takes_the_kwargs_we_send(
    api, group: str, method: str, kwargs: set,
) -> None:
    section = getattr(api, group, None)
    assert section is not None, (
        f"SnapTrade client has no `{group}` section. `snaptrade_service` calls "
        f"`api.{group}.{method}(...)` and would AttributeError on the first "
        "real request."
    )
    fn = getattr(section, method, None)
    assert fn is not None, (
        f"`{group}.{method}` does not exist in the installed SDK. This is the "
        "`get_user_account_positions` mistake again — check the wheel for the "
        "real name rather than trusting the docs or memory."
    )
    accepted = _params(fn)
    unknown = kwargs - accepted
    assert not unknown, (
        f"`{group}.{method}` does not accept {sorted(unknown)}. "
        f"It accepts {sorted(accepted)}. Every test in this repo injects a "
        "MagicMock client, so a renamed kwarg passes the whole suite and "
        "fails on the first real call."
    )


def test_the_literals_we_send_are_the_ones_the_sdk_defines() -> None:
    """`order_type="Market"` and `time_in_force="Day"` are exact strings.

    `"MARKET"` or `"DAY"` would be rejected by the API, and the failure
    would land on a user pressing Place — the single moment in this product
    where an error costs them something. `preview_order`'s defaults are
    pinned here against the SDK's own enums.
    """
    from app.api.routes.snaptrade import PreviewOrderRequest

    defaults = PreviewOrderRequest.model_fields
    assert defaults["order_type"].default == "Market"
    assert defaults["time_in_force"].default == "Day"

    try:
        from snaptrade_client.type.order_type_strict import OrderTypeStrict
        from snaptrade_client.type.time_in_force_strict import TimeInForceStrict
    except ImportError:  # pragma: no cover - SDK layout changed
        pytest.skip("SDK enum modules moved; update this test's imports")

    assert "Market" in str(OrderTypeStrict), (
        "The SDK no longer spells it 'Market'. Read the enum and update "
        "`PreviewOrderRequest`'s default to match exactly."
    )
    assert "Day" in str(TimeInForceStrict), (
        "The SDK no longer spells it 'Day'. Read the enum and update "
        "`PreviewOrderRequest`'s default to match exactly."
    )
