from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from app.core.config import get_settings
from app.schemas.strategy import (
    ClarificationState,
    CashManagement,
    PositionSizing,
    RiskManagement,
    StrategyChatResponse,
    StrategyExtractedField,
    StrategyJSON,
    StrategyMarkdownParseResponse,
    StrategyRule,
)
from app.services.llm_adapter import LLMAdapterError, get_llm_gateway


DEFAULT_BENCHMARK = "SPY"
DEFAULT_COMMODITY_BENCHMARK = "DBC"
SYMBOL_PATTERN = re.compile(r"\b[A-Z]{1,5}\b")

COMMODITY_TICKERS = {
    "GLD", "IAU", "SGOL",
    "SLV", "SIVR",
    "GDX", "GDXJ",
    "USO", "UCO", "BNO",
    "UNG", "BOIL",
    "XLE", "VDE",
    "DBA",
    "DBC", "PDBC", "COMT",
    "CPER", "COPX",
    "WEAT", "CORN", "SOYB",
    "DBB", "UGA",
    "PALL", "PPLT",
}
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
RESERVED_TOKENS = {
    "A",
    "AN",
    "AND",
    "ABOVE",
    "AT",
    "AVERAGE",
    "BASED",
    "BELOW",
    "BUY",
    "DAY",
    "DAYS",
    "EVERY",
    "FROM",
    "HOLD",
    "IS",
    "ITS",
    "LOW",
    "MONTH",
    "MONTHS",
    "MOVING",
    "OF",
    "ON",
    "OR",
    "PRICE",
    "RETURN",
    "SELL",
    "STOCK",
    "STOCKS",
    "THE",
    "THEN",
    "TOP",
    "WHEN",
}
AMBIGUOUS_TERMS = {
    "reasonable": "The memo uses 'reasonable', which still needs a concrete parameter.",
    "strong": "The memo refers to 'strong' conditions without a deterministic threshold.",
    "periodically": "The rebalance cadence is described as 'periodically' without a fixed schedule.",
    "favor": "The memo says to 'favor' something, but position sizing rules are not explicit.",
    "liquid": "The memo mentions liquidity without a concrete liquidity screen.",
    "may": "The memo uses discretionary language like 'may', which is not directly backtestable.",
}
SUPPORTED_STRATEGY_FAMILIES = (
    "moving_average_filter, moving_average_crossover, momentum_rotation, "
    "rsi_mean_reversion, breakout, static_allocation"
)


def _json_schema_text(model_type: type[object]) -> str:
    return str(model_type.model_json_schema())  # type: ignore[attr-defined]


