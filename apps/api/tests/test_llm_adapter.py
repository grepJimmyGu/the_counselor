from app.services.llm_adapter import LLMGateway


def test_extract_json_object_from_fenced_block():
    text = """
    Here is the response:

    ```json
    {"hello": "world"}
    ```
    """

    assert LLMGateway._extract_json_object(text) == '{"hello": "world"}'


def test_extract_json_object_from_mixed_text():
    text = 'I think this is the right shape: {"alpha": 1, "beta": [1, 2, 3]} thanks.'

    assert LLMGateway._extract_json_object(text) == '{"alpha": 1, "beta": [1, 2, 3]}'
