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
    # Live quotes behind GET /api/live/quotes (app/services/live_quote_service.py).
    #
    # `live_quote_provider`: "fmp" (default) or "alpha_vantage". The latter
    # asks Alpha Vantage's REALTIME_BULK_QUOTES first and falls back to FMP
    # for any symbol it does not return — including when the key turns out
    # not to be entitled, which AV answers with ARTIFICIAL sample data that
    # must never be shown as a price. Needs a plan that includes "Realtime
    # US Market Data"; serving those prices to users is commercial use, which
    # AV licenses separately — settle that before turning it on.
    #
    # `live_quote_ttl_seconds`: how old a cached quote may be when served
    # from /api/live/quotes. Other callers (Market Pulse asks for ~500
    # symbols at a time) keep the 30 s default regardless.
    #
    # `alpha_vantage_quote_entitlement`: "realtime", "delayed", or empty to
    # let AV pick from the plan.
    live_quote_provider: str = "fmp"
    live_quote_ttl_seconds: float = 30.0
    alpha_vantage_quote_entitlement: str = ""
    # FRED (Federal Reserve Economic Data) — free API used by Macro Pulse to
    # source Growth (Chicago Fed National Activity Index — CFNAI) and Stress
    # (ICE BofA HY OAS — BAMLH0A0HYM2) signals. Falls back to mock data when
    # unset so the page never breaks. Register key at
    # https://fred.stlouisfed.org/docs/api/api_key.html (free, instant).
    fred_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    # SnapTrade — read-only brokerage connection (slice 3). All three must
    # be present or the feature reports itself unconfigured and every route
    # 503s; it never degrades to storing a brokerage credential in the clear.
    #
    # `snaptrade_encryption_key` is a Fernet key protecting the per-user
    # `userSecret` SnapTrade issues at registration. That value cannot be
    # re-derived — it IS the user's identity to SnapTrade — so it must be
    # stored, and a credential to somebody's brokerage connection should not
    # sit in the database in plaintext.
    #
    # Deliberately NOT derived from the JWT secret. Rotating that is a
    # routine security operation; coupling them would make a routine
    # rotation silently orphan every brokerage connection we hold.
    #   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    snaptrade_client_id: str = ""
    snaptrade_consumer_key: str = ""
    snaptrade_encryption_key: str = ""
    # "commercial" (an app serving many users) or "personal" (individual
    # use). Configurable because it depends on the SnapTrade plan behind the
    # key, and getting it wrong should be an env-var flip rather than a
    # code change and redeploy.
    snaptrade_auth_mode: str = "commercial"
    # Order placement (slice 4c). SEPARATE from the read-only connection on
    # purpose: reading holdings and sending orders are different decisions
    # with different consequences, and merging the code should not turn
    # trading on. Defaults OFF — flip deliberately, per environment.
    snaptrade_trading_enabled: bool = False
    reddit_user_agent: str = "livermore-research/1.0"
    internal_api_key: str = ""  # shared secret for Next.js → FastAPI internal calls
    nextauth_secret: str = ""   # signs session JWTs; must match NEXTAUTH_SECRET in Next.js
    # The portfolio agent's scheduled scans. A kill switch: with it off the
    # agent still answers when a user asks it to look.
    agent_monitor_enabled: bool = True
    # Scans of one user's watchlist and holdings that may run at once, across
    # the scheduled job and "Check now". Each takes a database connection and
    # may read the broker, so this is also the most connections the agent's
    # checks can hold. The scheduled job keeps two of these free for people.
    agent_scan_concurrency: int = 8
    # Agent conversations streaming at once. Past this a new one is told the
    # agent is busy rather than left to queue behind the model provider.
    agent_chat_max_concurrent: int = 40
    # The scheduled job stops starting new scans this long after it began, so
    # one run can never run into the next (they are 30 minutes apart).
    agent_monitor_budget_seconds: int = 25 * 60
    google_client_id: str = ""
    # The iOS app's OAuth client. Its ID tokens carry this as their audience,
    # not the website's client ID.
    google_ios_client_id: str = ""
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
    # Ops health alerts (PR-C of 2026-06-07 reliability stack). When
    # enabled, a 1-minute cron polls the in-process /health state and
    # fires an email to `ops_alert_recipient` when the pulse warmup flips
    # to degraded. Off by default — turn on only when an `ops_alert_recipient`
    # mailbox exists. Cooldown prevents spamming when degraded persists.
    ops_health_alerts_enabled: bool = False
    ops_alert_recipient: str = ""
    ops_health_alert_cooldown_minutes: int = 60
    # PR-D — triage context bundle. Shared-secret token guards the
    # /internal/triage-context endpoint, which exposes /health + commit
    # SHAs + suspected trap matches. Embed in the PR-C alert email's
    # "Open triage" link so the one-click flow works for Jimmy without
    # exposing the bundle to anyone with the URL.
    ops_triage_token: str = ""
    frontend_url: str = "http://localhost:3000"  # used for portal/checkout return URLs
    llm_provider: str = "disabled"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_timeout_seconds: float = 45.0
    database_url: str = "sqlite:///./strategylab_ai.db"
    # Postgres connections. SQLAlchemy's defaults are 5 + 10 overflow = 15,
    # and FastAPI runs up to 40 plain-`def` routes at once, each holding one
    # for its whole request: the sixteenth waits 30 s and then fails. 10 + 20
    # leaves room for the scheduler's jobs and for the agent's scans, and two
    # containers during a deploy (60) still fit under Postgres's default 100.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # Connections older than this are replaced rather than reused, so one a
    # proxy has silently dropped is not handed to a request.
    db_pool_recycle_seconds: int = 1800
    api_timeout_seconds: float = 20.0
    price_cache_stale_hours: int = 24
    # Rows a day that `price_basis_service` may rewrite to bring adjusted
    # closes onto today's basis; about 220 bytes of table and index each, so
    # the default is some 110 MB. Zero turns reconciling off.
    price_basis_daily_row_budget: int = 500_000
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
