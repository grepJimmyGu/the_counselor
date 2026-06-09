"""Per-template signal metadata — PRD-16a Slice 3.

For each of the 19 backend templates (mirrored from
`app/services/chat_tools/template_search.py:_CATALOG`), records:

  - `categories`: the set of `SignalCategory` values the template uses,
    used as the input to the Jaccard similarity in
    `match_signal_combos_to_templates`.
  - `thresholds`: per-primitive suggested entry/exit thresholds — what
    the template uses for its canonical implementation. When a user
    picks {RSI, Bollinger} and matches "Bollinger Mean Reversion," the
    response includes `{"bbands": {...}, "rsi": {...}}` so the composer
    UX can pre-fill sensible defaults.

The mapping is **editorial work** — the choice of which categories /
primitives anchor each template is part of the catalog's UX, not a
deterministic derivation. Treat this file like the catalog itself:
review changes at the PR layer, not by-algorithm.

Sources:
  - Template descriptions in `template_search.py` (the canonical
    description per template).
  - Primitive IDs from `app/data/signal_primitives.py` (must match the
    catalog's IDs exactly — typo'd IDs silently drop from the matches).

Adding a new template? Add an entry here too, or
`test_template_signal_metadata.py::test_all_templates_have_signal_metadata`
fails at CI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from app.schemas.signal_primitive import SignalCategory


# ── Per-template metadata ────────────────────────────────────────────────────


TEMPLATE_SIGNAL_METADATA: Dict[str, Dict[str, Any]] = {
    "trend-following": {
        "categories": {SignalCategory.MOMENTUM, SignalCategory.VOLATILITY},
        "thresholds": {
            "donchian_breakout": {"period": 20},
            "atr": {"stop_multiplier": 2.0, "period": 14},
        },
    },
    "cross-sectional-momentum": {
        "categories": {SignalCategory.CROSS_SECTIONAL, SignalCategory.MOMENTUM},
        "thresholds": {
            "rank_return_6m": {"lookback_days": 126, "top_n": 2},
        },
    },
    "cross-sectional-momentum-12-1": {
        "categories": {SignalCategory.CROSS_SECTIONAL, SignalCategory.MOMENTUM},
        "thresholds": {
            "time_series_momentum": {"lookback_months": 12, "skip_months": 1},
            "rank_return_6m": {"lookback_days": 252, "top_n": 2},
        },
    },
    "time-series-momentum": {
        "categories": {SignalCategory.MOMENTUM},
        "thresholds": {
            "time_series_momentum": {"lookback_months": 12, "skip_months": 1},
        },
    },
    "etf-rotation": {
        "categories": {SignalCategory.CROSS_SECTIONAL, SignalCategory.MOMENTUM},
        "thresholds": {
            "rank_return_6m": {"lookback_days": 126, "top_n": 1},
        },
    },
    "sector-rotation-spdr": {
        "categories": {SignalCategory.CROSS_SECTIONAL, SignalCategory.MOMENTUM},
        "thresholds": {
            "sector_rotation_rank": {"lookback_days": 63, "top_n": 2},
        },
    },
    "dual-momentum": {
        "categories": {SignalCategory.MOMENTUM, SignalCategory.CROSS_SECTIONAL},
        "thresholds": {
            "time_series_momentum": {"lookback_months": 12, "skip_months": 1},
            "rank_return_6m": {"lookback_days": 126, "top_n": 1},
        },
    },
    "value-momentum": {
        "categories": {SignalCategory.FUNDAMENTAL, SignalCategory.MOMENTUM},
        "thresholds": {
            "book_to_market": {"min_bm": 0.5},
            "time_series_momentum": {"lookback_months": 12, "skip_months": 1},
        },
    },
    "low-volatility": {
        "categories": {SignalCategory.VOLATILITY, SignalCategory.CROSS_SECTIONAL},
        "thresholds": {
            "realized_vol": {"period": 252, "rank_pick": "lowest"},
        },
    },
    "value-composite-cs": {
        "categories": {SignalCategory.FUNDAMENTAL, SignalCategory.CROSS_SECTIONAL},
        "thresholds": {
            "book_to_market": {"min_bm": 0.5},
            "ebitda_ev": {"min_yield": 0.10},
            "fcf_yield": {"min_yield": 0.05},
        },
    },
    "quality-piotroski-cs": {
        "categories": {SignalCategory.FUNDAMENTAL, SignalCategory.CROSS_SECTIONAL},
        "thresholds": {
            "f_score": {"min_score": 7.0},
        },
    },
    "multi-factor-composite": {
        "categories": {
            SignalCategory.FUNDAMENTAL,
            SignalCategory.MOMENTUM,
            SignalCategory.CROSS_SECTIONAL,
        },
        "thresholds": {
            "rank_composite_score": {
                "value_weight": 0.4,
                "quality_weight": 0.3,
                "momentum_weight": 0.3,
                "top_n": 10,
            },
        },
    },
    "short-term-reversal": {
        "categories": {SignalCategory.MEAN_REVERSION, SignalCategory.CROSS_SECTIONAL},
        "thresholds": {
            "roc": {"period": 5, "rank_pick": "worst"},
        },
    },
    "bollinger-mean-reversion": {
        "categories": {SignalCategory.MEAN_REVERSION, SignalCategory.VOLATILITY},
        "thresholds": {
            "bbands": {"period": 20, "std_dev": 2.0, "enter_lt": 0.0, "exit_gte": 0.5},
        },
    },
    "pairs-trading-long-only": {
        "categories": {SignalCategory.CROSS_SECTIONAL, SignalCategory.MEAN_REVERSION},
        "thresholds": {
            "pair_spread_zscore": {"lookback_days": 60, "entry_z": -2.0, "exit_z": 0.0},
        },
    },
    "commodity-carry": {
        "categories": {SignalCategory.CROSS_SECTIONAL, SignalCategory.MOMENTUM},
        "thresholds": {
            "rank_return_6m": {"lookback_days": 21, "top_n": 2},
        },
    },
    "news-sentiment-momentum": {
        "categories": {SignalCategory.SENTIMENT, SignalCategory.MOMENTUM},
        "thresholds": {
            "sentiment_score": {"window_days": 30, "bullish": 0.2},
            "time_series_momentum": {"lookback_months": 6, "skip_months": 1},
        },
    },
    "insider-buying": {
        "categories": {SignalCategory.SENTIMENT},
        "thresholds": {
            "insider_net_buy": {"window_days": 90, "strong_buy": 0.001},
        },
    },
    "pead-drift-cs": {
        "categories": {SignalCategory.FUNDAMENTAL, SignalCategory.CROSS_SECTIONAL},
        "thresholds": {
            "earnings_surprise": {"window_days": 60, "positive": 0.0},
        },
    },
}


# ── Lookup helpers ──────────────────────────────────────────────────────────


def get_template_categories(template_id: str) -> Set[SignalCategory]:
    """Return the category set for a template, or an empty set if the
    template_id is unknown (defensive — never raises)."""
    return TEMPLATE_SIGNAL_METADATA.get(template_id, {}).get("categories", set())


def get_template_thresholds(template_id: str) -> Dict[str, Dict[str, Any]]:
    """Return the per-primitive thresholds map for a template, or an
    empty dict if the template_id is unknown."""
    return TEMPLATE_SIGNAL_METADATA.get(template_id, {}).get("thresholds", {})


def all_template_ids() -> List[str]:
    """List of every template_id with metadata authored. Used by tests."""
    return list(TEMPLATE_SIGNAL_METADATA.keys())
