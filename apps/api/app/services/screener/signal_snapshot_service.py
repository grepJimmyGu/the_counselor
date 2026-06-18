"""SignalSnapshotService — pre-warm + read the screener's primitive cache (PRD-23a §3.3-3.5).

Computes the latest value of every *locally-computable price* primitive for a
universe symbol from cached `price_bars` (NO live AV/FMP fetch), and reads
those values back as an in-memory frame the scan filters over.

Fidelity contract (why the scan == the backtest): the stored value is exactly
what `BacktestEngine._apply_rule_threshold` consumes at the last bar — the raw
last finite value of `provider._compute(frame)`, where `frame` is built the
same way the engine builds it (close = adjusted_close; real OHLV/volume). The
scan (slice 3) re-wraps the stored scalar into a 1-element Series and calls the
SAME evaluator, so a screen match is byte-identical to the backtest's signal on
the snapshot date.

Scope: the ~52 primitives whose provider is a local `TechnicalSignalProvider`
(not an AV-endpoint one) — exactly the set the custom_build engine can backtest
synchronously. AV-endpoint technicals + fundamentals/sentiment are excluded
(they'd need the forbidden live fetch); a fundamental snapshot is a documented
follow-up.

Default parameterization: each primitive is warmed at its catalog-default
params (the "lego brick" default). A rule's operator/threshold still apply at
scan time (RSI < 30 works); only a rule that overrides the *indicator period*
diverges from the snapshot — a documented v1 limitation.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.signal_snapshot import SignalSnapshot

logger = logging.getLogger("livermore.screener.snapshot")

# Wide enough to warm the longest-lookback local primitive (52-week extrema,
# ~252 trading days) at the latest bar, with buffer. get_price_frame fetches
# [end - lookback - 10, end], so ~345 trading days of history.
SNAPSHOT_LOOKBACK_DAYS = 500


# Primitives that are STRUCTURALLY degenerate in the per-symbol snapshot — they
# are locally-computable in principle but evaluate to all-null/all-zero across
# the whole universe, so any scan rule referencing one silently matches 0 with
# no error (the rank_composite_score trap, PRD-24a §6 / PR #234, which shipped
# matching 0/525 until a live curl caught it). Excluding them here drops them
# from the warmed + scannable vocabulary, so such a rule reports as
# `unsupported` (explicit) instead of silently empty. Grow this set as the
# warm-time coverage audit (see `compute_snapshot_coverage` + the warning
# `warm_universe` logs) surfaces more.
#
# - rank_composite_score: a cross-sectional composite rank; the snapshot warms
#   each symbol in isolation, so the per-symbol computation has no peer set and
#   the provider returns 0 for every symbol → an always-0 column.
DEGENERATE_SNAPSHOT_PRIMITIVE_IDS: frozenset = frozenset({"rank_composite_score"})


# Provider/primitive pairing for the snapshot-able set. A pair is one
# (catalog primitive, its stateless provider at default params). Providers are
# pure over `_compute(frame)`, so a single instance is reused across all
# symbols.
ProviderPair = Tuple[object, object]


@lru_cache(maxsize=1)
def local_price_providers() -> Tuple[ProviderPair, ...]:
    """The (primitive, provider) pairs the daily snapshot covers: local
    `TechnicalSignalProvider`s only (not AV-endpoint, not fundamental)."""
    from app.data.signal_primitives import SIGNAL_PRIMITIVES
    from app.services.backtester.signal_provider import get_signal_provider
    from app.services.backtester.technical_signal_providers import (
        AVTechnicalSignalProvider,
        TechnicalSignalProvider,
    )

    pairs: List[ProviderPair] = []
    for primitive in SIGNAL_PRIMITIVES:
        if primitive.id in DEGENERATE_SNAPSHOT_PRIMITIVE_IDS:
            # Known all-null/all-zero in the per-symbol snapshot — never warm
            # or advertise it as scannable (would silently match 0 in a preset).
            continue
        provider = get_signal_provider(primitive.provider_impl)
        if isinstance(provider, TechnicalSignalProvider) and not isinstance(
            provider, AVTechnicalSignalProvider
        ):
            pairs.append((primitive, provider))
    return tuple(pairs)


def snapshot_primitive_ids() -> List[str]:
    """The primitive ids covered by the daily snapshot (introspection / tests)."""
    return [p.id for p, _ in local_price_providers()]


@dataclass
class SnapshotFrame:
    """An in-memory view of the snapshot for a set of symbols.

    `frame`: index = symbol, columns = primitive_id, cell = stored value
    (NaN where a symbol has no row for that primitive — a *null cell* the scan
    must exclude from any referencing rule, never treat as a real value).
    `as_of_date`: the freshest snapshot date among the rows (visible stamp).
    """

    frame: pd.DataFrame
    as_of_date: Optional[date]


def _engine_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the OHLCV frame the way `BacktestEngine` feeds providers: close =
    adjusted_close (so close-based indicators match the backtest exactly), with
    real open/high/low/volume."""
    close = raw["adjusted_close"]
    return pd.DataFrame(
        {
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": close,
            "adjusted_close": close,
            "volume": raw["volume"],
        }
    )


