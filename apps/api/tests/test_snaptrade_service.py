"""SnapTrade read-only service (slice 3).

Covers the two things that would be expensive to get wrong: the per-user
secret is never stored in the clear, and the feature refuses to operate
rather than degrading when it is not configured.

Every SnapTrade call is injected, so nothing here touches the network.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.models.snaptrade_user import SnapTradeUser
from app.services import snaptrade_service as st


@pytest.fixture
def configured(monkeypatch):
    """A fully-configured feature with a throwaway Fernet key."""
    key = Fernet.generate_key().decode()
    s = st.get_settings()
    monkeypatch.setattr(s, "snaptrade_client_id", "cid", raising=False)
    monkeypatch.setattr(s, "snaptrade_consumer_key", "ckey", raising=False)
    monkeypatch.setattr(s, "snaptrade_encryption_key", key, raising=False)
    return key


def _api(**overrides) -> MagicMock:
    api = MagicMock()
    api.authentication.register_snap_trade_user.return_value = {
        "userId": "u1", "userSecret": "SECRET-VALUE",
    }
    api.authentication.login_snap_trade_user.return_value = {
        "redirectURI": "https://app.snaptrade.com/connect/abc123",
    }
    api.account_information.list_user_accounts.return_value = [{"id": "acct-1"}]
    api.account_information.get_all_account_positions.return_value = [{
        "symbol": {"symbol": {"symbol": "NVDA"}},
        "units": 120, "average_purchase_price": 118.40,
        "price": 108.93, "open_pnl": -1136.4,
    }]
    for k, v in overrides.items():
        setattr(api, k, v)
    return api


# ── configuration ───────────────────────────────────────────────────────────


def test_reports_unconfigured_when_env_is_absent(monkeypatch):
    s = st.get_settings()
    monkeypatch.setattr(s, "snaptrade_client_id", "", raising=False)
    assert st.is_configured() is False


def test_configuration_is_all_or_nothing(monkeypatch, configured):
    """Two of three is not "mostly working" — without the encryption key
    the only way to proceed would be storing a brokerage credential in the
    clear, which is worse than the feature being off."""
    s = st.get_settings()
    monkeypatch.setattr(s, "snaptrade_encryption_key", "", raising=False)
    assert st.is_configured() is False


def test_refuses_to_build_a_client_when_unconfigured(monkeypatch):
    s = st.get_settings()
    monkeypatch.setattr(s, "snaptrade_client_id", "", raising=False)
    with pytest.raises(st.SnapTradeNotConfigured):
        st._client()


# ── the secret ──────────────────────────────────────────────────────────────


def test_secret_round_trips(configured):
    token = st.encrypt_secret("SECRET-VALUE")
    assert token != "SECRET-VALUE"
    assert st.decrypt_secret(token) == "SECRET-VALUE"


def test_REGRESSION_the_stored_secret_is_never_plaintext(
    make_user, db: Session, configured
) -> None:
    """The whole reason for the encrypted column. `userSecret` cannot be
    re-derived — it IS the user's identity to SnapTrade — so it must be
    stored, and a credential to somebody's brokerage connection should be
    useless to anyone who gets a copy of the database."""
    user = make_user(email="st-secret@test.com")
    row = st.register_user(db, user.id, client=_api())

    stored = db.get(SnapTradeUser, row.id)
    assert "SECRET-VALUE" not in stored.user_secret_encrypted
    assert st.decrypt_secret(stored.user_secret_encrypted) == "SECRET-VALUE"


# ── registration ────────────────────────────────────────────────────────────


def test_registration_is_idempotent(make_user, db: Session, configured) -> None:
    """Re-registering would issue a NEW userSecret and orphan every
    connection the user had already authorised — the old secret stops
    working and their brokers silently detach."""
    user = make_user(email="st-idem@test.com")
    api = _api()
    first = st.register_user(db, user.id, client=api)
    second = st.register_user(db, user.id, client=api)

    assert first.id == second.id
    assert api.authentication.register_snap_trade_user.call_count == 1


def test_registration_without_a_secret_raises(make_user, db: Session, configured):
    """A registration we cannot store is not a registration. Better to
    fail loudly than to persist a row whose secret is empty and discover it
    at the first read."""
    user = make_user(email="st-nosecret@test.com")
    api = _api()
    api.authentication.register_snap_trade_user.return_value = {"userId": "u1"}
    with pytest.raises(RuntimeError):
        st.register_user(db, user.id, client=api)


# ── connect + read ──────────────────────────────────────────────────────────


def test_connect_returns_the_portal_url(make_user, db: Session, configured):
    user = make_user(email="st-connect@test.com")
    url = st.connection_portal_url(db, user.id, client=_api())
    assert url.startswith("https://")


def test_positions_map_to_what_declare_position_needs(
    make_user, db: Session, configured
) -> None:
    """The point of the integration. `declare_position` requires symbol,
    shares and entry price; the broker supplies all three, so the manual
    entry that gated the execution loop disappears rather than merely
    getting easier."""
    user = make_user(email="st-pos@test.com")
    api = _api()
    st.register_user(db, user.id, client=api)

    rows = st.list_positions(db, user.id, client=api)
    assert len(rows) == 1
    assert rows[0].symbol == "NVDA"
    assert rows[0].units == 120
    assert rows[0].average_purchase_price == pytest.approx(118.40)


def test_a_broken_account_does_not_lose_the_others(
    make_user, db: Session, configured
) -> None:
    """A user with three brokers connected should not lose sight of all of
    them because one is having a bad morning."""
    user = make_user(email="st-partial@test.com")
    api = _api()
    api.account_information.list_user_accounts.return_value = [
        {"id": "bad"}, {"id": "good"},
    ]
    calls = {"n": 0}

    def _flaky(**kwargs):
        calls["n"] += 1
        if kwargs.get("account_id") == "bad":
            raise RuntimeError("upstream 500")
        return [{
            "symbol": {"symbol": {"symbol": "MSFT"}},
            "units": 10, "average_purchase_price": 400.0,
        }]

    api.account_information.get_all_account_positions.side_effect = _flaky
    st.register_user(db, user.id, client=api)

    rows = st.list_positions(db, user.id, client=api)
    assert [r.symbol for r in rows] == ["MSFT"]
    assert calls["n"] == 2


def test_positions_are_empty_for_an_unregistered_user(
    make_user, db: Session, configured
) -> None:
    user = make_user(email="st-unreg@test.com")
    assert st.list_positions(db, user.id, client=_api()) == []


def test_a_malformed_symbol_drops_one_row_not_the_read(
    make_user, db: Session, configured
) -> None:
    """SnapTrade nests the ticker three levels deep. A shape change upstream
    should cost one position, not the user's whole portfolio view."""
    user = make_user(email="st-badsym@test.com")
    api = _api()
    api.account_information.get_all_account_positions.return_value = [
        {"symbol": None, "units": 5},
        {"symbol": {"symbol": {"symbol": "AAPL"}}, "units": 7,
         "average_purchase_price": 200.0},
    ]
    st.register_user(db, user.id, client=api)

    rows = st.list_positions(db, user.id, client=api)
    assert [r.symbol for r in rows] == ["AAPL"]


