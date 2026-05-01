from functools import lru_cache
from pathlib import Path
from typing import Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_parents = Path(__file__).resolve().parents
ROOT_ENV_FILE = _parents[min(4, len(_parents) - 1)] / ".env"


class Settings(BaseSettings):
    app_name: str = "StrategyLab AI API"
    app_env: str = "development"
    alpha_vantage_api_key: str = ""
    database_url: str = "sqlite:///./strategylab_ai.db"
    api_timeout_seconds: float = 20.0
    price_cache_stale_hours: int = 24
    allowed_origins: Union[str, list[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
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