def _last_bar_value(series: Optional[pd.Series]) -> Optional[float]:
    """The value at the LITERAL last bar (None if it's NaN / non-finite).

    Deliberately NOT "last non-NaN value": the backtest's `_apply_rule_threshold`
    reads the final bar and treats NaN as no-signal (`accumulator.fillna(False)`).
    So if the last bar is NaN (e.g. a stochastic's denominator-zero on a frozen/
    halted window), we must store NO value — the scan's null-cell guard then
    excludes the symbol exactly as the backtest would, instead of false-matching
    on a stale-but-finite earlier bar. Never fabricate."""
    if series is None or len(series) == 0:
        return None
    value = float(series.iloc[-1])
    return value if math.isfinite(value) else None


def compute_values_from_frame(
    frame: Optional[pd.DataFrame],
    providers: Optional[Sequence[ProviderPair]] = None,
) -> Tuple[Dict[str, float], Optional[date]]:
    """PURE core: a price frame -> {primitive_id: latest value} + as_of_date.

    Only finite values are returned (un-computable primitives are omitted — no
    null/placeholder rows). `as_of_date` is the latest bar's date, or None if
    the frame is empty.
    """
    if frame is None or frame.empty:
        return {}, None

    pairs = providers if providers is not None else local_price_providers()
    eframe = _engine_frame(frame)
    as_of = pd.Timestamp(eframe.index[-1]).date()

    values: Dict[str, float] = {}
    for primitive, provider in pairs:
        try:
            series = provider._compute(eframe)
        except Exception:
            # One bad primitive must not sink the whole symbol's snapshot.
            logger.exception(
                "signal_snapshot: _compute failed for primitive '%s'", primitive.id
            )
            continue
        value = _last_bar_value(series)
        if value is not None:
            values[primitive.id] = value
    return values, as_of


@dataclass
class PrimitiveCoverage:
    """Per-primitive coverage across a warmed universe (the PRD-24a §6 preset
    gate). A `degenerate` column — all-null, or all-zero across every symbol
    that has a value — can't safely back a scan rule: a threshold over it
    matches 0 (or all) with no error. `constant` (one distinct non-null value)
    is surfaced for review but NOT auto-degenerate, because a legitimately
    one-sided boolean (e.g. every name above its 200-DMA in a strong tape) is
    constant yet real."""

    primitive_id: str
    universe_size: int
    present: int            # symbols with a non-null value
    distinct: int           # distinct non-null values
    zero_fraction: float    # fraction of present values that are exactly 0
    all_null: bool
    all_zero: bool
    constant: bool
    degenerate: bool        # all_null or all_zero — unsafe for a preset rule