# Computed once at import time — avoids rebuilding the Pydantic schema on every request
_CHAT_PARSE_SYSTEM_PROMPT: str = (
    "You are a strategy parsing assistant for a deterministic backtesting engine. "
    "Convert the user's request into JSON matching the provided schema. "
    "Only use supported strategy families: "
    f"{SUPPORTED_STRATEGY_FAMILIES}. "
    "Map common indicator names to the closest supported family "
    "(descriptions may be in English or Chinese): "
    "MACD / MACD指标 (any period combination) → moving_average_crossover (use the two MACD periods as fast_window and slow_window); "
    "EMA crossover / SMA crossover / 均线交叉 / 上穿 / 下穿 / 金叉 / 死叉 → moving_average_crossover; "
    "golden cross / death cross → moving_average_crossover (50/200); "
    "price above/below moving average / 价格高于均线 / 价格低于均线 / 高于N日均线 / 低于N日均线 → moving_average_filter; "
    "relative strength / RSI / 相对强弱 → rsi_mean_reversion; "
    "52-week high / channel breakout / 突破 / 新高 → breakout; "
    "fixed weight portfolio / 固定比例 / 配置 → static_allocation; "
    "commodity trend following / CTA trend / price trend on commodity → moving_average_filter or moving_average_crossover; "
    "commodity momentum / rotate commodities / commodity rotation / 大宗商品动量 → momentum_rotation (monthly rebalance); "
    "commodity seasonality / seasonal commodity / 季节性 → momentum_rotation (monthly rebalance, use total_return ranking); "
    "commodity carry / roll yield / spread → static_allocation. "
    "For momentum_rotation strategies, always populate the rules array with exactly one rule: "
    "{top_n: <number of assets to hold>, ranking_measure: 'total_return', ranking_lookback_days: <lookback in trading days>}. "
    "Also set position_sizing.max_positions to the same value as top_n. "
    "Example: 'top 2 by 3-month return' → rules=[{top_n:2, ranking_measure:'total_return', ranking_lookback_days:63}], max_positions=2. "
    "Map common index and asset class names to their ETF tickers: "
    "S&P 500 / SPX / large cap US → SPY; "
    "Nasdaq / Nasdaq 100 / QQQ / tech → QQQ; "
    "Dow Jones / DJIA → DIA; "
    "Russell 2000 / small cap → IWM; "
    "emerging markets → EEM; "
    "international developed → EFA; "
    "US bonds / treasuries / fixed income → TLT (long) or IEF (medium) or SHY (short); "
    "gold / precious metals / bullion → GLD; "
    "silver → SLV; "
    "gold miners / gold mining stocks → GDX; "
    "crude oil / oil / WTI / Brent / petroleum → USO; "
    "natural gas → UNG; "
    "energy sector / energy stocks → XLE; "
    "agriculture / agricultural commodities / grains / farm → DBA; "
    "broad commodities / commodity index / diversified commodities / commodity basket → DBC; "
    "copper → CPER; "
    "wheat → WEAT; "
    "corn → CORN; "
    "soybeans / soy → SOYB; "
    "base metals → DBB; "
    "real estate / REITs → VNQ; "
    "total market → VTI. "
    "Always replace index names with their ETF ticker in the universe field. "
    "If the universe contains any Shanghai (.SHH) or Shenzhen (.SHZ) tickers, "
    "default the benchmark to 510300.SHH (CSI 300 ETF) instead of SPY. "
    "If the universe contains primarily commodity ETFs (GLD, SLV, USO, UNG, DBA, DBC, "
    "CPER, WEAT, CORN, SOYB, XLE, GDX, DBB, etc.), default the benchmark to DBC "
    "(Bloomberg Commodity ETF) instead of SPY. "
    "For commodity strategies, also note that ETF prices do not capture roll yield or "
    "contango/backwardation effects — the backtest reflects ETF price return only. "
    "Use these defaults for any field the user does not specify: "
    "benchmark=SPY, start_date=1 year before today, end_date=today, "
    "initial_capital=100000, rebalance_frequency=daily, transaction_cost_bps=5, slippage_bps=5, "
    "position_sizing.method=equal_weight. "
    "Only set validation_status to needs_clarification if the user has not provided "
    "a ticker symbol (universe) or a recognizable strategy type — these are the only two truly required fields. "
    "For all other missing fields apply the defaults above and return a valid strategy_json. "
    "Do not invent unsupported rules or arbitrary code. "
    "\n\n"
    "CLARIFICATION STATE RULES — always set clarification_state:\n"
    "Set clarification_state='needs_parameters' when:\n"
    "  - The strategy type is one of the supported families listed above\n"
    "  - AND one or more quantifiable parameters are missing or ambiguous:\n"
    "    lookback period, entry/exit threshold, universe of tickers, stop loss %, "
    "position sizing, rebalance frequency\n"
    "  - Populate clarification_questions with SPECIFIC, ANSWERABLE questions. "
    "Each question must correspond to exactly one missing parameter. Max 3 questions per turn. "
    "Ask the most blocking question first.\n"
    "  - GOOD: 'Over what lookback period should I check the moving average? (e.g. 50 days, 200 days)'\n"
    "  - BAD: 'Can you clarify your strategy?'\n"
    "\n"
    "Set clarification_state='not_supported' when the strategy requires:\n"
    "  - Signals derived from a DIFFERENT asset than the one being traded "
    "(e.g. 'buy gold when oil is up' — signal is oil price, trade target is gold)\n"
    "  - Fundamental data: P/E ratio, earnings, revenue, dividends, book value\n"
    "  - Macro or sentiment data: VIX, CPI, Fed funds rate, news sentiment, economic indicators\n"
    "  - Short selling, leverage, options, futures\n"
    "  - Intraday data (signals defined in minutes or hours)\n"
    "  For not_supported: set unsupported_reason to a brief plain-language explanation, "
    "and set suggested_reformulation to the closest supported equivalent "
    "(e.g. 'Use GLD with a 1-month moving average filter as a trend proxy').\n"
    "\n"
    "Set clarification_state='ready' when:\n"
    "  - strategy_json is fully populated with no missing required fields\n"
    "  - All parameters have explicit or clearly implied values\n"
    "\n"
    "APPROXIMATION TRANSPARENCY — when you map an under-specified or partially-unsupported "
    "intent to a supported strategy type, ALWAYS set approximation_note to a plain-language "
    "explanation of what proxy or simplification was used. "
    "Example: 'I am interpreting oil is up as USO's 1-month return being positive, "
    "and using that as a moving-average filter on GLD — the closest supported equivalent.' "
    "Leave approximation_note null when the mapping is direct with no approximation needed.\n\n"
    "Return JSON only.\n\n"
    f"Response schema: {_json_schema_text(StrategyChatResponse)}"
)

