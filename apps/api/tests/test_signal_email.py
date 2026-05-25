"""Stage 8 v0 Phase B — signal-alert email template.

Covers spec §10 #4 (email shape) and #11 (CAN-SPAM compliance) by asserting
the rendered subject/body/html contain the required strings. Doesn't exercise
Resend — `email_service.send_email` is a separate concern, already covered
by Stage 6a tests.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.emails.signal_alert import CAN_SPAM_ADDRESS, render_signal_alert


def _mk_user(display_name: str = "Alex") -> SimpleNamespace:
    return SimpleNamespace(id="u-1", email="alex@example.com", display_name=display_name)


def _mk_strategy(title: str = "200-day MA on NVDA") -> SimpleNamespace:
    return SimpleNamespace(id="s-1", title=title)


def _mk_event(
    *,
    change_type: str,
    previous_signal: dict | None,
    previous_display: str | None,
    new_signal: dict,
    new_display: str,
    prices: dict | None = None,
    as_of: date = date(2026, 5, 25),
) -> SimpleNamespace:
    return SimpleNamespace(
        change_type=change_type,
        previous_signal=previous_signal,
        previous_signal_display=previous_display,
        new_signal=new_signal,
        new_signal_display=new_display,
        as_of_date=as_of,
        reference_price_snapshot=prices,
    )


# ── Subject line shape (spec §7 + §10 #4) ───────────────────────────────────


def test_subject_flip_to_cash_includes_sell_and_ticker() -> None:
    event = _mk_event(
        change_type="flip_to_cash",
        previous_signal={"position": "long", "ticker": "NVDA"},
        previous_display="Hold NVDA",
        new_signal={"position": "cash"},
        new_display="In cash",
    )
    rendered = render_signal_alert(
        _mk_user(), _mk_strategy(), event,
        single_unsub_url="https://x/single", all_unsub_url="https://x/all",
    )
    assert rendered["subject"] == "Your saved strategy signaled SELL NVDA"


def test_subject_flip_to_long_includes_buy_and_ticker() -> None:
    event = _mk_event(
        change_type="flip_to_long",
        previous_signal={"position": "cash"},
        previous_display="In cash",
        new_signal={"position": "long", "ticker": "QQQ"},
        new_display="Hold QQQ",
    )
    rendered = render_signal_alert(
        _mk_user(), _mk_strategy(), event,
        single_unsub_url="https://x/single", all_unsub_url="https://x/all",
    )
    assert rendered["subject"] == "Your saved strategy signaled BUY QQQ"


def test_subject_rotation_has_no_ticker() -> None:
    event = _mk_event(
        change_type="rotation",
        previous_signal={"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "SLV", "weight": 0.5}]},
        previous_display="Top 2: GLD (50%), SLV (50%)",
        new_signal={"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "PLAT", "weight": 0.5}]},
        new_display="Top 2: GLD (50%), PLAT (50%)",
    )
    rendered = render_signal_alert(
        _mk_user(), _mk_strategy(), event,
        single_unsub_url="https://x/single", all_unsub_url="https://x/all",
    )
    assert rendered["subject"] == "Your saved strategy rotated holdings"


# ── Required content (spec §10 #4 + #11) ────────────────────────────────────


def test_body_includes_required_disclaimer() -> None:
    """Spec §11 — signal alert email body must include the publisher's-exclusion
    disclaimer. Both text and HTML versions carry it."""
    event = _mk_event(
        change_type="flip_to_cash",
        previous_signal={"position": "long", "ticker": "NVDA"},
        previous_display="Hold NVDA",
        new_signal={"position": "cash"},
        new_display="In cash",
    )
    rendered = render_signal_alert(
        _mk_user(), _mk_strategy(), event,
        single_unsub_url="https://x/single", all_unsub_url="https://x/all",
    )
    for field in ("html", "text"):
        body = rendered[field]
        assert "not investment advice" in body.lower()
        assert "past performance" in body.lower()


def test_body_includes_both_unsub_links() -> None:
    """Spec §10 #11 + §5.4 — every email carries both per-strategy and all-signals
    unsubscribe links."""
    event = _mk_event(
        change_type="flip_to_long",
        previous_signal={"position": "cash"},
        previous_display="In cash",
        new_signal={"position": "long", "ticker": "AAPL"},
        new_display="Hold AAPL",
    )
    rendered = render_signal_alert(
        _mk_user(), _mk_strategy(), event,
        single_unsub_url="https://livermorealpha.com/api/email/signal-unsub?token=SINGLE_TOKEN",
        all_unsub_url="https://livermorealpha.com/api/email/signal-unsub?token=ALL_TOKEN",
    )
    for field in ("html", "text"):
        body = rendered[field]
        assert "SINGLE_TOKEN" in body
        assert "ALL_TOKEN" in body


def test_body_includes_can_spam_physical_address() -> None:
    """Spec §10 #11 — CAN-SPAM requires a physical mailing address in every
    marketing email."""
    event = _mk_event(
        change_type="flip_to_cash",
        previous_signal={"position": "long", "ticker": "NVDA"},
        previous_display="Hold NVDA",
        new_signal={"position": "cash"},
        new_display="In cash",
    )
    rendered = render_signal_alert(
        _mk_user(), _mk_strategy(), event,
        single_unsub_url="https://x/single", all_unsub_url="https://x/all",
    )
    for field in ("html", "text"):
        assert CAN_SPAM_ADDRESS in rendered[field]


def test_body_includes_previous_new_and_as_of_date() -> None:
    """Spec §7 body contract — previous, now, as_of date all visible to the user."""
    event = _mk_event(
        change_type="rebalance",
        previous_signal={"holdings": [{"ticker": "SPY", "weight": 0.6}]},
        previous_display="Top 1: SPY (60%)",
        new_signal={"holdings": [{"ticker": "SPY", "weight": 0.7}]},
        new_display="Top 1: SPY (70%)",
        as_of=date(2026, 6, 1),
    )
    rendered = render_signal_alert(
        _mk_user(), _mk_strategy("Risk-parity SPY/TLT"), event,
        single_unsub_url="https://x/single", all_unsub_url="https://x/all",
    )
    for field in ("html", "text"):
        body = rendered[field]
        assert "Top 1: SPY (60%)" in body
        assert "Top 1: SPY (70%)" in body
        assert "2026-06-01" in body
        assert "Risk-parity SPY/TLT" in body