def test_a_successful_read_stamps_last_synced(
    make_user, db: Session, configured
) -> None:
    """So the UI can say how fresh the data is rather than implying it is
    live."""
    user = make_user(email="st-sync@test.com")
    api = _api()
    reg = st.register_user(db, user.id, client=api)
    assert reg.last_synced_at is None

    st.list_positions(db, user.id, client=api)
    assert st.get_registration(db, user.id).last_synced_at is not None


# ── the construction the mocks can't cover ──────────────────────────────────


def test_the_real_sdk_client_constructs(configured):
    """Every other test here injects a client, so none of them exercise the
    ONE line that talks to the SDK's constructor — and that line is easy to
    get wrong in a way nothing catches.

    `SnapTrade(...)` accepts `client_id=` and `consumer_key=` as kwargs and
    then raises TypeError telling you to pass them through `auth`. The
    natural-looking call therefore compiles, passes every mocked test, and
    fails the first time a real user clicks Connect.

    Skipped locally when the SDK isn't installed; CI installs
    requirements.txt, so there it actually runs.
    """
    pytest.importorskip("snaptrade_client")
    client = st._client()
    # The groups this service uses must exist on the constructed client.
    assert hasattr(client, "authentication")
    assert hasattr(client, "account_information")


def test_personal_mode_is_selectable(monkeypatch, configured):
    """Which factory applies depends on the SnapTrade plan behind the key.
    Getting it wrong should be an env-var flip, not a redeploy."""
    pytest.importorskip("snaptrade_client")
    s = st.get_settings()
    monkeypatch.setattr(s, "snaptrade_auth_mode", "personal", raising=False)
    assert st._client() is not None


