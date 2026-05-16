from functools import lru_cache
from pathlib import Path
from typing import Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_parents = Path(__file__).resolve().parents
ROOT_ENV_FILE = _parents[min(4, len(_parents) - 1)] / ".env"


class Settings(BaseSettings):
    app_name: str = "Livermore API"
    app_env: str = "development"
    alpha_vantage_api_key: str = ""
    financial_modeling_prep_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "livermore-research/1.0"
    internal_api_key: str = ""  # shared secret for Next.js → FastAPI internal calls
    llm_provider: str = "disabled"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_timeout_seconds: float = 45.0
    database_url: str = "sqlite:///./strategylab_ai.db"
    api_timeout_seconds: float = 20.0
    price_cache_stale_hours: int = 24
    allowed_origins: Union[str, list[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "https://livermorealpha.com",
        "https://www.livermorealpha.com",
    ]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Union[str, list[str]]) -> list[str]:
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
