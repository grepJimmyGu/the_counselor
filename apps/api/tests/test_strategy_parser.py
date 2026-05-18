from app.services.strategy_parser import (
    DEFAULT_COMMODITY_BENCHMARK,
    parse_strategy_markdown_fallback,
    parse_strategy_message_fallback,
)


def test_parser_ignores_action_words_and_keeps_actual_ticker():
    response = parse_strategy_message_fallback(
        "Buy AAPL when price is above its 200-day moving average. Sell when below."
    )

    assert response.validation_status == "valid"
    assert response.strategy_json is not None
    assert response.strategy_json.universe == ["AAPL"]
    assert response.strategy_json.strategy_name.startswith("AAPL")


def test_parser_keeps_multiple_real_symbols_for_momentum():
    response = parse_strategy_message_fallback(
        "Every month, buy the top 3 stocks from AAPL, MSFT, NVDA, AMZN, GOOGL based on 6-month return."
    )

    assert response.validation_status == "valid"
    assert response.strategy_json is not None
    assert response.strategy_json.universe == [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
    ]


def test_markdown_parser_extracts_strategy_and_assumptions():
    markdown = """
    # Momentum Rotation Research Note

    Universe: AAPL, MSFT, NVDA, AMZN, GOOGL
    Benchmark: QQQ
    Rebalance: monthly
    Start Date: 2024-01-01
    End Date: 2025-01-31
    Transaction Cost: 10 bps
    Slippage: 15 bps

    Every month, buy the top 3 stocks by 6-month return.
    """

    response = parse_strategy_markdown_fallback(markdown, "rotation.md")

    assert response.validation_status == "valid"
    assert response.strategy_json is not None
    assert response.strategy_json.strategy_type == "momentum_rotation"
    assert response.strategy_json.benchmark == "QQQ"
    assert response.strategy_json.transaction_cost_bps == 10
    assert response.strategy_json.slippage_bps == 15
    assert any(field.field == "benchmark" and field.status == "explicit" for field in response.extracted_fields)


def test_markdown_parser_flags_ambiguity_without_failing_translation():
    markdown = """
    # Trend Strategy

    Universe: AAPL
    Buy strong uptrends when price is above the 200-day moving average.
    Rebalance periodically.
    """

    response = parse_strategy_markdown_fallback(markdown)

    assert response.strategy_json is not None
    assert response.validation_status == "needs_clarification"
    assert response.ambiguities


def test_commodity_chat_parser_sets_dbc_benchmark():
    response = parse_strategy_message_fallback(
        "Buy GLD when price is above its 200-day moving average. Sell when below."
    )

    assert response.validation_status == "valid"
    assert response.strategy_json is not None
    assert response.strategy_json.benchmark == DEFAULT_COMMODITY_BENCHMARK
    assert response.strategy_json.universe == ["GLD"]


def test_commodity_rotation_parser_detects_momentum_type():
    response = parse_strategy_message_fallback(
        "Rotate monthly into the top 2 commodities from GLD, USO, UNG, DBA, SLV by 3-month return."
    )

    assert response.validation_status == "valid"
    assert response.strategy_json is not None
    assert response.strategy_json.strategy_type == "momentum_rotation"
    assert response.strategy_json.benchmark == DEFAULT_COMMODITY_BENCHMARK


def test_mixed_universe_does_not_get_commodity_benchmark():
    response = parse_strategy_message_fallback(
        "Every month rotate into top 2 from AAPL, MSFT, GLD based on momentum."
    )

    assert response.validation_status == "valid"
    assert response.strategy_json is not None
    # Only 1/3 tickers are commodity — should stay on SPY
    assert response.strategy_json.benchmark != DEFAULT_COMMODITY_BENCHMARK


# ── New template parser tests (one per new strategy_type) ────────────────────