# ── order placement (slice 4c) ──────────────────────────────────────────────


@pytest.fixture
def trading(monkeypatch, configured):
    monkeypatch.setattr(
        st.get_settings(), "snaptrade_trading_enabled", True, raising=False
    )
    return configured


def _trading_api() -> MagicMock:
    # SECTION CORRECTED 2026-08-23, openly per CLAUDE.md. These mocks were
    # set up on `api.trading.symbol_search_user_account`, matching the
    # service — and BOTH were wrong. The method lives on `reference_data`.
    #
    # A MagicMock answers to any attribute you ask it for, so the mock
    # agreed with the mistake and the whole file passed. That is the exact
    # blind spot `test_snaptrade_sdk_contract.py` now covers: it checks
    # every call against the REAL installed SDK rather than against a mock
    # built from the same assumption as the code.
    api = _api()
    api.reference_data.symbol_search_user_account.return_value = [
        {"id": "usym-nvda", "symbol": "NVDA", "description": "NVIDIA Corp"},
    ]
    api.trading.get_order_impact.return_value = {
        "trade": {"id": "trade-1"},
        "estimated_commission": 0.0,
        "remaining_cash": 4200.0,
    }
    api.trading.place_order.return_value = {
        "status": "EXECUTED", "brokerage_order_id": "bk-9",
    }
    return api


def test_REGRESSION_trading_is_off_unless_explicitly_enabled(
    make_user, db: Session, configured
) -> None:
    """Reading holdings and sending orders are different decisions.
    Merging the code must not turn trading on — the flag defaults False and
    is separate from the read-only configuration."""
    user = make_user(email="t-off@test.com")
    assert st.is_trading_enabled() is False
    with pytest.raises(st.TradingDisabled):
        st.preview_order(
            db, user.id, account_id="a1", ticker="NVDA", action="BUY",
            units=1, client=_trading_api(),
        )


def test_preview_prices_the_order_and_returns_a_trade_id(
    make_user, db: Session, trading
) -> None:
    user = make_user(email="t-preview@test.com")
    api = _trading_api()
    st.register_user(db, user.id, client=api)

    out = st.preview_order(
        db, user.id, account_id="a1", ticker="NVDA", action="BUY",
        units=10, client=api,
    )
    assert out["trade_id"] == "trade-1"
    assert out["remaining_cash"] == 4200.0
    # Nothing was sent.
    api.trading.place_order.assert_not_called()


def test_REGRESSION_symbol_resolution_requires_an_EXACT_ticker(
    make_user, db: Session, trading
) -> None:
    """SnapTrade's search is a substring match: "NV" returns NVDA, NVR and
    NVAX. Placing an order against a closest match to save the user a tap
    is not a mistake worth risking."""
    user = make_user(email="t-exact@test.com")
    api = _trading_api()
    api.reference_data.symbol_search_user_account.return_value = [
        {"id": "usym-nvr", "symbol": "NVR"},
        {"id": "usym-nvax", "symbol": "NVAX"},
    ]
    st.register_user(db, user.id, client=api)

    with pytest.raises(RuntimeError, match="not tradable"):
        st.preview_order(
            db, user.id, account_id="a1", ticker="NVDA", action="BUY",
            units=1, client=api,
        )


def test_place_takes_only_a_trade_id(make_user, db: Session, trading) -> None:
    """The signature is the guarantee: there is no way to pass a symbol and
    a quantity to the placing function, so no caller can assemble an order
    and send it in one motion."""
    import inspect

    params = set(inspect.signature(st.place_previewed_order).parameters)
    assert "trade_id" in params
    for forbidden in ("units", "ticker", "symbol", "action", "price"):
        assert forbidden not in params


