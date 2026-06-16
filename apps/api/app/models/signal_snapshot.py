"""Signal snapshot — the Market Screener's pre-warmed primitive cache (PRD-23a §3.2).

One row per (symbol, primitive_id, resolution): the *latest* value of a
catalog primitive for a universe symbol, computed once/day by the warm cron
from cached `price_bars` — NEVER a live AV/FMP fetch (§3.3).

Why pre-warm primitives (not rules): any composed reading is then a cheap
boolean filter over this in-memory frame (scan, §3.5), so the expensive
rank-by-backtest only ever runs on the matched subset (≪ universe). The
daily snapshot covers the ~52 locally-computable price primitives — the same
set the custom_build engine can backtest synchronously; fundamentals /
AV-endpoint technicals are a documented follow-up (a slower fundamental
snapshot), excluded here because they'd require the forbidden live fetch.

`value` stores exactly what `BacktestEngine._apply_rule_threshold` consumes
at the last bar — the raw last value of `provider._compute(frame)` — so the
scan filter (which reuses that evaluator) is byte-identical to the backtest.
Encoding by `output_kind` follows from the provider's emitted shape:
VALUE→scalar, EVENT→0/1 fired, LEVEL→0/1 bool, REGIME→category code,
DISTANCE→signed pct, CROSS→the provider's emitted state.

No FK to users — this is a universe-level cache, not user-scoped. Created via
`Base.metadata.create_all` (checkfirst, idempotent / Postgres-safe) like the
other ORM-backed tables (signal_events, position_state, price_bars).
"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import String, Float, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SignalSnapshot(Base):
    __tablename__ = "signal_snapshot"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    primitive_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 'daily' now; 'intraday' lands in PRD-23c. Part of the PK so a symbol can
    # hold one row per primitive per resolution.
    resolution: Mapped[str] = mapped_column(String(8), primary_key=True, default="daily")
    # Only finite, computed values are ever persisted — un-computable cells
    # get NO row (no fabricated placeholders; the scan treats a missing cell
    # as "does not match"). Hence NOT NULL.
    value: Mapped[float] = mapped_column(Float, nullable=False)
    # The latest cached bar's date this value was computed at (visible
    # freshness stamp — trap #20 / "date stamps must be visible").
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
