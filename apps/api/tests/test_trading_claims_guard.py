"""What the product says about trading must stay true when trading is ON.

CONTEXT. `SNAPTRADE_TRADING_ENABLED` defaults to False, and for as long as it
was off the product could truthfully say "Livermore does not place trades."
The day it flips, that sentence becomes false — and it was sitting in ten
places, including the landing-page hero, the sign-in trust note, and the
order ticket that carries the Place Order button. The ticket would have
contradicted itself at the exact moment someone transacted.

The fix was not to make the copy conditional on the flag. Copy that changes
meaning when an operator toggles an env var is copy nobody can reason about,
and the flag can move in either direction. Every claim below is now phrased
to be TRUE IN BOTH STATES:

    "Livermore never places an order you haven't approved"
    "no order goes out unless you send it"
    "No automated trading"

And each is STRUCTURALLY ENFORCED rather than promised:

  - `place_order` accepts only a trade id produced by a preview the user saw
    priced. There is no route taking a symbol and a quantity.
  - `place_force_order` — the no-preview path — is banned outright.
  - Nothing under `jobs/` may reach a trading call, so nothing on a timer can
    place an order.

`test_snaptrade_readonly_guard.py` keeps those three true. This file keeps
the product's description of them true.

If you are here because this went red: you have reintroduced a claim that
is false whenever order placement is enabled. That is not a copy nitpick —
it is the product telling a user it will not do something it is about to do.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = [
    ROOT / "apps" / "api" / "app",
    ROOT / "apps" / "web" / "src",
]

# Claims that are false the moment `SNAPTRADE_TRADING_ENABLED` is true.
_BANNED = {
    "does not place trades": (
        "Livermore does place trades once the flag is on — the user presses "
        "Place and the backend transmits the order. Say what stays true: "
        "\"never places an order you haven't approved\"."
    ),
    "doesn't place trades": "Same as \"does not place trades\".",
    "no live trading": (
        "There IS live trading when the flag is on. \"No automated trading\" "
        "is the claim that survives, and the readonly guard enforces it."
    ),
    "we never trade": "Ambiguous once trading is on — say who initiates.",
    "无实盘交易": "The CN equivalent of \"no live trading\".",
}

# The two files that DOCUMENT this history in a comment. Allowlisted by path
# and read explicitly rather than by a comment-syntax heuristic, which would
# quietly excuse a real claim that happened to sit in a JSX comment block.
_ALLOW = {
    ROOT / "apps" / "web" / "src" / "app" / "page.tsx",
}

_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md"}


def _sources():
    for root in SCAN_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in _EXTS:
                continue
            if "__tests__" in path.parts or path.name.endswith((".test.tsx", ".test.ts")):
                continue
            if path.name.startswith("test_"):
                continue
            yield path


def test_no_claim_that_becomes_false_when_trading_is_enabled() -> None:
    offenders = []
    for path in _sources():
        if path in _ALLOW:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lowered = text.lower()
        for phrase, why in _BANNED.items():
            if phrase in lowered:
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if phrase in line.lower():
                        rel = path.relative_to(ROOT)
                        offenders.append(f"  {rel}:{lineno}\n      {line.strip()[:100]}\n      → {why}")
                        break

    assert not offenders, (
        "Copy that becomes false when order placement is enabled:\n\n"
        + "\n".join(offenders)
        + "\n\nSee this file's docstring. Phrase the claim so it is true in "
        "BOTH states, and prefer claims the API structurally enforces."
    )


def test_the_replacement_claims_are_actually_present() -> None:
    """A ban alone would be satisfied by saying nothing at all.

    The user-facing promise has to still exist — the point was to make it
    accurate, not to delete it. Pin the surfaces where it must appear.
    """
    web = ROOT / "apps" / "web" / "src"
    required = {
        web / "components" / "notifications" / "exit-ticket.tsx":
            r"never places an order",
        web / "components" / "notifications" / "not-investment-advice-footer.tsx":
            r"never places an order",
        web / "components" / "notifications" / "unresolved-exits.tsx":
            r"no order goes out unless you send it",
        web / "app" / "page.tsx":
            r"No automated trading",
    }
    missing = [
        str(p.relative_to(ROOT))
        for p, pattern in required.items()
        if not (p.exists() and re.search(pattern, p.read_text(encoding="utf-8"), re.I))
    ]
    assert not missing, (
        "The accurate claim disappeared from: " + ", ".join(missing)
        + ". Removing the promise is not the fix — making it true was."
    )
