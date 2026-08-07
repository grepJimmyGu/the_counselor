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
    # People type "over-bought" and "over sold" as often as the closed form.
    # Without the separator class these extracted NOTHING and the query fell
    # through to the LLM.
    (r"\bover[-\s]?sold\b", "rsi", "lt", 30, {"period": 14}, "RSI below 30 (oversold)"),
    (r"\bover[-\s]?bought\b", "rsi", "gt", 70, {"period": 14}, "RSI above 70 (overbought)"),
    (r"\brsi\s*(?:below|under|<|<=)\s*(\d{1,3})\b", "rsi", "lt", "@1", {"period": 14},
     "RSI below {v}"),
    (r"\brsi\s*(?:above|over|>|>=)\s*(\d{1,3})\b", "rsi", "gt", "@1", {"period": 14},
     "RSI above {v}"),

    # ── trend / moving averages ───────────────────────────────────────────
    # "above the 200-day", "above its 200 day moving average", "above 50d MA"
    # "break(s) the 50 MA", "breaking above the 200-day". `crosses_up` is the
    # right operator: a break is the event, not the standing state that
    # `price_above_ma` describes (PRD-22c — a wrong operator for the kind
    # silently fails to evaluate rather than erroring).
    (r"\bbreak(?:s|ing)?\s+(?:above\s+)?(?:the\s+|its\s+)?(\d{1,4})"
     r"(?:[-\s]?d(?:ay)?\b|(?=[-\s]*(?:moving\s+average|ma|sma)\b))"
     r"[-\s]*(?:moving\s+average|ma|sma)?",
     "price_above_ma", "crosses_up", None, {"period": "@1"},
     "price breaking above the {p}-day average"),
    (r"\babove\s+(?:the\s+|its\s+)?(\d{1,4})[-\s]?d(?:ay)?\b", "price_above_ma", "is_true",
     None, {"period": "@1"}, "price above the {p}-day average"),
    (r"\babove\s+(?:the\s+|its\s+)?(\d{1,4})[-\s]?day\s+(?:moving\s+average|ma|sma)\b",
     "price_above_ma", "is_true", None, {"period": "@1"},
     "price above the {p}-day average"),
    (r"\bgolden\s+cross\b", "golden_cross", "crosses_up", None, None, "golden cross"),
    (r"\bdeath\s+cross\b", "death_cross", "crosses_down", None, None, "death cross"),
    # The bounded gap is what makes compounds work. Both MACD patterns used to
    # require "macd" IMMEDIATELY before their own phrase, so "MACD above zero
    # line and cross up" matched only the zero-line half and silently dropped
    # the cross — a narrower screen than the user asked for. {0,40} spans a
    # clause without reaching into the next sentence, and excluding [.;] stops
    # it attributing a later primitive's verb to MACD.
    (r"\bmacd\b[^.;]{0,40}?\b(?:golden\s+)?cross(?:ing|es)?\s*(?:up|above)\b",
     "macd_signal_cross", "crosses_up", None, None, "MACD crossing up"),
    # The down half. Its absence was a live wrong-answer bug: the up pattern
    # ended in `(?:up|above)?` — OPTIONAL — so "macd crossing down" matched it
    # and produced a crosses_up rule. The Conditions builder's "Crossing down"
    # pill therefore screened for crossings UP, with a chip that said down.
    (r"\bmacd\b[^.;]{0,40}?\b(?:death\s+)?cross(?:ing|es)?\s*(?:down|below)\b",
     "macd_signal_cross", "crosses_down", None, None, "MACD crossing down"),
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
    (r"\bmacd\b[^.;]{0,40}?\b(?:above\s+(?:the\s+)?zero|zero[-\s]?line)\b",
     "macd_zero_line_cross", "crosses_up", None, None, "MACD above the zero line"),
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
    # "solid / strong / good fundamentals", "high quality". Mapped to Piotroski
    # F-score >= 7 because that IS our fundamental-quality primitive — a
    # 9-point accounting-health score, the closest thing to what a trader means
    # by "solid fundamentals". Threshold 7 matches the Quality pill in the home
    # Conditions builder, so the phrase and the pill agree.
    (r"\b(?:solid|strong|good|healthy)\s+fundamentals\b|\bhigh[-\s]quality\b"
     r"|\bquality\s+(?:stocks?|names?|companies)\b",
     "f_score", "gte", 7, None, "Piotroski F-score at or above 7 (quality)"),
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

    # Collect every match first, then emit in the order the conditions appear in
    # the SENTENCE rather than in `_PATTERNS` order. Two reasons: the readings
    # then echo the query back in the order it was written, and the connective
    # between two conditions ("and" vs "or") is only recoverable from the text
    # BETWEEN them.
    hits = []
    for pattern, pid, operator, threshold, params, reading in _PATTERNS:
        m = re.search(pattern, lowered)
        if m:
            hits.append((m, pattern, pid, operator, threshold, params, reading))
    hits.sort(key=lambda h: h[0].start())

    # Drop a hit whose matched span sits INSIDE another hit's span for the same
    # primitive. "breaks above the 50-day" matches both the break pattern (the
    # whole phrase) and the standing "above the 50-day" pattern nested in it —
    # two rules, and two identical-looking readings, for one stated condition.
    # The wider span is the more specific reading, so it wins.
    def _contained(h) -> bool:
        m, _pat, pid = h[0], h[1], h[2]
        return any(
            o[2] == pid
            and o[0] is not m
            and o[0].start() <= m.start()
            and o[0].end() >= m.end()
            and (o[0].end() - o[0].start()) > (m.end() - m.start())
            for o in hits
        )

    hits = [h for h in hits if not _contained(h)]

    prev_end = None
    for m, pattern, pid, operator, threshold, params, reading in hits:
        # Keyed on (primitive, operator), not primitive alone: "over-bought or
        # over sold" is two legitimate RSI conditions with opposite operators.
        # Keying on the primitive alone silently dropped the second one and
        # screened for half of what was asked.
        if (pid, operator) in seen:
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

        seen.add((pid, operator))
        # AND unless the query joined these two conditions with "or". Getting
        # this wrong is not cosmetic: RSI>70 AND RSI<30 is unsatisfiable, so an
        # "or" query folded as AND returns zero names and looks like the screen
        # simply found nothing.
        if not rules:
            fold = None  # first rule must have a null fold (backend validator)
        else:
            between = lowered[prev_end:m.start()] if prev_end is not None else ""
            fold = "OR" if re.search(r"\bor\b", between) else "AND"
        rule: Dict[str, Any] = {
            "primitive_id": pid,
            "operator": operator,
            "logic_with_prior": fold,
        }
        if resolved_threshold is not None:
            rule["threshold"] = resolved_threshold
        if resolved_params:
            rule["primitive_params"] = resolved_params
        prev_end = m.end()
        rules.append(rule)
        readings.append(
            _fill(reading, resolved_threshold, resolved_params.get("period")
                  or resolved_params.get("lookback"))
        )

    return rules, readings
