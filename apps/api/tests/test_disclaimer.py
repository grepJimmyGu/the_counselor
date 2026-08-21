"""The disclaimer is the one piece of copy whose entire value is that it is
true. These tests pin the parts that carry legal weight and the parts §11
forbids.
"""

from __future__ import annotations

from app.services.disclaimer import FULL, SHORT, SHORT_CORE, SHORT_DIGEST


def _positions_of(haystack: str, needle: str):
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i == -1:
            return
        yield i
        start = i + 1


def test_REGRESSION_it_does_not_claim_we_cannot_see_holdings():
    """§11's original text said "we do not know your financial situation".
    Since slice 3 that is FALSE — a connected brokerage account is exactly
    that knowledge. A disclaimer containing a false statement is worse than
    an awkward one."""
    assert "do not know your financial situation" not in FULL


def test_it_states_the_thing_that_actually_carries_the_weight():
    """The publisher's exclusion covers IMPERSONAL publication. Knowing a
    user's holdings does not break it; TAILORING output to them does. So
    the load-bearing claim is not "we can't see" but "we don't use it" —
    which `test_no_personalization_guard.py` enforces rather than asserts."""
    assert "do not use them to change what any strategy tells you" in FULL


def test_it_says_livermore_never_transacts():
    assert "does not place trades" in SHORT
    assert "never places, cancels or modifies an order" in FULL


def test_neither_form_uses_language_section_11_forbids():
    """"advice" is permitted ONLY in the negated construction ("not
    investment advice"); the recommending register never is."""
    for text in (SHORT, SHORT_DIGEST, FULL):
        low = text.lower()
        assert "we recommend" not in low
        assert "you should" not in low
        assert "best for your portfolio" not in low
        assert "advised allocation" not in low
        # "advice" is allowed ONLY when negated. §11 forbids the word in
        # any context referring to Livermore's own output, so every
        # occurrence must sit inside a "not ..." construction — both
        # "not investment advice" and "not personalized investment advice"
        # qualify; a bare "our advice" would not.
        for idx in _positions_of(low, "advice"):
            window = low[max(0, idx - 40):idx]
            assert "not " in window, (
                f"'advice' at {idx} is not negated: ...{low[max(0, idx-40):idx+7]}"
            )


def test_the_short_form_is_short_enough_to_actually_be_read():
    """A disclaimer nobody reads protects nobody. The short form appears
    inline on signals and tickets."""
    assert len(SHORT) < 260


def test_the_full_form_still_covers_the_required_ground():
    low = FULL.lower()
    for required in [
        "not a registered investment adviser",
        "hypothetical",
        "past performance",
        "loss of principal",
        "licensed financial advisor",
    ]:
        assert required in low, f"missing required disclosure: {required}"


# ── the email templates must not drift from the canonical text ─────────────


def _squash(s: str) -> str:
    """Compare substance, not line wrapping — the text and HTML variants
    wrap differently and both are legitimate."""
    return " ".join(s.split())


def test_every_email_footer_matches_the_canonical_short_form():
    """`signal_change`, `position_event` and `daily_digest` each hardcode
    this footer. They agree today; three copies of a compliance string is
    exactly the shape that drifts, and a footer that drifts is one that
    stops being reviewed.

    Not refactored into an import, deliberately: the templates render
    correct text today and rewriting three working email bodies to remove
    duplication is a bigger change than pinning it.
    """
    from pathlib import Path

    canonical = _squash(SHORT_CORE)
    emails = Path(__file__).resolve().parents[1] / "app" / "emails"
    checked = 0
    for name in ("signal_change.py", "position_event.py", "daily_digest.py"):
        body = _squash((emails / name).read_text(encoding="utf-8"))
        assert canonical in body, (
            f"{name} no longer contains the canonical short disclaimer. "
            f"If the wording changed, change app/services/disclaimer.py and "
            f"every template together."
        )
        checked += 1
    assert checked == 3
