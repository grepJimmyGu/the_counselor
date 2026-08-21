"""Slice 3 is READ-ONLY, and this test is what makes that structural.

The SnapTrade SDK exposes order placement — `/trade/place`, `/trade/impact`,
`/accounts/{id}/trading/*`, and a whole `client.trading` group. Placing
orders is a different regulatory question from publishing: it is the piece
that needs counsel and probably a registered partner (§6.6 of
build_specs/daily_path_v1.md), and it must not become reachable because
somebody reached for the nearest SDK method while doing something else.

A comment saying "read-only" would not survive that. A failing build does.

If you are here because this test went red: that is the point. Placing
orders is not a code review question, it is a legal one. Do not relax this
to land a feature.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

# Method names and paths that transact. Drawn from the SDK's own surface
# (snaptrade_client/paths/__init__.py), not guessed.
FORBIDDEN = [
    r"\.trading\b",
    r"place_order",
    r"place_force_order",
    r"trade/place",
    r"trade/impact",
    r"get_order_impact",
    r"cancel_user_account_order",
    r"place_bracket_order",
    r"replace_order",
    r"preview_order",
]

_PATTERN = re.compile("|".join(FORBIDDEN))

# This file names the forbidden calls in order to forbid them.
_ALLOWED = {"test_snaptrade_readonly_guard.py"}


def _python_sources():
    for path in APP.rglob("*.py"):
        if path.name in _ALLOWED:
            continue
        yield path


def test_no_application_code_can_place_a_brokerage_order():
    offenders = []
    for path in _python_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # A comment explaining what we deliberately do NOT call is the
            # documentation this rule depends on; only real calls count.
            if stripped.startswith("#"):
                continue
            if _PATTERN.search(line):
                offenders.append(f"{path.relative_to(APP.parent)}:{lineno}: {stripped}")

    assert not offenders, (
        "Application code references a SnapTrade TRADING surface. Slice 3 is "
        "read-only; order placement needs counsel and probably a registered "
        "partner before any of this ships.\n  " + "\n  ".join(offenders)
    )


def test_the_guard_would_actually_catch_something():
    """A guard that cannot fail is decoration. This proves the pattern
    matches a real trading call, so a green result above means the codebase
    is clean rather than the regex being broken."""
    assert _PATTERN.search("api.trading.place_force_order(...)")
    assert _PATTERN.search("client.trading.get_order_impact(x)")
    assert not _PATTERN.search("api.account_information.get_all_account_positions(...)")


def test_the_service_exposes_no_write_helpers():
    """Read the module's public surface directly, so adding a transacting
    helper fails here even if it avoids every string above."""
    from app.services import snaptrade_service

    public = {n for n in dir(snaptrade_service) if not n.startswith("_")}
    forbidden_names = {
        n for n in public
        if any(v in n.lower() for v in ("place", "order", "trade_", "buy", "sell", "cancel"))
    }
    assert not forbidden_names, (
        f"snaptrade_service exposes what look like transacting helpers: "
        f"{sorted(forbidden_names)}"
    )
