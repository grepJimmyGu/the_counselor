from fastapi import APIRouter

from app.schemas.strategy import (
    StrategyChatRequest,
    StrategyChatResponse,
    StrategyMarkdownParseRequest,
    StrategyMarkdownParseResponse,
)
from app.services.strategy_parser import (
    parse_strategy_markdown,
    parse_strategy_message,
)

router = APIRouter(prefix="/api", tags=["strategy"])


@router.post("/chat/strategy", response_model=StrategyChatResponse)
async def chat_strategy(payload: StrategyChatRequest) -> StrategyChatResponse:
    return await parse_strategy_message(payload.user_message, payload.previous_strategy_json)


@router.post(
    "/strategy/parse-markdown",
    response_model=StrategyMarkdownParseResponse,
)
async def parse_markdown_strategy(
    payload: StrategyMarkdownParseRequest,
) -> StrategyMarkdownParseResponse:
    return await parse_strategy_markdown(payload.markdown_content, payload.document_name)
