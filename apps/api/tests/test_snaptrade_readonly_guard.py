"""Order placement is allowed. TWO things about it are not.

CONTRACT CHANGE, stated openly per CLAUDE.md. This file previously asserted
that NO application code could reach a SnapTrade trading endpoint at all
(slice 3 was read-only). Order placement is now a deliberate product
decision, so a blanket ban would be wrong — it would just get deleted the
first time someone needed it, taking the useful invariants with it.

What replaces it are the two rules that actually protect a user, and both
are stronger than "don't trade":

  1. NO ORDER WITHOUT A PREVIEW THE USER SAW.
     SnapTrade's `place_force_order` (POST /trade/place) sends an order with
     no impact check. The supported path is `get_order_impact` -> a trade
     id -> `place_order(trade_id)`, so the only way to place anything is to
     have first priced it. `place_force_order` is banned outright: it is
     the one call that can put an order in the market without the user
     having seen what it costs.

  2. NO AUTOMATIC ORDERS.
     Trading calls may appear ONLY in the service that owns them and the
     routes that expose them. Not in `jobs/` — nothing on a timer may place
     an order — and not in the screener, backtester or signal paths. Every
     order must originate in a request a person made.

If you are here because this went red: adding a trading call to a cron, or
reaching for `place_force_order` to skip a round-trip, changes what this
product does to people's money without anyone deciding to. That is not a
code review question.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# The only two files permitted to call a trading endpoint.
_TRADING_OWNERS = {
    APP / "services" / "snaptrade_service.py",
    APP / "api" / "routes" / "snaptrade.py",
}

# Banned everywhere, including the owners above.
_FORCE = re.compile(r"place_force_order|trade/place\b")

# Allowed, but only in the owners.
_TRADING = re.compile(
    r"\.trading\b|place_order|get_order_impact|place_complex_order"
    r"|place_crypto_order|place_mleg_order|replace_order|cancel_order"
)

_SELF = "test_snaptrade_readonly_guard.py"


def _sources():
    for path in APP.rglob("*.py"):
        yield path


def _code_lines(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        yield lineno, line, stripped


def test_nothing_can_place_an_order_the_user_never_saw_priced():
    """`place_force_order` skips the impact check. The whole confirmation
    guarantee rests on a trade id being obtainable only from a preview, and
    this call routes around that."""
    offenders = []
    for path in _sources():
        if path.name == _SELF:
            continue
        for lineno, line, stripped in _code_lines(path):
            if _FORCE.search(line):
                offenders.append(f"{path.relative_to(APP.parent)}:{lineno}: {stripped}")

    assert not offenders, (
        "Code reaches SnapTrade's force-order path, which places an order "
        "with no impact preview. Use get_order_impact -> place_order so the "
        "user sees the cost before anything is sent.\n  " + "\n  ".join(offenders)
    )


def test_only_the_designated_service_and_routes_can_trade_at_all():
    """No automatic orders. A trading call in `jobs/` would mean something
    on a timer can move real money with nobody in the loop."""
    offenders = []
    for path in _sources():
        if path.name == _SELF or path in _TRADING_OWNERS:
            continue
        for lineno, line, stripped in _code_lines(path):
            if _TRADING.search(line):
                offenders.append(f"{path.relative_to(APP.parent)}:{lineno}: {stripped}")

    assert not offenders, (
        "A trading call appears outside snaptrade_service.py and its routes. "
        "Every order must originate in a request a person made — nothing on "
        "a schedule, and nothing in a signal path.\n  " + "\n  ".join(offenders)
    )


def test_no_job_or_cron_imports_the_trading_service():
    """Belt and braces for the rule above: even importing the module into a
    scheduled path is a step toward automatic execution."""
    offenders = []
    for path in (APP / "jobs").rglob("*.py"):
        for lineno, line, stripped in _code_lines(path):
            if "snaptrade" in line.lower():
                offenders.append(f"{path.relative_to(APP.parent)}:{lineno}: {stripped}")
    assert not offenders, (
        "A scheduled job references SnapTrade. Orders must never be placed "
        "by a timer.\n  " + "\n  ".join(offenders)
    )


def test_the_guards_would_actually_catch_something():
    """Guards that cannot fail are decoration."""
    assert _FORCE.search("api.trading.place_force_order(...)")
    assert _TRADING.search("api.trading.place_order(trade_id=t)")
    assert _TRADING.search("client.trading.get_order_impact(x)")
    assert not _TRADING.search("api.account_information.get_all_account_positions(...)")


def test_the_guard_is_actually_reading_files():
    """If `app/` moved, every test above would pass by scanning nothing."""
    assert len(list(_sources())) > 50