_MARKDOWN_PARSE_SYSTEM_PROMPT: str = (
    "You are a quant research memo parser. Read the markdown memo and convert it into "
    "structured strategy JSON for a deterministic backtester. "
    "The markdown is human intent, not executable code. "
    "Only map the memo into supported strategy families: "
    f"{SUPPORTED_STRATEGY_FAMILIES}. "
    "Preserve uncertainty with ambiguities, assumption_log, missing_fields, and clarification_questions. "
    "When you have enough structure, include a valid strategy_json. Return JSON only.\n\n"
    f"Response schema: {_json_schema_text(StrategyMarkdownParseResponse)}"
)


def _chat_parse_user_prompt(
    user_message: str, previous_strategy_json: Optional[StrategyJSON]
) -> str:
    previous_payload = (
        previous_strategy_json.model_dump_json(indent=2)
        if previous_strategy_json is not None
        else "null"
    )
    return (
        f"Today: {date.today().isoformat()}\n"
        f"User message:\n{user_message}\n\n"
        f"Previous strategy JSON:\n{previous_payload}\n\n"
        "Interpret this into the response schema."
    )


def _markdown_parse_user_prompt(markdown_content: str, document_name: Optional[str]) -> str:
    return (
        f"Document name: {document_name or 'strategy-memo.md'}\n"
        f"Default benchmark if missing: {DEFAULT_BENCHMARK}\n"
        f"Default initial capital if missing: 100000\n"
        f"Default transaction cost if missing: 5 bps\n"
        f"Default slippage if missing: 5 bps\n"
        f"Today: {date.today().isoformat()}\n\n"
        f"Markdown memo:\n{markdown_content}\n\n"
        "Extract the strategy into the response schema."
    )


def _find_first_number(pattern: str, text: str) -> Optional[int]:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def _format_field_value(value: object) -> str:
    if value is None:
        return "Not provided"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}: {val}" for key, val in value.items())
    return str(value)


def _summarize_markdown(markdown_content: str, document_name: Optional[str]) -> str:
    heading_match = re.search(r"^\s*#\s+(.+)$", markdown_content, flags=re.MULTILINE)
    if heading_match:
        title = heading_match.group(1).strip()
        return f"{document_name or 'Strategy memo'} centers on '{title}'."

    first_paragraph = next(
        (line.strip() for line in markdown_content.splitlines() if line.strip()), ""
    )
    trimmed = first_paragraph[:140].rstrip()
    if len(first_paragraph) > 140:
        trimmed += "..."
    return f"{document_name or 'Strategy memo'} starts with: {trimmed}"


def _is_commodity_universe(symbols: list[str]) -> bool:
    if not symbols:
        return False
    commodity_count = sum(1 for s in symbols if s in COMMODITY_TICKERS)
    return commodity_count / len(symbols) >= 0.5


