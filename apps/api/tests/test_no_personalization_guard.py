"""Connected-account data must not reach anything that produces a signal.

THE DISTINCTION THIS PROTECTS. Livermore ships under the publisher's
exclusion (Lowe v. SEC, 1985), which covers IMPERSONAL publication.

Since slice 3 we can read a user's brokerage holdings — so the old
disclaimer sentence "we do not know your financial situation" became false.
But knowing is not the thing that breaks the exclusion. TAILORING is. The
line is whether what a user sees varies because of what they own, and today
it does not: broker data comes in through `snaptrade_service`, gets
displayed back through its own routes, and touches nothing that generates a
screen, a backtest or a signal.

WHY THIS IS A TEST AND NOT A NOTE. The temptation is real and it sounds
like a good product idea — "rank the screen by what they already own",
"hide names they can't afford", "size the suggestion to their account".
Each is a plausible ticket, and the moment one ships the exclusion argument
gets much harder to make. A note in a spec does not survive that. A failing
build does.

If you are here because this went red: you are about to make Livermore's
output depend on an individual's finances. That is a securities question,
not a code review question. Do not relax this to land a feature.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# Where output is PRODUCED. If broker data reaches any of these, what a user
# sees can start varying by what they hold.
SIGNAL_PATHS = [
    APP / "services" / "screener",
    APP / "services" / "backtester",
    APP / "jobs",
    APP / "services" / "signal_service.py",
    APP / "services" / "fundamental_service.py",
    APP / "services" / "exit_ladder.py",
]

# Anything that carries a user's real holdings.
_BROKER = re.compile(
    r"\bsnaptrade\w*\b|\bSnapTrade\w*\b|\bBrokerPosition\b",
    re.IGNORECASE,
)


def _sources():
    for target in SIGNAL_PATHS:
        if target.is_file():
            yield target
        elif target.is_dir():
            for path in target.rglob("*.py"):
                yield path


def test_no_signal_path_reads_connected_account_data():
    offenders = []
    for path in _sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # A comment explaining that we deliberately do NOT read broker
            # data is the documentation this rule depends on.
            if stripped.startswith("#"):
                continue
            if _BROKER.search(line):
                offenders.append(
                    f"{path.relative_to(APP.parent)}:{lineno}: {stripped}"
                )

    assert not offenders, (
        "A signal-producing path references connected-account data. That "
        "would make Livermore's output vary with an individual's holdings, "
        "which is the thing the publisher's exclusion does not cover — "
        "knowing someone's finances is fine, tailoring to them is not.\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_would_actually_catch_something():
    """A guard that cannot fail is decoration. This proves the pattern
    matches a real import, so a green result above means the codebase is
    clean rather than the regex being broken."""
    assert _BROKER.search("from app.services import snaptrade_service as st")
    assert _BROKER.search("positions: list[BrokerPosition] = []")
    assert not _BROKER.search("from app.services.exit_ladder import evaluate_bar")


def test_the_guard_is_actually_looking_at_files():
    """If SIGNAL_PATHS ever goes stale — a directory renamed, a service
    moved — this test would pass by scanning nothing at all. Pin that it
    reads a real, non-trivial number of sources."""
    assert len(list(_sources())) > 10
