from app.services.strategy_parser import parse_strategy_markdown, parse_strategy_message


def test_parser_ignores_action_words_and_keeps_actual_ticker():
    response = parse_strategy_message(
        "Buy AAPL when price is above its 200-day moving average. Sell when below."
    )

    assert response.validation_status == "valid"
    assert response.strategy_json is not None
    assert response.strategy_json.universe == ["AAPL"]
    assert response.strategy_json.strategy_name.startswith("AAPL")


def test_parser_keeps_multiple_real_symbols_for_momentum():
    response = parse_strategy_message(
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

    response = parse_strategy_markdown(markdown, "rotation.md")

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

    response = parse_strategy_markdown(markdown)

    assert response.strategy_json is not None
    assert response.validation_status == "needs_clarification"
    assert response.ambiguities
