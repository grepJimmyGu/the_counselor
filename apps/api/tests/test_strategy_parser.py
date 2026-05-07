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
