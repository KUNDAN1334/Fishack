"""Google Gemini provider — second in the fallback chain.

Why second: Gemini Flash's free tier has solid daily quota and strong
quality, but Groq is faster. Gemini does NOT speak the OpenAI dialect, so
this file translates both directions:

  OpenAI-style                      Gemini-style
  ------------                      ------------
  messages[{role, content}]    ->   contents[{role, parts:[{text}]}]
  role "assistant"             ->   role "model"
  role "system"                ->   top-level systemInstruction
  choices[0].message.content   <-   candidates[0].content.parts[*].text
  usage.prompt_tokens          <-   usageMetadata.promptTokenCount

Streaming uses `:streamGenerateContent?alt=sse` (SSE frames like OpenAI, but
each frame is a full GenerateContentResponse fragment, no [DONE] sentinel).
"""

import json
import logging
import time
from typing import AsyncIterator

import httpx

from app.llm.base import (
    AuthError,
    ChatMessage,
    LLMProvider,
    LLMResponse,
    ProviderError,
    RateLimitError,
    StreamEvent,
    TokenUsage,
    TransientError,
    estimate_tokens,
)
from app.llm.providers.openai_compat import parse_retry_after

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, *, model: str, api_key: str, timeout: float = 60.0):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------- translation --

    def _payload(
        self, messages: list[ChatMessage], temperature: float, max_tokens: int
    ) -> dict:
        contents = []
        system_parts: list[str] = []
        for m in messages:
            if m.role == "system":
                # Gemini takes system prompts out-of-band, not as a message
                system_parts.append(m.content)
            else:
                contents.append(
                    {
                        "role": "model" if m.role == "assistant" else "user",
                        "parts": [{"text": m.content}],
                    }
                )
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        return payload

    def _headers(self) -> dict[str, str]:
        # Header auth instead of ?key= query param: keys in URLs end up in
        # access logs and tracebacks.
        return {"x-goog-api-key": self.api_key}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body = response.text[:500]
        if response.status_code in (401, 403):
            raise AuthError(self.name, f"auth failed ({response.status_code}): {body}")
        if response.status_code == 429:
            raise RateLimitError(
                self.name, f"rate limited: {body}", retry_after=parse_retry_after(response)
            )
        if response.status_code >= 500:
            raise TransientError(self.name, f"server error ({response.status_code}): {body}")
        raise ProviderError(self.name, f"http {response.status_code}: {body}")

    @staticmethod
    def _extract_text(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

    @staticmethod
    def _extract_usage(data: dict) -> TokenUsage | None:
        meta = data.get("usageMetadata")
        if not meta:
            return None
        return TokenUsage(
            input_tokens=meta.get("promptTokenCount", 0),
            output_tokens=meta.get("candidatesTokenCount", 0),
        )

    # ----------------------------------------------------------- complete --

    async def complete(
        self, messages: list[ChatMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        started = time.monotonic()
        url = f"{GEMINI_BASE_URL}/models/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json=self._payload(messages, temperature, max_tokens),
                )
        except httpx.HTTPError as exc:
            raise TransientError(self.name, f"network error: {exc}") from exc

        self._raise_for_status(response)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(self.name, f"unexpected response shape: {exc}") from exc

        text = self._extract_text(data)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            usage=self._extract_usage(data)
            or TokenUsage(output_tokens=estimate_tokens(text), estimated=True),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    # ------------------------------------------------------------- stream --

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float, max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        started = time.monotonic()
        url = f"{GEMINI_BASE_URL}/models/{self.model}:streamGenerateContent?alt=sse"
        parts: list[str] = []
        usage: TokenUsage | None = None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json=self._payload(messages, temperature, max_tokens),
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        self._raise_for_status(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = json.loads(line[len("data: "):])
                        # usageMetadata arrives on the final frame
                        usage = self._extract_usage(data) or usage
                        delta = self._extract_text(data)
                        if delta:
                            parts.append(delta)
                            yield StreamEvent(type="delta", text=delta)
        except httpx.HTTPError as exc:
            raise TransientError(self.name, f"network error mid-stream: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(self.name, f"bad SSE frame: {exc}") from exc

        full_text = "".join(parts)
        yield StreamEvent(
            type="done",
            response=LLMResponse(
                text=full_text,
                provider=self.name,
                model=self.model,
                usage=usage
                or TokenUsage(output_tokens=estimate_tokens(full_text), estimated=True),
                latency_ms=int((time.monotonic() - started) * 1000),
            ),
        )
