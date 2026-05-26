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
    # FRED (Federal Reserve Economic Data) — free API used by Macro Pulse to
    # source Growth (Chicago Fed National Activity Index — CFNAI) and Stress
    # (ICE BofA HY OAS — BAMLH0A0HYM2) signals. Falls back to mock data when
    # unset so the page never breaks. Register key at
    # https://fred.stlouisfed.org/docs/api/api_key.html (free, instant).
    fred_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "livermore-research/1.0"
    internal_api_key: str = ""  # shared secret for Next.js → FastAPI internal calls
    nextauth_secret: str = ""   # signs session JWTs; must match NEXTAUTH_SECRET in Next.js
    google_client_id: str = ""
    google_client_secret: str = ""
    # Stage 2 — Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_strategist_monthly: str = ""
    stripe_price_strategist_annual: str = ""
    stripe_price_quant_monthly: str = ""
    stripe_price_quant_annual: str = ""
    # Stage 3 — gating feature flag. Defaults to False (shadow mode: log would-be
    # 402s but allow the request). Flip to True in production after observing
    # shadow-mode telemetry for ~24h. Stage 6 will replace this with a PostHog flag.
    gating_enabled: bool = False
    # Stage 8 v0 — signals & alerts feature flag. Defaults to False. Gates the
    # /api/saved-strategies/{id}/signal endpoints AND the daily recompute cron
    # (Phase B). Must remain False in production until the disclaimer copy has
    # been blessed by a securities attorney — see
    # build_specs/research_execution_v0_signals_and_alerts.md §11, §15.
    signal_alerts_enabled: bool = False
    # Stage 6a — analytics + email. All empty defaults so the no-op wrappers
    # silently skip when keys aren't configured (local dev, CI, pre-launch).
    posthog_api_key: str = ""
    posthog_host: str = "https://us.posthog.com"
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    resend_from_transactional: str = "team@livermorealpha.com"
    resend_from_marketing: str = "growth@livermorealpha.com"
    email_unsub_signing_key: str = ""  # 32-byte hex; HMAC-signs unsub tokens
    frontend_url: str = "http://localhost:3000"  # used for portal/checkout return URLs
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
