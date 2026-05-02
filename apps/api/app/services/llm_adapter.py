from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings


T = TypeVar("T", bound=BaseModel)


class LLMAdapterError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str: ...


@dataclass
class OpenAICompatibleProvider:
    settings: Settings

    def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        endpoint = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        try:
            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMAdapterError(f"LLM request failed: {exc}") from exc

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMAdapterError("LLM response did not match the expected chat completion shape.") from exc

        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            content = "\n".join(part for part in text_parts if part)

        if not isinstance(content, str) or not content.strip():
            raise LLMAdapterError("LLM returned an empty completion.")

        return content.strip()


class LLMGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = self._build_provider(settings)

    @staticmethod
    def _build_provider(settings: Settings) -> LLMProvider | None:
        provider_name = settings.llm_provider.lower().strip()
        if provider_name == "disabled" or not settings.llm_api_key:
            return None
        if provider_name == "openai_compatible":
            return OpenAICompatibleProvider(settings)
        raise LLMAdapterError(
            f"Unsupported llm_provider '{settings.llm_provider}'. Supported values: disabled, openai_compatible."
        )

    @property
    def is_enabled(self) -> bool:
        return self.provider is not None

    def _require_provider(self) -> LLMProvider:
        if self.provider is None:
            raise LLMAdapterError("LLM provider is not configured.")
        return self.provider

    @staticmethod
    def _extract_json_object(text: str) -> str:
        fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced_match:
            return fenced_match.group(1)

        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                _, end = decoder.raw_decode(text[index:])
                return text[index : index + end]
            except json.JSONDecodeError:
                continue

        raise LLMAdapterError("LLM response did not contain a valid JSON object.")

    def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.1,
    ) -> T:
        if not model:
            raise LLMAdapterError("No model is configured for this LLM task.")

        provider = self._require_provider()
        raw_text = provider.generate(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
        try:
            json_text = self._extract_json_object(raw_text)
            payload = json.loads(json_text)
            return response_model.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, LLMAdapterError) as exc:
            raise LLMAdapterError(f"Could not validate structured LLM output: {exc}") from exc


@lru_cache(maxsize=1)
def get_llm_gateway() -> LLMGateway:
    return LLMGateway(get_settings())
