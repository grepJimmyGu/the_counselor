"""The Mirror's deep lens views — PRD-43b §3.7.

`GET /api/mirror/timing` is the WHEN section's **deep view**: the per-episode
table, the setup breakdown, the markout profiles. The Mirror's *summary* stays
on `GET /api/snaptrade/behavior` (43a §3.6) — 43a's ban is on forking a second
*behavior* route, never on lens routes, and this parallels the allocation
lens's own endpoint.

⚠ **Ungated in this PR, deliberately.** The PRD gates this at Strategist+, but
Stripe is built and unconfigured, so a tier gate today enforces against a
paywall nobody can pass. Gating is an `entitlements.py` change, not a rebuild.
Sign-in is still required — this reads the caller's own brokerage record.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import snaptrade_service as st

router = APIRouter(prefix="/api/mirror", tags=["mirror"])
_log = logging.getLogger("livermore.mirror")

_CACHE_TTL_SECONDS = 60 * 60
_CACHE_MAX_ENTRIES = 256
_CACHE: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()

# Hourly cap, held in-process rather than on `weekly_usage`. The DB counters
# are per-feature columns, and adding one for a read-only endpoint would mean a
# migration for rate limiting alone. Revisit when the tier gate lands — that is
# the change that makes a durable counter worth its column.
_TIMING_HOURLY_CAP = 30
_CALLS: "OrderedDict[str, Tuple[int, int]]" = OrderedDict()


def _cache_get(key: str) -> Optional[Any]:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    ts, payload = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    _CACHE.move_to_end(key)
    return payload


def _cache_put(key: str, value: Any) -> None:
    _CACHE[key] = (time.time(), value)
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX_ENTRIES:
        _CACHE.popitem(last=False)


def _cache_clear() -> None:
    _CACHE.clear()
    _CALLS.clear()


def _rate_limit(user_id: str) -> None:
    hour = int(time.time() // 3600)
    seen_hour, count = _CALLS.get(user_id, (hour, 0))
    if seen_hour != hour:
        seen_hour, count = hour, 0
    if count >= _TIMING_HOURLY_CAP:
        raise HTTPException(
            status_code=429,
            detail="You've refreshed this a lot in the last hour. Try again shortly.",
        )
    _CALLS[user_id] = (seen_hour, count + 1)
    _CALLS.move_to_end(user_id)
    while len(_CALLS) > _CACHE_MAX_ENTRIES:
        _CALLS.popitem(last=False)


# ── response ────────────────────────────────────────────────────────────────


class HorizonView(BaseModel):
    horizon: int
    n: int
    median: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None
    straddles_zero: bool = True


class ProfileView(BaseModel):
    horizons: List[HorizonView] = []
    excluded_beyond_window: int = 0
    # False when every horizon's quartiles straddle zero. The surface renders
    # that as "no consistent timing pattern", never a diagnosis read out of
    # the medians — §3.1's correction after the first live run.
    has_consistent_pattern: bool = False


class ExcursionView(BaseModel):
    winner_mae: Optional[float] = None
    winner_n: int = 0
    loser_mae: Optional[float] = None
    loser_n: int = 0
    median_capture: Optional[float] = None
    capture_n: int = 0
    # Must render wherever the MAE gap renders: same-day episodes have no
    # excursion at all, and a reader who does not know they were dropped will
    # read the gap as covering the whole record.
    same_day_excluded: int = 0
    approximate_boundary: int = 0


class SetupView(BaseModel):
    setup: str
    n: int
    wins: int
    win_rate: Optional[float] = None
    median_return: Optional[float] = None
    median_mae: Optional[float] = None
    median_capture: Optional[float] = None


class LeakView(BaseModel):
    key: str
    n: int
    dollars: float


class TimingCoverageView(BaseModel):
    episodes_total: int = 0
    episodes_analysed: int = 0
    symbols_measured: int = 0
    excluded: List[Tuple[str, str]] = []
    unclassified_entries: int = 0
    classified_entries: int = 0
    unclassified_share: Optional[float] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None


class TimingView(BaseModel):
    opening_entry_profile: ProfileView = ProfileView()
    add_on_profile: ProfileView = ProfileView()
    final_exit_profile: ProfileView = ProfileView()
    partial_exit_profile: ProfileView = ProfileView()
    excursions: ExcursionView = ExcursionView()
    setups: List[SetupView] = []
    outcomes: Dict[str, int] = {}
    leaks: List[LeakView] = []
    coverage: TimingCoverageView = TimingCoverageView()


def _profile_view(p) -> ProfileView:
    return ProfileView(
        horizons=[
            HorizonView(horizon=h.horizon, n=h.n, median=h.median,
                        q1=h.q1, q3=h.q3, straddles_zero=h.straddles_zero)
            for h in p.horizons
        ],
        excluded_beyond_window=p.excluded_beyond_window,
        has_consistent_pattern=p.has_consistent_pattern,
    )


@router.get("/timing", response_model=TimingView)
def mirror_timing(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TimingView:
    """Entry and exit timing measured against the caller's own record.

    `def`, not `async def` — `list_activities` is a blocking SDK call, and
    running it on the event loop is the trap #21 failure that cost 14
    consecutive deploys. FastAPI runs this in a worker thread instead.
    """
    from app.services.mirror.portfolio_ledger_service import build_ledger, load_splits
    from app.services.timing.service import analyse_record
    from app.services.trading_behavior import _parse_date

    # Trap #17: snapshot before anything can commit and expire the instance.
    user_id: str = current_user.id
    _rate_limit(user_id)

    cached = _cache_get(f"timing:{user_id}")
    if cached is not None:
        return cached

    try:
        activities = st.list_activities(db, user_id, limit=250)
        positions = st.list_positions(db, user_id)
    except st.SnapTradeNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="Brokerage connections aren't available right now.",
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("mirror: timing read failed user=%s", user_id)
        raise HTTPException(
            status_code=502, detail="Couldn't read your trading history.",
        ) from exc

    rows = [vars(a) for a in activities]
    # The broker round-trip above is the slow part and it is a BLOCKING call.
    # Hand the pool connection back now rather than holding it across a third
    # party; the session stays usable and checks out a fresh one below.
    db.close()

    symbols = {str(r.get("symbol") or "").upper() for r in rows}
    symbols.discard("")
    ledger = build_ledger(rows, {})
    if symbols:
        try:
            # Unbounded on the start side on purpose: the split that explains
            # an unmatchable sell usually happened before the first row we can
            # see (43a §3.2).
            splits = load_splits(db, symbols, end=ledger.coverage.window_end)
            ledger = build_ledger(rows, splits)
        except Exception:  # noqa: BLE001
            _log.exception("mirror: split lookup failed user=%s", user_id)

    try:
        analysis = analyse_record(
            db, ledger.transactions, positions=positions,
            window_end=date.today(),
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("mirror: timing analysis failed user=%s", user_id)
        raise HTTPException(
            status_code=500, detail="Couldn't measure your trade timing.",
        ) from exc

    rep = analysis.report
    view = TimingView(
        opening_entry_profile=_profile_view(rep.opening_entry_profile),
        add_on_profile=_profile_view(rep.add_on_profile),
        final_exit_profile=_profile_view(rep.final_exit_profile),
        partial_exit_profile=_profile_view(rep.partial_exit_profile),
        excursions=ExcursionView(
            winner_mae=rep.excursions.winner_mae,
            winner_n=rep.excursions.winner_n,
            loser_mae=rep.excursions.loser_mae,
            loser_n=rep.excursions.loser_n,
            median_capture=rep.excursions.median_capture,
            capture_n=rep.excursions.capture_n,
            same_day_excluded=rep.excursions.same_day_excluded,
            approximate_boundary=rep.excursions.approximate_boundary,
        ),
        setups=[
            SetupView(
                setup=s.label, n=s.n, wins=s.wins, win_rate=s.win_rate,
                median_return=s.median_return, median_mae=s.median_mae,
                median_capture=s.median_capture,
            )
            for s in rep.setups
        ],
        outcomes=dict(rep.outcomes),
        leaks=[LeakView(key=l.key, n=l.n, dollars=l.dollars) for l in rep.leaks],
        coverage=TimingCoverageView(
            episodes_total=rep.coverage.episodes_total,
            episodes_analysed=len(analysis.episodes),
            symbols_measured=analysis.symbols_measured,
            excluded=list(analysis.excluded),
            unclassified_entries=rep.coverage.unclassified_entries,
            classified_entries=rep.coverage.classified_entries,
            unclassified_share=rep.coverage.unclassified_share,
            window_start=str(analysis.window_start) if analysis.window_start else None,
            window_end=str(analysis.window_end) if analysis.window_end else None,
        ),
    )
    _cache_put(f"timing:{user_id}", view)
    return view
