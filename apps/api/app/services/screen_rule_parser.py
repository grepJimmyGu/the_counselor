"""Extract SCREENING rules from a plain-English query (PRD-29 hotfix).

WHY THIS EXISTS. `/api/search/parse` originally reused `parse_strategy_message`
to turn free text into rules. That parser's job is to produce a COMPLETE,
backtestable `StrategyJSON`, so when a field is missing it interrogates the user
instead of extracting what it was given. Measured against production:

    "oversold above 200 day MA"          -> "What universe of tickers…?"   0 rules
    "SPY oversold above 200 day MA"      -> "What lookback period…?"       0 rules
    "S&P 500 stocks oversold above…"     -> "What specific tickers…?"      0 rules

Every one of those is a perfectly clear screen. The parser is right for building
a strategy and wrong for screening: a screen needs no universe (the scope pill
sets it), no capital, no rebalance frequency — just conditions.

So this module extracts conditions directly. Deterministic, like its sibling
`screen_filter_parser` (fundamentals): free, fast, no LLM on a public endpoint,
and every phrase is unit-testable. Unmatched text yields nothing rather than a
guess, and the caller may still fall back to the LLM parser.

Operators follow PRD-22c's kind dispatch — VALUE takes gt/gte/lt/lte, CROSS
takes crosses_up/down, LEVEL is_true, EVENT fires, DISTANCE in_range — because
a rule carrying the wrong operator for its primitive's kind silently fails to
evaluate.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Each entry: (regex, primitive_id, operator, threshold, params, reading)
# `threshold`/`params` may be None. A `{n}` group in the pattern, when present,
# overrides the period param — so "above the 50-day" and "above the 200-day"
# both work from one rule.
_PATTERNS: Tuple[Tuple[str, str, str, Optional[Any], Optional[Dict[str, Any]], str], ...] = (
    # ── momentum / mean reversion ─────────────────────────────────────────
    (r"\boversold\b", "rsi", "lt", 30, {"period": 14}, "RSI below 30 (oversold)"),
    (r"\boverbought\b", "rsi", "gt", 70, {"period": 14}, "RSI above 70 (overbought)"),
    (r"\brsi\s*(?:below|under|<|<=)\s*(\d{1,3})\b", "rsi", "lt", "@1", {"period": 14},
     "RSI below {v}"),
    (r"\brsi\s*(?:above|over|>|>=)\s*(\d{1,3})\b", "rsi", "gt", "@1", {"period": 14},
     "RSI above {v}"),

    # ── trend / moving averages ───────────────────────────────────────────
    # "above the 200-day", "above its 200 day moving average", "above 50d MA"
    (r"\babove\s+(?:the\s+|its\s+)?(\d{1,4})[-\s]?d(?:ay)?\b", "price_above_ma", "is_true",
     None, {"period": "@1"}, "price above the {p}-day average"),
    (r"\babove\s+(?:the\s+|its\s+)?(\d{1,4})[-\s]?day\s+(?:moving\s+average|ma|sma)\b",
     "price_above_ma", "is_true", None, {"period": "@1"},
     "price above the {p}-day average"),
    (r"\bgolden\s+cross\b", "golden_cross", "crosses_up", None, None, "golden cross"),
    (r"\bdeath\s+cross\b", "death_cross", "crosses_down", None, None, "death cross"),
    (r"\bmacd\s+(?:golden\s+)?cross(?:ing|es)?\s*(?:up|above)?\b", "macd_signal_cross",
     "crosses_up", None, None, "MACD crossing up"),
    (r"\b(?:rising|upward)\s+(?:moving\s+average|ma|trend)\b|\buptrend\b",
     "ma_slope_positive", "is_true", None, {"period": 50}, "moving average rising"),
    (r"\b(?:strong(?:ly)?\s+)?trending\b|\bstrong\s+trend\b", "adx", "gte", 25,
     {"period": 14}, "ADX at or above 25 (trending)"),

    # ── breakout / volatility ─────────────────────────────────────────────
    (r"\bbreak(?:ing)?\s*out\b|\bbreakouts?\b", "donchian_breakout", "fires",
     None, {"period": 20}, "20-day breakout"),
    (r"\bsqueez(?:e|ing)\b|\bcoiling\b", "ttm_squeeze", "is_true", None, None,
     "volatility squeeze"),

    # ── volume ────────────────────────────────────────────────────────────
    (r"\b(?:volume\s+surge|unusual\s+volume|high\s+volume|volume\s+spike)\b",
     "rvol_surge", "fires", None, None, "volume surge"),

    # ── oscillators / crosses added for the condition builder ─────────────
    (r"\bmacd\s+above\s+zero\b|\bmacd\s+zero[-\s]?line\b", "macd_zero_line_cross",
     "crosses_up", None, None, "MACD above the zero line"),
    (r"\bstochastic\s+cross(?:ing|es)?\s*(?:up|above)\b", "stoch_k_d_cross",
     "crosses_up", None, None, "stochastic crossing up"),
    (r"\bstochastic\s+cross(?:ing|es)?\s*(?:down|below)\b", "stoch_k_d_cross",
     "crosses_down", None, None, "stochastic crossing down"),
    (r"\babove\s+vwap\b", "vwap", "gt", 0, {"period": 20}, "above VWAP"),
    (r"\broc\s*(?:above|over|>)\s*(-?\d{1,3})\b", "roc", "gt", "@1", {"period": 20},
     "20-day change above {v}%"),
    (r"\broc\s*(?:below|under|<)\s*(-?\d{1,3})\b", "roc", "lt", "@1", {"period": 20},
     "20-day change below {v}%"),

    # ── fundamentals expressed as primitives (not ScreenerFilters) ────────
    (r"\bbook\s+to\s+market\s*(?:above|over|>)\s*([\d.]+)", "book_to_market", "gt",
     "@1", None, "book-to-market above {v}"),
    (r"\bfcf\s+yield\s*(?:above|over|>)\s*([\d.]+)", "fcf_yield", "gt", "@1", None,
     "FCF yield above {v}"),
    (r"\bf[-\s]?score\s*(?:above|over|>=?|at least)\s*([\d.]+)", "f_score", "gte",
     "@1", None, "Piotroski F-score at or above {v}"),

    # ── sentiment / events ────────────────────────────────────────────────
    (r"\bsentiment\s*(?:above|over|>)\s*([\d.]+)", "sentiment_score", "gt", "@1",
     {"window_days": 30}, "news sentiment above {v}"),
    (r"\binsider\s+buying\b", "insider_net_buy", "gt", 0, {"window_days": 90},
     "net insider buying"),
    (r"\bpositive\s+earnings\s+surprise\b", "earnings_surprise", "gt", 0,
     {"window_days": 60}, "positive earnings surprise"),
    (r"\bestimates?\s+rising\b", "estimate_revision_3m", "gt", 0, None,
     "analyst estimates rising"),

    # ── position within range ─────────────────────────────────────────────
    # signed percent, negative below the high — so "near the high" is >= -5.
    (r"\bnear(?:ing)?\s+(?:its\s+|the\s+)?52[-\s]?week\s+high\b|\bnear\s+(?:its\s+)?highs?\b",
     "distance_to_52w_high", "gte", -5.0, {"lookback": 252},
     "within 5% of the 52-week high"),
)


def _fill(template: str, value: Any, period: Any) -> str:
    return template.replace("{v}", str(value)).replace("{p}", str(period))


def extract_rules(query: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Turn a query into composer-shaped rules + a plain-English echo.

    Returns `([], [])` when nothing matches, so the caller can fall back rather
    than screen on a fabricated condition.
    """
    lowered = query.lower()
    rules: List[Dict[str, Any]] = []
    readings: List[str] = []
    seen: set = set()

    for pattern, pid, operator, threshold, params, reading in _PATTERNS:
        m = re.search(pattern, lowered)
        if not m:
            continue
        if pid in seen:  # one rule per primitive — first phrasing wins
            continue

        captured = m.group(1) if m.groups() else None

        resolved_threshold = threshold
        if threshold == "@1" and captured is not None:
            try:
                resolved_threshold = float(captured)
                if resolved_threshold.is_integer():
                    resolved_threshold = int(resolved_threshold)
            except ValueError:
                continue

        resolved_params: Dict[str, Any] = {}
        for k, v in (params or {}).items():
            if v == "@1" and captured is not None:
                try:
                    resolved_params[k] = int(captured)
                except ValueError:
                    continue
            else:
                resolved_params[k] = v

        seen.add(pid)
        rule: Dict[str, Any] = {
            "primitive_id": pid,
            "operator": operator,
            # First rule must have a null fold; the backend validator enforces it.
            "logic_with_prior": None if not rules else "AND",
        }
        if resolved_threshold is not None:
            rule["threshold"] = resolved_threshold
        if resolved_params:
            rule["primitive_params"] = resolved_params
        rules.append(rule)
        readings.append(
            _fill(reading, resolved_threshold, resolved_params.get("period")
                  or resolved_params.get("lookback"))
        )

    return rules, readings