def test_placing_sends_the_previewed_trade(make_user, db: Session, trading) -> None:
    user = make_user(email="t-place@test.com")
    api = _trading_api()
    st.register_user(db, user.id, client=api)

    out = st.place_previewed_order(db, user.id, "trade-1", client=api)
    assert out["status"] == "EXECUTED"
    _, kwargs = api.trading.place_order.call_args
    assert kwargs["trade_id"] == "trade-1"


def test_preview_rejects_nonsense_before_it_reaches_the_broker(
    make_user, db: Session, trading
) -> None:
    user = make_user(email="t-valid@test.com")
    api = _trading_api()
    st.register_user(db, user.id, client=api)

    for bad in ({"units": 0}, {"units": -5}, {"action": "HODL"}):
        kwargs = {"account_id": "a1", "ticker": "NVDA", "action": "BUY", "units": 1}
        kwargs.update(bad)
        with pytest.raises(ValueError):
            st.preview_order(db, user.id, client=api, **kwargs)
    api.trading.get_order_impact.assert_not_called()


def test_a_preview_with_no_trade_id_is_an_error_not_a_silent_pass(
    make_user, db: Session, trading
) -> None:
    """Without a trade id there is nothing to place. Returning a preview
    that cannot be executed would strand the user at the confirm step."""
    user = make_user(email="t-notrade@test.com")
    api = _trading_api()
    api.trading.get_order_impact.return_value = {"estimated_commission": 0.0}
    st.register_user(db, user.id, client=api)

    with pytest.raises(RuntimeError, match="no trade id"):
        st.preview_order(
            db, user.id, account_id="a1", ticker="NVDA", action="BUY",
            units=1, client=api,
        )


# ── the return path (open-redirect guard) ───────────────────────────────────


def test_a_plain_path_becomes_a_url_on_our_own_origin(configured):
    url = st.return_url_for("/flow/portfolio_mode?connected=1")
    assert url.endswith("/flow/portfolio_mode?connected=1")
    assert url.startswith("http")


@pytest.mark.parametrize("hostile", [
    "https://evil.com/steal",
    "http://evil.com",
    "//evil.com",
    "///evil.com",
    "\\\\evil.com",
    "javascript:alert(1)",
    "/legit\nLocation: https://evil.com",
])
def test_REGRESSION_a_hostile_return_target_never_leaves_our_origin(
    hostile, configured
):
    """`custom_redirect` is where SnapTrade sends a real person immediately
    after we asked them to trust us with a brokerage login. If a caller
    could pass a full URL, that is an open redirect at the single most
    sensitive moment in the product.

    The guard DISCARDS rather than sanitises — half-cleaning a hostile input
    is how this bug class survives review.
    """
    url = st.return_url_for(hostile)
    assert "evil.com" not in url
    assert not url.startswith("javascript:")
    assert "\n" not in url and "\r" not in url


def test_no_path_returns_the_site_root(configured):
    assert st.return_url_for(None).startswith("http")
    assert st.return_url_for("").startswith("http")


def test_the_portal_url_carries_the_return_target(
    make_user, db: Session, configured
) -> None:
    """Without it the user lands wherever SnapTrade defaults to, which for
    someone halfway through the portfolio flow means losing their place
    right after doing the most trust-demanding thing we ask of them."""
    user = make_user(email="st-return@test.com")
    api = _api()
    st.connection_portal_url(
        db, user.id, return_path="/flow/portfolio_mode?connected=1", client=api,
    )
    _, kwargs = api.authentication.login_snap_trade_user.call_args
    assert kwargs["custom_redirect"].endswith("/flow/portfolio_mode?connected=1")


# ── buys are sized in dollars (PRD-41 §8.6) ─────────────────────────────────


def test_a_buy_is_sized_in_dollars_not_shares(make_user, db: Session, configured, trading):
    """`notional_value` goes to SnapTrade natively.

    A sell is sized in shares — you sell what you hold. A buy answers "how
    much of my money", and converting that to a share count ourselves means
    rounding, a stale price, and a number on the ticket that differs from
    what the broker fills. SnapTrade takes the dollar amount directly.
    """
    user = make_user(email="st-notional@test.com")
    api = _trading_api()
    st.register_user(db, user.id, client=api)

    st.preview_order(
        db, user.id, account_id="acct-1", ticker="NVDA",
        action="BUY", notional=2000.0, client=api,
    )
    kwargs = api.trading.get_order_impact.call_args.kwargs
    assert kwargs["notional_value"] == 2000.0
    assert "units" not in kwargs, (
        "sent both a share count and a dollar amount — SnapTrade takes one, "
        "and sending both lets the ticket display one and transmit the other"
    )
    assert kwargs["action"] == "BUY"


