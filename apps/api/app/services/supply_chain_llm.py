"""Dedicated LLM gateway for the supply-chain lens (PRD-25).

The app's default gateway (``get_llm_gateway``) points at whatever ``LLM_BASE_URL``
/ ``LLM_API_KEY`` / ``LLM_MODEL`` are configured (OpenAI by default). The
supply-chain extraction + chokepoint calls can route to a SEPARATE provider —
e.g. DeepSeek for lower cost — WITHOUT changing the model for the rest of the app,
by setting:

    SUPPLY_CHAIN_LLM_BASE_URL    e.g. https://api.deepseek.com/v1
    SUPPLY_CHAIN_LLM_API_KEY     that provider's key
    SUPPLY_CHAIN_EXTRACT_MODEL / SUPPLY_CHAIN_CHOKEPOINT_MODEL   model NAMES

Only the model *name* was overridable before; the base URL + key were shared with
the app, so a DeepSeek model id couldn't reach DeepSeek. This adds a per-feature
gateway. If ``SUPPLY_CHAIN_LLM_BASE_URL`` + ``SUPPLY_CHAIN_LLM_API_KEY`` are not
BOTH set, it falls back to the app's default gateway (so the model-name vars run
against the existing provider).
"""
from __future__ import annotations

import os

from app.core.config import get_settings
from app.services.llm_adapter import LLMGateway, get_llm_gateway


def get_supply_chain_gateway() -> LLMGateway:
    base = os.environ.get("SUPPLY_CHAIN_LLM_BASE_URL", "").strip()
    key = os.environ.get("SUPPLY_CHAIN_LLM_API_KEY", "").strip()
    if not base or not key:
        # No dedicated provider configured — use the app's default gateway.
        return get_llm_gateway()
    settings = get_settings().model_copy(
        update={
            "llm_provider": "openai_compatible",
            "llm_base_url": base,
            "llm_api_key": key,
        }
    )
    return LLMGateway(settings)
