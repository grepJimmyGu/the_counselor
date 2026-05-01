from fastapi import APIRouter

from app.schemas.strategy import StrategyChatRequest, StrategyChatResponse
from app.services.strategy_parser import parse_strategy_message

router = APIRouter(prefix="/api/chat", tags=["strategy"])


@router.post("/strategy", response_model=StrategyChatResponse)
async def chat_strategy(payload: StrategyChatRequest) -> StrategyChatResponse:
    return parse_strategy_message(payload.user_message, payload.previous_strategy_json)