def test_a_sell_still_goes_by_share_count(make_user, db: Session, configured, trading):
    user = make_user(email="st-units@test.com")
    api = _trading_api()
    st.register_user(db, user.id, client=api)

    st.preview_order(
        db, user.id, account_id="acct-1", ticker="NVDA",
        action="SELL", units=120, client=api,
    )
    kwargs = api.trading.get_order_impact.call_args.kwargs
    assert kwargs["units"] == 120
    assert "notional_value" not in kwargs


def test_sending_both_sizes_is_refused(make_user, db: Session, configured, trading):
    """The ambiguity is the danger: which one would the broker honour?"""
    user = make_user(email="st-both@test.com")
    api = _trading_api()
    st.register_user(db, user.id, client=api)
    with pytest.raises(ValueError, match="exactly one"):
        st.preview_order(
            db, user.id, account_id="acct-1", ticker="NVDA",
            action="BUY", units=10, notional=2000.0, client=api,
        )


def test_sending_neither_size_is_refused(make_user, db: Session, configured, trading):
    user = make_user(email="st-neither@test.com")
    api = _trading_api()
    st.register_user(db, user.id, client=api)
    with pytest.raises(ValueError, match="exactly one"):
        st.preview_order(
            db, user.id, account_id="acct-1", ticker="NVDA",
            action="BUY", client=api,
        )


def test_accounts_are_listed_so_a_buy_can_choose_one(
    make_user, db: Session, configured,
) -> None:
    """A SELL learns its account from the position being sold. A BUY cannot —
    you do not own the thing yet — so the account list has to be reachable on
    its own, including for a user whose brokerage account is still empty.
    """
    from app.api.routes.snaptrade import snaptrade_accounts

    user = make_user(email="st-accts@test.com")
    api = _api()
    api.account_information.list_user_accounts.return_value = [
        {"id": "acct-1", "name": "Roth", "number": "…8821",
         "institution_name": "Schwab"},
        {"name": "no id — unaddressable"},
    ]
    st.register_user(db, user.id, client=api)

    with patch.object(st, "_client", return_value=api):
        rows = snaptrade_accounts(current_user=user, db=db)

    assert len(rows) == 1, "an account with no id is not an option we can offer"
    assert rows[0].id == "acct-1"
    assert rows[0].institution_name == "Schwab"


# ── the account as the broker sees it (PRD-42) ──────────────────────────────


def _account_api() -> MagicMock:
    api = _api()
    api.account_information.get_account_activities.return_value = {"data": [
        {"id": "a1", "type": "BUY", "symbol": {"symbol": {"symbol": "NVDA"}},
         "units": 10, "price": 118.40, "amount": -1184.0, "fee": 0.0,
         "currency": {"code": "USD"}, "trade_date": "2026-08-20",
         "settlement_date": "2026-08-22", "description": "Bought 10 NVDA"},
        {"id": "a2", "type": "DIVIDEND", "symbol": {"symbol": {"symbol": "KO"}},
         "amount": 42.10, "trade_date": "2026-07-15"},
    ]}
    api.account_information.get_user_account_orders.return_value = [
        {"brokerage_order_id": "o1", "status": "EXECUTED", "symbol": "NVDA"},
    ]
    api.account_information.get_user_account_return_rates.return_value = {
        "data": [{"timeframe": "1Y", "rate_of_return": 0.184}]}
    api.account_information.get_account_balance_history.return_value = {
        "data": [{"date": "2026-08-01", "value": 41200.0}]}
    return api


def test_activities_carry_what_a_person_means_by_when_i_bought_it(
    make_user, db: Session, configured,
) -> None:
    """`trade_date` is when it happened. `settlement_date` is days later and
    is not the answer to "when did I buy this" — both are kept, and the
    consumer picks."""
    user = make_user(email="acct-act@test.com")
    api = _account_api()
    st.register_user(db, user.id, client=api)

    rows = st.list_activities(db, user.id, client=api)
    buy = next(r for r in rows if r.type == "BUY")
    assert buy.symbol == "NVDA"
    assert buy.units == 10 and buy.price == 118.40
    assert buy.trade_date == "2026-08-20"
    assert buy.settlement_date == "2026-08-22"
    assert buy.currency == "USD"


