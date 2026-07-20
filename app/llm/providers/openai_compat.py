"""Base implementation for every provider that speaks the OpenAI chat
completions dialect (Groq, OpenRouter, Ollama — the industry's de-facto
wire format).

Built on raw httpx, no vendor SDKs (ADR-006): you see the exact HTTP
request, the exact SSE frames, and the exact error mapping — nothing hidden.
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

logger = logging.getLogger(__name__)


def parse_retry_after(response: httpx.Response) -> float | None:
    """Extract 'wait this many seconds' from a 429 response, if present.

    Providers vary: standard Retry-After (seconds), or vendor headers like
    x-ratelimit-reset-* . We read Retry-After and fall back to None (our own
    exponential backoff takes over).
    """
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None  # HTTP-date format — rare on APIs; let backoff handle it


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------ request --

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", **self.extra_headers}

    def _payload(
        self, messages: list[ChatMessage], temperature: float, max_tokens: int, stream: bool
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if stream:
            # Ask for a final usage frame in the stream (Groq/OpenRouter
            # support this; providers that don't simply ignore it and we
            # fall back to estimation).
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map HTTP status -> our error taxonomy (see base.py for why)."""
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

    # ----------------------------------------------------------- complete --

    async def complete(
        self, messages: list[ChatMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(messages, temperature, max_tokens, stream=False),
                )
        except httpx.HTTPError as exc:
            # Timeouts / connection resets are transient: retry, then fail over
            raise TransientError(self.name, f"network error: {exc}") from exc

        self._raise_for_status(response)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, f"unexpected response shape: {exc}") from exc

        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            usage=self._parse_usage(data.get("usage"), text),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def _parse_usage(self, usage: dict | None, text: str) -> TokenUsage:
        if usage:
            return TokenUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
        return TokenUsage(output_tokens=estimate_tokens(text), estimated=True)

    # ------------------------------------------------------------- stream --

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float, max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        """SSE streaming. The wire format is lines of `data: {json}` with a
        terminal `data: [DONE]` — what every SDK parses for you; here it's
        ~30 visible lines."""
        started = time.monotonic()
        parts: list[str] = []
        usage: TokenUsage | None = None
        model = self.model
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(messages, temperature, max_tokens, stream=True),
                ) as response:
                    if response.status_code >= 400:
                        # Body must be read before raising — stream responses
                        # don't have .text until read
                        await response.aread()
                        self._raise_for_status(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue  # comments/keepalives/blank lines
                        raw = line[len("data: "):]
                        if raw.strip() == "[DONE]":
                            break
                        event = json.loads(raw)
                        model = event.get("model", model)
                        if event.get("usage"):
                            usage = self._parse_usage(event["usage"], "")
                        choices = event.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta", {}).get("content")
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
                model=model,
                usage=usage or TokenUsage(output_tokens=estimate_tokens(full_text), estimated=True),
                latency_ms=int((time.monotonic() - started) * 1000),
            ),
        )
