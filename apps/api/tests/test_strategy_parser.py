from app.services.strategy_parser import parse_strategy_message


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
