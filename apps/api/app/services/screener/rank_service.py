"""Market Screener — rank service (PRD-23a §3.5).

Backtest the MATCHED SUBSET (≪ universe — the reading already narrowed it) and
rank by return. The expensive step by construction only ever runs on the
survivors of the scan.

- Each matched symbol is backtested with the SAME composed reading, universe
  swapped to that one symbol (`StrategyJSON.model_copy(universe=[symbol])`),
  via the existing `BacktestEngine` (read-only reuse, no new strategy_type).
- Results are ranked by total return.
- A `(symbol, rule_hash, as_of_date)` cache skips re-backtesting an unchanged
  reading on the same snapshot day.
- A top-K cap bounds cost on a loose rule: pre-order by a cheap proxy (a
  snapshot momentum score, if supplied) and backtest only the top K — logging
  what was dropped (no silent cap).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from app.schemas.strategy import StrategyJSON

logger = logging.getLogger("livermore.screener.rank")

DEFAULT_TOP_K = 50


@dataclass
class RankedEntry:
    symbol: str
    total_return: float
    annualized_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None


@dataclass
class RankResult:
    ranked: List[RankedEntry]  # sorted by total_return desc
    as_of_date: Optional[date]
    matched_count: int
    backtested_count: int
    dropped_count: int = 0


# backtest_fn(db, symbol, strategy_json) -> RankedEntry | None
BacktestFn = Callable[[object, str, StrategyJSON], Awaitable[Optional[RankedEntry]]]


def rule_hash(strategy_json: StrategyJSON) -> str:
    """Stable short hash of the composed reading (the rules) — the cache key's
    identity component. Independent of the universe so the same reading on
    different symbols shares nothing but the hash."""
    rules = [
        {
            "primitive_id": r.primitive_id,
            "operator": r.operator,
            "threshold": r.threshold,
            "primitive_params": r.primitive_params,
            "logic_with_prior": r.logic_with_prior,
        }
        for r in strategy_json.rules
    ]
    payload = json.dumps(rules, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


class RankService:
    def __init__(self) -> None:
        # (symbol, rule_hash, as_of_date) -> RankedEntry. Process-level; the
        # as_of_date component self-invalidates on a new snapshot day.
        self._cache: Dict[Tuple[str, str, Optional[date]], RankedEntry] = {}

    async def _default_backtest(
        self, db, symbol: str, strategy_json: StrategyJSON
    ) -> Optional[RankedEntry]:
        from app.services.backtester.engine import BacktestEngine

        single = strategy_json.model_copy(update={"universe": [symbol]})
        try:
            result = await BacktestEngine().run(db, single)
        except Exception:
            logger.exception("rank: backtest failed for '%s' — skipped", symbol)
            return None
        m = result.metrics
        return RankedEntry(
            symbol=symbol,
            total_return=m.total_return,
            annualized_return=getattr(m, "annualized_return", None),
            sharpe_ratio=getattr(m, "sharpe_ratio", None),
        )

    async def rank(
        self,
        db,
        matched: Sequence[str],
        strategy_json: StrategyJSON,
        *,
        as_of_date: Optional[date] = None,
        top_k: int = DEFAULT_TOP_K,
        proxy_scores: Optional[Dict[str, float]] = None,
        backtest_fn: Optional[BacktestFn] = None,
    ) -> RankResult:
        fn = backtest_fn or self._default_backtest
        rhash = rule_hash(strategy_json)

        candidates = list(matched)
        # Cheap-proxy pre-order so the top-K cap keeps the most promising names.
        if proxy_scores:
            candidates.sort(
                key=lambda s: proxy_scores.get(s, float("-inf")), reverse=True
            )

        dropped = 0
        if len(candidates) > top_k:
            dropped = len(candidates) - top_k
            logger.info(
                "rank: capping %d matched to top %d (dropped %d) — ordered by %s",
                len(candidates),
                top_k,
                dropped,
                "proxy score" if proxy_scores else "scan order",
            )
            candidates = candidates[:top_k]

        entries: List[RankedEntry] = []
        for symbol in candidates:
            key = (symbol, rhash, as_of_date)
            cached = self._cache.get(key)
            if cached is not None:
                entries.append(cached)
                continue
            entry = await fn(db, symbol, strategy_json)
            if entry is not None:
                self._cache[key] = entry
                entries.append(entry)

        entries.sort(key=lambda e: e.total_return, reverse=True)
        return RankResult(
            ranked=entries,
            as_of_date=as_of_date,
            matched_count=len(matched),
            backtested_count=len(entries),
            dropped_count=dropped,
        )


# Process-level singleton so the (symbol, rule_hash, as_of_date) cache persists
# across requests (the live funnel re-ranks an unchanged reading instantly).
rank_service = RankService()
