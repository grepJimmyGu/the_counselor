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

**Category coverage is load-bearing** (2026-07-30). The matcher scores Jaccard
over CATEGORIES, so a category that no template declares makes every primitive
in it silently unmatchable — the user gets "no match" and zero seeded
parameters. `trend` (30 primitives) and `volume` (12) were in that dead zone,
i.e. 38% of the catalog, including `price_above_ma` — the most-used primitive
in the recommended-template registry. `test_every_category_is_declared_by_some_template`
now guards this; don't add a catalog category without giving it a home here.

`volume` currently lives on `trend-following` as breakout confirmation, which
is the weaker of the two claims — a dedicated volume/breakout template in
`template_search.py:_CATALOG` would own it more honestly.

Threshold key names are a CONTRACT with the composer's
`applyTemplateThresholdsToRules`: only `enter_*` / `exit_*` / `threshold` /
`min` / `max` / `upper` / `lower` shaped keys become thresholds, and only
`enter_lt|lte|gt|gte` / `exit_lt|lte|gt|gte` / `upper` / `lower` / `positive`
map to an operator. **Every other key is forwarded to the primitive as a
`primitive_params` override** — so a stray key here becomes a bogus provider
parameter. The mapper also takes the FIRST threshold-shaped key only, so
two-sided ranges (`{min, max}`) silently apply one bound; use a single-sided
`enter_*` instead.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from app.schemas.signal_primitive import SignalCategory


# ── Per-template metadata ────────────────────────────────────────────────────


TEMPLATE_SIGNAL_METADATA: Dict[str, Dict[str, Any]] = {
    "trend-following": {
        # TREND was missing until 2026-07-30. Because the matcher scores
        # Jaccard over CATEGORIES, a category no template declared made every
        # primitive in it unmatchable — and `trend` is the catalog's largest
        # category (30 primitives, incl. `price_above_ma`, the single most-used
        # primitive in the recommended templates). VOLUME (12 primitives) had
        # the same problem; breakout systems canonically confirm with volume,
        # so this template is its closest home. A dedicated volume/breakout
        # template in `template_search.py:_CATALOG` would be the cleaner
        # long-term owner — see the note in the module docstring.
        "categories": {
            SignalCategory.TREND,
            SignalCategory.MOMENTUM,
            SignalCategory.VOLATILITY,
            SignalCategory.VOLUME,
        },
        "thresholds": {
            "donchian_breakout": {"period": 20},
            "atr": {"stop_multiplier": 2.0, "period": 14},
            # Level primitives: params only. The operator for a LEVEL is
            # `is_true`, which the composer already sets when the primitive is
            # added — a threshold value here would be meaningless.
            "price_above_ma": {"period": 200},
            "ma_slope_positive": {"period": 50, "lookback": 10},
            # Wilder's convention: >25 trending. Exit at 20, not 25, so a
            # reading hovering on the line can't thrash in/out.
            "adx": {"period": 14, "enter_gte": 25, "exit_lt": 20},
            # 2.0 = twice normal turnover (the primitive's own description).
            # Confirmation only — see ENTRY_ONLY_PRIMITIVES.
            "rvol": {"lookback": 20, "enter_gte": 2.0},
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
            # `distance_to_52w_high` returns (close / 52w_high - 1) * 100 —
            # signed PERCENT, negative below the high, 0 at the high. So
            # "within 5% of the 52-week high" is `>= -5.0`.
            # Single-sided on purpose: the composer's threshold mapper takes
            # the FIRST threshold-shaped key only, so a {min,max} range would
            # silently apply just one bound.
            "distance_to_52w_high": {"lookback": 252, "enter_gte": -5.0},
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
            # Params only. NOTE: the catalog declares `ttm_squeeze` as
            # output_kind=REGIME, but its provider returns 0.0/1.0
            # (`(bb_upper < kc_upper) & (bb_lower > kc_lower)`), so the correct
            # operator is `is_true`, not REGIME's `equals`. Flagging rather
            # than changing the catalog — the kind is a separate decision.
            "ttm_squeeze": {"period": 20, "bb_std": 2.0, "kc_mult": 1.5},
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
            # Catalog description: oversold <30, overbought >70. Exit at the
            # midline rather than 70 — holding for 70 routinely gives the
            # bounce back. This is the most debatable value in the file;
            # change it here and every seeded RSI screen follows.
            "rsi": {"period": 14, "enter_lt": 30, "exit_gte": 55},
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


# ── Entry-only primitives ───────────────────────────────────────────────────
#
# Most primitives cannot express an exit. Only oscillators (rsi, adx, bbands)
# are genuinely two-sided; level filters (price_above_ma, ma_slope_positive)
# "exit" by going false; and the rest are one-shot confirmations. Listing them
# explicitly means the UI can SAY "no calculated exit for this indicator"
# instead of inventing one.
#
# Deliberately a module-level set, NOT a key inside the thresholds dicts:
# `applyTemplateThresholdsToRules` treats every non-threshold-shaped key as a
# primitive_params override, so an `entry_only` key there would be forwarded to
# the provider as a bogus parameter.

ENTRY_ONLY_PRIMITIVES: Set[str] = {
    "rvol",                    # confirmation spike — an rvol "exit" is meaningless
    "ttm_squeeze",             # coiling regime; says nothing about when to leave
    "distance_to_52w_high",    # proximity at entry; not a holding condition
}


# ── Default calculated exit ladder ──────────────────────────────────────────
#
# Since most screens can't express an indicator exit (above), the default exit
# is volatility-scaled: stop at N x ATR, targets at multiples of the same unit,
# converted to the percent `trigger_pct` that `RiskManagement.exit_ladder`
# already consumes. `2.0` mirrors this file's own `atr.stop_multiplier`.
#
# Clamped because ATR/price varies wildly across the universe: an unclamped
# 2x ATR stop is ~-3% on a utility and ~-30% on a small-cap biotech. The band
# keeps a seeded ladder inside a range a human would plausibly accept, and the
# consumer must state that the values are derived, not optimised.

DEFAULT_EXIT_LADDER: Dict[str, Any] = {
    "atr_period": 14,
    "stop_atr_multiple": 2.0,
    "target_atr_multiples": [3.0, 5.0],   # TP1 sells half, TP2 the rest
    "target_fractions": [0.5, 1.0],
    "stop_pct_clamp": [-15.0, -4.0],      # [min, max] — always negative
    "target_pct_clamp": [6.0, 60.0],
}


# ── Lookup helpers ──────────────────────────────────────────────────────────


def is_entry_only(primitive_id: str) -> bool:
    """True when the KB has no exit for this primitive, so the caller must ask
    the user for one rather than fabricating a default."""
    return primitive_id in ENTRY_ONLY_PRIMITIVES


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
