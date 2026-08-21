"""The compliance disclaimer — one canonical source.

§11 of build_specs/research_execution_v0_signals_and_alerts.md specified
this text and it was never implemented; what actually shipped was the short
footer in the email templates. This module is that single source, so the
wording cannot drift between an email, a page footer and a modal.

WHAT CHANGED FROM THE SPEC'S ORIGINAL, AND WHY. The spec's text said:

    "We do not know your financial situation, investment objectives, or
     risk tolerance"

Since slice 3 that is FALSE — a user can connect a brokerage account and we
read their holdings. Shipping a disclaimer containing a false statement is
worse than shipping an awkward one: it is the one piece of copy whose whole
value is that it is true.

The replacement says the thing that IS true and that actually carries the
legal weight:

    "We can see the holdings you choose to connect. We do not use them to
     change what any strategy tells you."

That distinction is the hinge. The publisher's exclusion (Lowe v. SEC,
1985) covers IMPERSONAL publication. Knowing someone's finances does not
break it; TAILORING output to them does. Today nothing does — enforced by
`tests/test_no_personalization_guard.py`, not merely asserted here — so
this sentence is accurate and stays accurate by construction.

The spec says to have a securities lawyer bless the final wording before
launch. That still applies, and applies MORE to this version, because the
change is substantive rather than cosmetic.
"""

# The invariant core. Every surface says exactly this, word for word — it
# is the part that carries the compliance weight and it must not vary.
SHORT_CORE = (
    "Not investment advice. Past performance does not guarantee future "
    "results. Livermore does not place trades on your behalf."
)

# The closing sentence legitimately varies with context: a single alert
# says "this signal", a digest covering several says "any signal". That
# difference is correct rather than drift, so the invariant above stops
# short of it — a test pinning the whole string would have forced the
# digest into saying something slightly wrong about its own contents.
SHORT = SHORT_CORE + " You decide whether to act on this signal."
SHORT_DIGEST = SHORT_CORE + " You decide whether to act on any signal."

# The full text, for the expandable "read full disclaimer" surfaces.
FULL = (
    "Research only — not investment advice. Livermore publishes algorithmic "
    "signals from quantitative strategies you choose to follow. The signals, "
    "performance data, and any references to securities are educational "
    "research, not personalized investment advice. Livermore is not a "
    "registered investment adviser, broker-dealer, or financial planner.\n\n"
    "We can see the holdings you choose to connect through a brokerage "
    "connection. We do not use them to change what any strategy tells you — "
    "every strategy reports the same signal to every user who follows it, "
    "and nothing you own alters it. We do not know your investment "
    "objectives or risk tolerance, and we are not making recommendations to "
    "you personally.\n\n"
    "Livermore never places, cancels or modifies an order on your behalf. "
    "Backtested performance is hypothetical and depends on the selected "
    "period, price data, and strategy assumptions. Past performance does "
    "not guarantee future results. Trading involves substantial risk "
    "including loss of principal. Consult a licensed financial advisor "
    "before making investment decisions."
)