def compute_snapshot_coverage(
    frame: Optional[pd.DataFrame], primitive_ids: Sequence[str]
) -> List[PrimitiveCoverage]:
    """Per-primitive coverage over a snapshot frame (index=symbol,
    columns=primitive_id) — pass `get_snapshot(...).frame`. Pure / no DB. A
    primitive with no column or no non-null cell is `all_null`; one whose
    present values are all exactly 0 is `all_zero`; either is `degenerate`."""
    universe = int(frame.shape[0]) if frame is not None and not frame.empty else 0
    out: List[PrimitiveCoverage] = []
    for pid in primitive_ids:
        if frame is None or universe == 0 or pid not in frame.columns:
            out.append(
                PrimitiveCoverage(pid, universe, 0, 0, 0.0, True, False, False, True)
            )
            continue
        col = frame[pid].dropna()
        present = int(col.shape[0])
        if present == 0:
            out.append(
                PrimitiveCoverage(pid, universe, 0, 0, 0.0, True, False, False, True)
            )
            continue
        zeros = int((col == 0).sum())
        distinct = int(col.nunique())
        all_zero = zeros == present
        out.append(
            PrimitiveCoverage(
                primitive_id=pid,
                universe_size=universe,
                present=present,
                distinct=distinct,
                zero_fraction=zeros / present,
                all_null=False,
                all_zero=all_zero,
                constant=distinct <= 1,
                degenerate=all_zero,
            )
        )
    return out


