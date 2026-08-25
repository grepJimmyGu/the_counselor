"""A strategy's exit ladder may only be set by a request that carried it.

PRD-28 §2.2. Founder decision, 2026-08-21: saving a strategy and placing an
order both require explicit user sign-off, and NEITHER may depend on a
developer remembering to render a confirmation dialog.

Order placement already had that property structurally — `place_order` takes
only a trade id produced by a preview, so an order can only ever be one the
user saw priced (`test_snaptrade_readonly_guard.py` keeps it that way). This
file gives the other half the same property.

WHY A STOP IS WORTH THIS MUCH CEREMONY
An exit ladder is the rule that decides when someone's real position gets
sold. A stop the user did not choose is one they will not believe when it
fires — they will override it, at the worst possible moment, because it
feels like something the app did to them rather than something they decided.
So the ladder that lands on a strategy must be one the user was shown.

The enforcement is not "call the confirm dialog". It is that the ONLY way to
write `risk_management.exit_ladder` onto an existing SavedStrategy is an
endpoint whose request body is the ladder itself. The server has no path
that invents one — no default-applier, no ATR-deriver, no template-copier.
So whatever lands was sent by a client, and a client can only send what it
rendered.

TWO THINGS THIS DELIBERATELY DOES NOT BAN

  1. Setting a ladder at CREATE time. A strategy saved from the composer
     carries whatever ladder the user built in the editor, and that arrived
     in the same request. The rule is about mutating a strategy that already
     exists — that is the case where a user could find their stop changed
     without having asked.

  2. READING the ladder. The backtester, the monitor and the dashboard all
     read it constantly. Reading is the point.

If you are here because this went red: you have added a way for a stop to
change without the person it belongs to choosing it. That is not a code
review question.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# The one module allowed to write a ladder onto an existing strategy.
_LADDER_OWNER = APP / "api" / "routes" / "saved_strategies.py"

# Assignment into a ladder key — `x["exit_ladder"] = ...`, `risk["exit_ladder"] =`,
# `.exit_ladder = ...`. Reads (`get("exit_ladder")`, `["exit_ladder"]` in an
# expression) are untouched: this matches only assignment.
_LADDER_WRITE = re.compile(
    r"""(?x)
    (
      \[ \s* ['"]exit_ladder['"] \s* \]      # ["exit_ladder"]
      |
      \. exit_ladder                          # .exit_ladder
    )
    \s* = (?!=)                               # assignment, not ==
    """
)

_SELF = "test_exit_ladder_signoff_guard.py"


def _sources():
    for path in APP.rglob("*.py"):
        yield path


def _offending_lines(path: Path):
    out = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if _LADDER_WRITE.search(line):
            out.append((lineno, stripped))
    return out


def test_only_the_attach_endpoint_writes_a_ladder_onto_a_strategy() -> None:
    """The structural half of the sign-off.

    Every `exit_ladder` assignment in app code must live in the module that
    owns the attach endpoint. Anywhere else is a path by which a user's stop
    changes without them being asked.
    """
    offenders = {}
    for path in _sources():
        if path == _LADDER_OWNER:
            continue
        hits = _offending_lines(path)
        if hits:
            offenders[path.relative_to(APP)] = hits

    assert not offenders, (
        "exit_ladder is assigned outside the attach endpoint:\n"
        + "\n".join(
            f"  app/{p}:{ln}  {src}"
            for p, hits in offenders.items()
            for ln, src in hits
        )
        + "\n\nPRD-28 §2.2: a ladder may only reach a saved strategy through "
        "POST /api/saved-strategies/{id}/exit-ladder, whose body IS the "
        "ladder. If this is a new legitimate surface, it should call that "
        "endpoint rather than write the field."
    )


def test_the_attach_endpoint_has_no_server_side_default() -> None:
    """The other half — the endpoint must not be able to invent a ladder.

    A ban on writing the field elsewhere is worth nothing if the endpoint
    itself will happily apply `DEFAULT_EXIT_LADDER` when the payload omits
    one. The seed is computed and displayed CLIENT-side (`ladderFromNatr`),
    precisely so the user sees the numbers before they are saved.
    """
    src = _LADDER_OWNER.read_text()
    # The KB's default lives in `template_signal_metadata`. The attach path
    # must not reach for it.
    assert "DEFAULT_EXIT_LADDER" not in src, (
        "saved_strategies.py references DEFAULT_EXIT_LADDER. The attach "
        "endpoint must never supply a ladder the user did not send — a "
        "server-chosen stop is exactly the one they will not believe."
    )


def test_the_request_model_requires_the_ladder() -> None:
    """A missing `exit_ladder` must be a validation error, not a default.

    Pydantic makes this easy to get wrong: `exit_ladder: list = []` looks
    harmless and silently turns "the client forgot" into "save an empty
    ladder". Assert the field is genuinely required.
    """
    from app.api.routes.saved_strategies import AttachExitLadderRequest

    field = AttachExitLadderRequest.model_fields["exit_ladder"]
    assert field.is_required(), (
        "AttachExitLadderRequest.exit_ladder has a default. It must be "
        "required so that omitting it is a 422 rather than a silent write."
    )