def _extract_symbols(message: str) -> list[str]:
    matches = SYMBOL_PATTERN.findall(message.upper())
    filtered = [
        token for token in matches if token not in RESERVED_TOKENS and len(token) >= 2
    ]
    return list(dict.fromkeys(filtered))


def _extract_strategy_type(text: str) -> Optional[str]:
    lowered = text.lower()
    if "rsi" in lowered:
        return "rsi_mean_reversion"
    if "breakout" in lowered or ("day high" in lowered and "day low" in lowered):
        return "breakout"
    if "allocation" in lowered or "carry" in lowered or re.search(r"\b\d+%\s+[A-Z]{1,5}\b", text):
        return "static_allocation"
    if (
        "top " in lowered
        or "momentum" in lowered
        or "rank" in lowered
        or "rotation" in lowered
        or "seasonal" in lowered
    ):
        return "momentum_rotation"
    if "crossover" in lowered or (
        "moving average" in lowered and len(re.findall(r"(\d+)[-\s]?day", lowered)) >= 2
    ):
        return "moving_average_crossover"
    if "moving average" in lowered or "ema" in lowered or "trend" in lowered:
        return "moving_average_filter"
    return None


def _extract_rebalance_frequency(text: str) -> Optional[str]:
    lowered = text.lower()
    for frequency in ("daily", "weekly", "monthly", "quarterly"):
        if frequency in lowered:
            return frequency
    if "every month" in lowered:
        return "monthly"
    if "every week" in lowered:
        return "weekly"
    if "every quarter" in lowered:
        return "quarterly"
    return None


def _extract_benchmark(text: str) -> Optional[str]:
    benchmark_match = re.search(
        r"benchmark(?:\s+is|\s*[:\-])?\s*([A-Z]{2,5})", text, flags=re.IGNORECASE
    )
    return benchmark_match.group(1).upper() if benchmark_match else None


def _extract_dates(text: str) -> tuple[Optional[date], Optional[date]]:
    matches = DATE_PATTERN.findall(text)
    if len(matches) >= 2:
        return date.fromisoformat(matches[0]), date.fromisoformat(matches[1])
    if len(matches) == 1:
        start_match = re.search(rf"(?:start|from)[^\n]*{re.escape(matches[0])}", text, re.IGNORECASE)
        end_match = re.search(rf"(?:end|to|through)[^\n]*{re.escape(matches[0])}", text, re.IGNORECASE)
        if start_match:
            return date.fromisoformat(matches[0]), None
        if end_match:
            return None, date.fromisoformat(matches[0])
    return None, None