class SignalSnapshotService:
    def __init__(self, price_svc=None) -> None:
        # Lazily import so the service module is importable without dragging the
        # full price stack into unit tests of the pure core.
        if price_svc is None:
            from app.services.price_data_service import PriceDataService

            price_svc = PriceDataService()
        self.price_svc = price_svc

    # ── write path ────────────────────────────────────────────────────────────

    def write_symbol(
        self,
        db: Session,
        symbol: str,
        values: Dict[str, float],
        as_of: date,
        *,
        resolution: str = "daily",
    ) -> int:
        """Idempotent upsert: replace all rows for (symbol, resolution) with the
        freshly computed set. Delete-then-insert so a primitive that stops
        computing loses its (now-stale) row. Flushes; the CALLER commits."""
        symbol = symbol.upper()
        db.execute(
            delete(SignalSnapshot).where(
                SignalSnapshot.symbol == symbol,
                SignalSnapshot.resolution == resolution,
            )
        )
        now = datetime.utcnow()
        db.add_all(
            [
                SignalSnapshot(
                    symbol=symbol,
                    primitive_id=pid,
                    resolution=resolution,
                    value=value,
                    as_of_date=as_of,
                    computed_at=now,
                )
                for pid, value in values.items()
            ]
        )
        db.flush()
        return len(values)

    async def warm_symbol(
        self,
        db: Session,
        symbol: str,
        *,
        resolution: str = "daily",
        as_of: Optional[date] = None,
    ) -> int:
        """Fetch this symbol's cached bars, compute every snapshot primitive's
        latest value, and persist them. Returns the row count written (0 if the
        symbol has no bars — a null/skip, never a fabricated row).

        `resolution="intraday"` sources the frame from the PRD-16c intraday
        bars (FMP ~15-min-delayed) instead of the daily `price_bars`, so the
        SAME providers compute *intraday* indicator values."""
        symbol = symbol.upper()
        if resolution != "daily":
            return await self._warm_symbol_intraday(db, symbol, resolution=resolution)
        end = as_of or date.today()
        frame = await self.price_svc.get_price_frame(
            db, symbol, end, end, lookback_days=SNAPSHOT_LOOKBACK_DAYS
        )
        values, frame_as_of = compute_values_from_frame(frame)
        if frame_as_of is None:
            logger.info("signal_snapshot: '%s' has no cached bars — skipped", symbol)
            return 0
        return self.write_symbol(
            db, symbol, values, frame_as_of, resolution=resolution
        )

    async def _warm_symbol_intraday(
        self,
        db: Session,
        symbol: str,
        *,
        resolution: str = "intraday",
        interval: str = "15min",
        lookback_days: int = 14,
    ) -> int:
        """Warm one symbol's intraday snapshot from IntradayBarService bars.
        Intraday bars carry no within-day split/div adjustment, so
        `adjusted_close = close` for `_engine_frame`. ~14 calendar days of
        15-min bars (~360 bars) covers the providers' longest look-backs."""
        from datetime import timedelta

        from app.services.intraday_bar_service import IntradayBarService, et_now_naive

        end = et_now_naive()
        start = end - timedelta(days=lookback_days)
        raw = await IntradayBarService().get_bars(db, symbol, interval, start, end)
        if raw is None or raw.empty:
            return 0
        frame = raw.copy()
        frame["adjusted_close"] = frame["close"]
        values, frame_as_of = compute_values_from_frame(frame)
        if frame_as_of is None:
            return 0
        return self.write_symbol(db, symbol, values, frame_as_of, resolution=resolution)

    async def warm_universe(
        self,
        db: Session,
        symbols: Sequence[str],
        *,
        resolution: str = "daily",
        as_of: Optional[date] = None,
    ) -> Dict[str, int]:
        """Warm the whole universe, committing per symbol (short transactions —
        traps #13/#21). Returns a summary and logs the totals (trap #10)."""
        ok = empty = total_rows = 0
        for symbol in symbols:
            try:
                n = await self.warm_symbol(
                    db, symbol, resolution=resolution, as_of=as_of
                )
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("signal_snapshot: warm failed for '%s'", symbol)
                empty += 1
                continue
            if n > 0:
                ok += 1
                total_rows += n
            else:
                empty += 1
        logger.info(
            "signal_snapshot warm complete: %d symbols ok, %d empty, %d rows "
            "(resolution=%s)",
            ok,
            empty,
            total_rows,
            resolution,
        )
        # PRD-24a §6 gate — flag any primitive that warmed all-null/all-zero
        # across the universe, so a degenerate column can't silently back a scan
        # preset (the rank_composite_score trap). Logged, never raised: the warm
        # must still complete; findings feed DEGENERATE_SNAPSHOT_PRIMITIVE_IDS.
        try:
            degenerate = [
                c.primitive_id
                for c in self.audit_coverage(
                    db, list(symbols), resolution=resolution
                )
                if c.degenerate
            ]
            if degenerate:
                logger.warning(
                    "signal_snapshot coverage: %d primitive(s) degenerate "
                    "(all-null/all-zero across the warmed universe) — exclude "
                    "from presets or add to DEGENERATE_SNAPSHOT_PRIMITIVE_IDS: %s",
                    len(degenerate),
                    degenerate,
                )
        except Exception:
            logger.exception("signal_snapshot coverage audit failed")
        return {"symbols_ok": ok, "symbols_empty": empty, "rows": total_rows}

    # ── read path ─────────────────────────────────────────────────────────────

    def get_snapshot(
        self,
        db: Session,
        symbols: Sequence[str],
        *,
        resolution: str = "daily",
    ) -> SnapshotFrame:
        """Load the snapshot rows for `symbols` into one in-memory frame the
        scan filters over (one indexed query). Missing cells are NaN."""
        syms = [s.upper() for s in symbols]
        if not syms:
            return SnapshotFrame(frame=pd.DataFrame(), as_of_date=None)

        rows = (
            db.execute(
                select(SignalSnapshot).where(
                    SignalSnapshot.symbol.in_(syms),
                    SignalSnapshot.resolution == resolution,
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return SnapshotFrame(frame=pd.DataFrame(index=syms), as_of_date=None)

        data: Dict[str, Dict[str, float]] = {}
        as_of: Optional[date] = None
        for row in rows:
            data.setdefault(row.symbol, {})[row.primitive_id] = row.value
            if as_of is None or row.as_of_date > as_of:
                as_of = row.as_of_date

        frame = pd.DataFrame.from_dict(data, orient="index").reindex(syms)
        return SnapshotFrame(frame=frame, as_of_date=as_of)

    # ── coverage audit (PRD-24a §6 preset gate) ─────────────────────────────────

    def audit_coverage(
        self, db: Session, symbols: Sequence[str], *, resolution: str = "daily"
    ) -> List[PrimitiveCoverage]:
        """Coverage of every advertised snapshot primitive across `symbols` —
        the §6 preset gate. Reads the warmed snapshot and returns per-primitive
        stats; callers flag `.degenerate` columns (all-null/all-zero), which
        can't safely back a scan rule. Run over a standing universe (e.g.
        `SP500_TICKERS`) for the one-time sweep."""
        frame = self.get_snapshot(db, symbols, resolution=resolution).frame
        return compute_snapshot_coverage(frame, snapshot_primitive_ids())