def test_low_volatility_detected():
    r = parse_strategy_message_fallback(
        "Build a low volatility strategy over AAPL, MSFT, NVDA, AMZN, GOOGL"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "low_volatility"
    assert r.strategy_json.rebalance_frequency == "monthly"
    assert r.strategy_json.rules[0].lookback_days == 63


def test_sector_rotation_detected():
    r = parse_strategy_message_fallback(
        "Sector rotation across XLK, XLF, XLE, XLV, XLI monthly"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "sector_rotation"
    assert r.strategy_json.rebalance_frequency == "monthly"
    assert r.strategy_json.rules[0].formation_period_days == 126


def test_time_series_momentum_detected():
    r = parse_strategy_message_fallback(
        "Time series momentum on AAPL, MSFT, NVDA using 12-month lookback"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "time_series_momentum"
    assert r.strategy_json.rules[0].lookback_days is not None


def test_cross_sectional_momentum_detected():
    r = parse_strategy_message_fallback(
        "Cross-sectional momentum on AAPL, MSFT, NVDA, AMZN, GOOGL, META"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "cross_sectional_momentum"
    assert r.strategy_json.rules[0].skip_period_days == 21


def test_short_term_reversal_detected():
    r = parse_strategy_message_fallback(
        "Short term reversal on AAPL, MSFT, NVDA, AMZN, GOOGL, META"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "short_term_reversal"
    assert r.strategy_json.rules[0].rank_direction == "bottom"
    assert r.strategy_json.rules[0].formation_period_days == 5


def test_dual_momentum_detected():
    r = parse_strategy_message_fallback(
        "Dual momentum strategy on AAPL, QQQ, TLT monthly"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "dual_momentum"
    assert r.strategy_json.rules[0].formation_period_days == 252


def test_bollinger_mean_reversion_detected():
    r = parse_strategy_message_fallback(
        "Bollinger band mean reversion on AAPL"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "bollinger_mean_reversion"
    assert r.strategy_json.rules[0].lookback_days == 20
    assert r.strategy_json.rules[0].num_std == 2.0


def test_pairs_trading_detected():
    r = parse_strategy_message_fallback(
        "Pairs trading strategy between AAPL and MSFT"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "pairs_trading"
    assert r.strategy_json.rules[0].zscore_entry == 2.0
    assert r.strategy_json.rules[0].zscore_exit == 0.5
    assert len(r.strategy_json.universe) == 2


def test_value_composite_detected():
    r = parse_strategy_message_fallback(
        "Value composite strategy on AAPL, MSFT, JPM, XOM, PG"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "value_composite"
    assert r.strategy_json.rules[0].top_pct == 0.1


def test_quality_piotroski_detected():
    r = parse_strategy_message_fallback(
        "Piotroski F-score quality strategy over AAPL, MSFT, NVDA, JPM, XOM"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "quality_piotroski"
    assert r.strategy_json.rules[0].top_pct == 0.3


def test_buyback_yield_detected():
    r = parse_strategy_message_fallback(
        "Buyback yield strategy on AAPL, MSFT, NVDA, AMZN, GOOGL"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "buyback_yield"
    assert r.strategy_json.rules[0].top_pct == 0.1


def test_pead_drift_detected():
    r = parse_strategy_message_fallback(
        "PEAD drift strategy on AAPL, MSFT, NVDA, AMZN"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "pead_drift"
    assert r.strategy_json.rules[0].holding_window_days == 60
    assert r.strategy_json.rebalance_frequency == "weekly"


def test_earnings_revision_detected():
    r = parse_strategy_message_fallback(
        "Estimate revision momentum on AAPL, MSFT, NVDA, AMZN, GOOGL"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "earnings_revision"
    assert r.strategy_json.rules[0].top_pct == 0.1


def test_news_sentiment_momentum_detected():
    r = parse_strategy_message_fallback(
        "News sentiment momentum strategy on AAPL, MSFT, NVDA, AMZN, GOOGL"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "news_sentiment_momentum"
    assert r.strategy_json.rebalance_frequency == "monthly"


def test_insider_buying_detected():
    r = parse_strategy_message_fallback(
        "Insider buying strategy on AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "insider_buying"
    assert r.strategy_json.rules[0].top_n == 20
    assert r.strategy_json.rebalance_frequency == "weekly"


def test_multi_factor_composite_detected():
    r = parse_strategy_message_fallback(
        "Multi-factor composite strategy on AAPL, MSFT, NVDA, AMZN, GOOGL, JPM, XOM"
    )
    assert r.validation_status == "valid"
    assert r.strategy_json.strategy_type == "multi_factor_composite"
    fw = r.strategy_json.rules[0].factor_weights
    assert fw is not None
    assert set(fw.keys()) == {"value_composite", "momentum_12_1", "quality_f_score", "low_volatility"}
    assert abs(sum(fw.values()) - 1.0) < 1e-6


# ── Clarification state: needs_parameters when no tickers ────────────────────

def test_needs_parameters_for_new_type_without_tickers():
    """
    Phrases where every word is either a RESERVED_TOKEN or exceeds the 5-char
    symbol-pattern limit — so no fake ticker is extracted and the fallback
    parser correctly returns needs_parameters asking for the universe.

    Note: the fallback parser extracts ALL 1–5 letter uppercase tokens not in
    RESERVED_TOKENS as potential tickers.  Phrases are chosen to contain only
    longer words (>5 chars) so that no fake symbol is produced.
    """
    for phrase in [
        "low volatility",          # LOW=reserved, VOLATILITY=10 chars
        "sector rotation",         # SECTOR=6, ROTATION=8
        "insider buying",          # INSIDER=7, BUYING=6
        "bollinger strategy",      # BOLLINGER=9, STRATEGY=8
        "earnings revision",       # EARNINGS=8, REVISION=8
        "estimate revision strategy",  # all > 5 chars
    ]:
        r = parse_strategy_message_fallback(phrase)
        assert r.clarification_state.value == "needs_parameters", (
            f"Expected needs_parameters for '{phrase}', got {r.clarification_state}"
        )
        assert "universe" in r.missing_fields


# ── No regressions: old types still detected ─────────────────────────────────

def test_original_types_still_detected():
    cases = [
        ("Buy AAPL when price is above its 200-day moving average", "moving_average_filter"),
        ("AAPL 50-day crossover 200-day moving average", "moving_average_crossover"),
        ("Buy AAPL when RSI drops below 30", "rsi_mean_reversion"),
        # Use the keyword "breakout" — "breaks above" alone is not enough
        ("AAPL 20-day breakout strategy", "breakout"),
    ]
    for msg, expected in cases:
        r = parse_strategy_message_fallback(msg)
        assert r.strategy_json is not None
        assert r.strategy_json.strategy_type == expected, (
            f"'{msg}' → expected {expected}, got {r.strategy_json.strategy_type}"
        )