def test_activities_come_back_newest_first(make_user, db: Session, configured):
    user = make_user(email="acct-order@test.com")
    api = _account_api()
    st.register_user(db, user.id, client=api)
    dates = [r.trade_date for r in st.list_activities(db, user.id, client=api)]
    assert dates == sorted(dates, reverse=True)


def test_a_date_window_is_passed_through_not_filtered_here(
    make_user, db: Session, configured,
) -> None:
    """The broker does the filtering. Pulling everything and slicing locally
    would page through years to show a month."""
    user = make_user(email="acct-window@test.com")
    api = _account_api()
    st.register_user(db, user.id, client=api)

    st.list_activities(
        db, user.id, start_date="2026-08-01", end_date="2026-08-31", client=api,
    )
    kwargs = api.account_information.get_account_activities.call_args.kwargs
    assert kwargs["start_date"] == "2026-08-01"
    assert kwargs["end_date"] == "2026-08-31"


def test_a_bare_list_body_is_accepted_as_well_as_a_paginated_one(
    make_user, db: Session, configured,
) -> None:
    """SnapTrade returns {"data": [...]} on the paginated endpoints and a
    bare list on others. Handling only one shape would silently return
    nothing for the other."""
    user = make_user(email="acct-shape@test.com")
    api = _account_api()
    api.account_information.get_account_activities.return_value = [
        {"id": "b1", "type": "SELL", "symbol": {"symbol": {"symbol": "MSFT"}},
         "units": 5, "trade_date": "2026-08-19"},
    ]
    st.register_user(db, user.id, client=api)
    rows = st.list_activities(db, user.id, client=api)
    assert len(rows) == 1 and rows[0].type == "SELL"


def test_one_bad_account_does_not_lose_the_others_history(
    make_user, db: Session, configured,
) -> None:
    """Same rule as positions: three brokers connected, one having a bad
    morning, and the user still sees the other two."""
    user = make_user(email="acct-partial@test.com")
    api = _account_api()
    api.account_information.list_user_accounts.return_value = [
        {"id": "bad"}, {"id": "good"},
    ]

    def _flaky(**kw):
        if kw.get("account_id") == "bad":
            raise RuntimeError("upstream 500")
        return {"data": [{"id": "x", "type": "BUY",
                          "symbol": {"symbol": {"symbol": "AAPL"}},
                          "trade_date": "2026-08-18"}]}

    api.account_information.get_account_activities.side_effect = _flaky
    st.register_user(db, user.id, client=api)
    rows = st.list_activities(db, user.id, client=api)
    assert [r.symbol for r in rows] == ["AAPL"]


def test_performance_is_the_brokers_number_not_ours(
    make_user, db: Session, configured,
) -> None:
    """We do not see deposits and withdrawals, and a return computed without
    them would be worse than one passed through."""
    user = make_user(email="acct-perf@test.com")
    api = _account_api()
    st.register_user(db, user.id, client=api)
    rows = st.get_return_rates(db, user.id, client=api)
    assert rows[0]["timeframe"] == "1Y"
    assert rows[0]["rate_of_return"] == 0.184
    assert rows[0]["account_id"] == "acct-1"


def test_orders_and_balance_history_read(make_user, db: Session, configured):
    user = make_user(email="acct-misc@test.com")
    api = _account_api()
    st.register_user(db, user.id, client=api)
    assert st.list_recent_orders(db, user.id, client=api)[0]["status"] == "EXECUTED"
    assert st.get_balance_history(db, user.id, client=api)[0]["value"] == 41200.0


def test_an_unregistered_user_reads_empty_rather_than_erroring(
    make_user, db: Session, configured,
) -> None:
    user = make_user(email="acct-unreg@test.com")
    api = _account_api()
    assert st.list_activities(db, user.id, client=api) == []
    assert st.get_return_rates(db, user.id, client=api) == []
    assert st.get_balance_history(db, user.id, client=api) == []