def _extract_initial_capital(text: str) -> Optional[float]:
    match = re.search(
        r"(?:initial capital|starting capital|capital)(?:\s+of|\s*[:\-])?\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    return float(match.group(1).replace(",", "")) if match else None


def _extract_bps(text: str, label: str) -> Optional[float]:
    match = re.search(rf"{label}[^\n]{{0,30}}?(\d+(?:\.\d+)?)\s*bps", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    percent_match = re.search(
        rf"{label}[^\n]{{0,30}}?(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE
    )
    return float(percent_match.group(1)) * 100 if percent_match else None


def _extract_risk_management(text: str) -> RiskManagement:
    stop_loss = re.search(r"stop loss[^\n]{0,20}?(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
    take_profit = re.search(r"take profit[^\n]{0,20}?(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
    max_drawdown = re.search(r"max drawdown[^\n]{0,20}?(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
    return RiskManagement(
        stop_loss_pct=(float(stop_loss.group(1)) / 100) if stop_loss else None,
        take_profit_pct=(float(take_profit.group(1)) / 100) if take_profit else None,
        max_drawdown_stop=(float(max_drawdown.group(1)) / 100) if max_drawdown else None,
    )


def _extract_static_weights(text: str, symbols: list[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for symbol in symbols:
        match = re.search(rf"(\d+(?:\.\d+)?)%\s+{symbol}\b", text, flags=re.IGNORECASE)
        if match:
            weights[symbol] = float(match.group(1)) / 100
    return weights


def _infer_strategy_from_text(
    text: str, symbols: list[str], strategy_type: str, rebalance_frequency: Optional[str]
) -> StrategyJSON:
    lowered = text.lower()
    if strategy_type == "moving_average_filter":
        lookback = _find_first_number(r"(\d+)[-\s]?day", lowered) or 200
        strategy = _base_strategy(
            strategy_name=f"{symbols[0]} {lookback}-Day Moving Average Filter",
            strategy_type="moving_average_filter",
            universe=[symbols[0]],
            rebalance_frequency=rebalance_frequency or "daily",
            rules=[
                StrategyRule(
                    indicator="moving_average",
                    lookback_days=lookback,
                    operator="gt",
                    source="adjusted_close",
                )
            ],
            position_sizing=PositionSizing(method="equal_weight", max_positions=1),
        )
    elif strategy_type == "moving_average_crossover":
        windows = [int(item) for item in re.findall(r"(\d+)[-\s]?day", lowered)]
        fast_window = windows[0] if windows else 50
        slow_window = windows[1] if len(windows) > 1 else 200
        strategy = _base_strategy(
            strategy_name=f"{symbols[0]} {fast_window}/{slow_window} Moving Average Crossover",
            strategy_type="moving_average_crossover",
            universe=[symbols[0]],
            rebalance_frequency=rebalance_frequency or "daily",
            rules=[
                StrategyRule(
                    indicator="moving_average",
                    fast_window=fast_window,
                    slow_window=slow_window,
                )
            ],
            position_sizing=PositionSizing(method="equal_weight", max_positions=1),
        )
    elif strategy_type == "momentum_rotation":
        top_n = _find_first_number(r"top\s+(\d+)", lowered) or min(3, len(symbols))
        lookback_months = _find_first_number(r"(\d+)[-\s]?month", lowered) or 6
        strategy = _base_strategy(
            strategy_name="Momentum Rotation",
            strategy_type="momentum_rotation",
            universe=symbols,
            rebalance_frequency=rebalance_frequency or "monthly",
            rules=[
                StrategyRule(
                    top_n=top_n,
                    ranking_measure="total_return",
                    ranking_lookback_days=lookback_months * 21,
                )
            ],
            position_sizing=PositionSizing(method="equal_weight", max_positions=top_n),
        )
        strategy.cash_management.hold_cash_when_no_signal = False
    elif strategy_type == "rsi_mean_reversion":
        below_matches = [int(item) for item in re.findall(r"below\s+(\d+)", lowered)]
        above_matches = [int(item) for item in re.findall(r"above\s+(\d+)", lowered)]
        buy_level = below_matches[0] if below_matches else 30
        sell_level = above_matches[0] if above_matches else 60
        strategy = _base_strategy(
            strategy_name=f"{symbols[0]} RSI Mean Reversion",
            strategy_type="rsi_mean_reversion",
            universe=[symbols[0]],
            rebalance_frequency=rebalance_frequency or "daily",
            rules=[
                StrategyRule(indicator="rsi", lookback_days=14, operator="lt", threshold=buy_level),
                StrategyRule(indicator="rsi", lookback_days=14, operator="gt", threshold=sell_level),
            ],
            position_sizing=PositionSizing(method="equal_weight", max_positions=1),
        )
    elif strategy_type == "breakout":
        windows = [int(item) for item in re.findall(r"(\d+)[-\s]?day", lowered)]
        entry_window = windows[0] if windows else 60
        exit_window = windows[1] if len(windows) > 1 else 20
        strategy = _base_strategy(
            strategy_name=f"{symbols[0]} Breakout Strategy",
            strategy_type="breakout",
            universe=[symbols[0]],
            rebalance_frequency=rebalance_frequency or "daily",
            rules=[StrategyRule(entry_window=entry_window, exit_window=exit_window)],
            position_sizing=PositionSizing(method="equal_weight", max_positions=1),
        )
    else:
        weights = _extract_static_weights(text, symbols)
        if not weights:
            equal_weight = round(1 / len(symbols), 4)
            weights = {symbol: equal_weight for symbol in symbols}
        strategy = _base_strategy(
            strategy_name="Static Allocation",
            strategy_type="static_allocation",
            universe=list(weights.keys()),
            rebalance_frequency=rebalance_frequency or "monthly",
            rules=[],
            position_sizing=PositionSizing(method="fixed_weight", weights=weights),
        )
        strategy.cash_management.hold_cash_when_no_signal = False

    return strategy


def _extract_assumptions_and_fields(
    strategy: StrategyJSON,
    strategy_type_found: bool,
    benchmark_found: bool,
    start_date_found: bool,
    end_date_found: bool,
    capital_found: bool,
    rebalance_found: bool,
    transaction_cost_found: bool,
    slippage_found: bool,
) -> tuple[list[str], list[StrategyExtractedField]]:
    assumption_log: list[str] = []
    extracted_fields: list[StrategyExtractedField] = []

    field_specs = [
        ("strategy_type", strategy.strategy_type, strategy_type_found, "Supported strategy family inferred from the memo."),
        ("universe", strategy.universe, True, ""),
        ("benchmark", strategy.benchmark, benchmark_found, f"Defaulted benchmark to {DEFAULT_BENCHMARK}."),
        ("start_date", strategy.start_date.isoformat(), start_date_found, "Defaulted start date to one year before the end date."),
        ("end_date", strategy.end_date.isoformat(), end_date_found, "Defaulted end date to today."),
        ("initial_capital", strategy.initial_capital, capital_found, "Defaulted initial capital to 100000."),
        ("rebalance_frequency", strategy.rebalance_frequency, rebalance_found, f"Defaulted rebalance frequency to {strategy.rebalance_frequency}."),
        ("transaction_cost_bps", strategy.transaction_cost_bps, transaction_cost_found, "Defaulted transaction cost to 5 bps."),
        ("slippage_bps", strategy.slippage_bps, slippage_found, "Defaulted slippage to 5 bps."),
    ]

    for field_name, value, is_explicit, assumption in field_specs:
        status = "explicit" if is_explicit else "inferred"
        extracted_fields.append(
            StrategyExtractedField(
                field=field_name,
                value=_format_field_value(value),
                status=status,
            )
        )
        if not is_explicit and assumption:
            assumption_log.append(assumption)

    return assumption_log, extracted_fields


def _extract_ambiguities(text: str, strategy_type: str, symbols: list[str]) -> list[str]:
    ambiguities = [
        message for term, message in AMBIGUOUS_TERMS.items() if term in text.lower()
    ]
    if strategy_type in {
        "moving_average_filter",
        "moving_average_crossover",
        "rsi_mean_reversion",
        "breakout",
    } and len(symbols) > 1:
        ambiguities.append(
            "The memo names multiple tickers, but the detected strategy family is single-asset in the current engine."
        )
    return ambiguities


def _base_strategy(
    strategy_name: str,
    strategy_type: str,
    universe: list[str],
    rebalance_frequency: str,
    rules: list[StrategyRule],
    position_sizing: PositionSizing,
) -> StrategyJSON:
    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    return StrategyJSON(
        strategy_name=strategy_name,
        strategy_type=strategy_type,
        universe=universe,
        benchmark=DEFAULT_BENCHMARK,
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=rules,
        position_sizing=position_sizing,
        risk_management=RiskManagement(),
        cash_management=CashManagement(hold_cash_when_no_signal=True),
    )


def parse_strategy_message_fallback(
    user_message: str, previous_strategy_json: Optional[StrategyJSON] = None
) -> StrategyChatResponse:
    message = user_message.strip()
    lowered = message.lower()
    symbols = _extract_symbols(message)

    # Shortcut: user is updating the benchmark on an existing strategy
    if previous_strategy_json and "benchmark" in lowered and symbols:
        updated = previous_strategy_json.model_copy(deep=True)
        updated.benchmark = symbols[0]
        return StrategyChatResponse(
            assistant_message=f"Updated the benchmark to {updated.benchmark}.",
            strategy_json=updated,
            validation_status="valid",
            missing_fields=[],
            clarification_questions=[],
            clarification_state=ClarificationState.ready,
        )

    if not symbols:
        return StrategyChatResponse(
            assistant_message="I can draft the strategy shape, but I still need at least one ticker symbol.",
            strategy_json=None,
            validation_status="needs_clarification",
            missing_fields=["universe"],
            clarification_questions=["Which stock or ETF symbols should this strategy trade? (e.g. SPY, GLD, AAPL)"],
            clarification_state=ClarificationState.needs_parameters,
        )

    strategy_type = _extract_strategy_type(message)
    if not strategy_type:
        return StrategyChatResponse(
            assistant_message="I recognised the tickers, but I need the strategy style.",
            strategy_json=None,
            validation_status="needs_clarification",
            missing_fields=["strategy_type", "rules"],
            clarification_questions=[
                "Which strategy type should I use: moving average filter, MA crossover, momentum rotation, RSI mean reversion, breakout, or static allocation?"
            ],
            clarification_state=ClarificationState.needs_parameters,
        )

    try:
        strategy = _infer_strategy_from_text(
            message, symbols, strategy_type, _extract_rebalance_frequency(message)
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        return StrategyChatResponse(
            assistant_message=f"I couldn't safely translate that into the supported schema yet: {exc}",
            strategy_json=None,
            validation_status="invalid",
            missing_fields=["strategy_json"],
            clarification_questions=[],
            clarification_state=ClarificationState.needs_parameters,
        )

    if _is_commodity_universe(strategy.universe):
        strategy.benchmark = DEFAULT_COMMODITY_BENCHMARK

    return StrategyChatResponse(
        assistant_message=f"I interpreted your idea as a {strategy.strategy_type.replace('_', ' ')} strategy over {', '.join(strategy.universe)}.",
        strategy_json=strategy,
        validation_status="valid",
        missing_fields=[],
        clarification_questions=[],
        clarification_state=ClarificationState.ready,
    )


def parse_strategy_markdown_fallback(
    markdown_content: str,
    document_name: Optional[str] = None,
) -> StrategyMarkdownParseResponse:
    text = markdown_content.strip()
    source_summary = _summarize_markdown(text, document_name)
    symbols = _extract_symbols(text)
    strategy_type = _extract_strategy_type(text)
    missing_fields: list[str] = []
    clarification_questions: list[str] = []

    if not symbols:
        missing_fields.append("universe")
        clarification_questions.append("Which ticker symbols should this strategy trade?")
    if not strategy_type:
        missing_fields.append("strategy_type")
        clarification_questions.append(
            "Which supported strategy family does this memo map to: moving average filter, crossover, momentum rotation, RSI mean reversion, breakout, or static allocation?"
        )

    if missing_fields:
        return StrategyMarkdownParseResponse(
            assistant_message="I could read the memo, but I still need a few concrete fields before I can convert it into deterministic strategy JSON.",
            strategy_json=None,
            validation_status="needs_clarification",
            extracted_fields=[
                StrategyExtractedField(field=field_name, value="Not provided", status="missing")
                for field_name in missing_fields
            ],
            ambiguities=_extract_ambiguities(text, strategy_type or "", symbols),
            assumption_log=[],
            missing_fields=missing_fields,
            clarification_questions=clarification_questions,
            source_summary=source_summary,
        )

    assert strategy_type is not None  # for typing
    strategy = _infer_strategy_from_text(
        text,
        symbols,
        strategy_type,
        _extract_rebalance_frequency(text),
    )

    benchmark = _extract_benchmark(text)
    if benchmark:
        strategy.benchmark = benchmark
    elif _is_commodity_universe(strategy.universe):
        strategy.benchmark = DEFAULT_COMMODITY_BENCHMARK

    start_date, end_date = _extract_dates(text)
    if end_date:
        strategy.end_date = end_date
    if start_date:
        strategy.start_date = start_date
    elif end_date:
        strategy.start_date = end_date - timedelta(days=365)

    initial_capital = _extract_initial_capital(text)
    if initial_capital:
        strategy.initial_capital = initial_capital

    transaction_cost_bps = _extract_bps(text, "transaction cost")
    if transaction_cost_bps is not None:
        strategy.transaction_cost_bps = transaction_cost_bps

    slippage_bps = _extract_bps(text, "slippage")
    if slippage_bps is not None:
        strategy.slippage_bps = slippage_bps

    strategy.risk_management = _extract_risk_management(text)

    validation_status = "valid"
    ambiguities = _extract_ambiguities(text, strategy_type, symbols)

    assumption_log, extracted_fields = _extract_assumptions_and_fields(
        strategy=strategy,
        strategy_type_found=True,
        benchmark_found=benchmark is not None,
        start_date_found=start_date is not None,
        end_date_found=end_date is not None,
        capital_found=initial_capital is not None,
        rebalance_found=_extract_rebalance_frequency(text) is not None,
        transaction_cost_found=transaction_cost_bps is not None,
        slippage_found=slippage_bps is not None,
    )

    if ambiguities:
        validation_status = "needs_clarification"
        clarification_questions.extend(
            [
                "Should I keep the inferred defaults, or do you want explicit parameters for the ambiguous parts of the memo?"
            ]
        )

    return StrategyMarkdownParseResponse(
        assistant_message=(
            f"I translated the markdown memo into a {strategy.strategy_type.replace('_', ' ')} strategy and preserved the assumptions separately so you can review them before the backtest."
        ),
        strategy_json=strategy,
        validation_status=validation_status,
        extracted_fields=extracted_fields,
        ambiguities=ambiguities,
        assumption_log=assumption_log,
        missing_fields=[],
        clarification_questions=clarification_questions,
        source_summary=source_summary,
    )


def _locale_instruction(locale: str) -> str:
    return " Respond in Simplified Chinese (中文)." if locale == "zh" else ""


def _fix_momentum_rules(response: StrategyChatResponse, user_message: str) -> StrategyChatResponse:
    """If the LLM returned a momentum_rotation strategy with no rules, fill them in."""
    s = response.strategy_json
    if not s or s.strategy_type != "momentum_rotation" or s.rules:
        return response
    lowered = user_message.lower()
    top_n = _find_first_number(r"top\s+(\d+)", lowered) or min(3, len(s.universe))
    lookback_months = _find_first_number(r"(\d+)[-\s]?month", lowered) or 6
    s.rules = [
        StrategyRule(
            top_n=top_n,
            ranking_measure="total_return",
            ranking_lookback_days=lookback_months * 21,
        )
    ]
    s.position_sizing.max_positions = top_n
    return response


async def parse_strategy_message(
    user_message: str,
    previous_strategy_json: Optional[StrategyJSON] = None,
    locale: str = "en",
) -> StrategyChatResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return parse_strategy_message_fallback(user_message, previous_strategy_json)

    system_prompt = _CHAT_PARSE_SYSTEM_PROMPT + _locale_instruction(locale)
    try:
        result = await gateway.generate_structured(
            model=get_settings().llm_model,
            system_prompt=system_prompt,
            user_prompt=_chat_parse_user_prompt(user_message, previous_strategy_json),
            response_model=StrategyChatResponse,
            temperature=0.1,
        )
        return _fix_momentum_rules(result, user_message)
    except LLMAdapterError:
        return parse_strategy_message_fallback(user_message, previous_strategy_json)


async def parse_strategy_markdown(
    markdown_content: str,
    document_name: Optional[str] = None,
    locale: str = "en",
) -> StrategyMarkdownParseResponse:
    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        return parse_strategy_markdown_fallback(markdown_content, document_name)

    system_prompt = _MARKDOWN_PARSE_SYSTEM_PROMPT + _locale_instruction(locale)
    try:
        return await gateway.generate_structured(
            model=get_settings().llm_model,
            system_prompt=system_prompt,
            user_prompt=_markdown_parse_user_prompt(markdown_content, document_name),
            response_model=StrategyMarkdownParseResponse,
            temperature=0.1,
        )
    except LLMAdapterError:
        return parse_strategy_markdown_fallback(markdown_content, document_name)
