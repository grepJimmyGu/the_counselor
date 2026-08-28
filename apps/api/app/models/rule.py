"""PRD-43e §3.1 — a Rule: the smallest systematic decision a user can hold.

The intermediate object the packet was missing. Before it, a lens finding's
only next step was the composer — a surface that presumes you think in
universes, Boolean conditions and sizing functions. That leap loses almost
everyone, and the finding evaporates when the tab closes.

TWO FIELDS CARRY THE HONESTY, and both were added after the first live run:

**`scope`** — `behavioural` or `mechanical`. A behavioural rule is a claim
about what the user has been doing ("stop entering oversold", N=8, 0 winners);
its evidence is their own record and it is COMPLETE at `saved`. A mechanical
rule claims a systematic edge, for which the user's record is only the
hypothesis. A ladder whose sole endpoint is validation discards its own best
output — the oversold finding will never pass walk-forward and is still the
most actionable thing the product has said to this user.

**`status`** — `discovered → saved → tested`, and deliberately **no
`validated`**. Validation belongs to the Playbook, not the rule. A Playbook is
a conjunction, and 43d measures the whole thing; when it passes, the evidence
attaches to the combination. Any individual rule inside might be inert, might
be doing all the work, or might be actively harmful and outvoted. Marking each
member validated would let a user lift a rule into a different Playbook
carrying a credential it never earned.

`included_in_validated_playbook` exists for exactly that reason: it is
PROVENANCE — "used in 'Momentum Pullback', which validated on 2026-09-14" is a
true statement about where a rule has been. It must never render as a
checkmark on the rule, sort as if it were a validation, or gate anything.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

RULE_TYPES = ("selection", "entry", "sizing", "exit", "portfolio")
RULE_SCOPES = ("behavioural", "mechanical")
RULE_STATUSES = ("discovered", "saved", "tested")
RULE_SOURCES = (
    "user", "trade_analysis", "stock_analysis", "allocation_analysis",
)


class Rule(Base):
    """Note: `user_id` is intentionally NOT a FOREIGN KEY — trap #1. Production
    `users.id` may exist as UUID, and Postgres rejects FK constraints between
    mismatched types. App layer enforces identity, as everywhere else."""

    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    rule_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="mechanical",
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Provenance. Nullable for a hand-written rule, and that is not a defect —
    # "why is this rule in my Playbook?" simply answers "you wrote it."
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="user",
    )
    source_analysis_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    historical_effect: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="saved", index=True,
    )
    # "tested_on_personal_record" or None. Never a market-validation claim —
    # this column describes a population, and the two must not merge.
    evidence: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Playbook ids. PROVENANCE ONLY (see the module docstring).
    included_in_validated_playbook: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )
