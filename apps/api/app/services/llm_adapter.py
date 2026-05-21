from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, AsyncIterable, AsyncIterator, Protocol, TypeVar, Union

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings


T = TypeVar("T", bound=BaseModel)


class LLMAdapterError(RuntimeError):
    pass


# ── Streaming chat events (Stage 7 / ticket #2) ───────────────────────────────
#
# `chat_completion_with_tools` yields a sequence of these. The endpoint handler
# in ticket #5 will reshape them into SSE frames for the browser; the chat
# tool-call dispatch loop only cares about the order:
#   1. zero or more ChatToken (streaming assistant prose)
#   2. zero or more ChatToolCall (each fully assembled from streamed deltas)
#   3. exactly one ChatDone (finish_reason; optional usage stats)


@dataclass(frozen=True)
class ChatToken:
    """A chunk of streaming assistant text. May be a single character or many."""
    text: str


@dataclass(frozen=True)
class ChatToolCall:
    """A fully-assembled tool call. OpenAI streams tool-call function name and
    JSON arguments in fragments; this event is yielded only after the full call
    has been reconstructed and the arguments parsed."""
    call_id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ChatDone:
    """End-of-stream marker. `finish_reason` is OpenAI's ("stop", "tool_calls",
    "length", "content_filter"). `usage` is the {prompt,completion,total}_tokens
    dict if the provider returned it; otherwise None."""
    finish_reason: str
    usage: dict | None = None


ChatEvent = Union[ChatToken, ChatToolCall, ChatDone]


class LLMProvider(Protocol):
    async def generate(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str: ...


async def _events_from_chunks(
    chunks: AsyncIterable[dict],
) -> AsyncIterator[ChatEvent]:
    """Translate OpenAI streaming chunks into normalized ChatEvent's.

    Pure logic — no HTTP, no settings, no provider. Takes any async iterable of
    parsed-JSON OpenAI chunks (e.g. from `provider.stream_chat`, or from a list
    in tests) and yields events in this order:

      ChatToken*  (text deltas as they arrive)
      ChatToolCall*  (each emitted when the assistant signals finish_reason)
      ChatDone  (once)

    Tool-call fragments arrive across multiple chunks (`function.name` may be
    in one chunk, `function.arguments` split across several JSON pieces). We
    buffer them by their `index` and emit a single ChatToolCall per index once
    finish_reason='tool_calls' shows up.
    """
    pending: dict[int, dict[str, str]] = {}

    async for chunk in chunks:
        choices = chunk.get("choices") or []
        if not choices:
            continue
        choice = choices[0]
        delta = choice.get("delta") or {}

        content = delta.get("content")
        if content:
            yield ChatToken(text=content)

        for tc_delta in delta.get("tool_calls") or []:
            idx = tc_delta.get("index", 0)
            slot = pending.setdefault(idx, {"id": "", "name": "", "args": ""})
            if tc_delta.get("id"):
                slot["id"] = tc_delta["id"]
            fn = tc_delta.get("function") or {}
            if fn.get("name"):
                slot["name"] += fn["name"]
            if fn.get("arguments") is not None:
                slot["args"] += fn["arguments"]

        finish_reason = choice.get("finish_reason")
        if finish_reason is None:
            continue

        for slot in pending.values():
            if not slot["name"]:
                continue
            try:
                args = json.loads(slot["args"]) if slot["args"] else {}
            except json.JSONDecodeError:
                args = {"_unparseable_json": slot["args"]}
            yield ChatToolCall(
                call_id=slot["id"] or "",
                name=slot["name"],
                arguments=args,
            )

        yield ChatDone(finish_reason=finish_reason, usage=chunk.get("usage"))
        return


@dataclass
class OpenAICompatibleProvider:
    settings: Settings

    async def generate(
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
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(endpoint, headers=headers, json=body)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMAdapterError(f"LLM request failed: {exc}") from exc

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMAdapterError(
                "LLM response did not match the expected chat completion shape."
            ) from exc

        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )

        if not isinstance(content, str) or not content.strip():
            raise LLMAdapterError("LLM returned an empty completion.")

        return content.strip()

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
    ) -> AsyncIterator[dict]:
        """Stream raw parsed OpenAI chunks. Consumer normalizes via
        `_events_from_chunks`."""
        endpoint = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                async with client.stream("POST", endpoint, headers=headers, json=body) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPError as exc:
            raise LLMAdapterError(f"LLM streaming request failed: {exc}") from exc


class LLMGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = self._build_provider(settings)

    @staticmethod
    def _build_provider(settings: Settings) -> LLMProvider | None:
        name = settings.llm_provider.lower().strip()
        if name == "disabled" or not settings.llm_api_key:
            return None
        if name == "openai_compatible":
            return OpenAICompatibleProvider(settings)
        raise LLMAdapterError(
            f"Unsupported llm_provider '{settings.llm_provider}'. "
            "Supported values: disabled, openai_compatible."
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
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            return fenced.group(1)

        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                _, end = decoder.raw_decode(text[i:])
                return text[i : i + end]
            except json.JSONDecodeError:
                continue

        raise LLMAdapterError("LLM response did not contain a valid JSON object.")

    async def generate_structured(
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
        raw_text = await provider.generate(
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
            raise LLMAdapterError(
                f"Could not validate structured LLM output: {exc}"
            ) from exc

    async def chat_completion_with_tools(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = True,
    ) -> AsyncIterator[ChatEvent]:
        """Tool-calling chat with streaming (Stage 7 / ticket #2).

        Yields ChatToken's as the assistant streams text, then one ChatToolCall
        per fully-assembled tool call when the assistant decides to call tools,
        then exactly one ChatDone.

        Raises LLMAdapterError on: provider not configured, model not set,
        provider lacks streaming support, or any HTTP error mid-stream. The
        error propagates from the first `__anext__` if the provider check
        fails, or from later iterations if the HTTP stream breaks.

        Non-streaming mode (`stream=False`) is intentionally unsupported —
        every chat consumer (chat endpoint, tool dispatch loop) needs the
        incremental event stream. Pass stream=True or expect an error.
        """
        if not stream:
            raise LLMAdapterError(
                "chat_completion_with_tools requires stream=True; "
                "non-streaming completion is unsupported."
            )

        provider = self._require_provider()
        if not hasattr(provider, "stream_chat"):
            raise LLMAdapterError(
                f"Provider {type(provider).__name__} does not support "
                f"streaming tool-calling chat."
            )

        effective_model = model or self.settings.llm_model
        if not effective_model:
            raise LLMAdapterError("No model configured for chat.")

        chunk_iter = provider.stream_chat(
            model=effective_model,
            messages=messages,
            tools=tools or [],
            temperature=temperature,
        )
        async for event in _events_from_chunks(chunk_iter):
            yield event

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> dict:
        """Call the configured LLM and return parsed JSON as a plain dict."""
        if not self.settings.llm_model:
            raise LLMAdapterError("No model is configured for this LLM task.")

        provider = self._require_provider()
        raw_text = await provider.generate(
            model=self.settings.llm_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
        try:
            json_text = self._extract_json_object(raw_text)
            return json.loads(json_text)
        except (json.JSONDecodeError, LLMAdapterError) as exc:
            raise LLMAdapterError(
                f"LLM response could not be parsed as JSON: {exc}"
            ) from exc


@lru_cache(maxsize=1)
def get_llm_gateway() -> LLMGateway:
    return LLMGateway(get_settings())
