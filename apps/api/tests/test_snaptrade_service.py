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
